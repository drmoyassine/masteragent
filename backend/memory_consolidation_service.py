"""memory_consolidation_service.py — Single orchestration boundary for knowledge hygiene.

Every caller — manual UI, scheduled job, admin trigger, automatic policy, and
creation-time hook — goes through :func:`preview` and :func:`apply` here. There
is no second merge implementation.

Embedding similarity discovers and groups candidates; the semantic merge
decision comes from the category-aware LLM proposal plus deterministic safety
checks and review policy. Preview never mutates; apply is transactional and
reversible.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from memory_consolidation_prompts import (
    CONSOLIDATION_PROMPT_VERSION,
    ConsolidationProposal,
    build_system_prompt,
    build_user_prompt,
    proposal_to_dict,
    repair_prompt,
    validate_proposal,
)
from memory_consolidation_repository import (
    ConsolidationError,
    aggregate_canonical_payload,
    apply_consolidation as repo_apply,
    create_hygiene_run,
    expire_preview,
    insert_hygiene_cluster,
    insert_preview,
    link_cluster_proposal,
    load_active_records_for_categories,
    load_event,
    load_event_sources,
    load_hygiene_clusters,
    load_hygiene_run,
    load_knowledge_record,
    load_knowledge_records,
    load_preview,
    load_preview_sources,
    reverse_event as repo_reverse,
    update_hygiene_run,
)
from memory_clustering import (
    accepted_proposal_groups,
    discover_candidate_groups,
    manual_group_metrics,
)
from memory_embedding import (
    CONSOLIDATABLE_KNOWLEDGE_CATEGORIES,
    current_embedding_model,
    embed_knowledge_fields,
    is_embedding_compatible,
)

logger = logging.getLogger(__name__)


# ─── settings helpers ────────────────────────────────────────────────────────

def _settings() -> Dict[str, Any]:
    from services.config_helpers import get_memory_settings
    return get_memory_settings() or {}


def _ttl_seconds(settings: Dict[str, Any]) -> int:
    try:
        return max(5, int(settings.get("knowledge_hygiene_preview_ttl_minutes", 60))) * 60
    except (TypeError, ValueError):
        return 3600


def _llm_config() -> Dict[str, Any]:
    from services.config_helpers import get_llm_config
    return get_llm_config("knowledge_consolidation") or {}


# ─── preview ─────────────────────────────────────────────────────────────────

async def preview(
    *,
    knowledge_ids: Sequence[str],
    origin: str = "manual",
    options: Optional[Dict[str, Any]] = None,
    actor_type: str = "admin",
    actor_id: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a non-mutating consolidation preview for 2+ same-category records.

    Validates the source set, computes grouping metrics, calls the
    category-aware LLM, and persists an immutable preview + source snapshot.
    Never mutates knowledge.
    """
    settings = settings if settings is not None else _settings()
    options = options or {}
    ids = _distinct_ids(knowledge_ids)
    if len(ids) < 2:
        raise ConsolidationError("invalid_input", "At least two distinct knowledge ids are required", 400)

    rows = load_knowledge_records(ids)
    if len(rows) != len(ids):
        missing = sorted(set(ids) - {r["id"] for r in rows})
        raise ConsolidationError("missing_source", f"Source records not found: {missing}", 404)

    category = _validate_source_set(rows, origin=origin)

    # Grouping metrics (information only for manual origin; gating for automated).
    metrics = _flatten_manual_metrics(manual_group_metrics(
        _metric_projection(rows),
        weak_link_threshold=float(settings.get("knowledge_hygiene_weak_link_threshold", 0.65)),
    ))
    metrics["embedding_compatible"] = _embedding_compat_summary(rows, settings)
    metrics["category"] = category

    if origin in ("scheduled", "admin", "creation_time"):
        _enforce_automated_controls(metrics, settings, rows)

    source_snapshot = {
        r["id"]: {
            "version": r.get("version"),
            "updated_at": _normalize_ts(r.get("updated_at")),
            "status": r.get("status"),
            "record": _snapshot_for_llm(r),
        }
        for r in rows
    }

    settings_snapshot = _hygiene_settings_snapshot(settings)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_ttl_seconds(settings))

    proposal, raw_response, validation_errors, model_name = await _generate_proposal(rows, metrics, category)

    llm_cfg = _llm_config()
    preview_id = insert_preview(
        origin=origin, actor_type=actor_type, actor_id=actor_id, category=category,
        source_ids=ids, source_snapshot=source_snapshot, metrics=metrics,
        options=options, settings_snapshot=settings_snapshot,
        model_provider=llm_cfg.get("provider"), model_name=model_name or llm_cfg.get("model_name"),
        prompt_version=CONSOLIDATION_PROMPT_VERSION, raw_response=raw_response,
        proposal=proposal, validation_errors=validation_errors, expires_at=expires_at,
    )
    return _preview_view(preview_id)


async def regenerate(*, preview_id: str, actor_type: str = "admin", actor_id: Optional[str] = None) -> Dict[str, Any]:
    """Expire the old preview and create a fresh one from current source versions."""
    existing = load_preview(preview_id)
    if not existing:
        raise ConsolidationError("missing_preview", "Preview not found", 404)
    if existing.get("state") == "applied":
        raise ConsolidationError("already_applied", "An applied preview cannot be regenerated", 409)
    expire_preview(preview_id)
    return await preview(
        knowledge_ids=existing.get("source_ids") or [],
        origin=existing.get("origin") or "manual",
        options=existing.get("options") or {},
        actor_type=actor_type, actor_id=actor_id,
    )


def _distinct_ids(knowledge_ids: Sequence[str]) -> List[str]:
    seen: List[str] = []
    for kid in knowledge_ids:
        if kid and kid not in seen:
            seen.append(kid)
    return seen


def _validate_source_set(rows: Sequence[Dict[str, Any]], *, origin: str) -> str:
    categories = {r.get("category") for r in rows}
    if len(categories) > 1:
        raise ConsolidationError(
            "mixed_categories",
            f"Cross-category consolidation is unsupported. Selected categories: {sorted(categories)}",
            400,
        )
    category = next(iter(categories)) if categories else None
    if category not in CONSOLIDATABLE_KNOWLEDGE_CATEGORIES:
        raise ConsolidationError(
            "invalid_category",
            f"Category {category!r} is not consolidatable. Allowlist: {sorted(CONSOLIDATABLE_KNOWLEDGE_CATEGORIES)}",
            400,
        )
    statuses = {r.get("status") for r in rows}
    bad = sorted(s for s in statuses if s not in ("active", "confirmed"))
    if bad:
        raise ConsolidationError("invalid_status", f"Sources have non-active statuses: {bad}", 400)
    for r in rows:
        if r.get("merged_into"):
            raise ConsolidationError("already_merged", f"Source {r['id']} was already merged", 409)
        if r.get("consolidation_protected"):
            raise ConsolidationError("protected", f"Source {r['id']} is protected from consolidation", 409)
    return category


def _enforce_automated_controls(metrics: Dict[str, Any], settings: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> None:
    """For automated origins, require threshold/cohesion/size/embedding gates.

    Manual origin never rejects for low similarity; it only reports metrics.
    """
    min_cohesion = float(settings.get("knowledge_hygiene_min_cluster_cohesion", 0.72))
    min_size = int(settings.get("knowledge_hygiene_min_cluster_size", 2))
    raw_max_size = settings.get("knowledge_hygiene_max_cluster_size", 5)
    max_size = None if raw_max_size is None else int(raw_max_size)
    size = metrics.get("size", 0)
    if size < min_size:
        raise ConsolidationError("below_min_size", f"Cluster size {size} below minimum {min_size}", 400)
    if max_size is not None and size > max_size:
        raise ConsolidationError("above_max_size", f"Cluster size {size} above maximum {max_size}", 400)
    if metrics.get("cohesion", 0.0) < min_cohesion:
        raise ConsolidationError("low_cohesion", "Cluster cohesion below threshold", 400)
    if metrics.get("weak_links"):
        raise ConsolidationError("weak_link", "Cluster contains a member below the centroid weak-link threshold", 400)
    cv = int(settings.get("knowledge_hygiene_embedding_version", 2))
    if not all(is_embedding_compatible(r, cv, current_embedding_model()) for r in rows):
        raise ConsolidationError("embedding_incompatible", "Sources have incompatible embedding versions", 400)


def _metric_projection(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        out.append({"id": r["id"], "category": r.get("category"), "embedding": r.get("embedding")})
    return out


def _flatten_manual_metrics(group: Dict[str, Any]) -> Dict[str, Any]:
    """Expose the metric bundle consistently to API, gates, prompts, and UI."""
    return {
        **(group.get("metrics") or {}),
        "member_ids": group.get("member_ids") or [],
        "embedding_member_ids": group.get("embedding_member_ids") or [],
        "size": group.get("size", 0),
        "status": group.get("status"),
        "split_reason": group.get("split_reason"),
    }


def _embedding_compat_summary(rows: Sequence[Dict[str, Any]], settings: Dict[str, Any]) -> Dict[str, Any]:
    cv = int(settings.get("knowledge_hygiene_embedding_version", 2))
    incompatible = [r["id"] for r in rows if not is_embedding_compatible(r, cv, current_embedding_model())]
    return {"configured_version": cv, "incompatible_ids": incompatible, "all_compatible": not incompatible}


def selection_metrics(knowledge_ids: Sequence[str]) -> Dict[str, Any]:
    """Non-mutating, no-LLM metrics for the manual Sources review step."""
    ids = _distinct_ids(knowledge_ids)
    if len(ids) < 2:
        raise ConsolidationError("invalid_input", "At least two distinct knowledge ids are required", 400)
    rows = load_knowledge_records(ids)
    if len(rows) != len(ids):
        missing = sorted(set(ids) - {r["id"] for r in rows})
        raise ConsolidationError("missing_source", f"Source records not found: {missing}", 404)
    category = _validate_source_set(rows, origin="manual")
    settings = _settings()
    metrics = _flatten_manual_metrics(manual_group_metrics(
        _metric_projection(rows),
        weak_link_threshold=float(settings.get("knowledge_hygiene_weak_link_threshold", 0.65)),
    ))
    metrics["embedding_compatible"] = _embedding_compat_summary(rows, settings)
    metrics["category"] = category
    return metrics


def _snapshot_for_llm(row: Dict[str, Any]) -> Dict[str, Any]:
    """Complete source record for the LLM (no embedding ever)."""
    snap = {k: v for k, v in row.items() if k != "embedding"}
    return snap


def _normalize_ts(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _hygiene_settings_snapshot(settings: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "knowledge_hygiene_enabled", "knowledge_hygiene_enabled_categories",
        "knowledge_hygiene_similarity_threshold", "knowledge_hygiene_min_cluster_size",
        "knowledge_hygiene_max_cluster_size", "knowledge_hygiene_min_cluster_cohesion",
        "knowledge_hygiene_weak_link_threshold", "knowledge_hygiene_embedding_version",
        "knowledge_hygiene_mode", "knowledge_hygiene_preview_ttl_minutes",
        "knowledge_hygiene_min_auto_confidence", "knowledge_hygiene_contradiction_policy",
        "knowledge_hygiene_default_canonical_strategy",
    )
    return {k: settings.get(k) for k in keys}


async def _generate_proposal(
    rows: Sequence[Dict[str, Any]], metrics: Dict[str, Any], category: str
) -> tuple:
    """Call the LLM, validate, one repair retry. Returns (proposal_dict|None, raw, errors, model)."""
    from memory_services import call_llm
    from services.llm import parse_llm_json

    llm_cfg = _llm_config()
    if not llm_cfg:
        return None, None, ["knowledge_consolidation LLM config is not configured"], None
    model_name = llm_cfg.get("model_name")
    system_prompt = build_system_prompt(category)
    sources_for_llm = [_snapshot_for_llm(r) for r in rows]
    user_prompt = build_user_prompt(sources_for_llm, metrics, category)

    last_errors: List[str] = []
    for attempt in range(2):
        try:
            raw_text = await call_llm(
                user_prompt,
                system_prompt=system_prompt + ("\n\n" + repair_prompt(last_errors, category) if attempt else ""),
                max_tokens=int(_settings().get("knowledge_max_tokens") or 1600),
                task_type="knowledge_consolidation",
            )
        except Exception as exc:
            logger.warning("Consolidation LLM call failed: %s", exc)
            return None, None, [f"LLM call failed: {exc}"], model_name
        try:
            parsed = parse_llm_json(raw_text, context="knowledge_consolidation")
        except ValueError as exc:
            last_errors = [f"LLM returned unparseable JSON: {exc}"]
            if attempt == 0:
                continue
            return None, raw_text, last_errors, model_name
        proposal_obj, errors = validate_proposal(parsed, category)
        if not errors and proposal_obj is not None:
            return proposal_to_dict(proposal_obj), parsed, [], model_name
        if attempt == 0 and errors:
            last_errors = list(errors)
            continue
        return (proposal_to_dict(proposal_obj) if proposal_obj else parsed), parsed, errors, model_name
    return None, None, ["LLM proposal validation failed after retry"], model_name


# ─── apply ───────────────────────────────────────────────────────────────────

async def apply(
    *,
    preview_id: str,
    approved_canonical: Dict[str, Any],
    canonical_strategy: str = "update_existing",
    canonical_target_id: Optional[str] = None,
    actor_type: str = "admin",
    actor_id: Optional[str] = None,
    origin: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply an approved preview transactionally. Returns the event view."""
    preview_row = load_preview(preview_id)
    if not preview_row:
        raise ConsolidationError("missing_preview", "Preview not found", 404)
    if preview_row.get("state") == "expired":
        raise ConsolidationError("expired", "Preview has expired — regenerate it", 410)
    if preview_row.get("state") == "applied":
        raise ConsolidationError("already_applied", "Preview was already applied", 409)
    if preview_row.get("state") == "failed" or preview_row.get("proposal") is None:
        raise ConsolidationError("invalid_preview", "Preview has no valid proposal to apply", 422)
    expires_at = preview_row.get("expires_at")
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        raise ConsolidationError("expired", "Preview has expired — regenerate it", 410)

    category = preview_row["category"]
    _validate_approved_canonical(approved_canonical, category)

    # Generate the canonical embedding BEFORE retiring sources (§9.3 step 5).
    embedding = None
    model_name = None
    try:
        embedding, model_name = await embed_knowledge_fields(
            name=approved_canonical.get("name", ""),
            category=category,
            content=approved_canonical.get("content", ""),
            summary=approved_canonical.get("summary", ""),
            signals=approved_canonical.get("signals") or [],
            tags=approved_canonical.get("tags") or [],
            metadata=approved_canonical.get("metadata") or {},
        )
    except Exception as exc:
        raise ConsolidationError("embedding_failed", f"Canonical embedding failed: {exc}", 422)
    if not embedding:
        raise ConsolidationError("embedding_failed",
                                 "Canonical embedding could not be generated; run the embedding backfill and retry", 422)

    event_id = repo_apply(
        preview=preview_row, approved_canonical=approved_canonical,
        canonical_strategy=canonical_strategy, canonical_target_id=canonical_target_id,
        embedding=embedding, embedding_model=model_name,
        actor_type=actor_type, actor_id=actor_id,
        origin=origin or preview_row.get("origin") or "manual",
    )
    return _event_view(event_id)


def _validate_approved_canonical(approved: Dict[str, Any], category: str) -> None:
    if not isinstance(approved, dict):
        raise ConsolidationError("invalid_canonical", "approved_canonical must be an object", 422)
    name = (approved.get("name") or "").strip()
    content = (approved.get("content") or "").strip()
    if not name or not content:
        raise ConsolidationError("invalid_canonical", "canonical.name and canonical.content are required", 422)
    # Skills/playbooks: validate the canonical body parses/render round-trips.
    if category in ("skill", "playbook"):
        try:
            from memory_skill_md import is_skill_md, parse_skill_md, render_skill_md
            candidate = content if is_skill_md(content) else render_skill_md(
                name=name, category=category,
                description=(approved.get("summary") or content), body=content,
                metadata=approved.get("metadata") or {},
                signals=approved.get("signals") or [], tags=approved.get("tags") or [],
            )
            parse_skill_md(candidate)
        except ConsolidationError:
            raise
        except Exception as exc:
            raise ConsolidationError("invalid_canonical", f"skill/playbook validation failed: {exc}", 422)


# ─── read views ──────────────────────────────────────────────────────────────

def _preview_view(preview_id: str) -> Dict[str, Any]:
    p = load_preview(preview_id)
    if not p:
        raise ConsolidationError("missing_preview", "Preview not found", 404)
    sources = load_preview_sources(preview_id)
    return {
        "preview": p,
        "sources": sources,
        "metrics": p.get("metrics") or {},
        "proposal": p.get("proposal"),
    }


def _event_view(event_id: str) -> Dict[str, Any]:
    e = load_event(event_id)
    if not e:
        raise ConsolidationError("missing_event", "Event not found", 404)
    return {"event": e, "sources": load_event_sources(event_id)}


def get_preview(preview_id: str) -> Dict[str, Any]:
    return _preview_view(preview_id)


def get_event(event_id: str) -> Dict[str, Any]:
    return _event_view(event_id)


def get_lineage(knowledge_id: str) -> Dict[str, Any]:
    """Lineage for the lineage panel: successor (merged_into), predecessors
    (merged_from), and the consolidation event that absorbed/created this row."""
    row = load_knowledge_record(knowledge_id)
    if not row:
        raise ConsolidationError("missing_source", "Knowledge record not found", 404)
    from memory_consolidation_repository import load_latest_event_for_canonical
    event_id = row.get("consolidation_event_id")
    event = load_event(event_id) if event_id else None
    successor_event = load_latest_event_for_canonical(knowledge_id) if row.get("status") != "retired" else None
    return {
        "knowledge_id": knowledge_id,
        "status": row.get("status"),
        "merged_into": row.get("merged_into"),
        "merged_from": row.get("merged_from") or [],
        "consolidation_event_id": event_id,
        "event": event,
        "created_as_canonical_event": successor_event,
    }


def reverse(preview_event_id: str, *, actor_type: str = "admin", actor_id: Optional[str] = None) -> Dict[str, Any]:
    reversed_id = repo_reverse(preview_event_id, actor_type=actor_type, actor_id=actor_id)
    return {"reversed": True, "reversal_event_id": reversed_id, "original_event_id": preview_event_id}


# ─── automated discovery (scheduled / admin / creation-time) ─────────────────

async def discover_and_propose(
    *,
    run_id: Optional[str] = None,
    origin: str = "scheduled",
    mode: Optional[str] = None,
    category_filter: Optional[str] = None,
    actor_id: Optional[str] = None,
    auto_apply: bool = False,
    max_records: int = 5000,
    max_clusters: int = 100,
    progress_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Discover candidate clusters, generate proposals, optionally auto-apply.

    Returns a run summary. ``auto_apply`` is honored only when the configured
    mode/policy permits (the caller passes ``auto_apply`` based on mode; this
    function still gates each apply on policy confidence/contradiction checks).
    """
    settings = _settings()
    if not settings.get("knowledge_hygiene_enabled", True):
        return {"status": "disabled", "reason": "knowledge_hygiene_enabled is false"}

    mode = mode or settings.get("knowledge_hygiene_mode", "manual_only")
    categories = settings.get("knowledge_hygiene_enabled_categories") or list(CONSOLIDATABLE_KNOWLEDGE_CATEGORIES)
    if category_filter:
        categories = [category_filter] if category_filter in categories else []
    threshold = float(settings.get("knowledge_hygiene_similarity_threshold", 0.82))
    raw_max_size = settings.get("knowledge_hygiene_max_cluster_size", 5)
    max_size = None if raw_max_size is None else int(raw_max_size)
    min_cohesion = float(settings.get("knowledge_hygiene_min_cluster_cohesion", 0.72))
    weak_link = float(settings.get("knowledge_hygiene_weak_link_threshold", 0.65))
    min_size = int(settings.get("knowledge_hygiene_min_cluster_size", 2))

    if not run_id:
        run_id = create_hygiene_run(
            origin=origin, mode=mode, settings_snapshot=_hygiene_settings_snapshot(settings),
            embedding_version=int(settings.get("knowledge_hygiene_embedding_version", 2)),
            categories=categories, created_by=actor_id,
        )

    max_records = max(1, int(max_records))
    max_clusters = max(1, int(max_clusters))
    all_records = load_active_records_for_categories(categories, limit=max_records)
    configured_version = int(settings.get("knowledge_hygiene_embedding_version", 2))
    records = [r for r in all_records if is_embedding_compatible(r, configured_version, current_embedding_model())]
    incompatible_skipped = len(all_records) - len(records)
    groups = discover_candidate_groups(
        records, threshold=threshold, min_size=min_size, max_size=max_size,
        min_cohesion=min_cohesion, weak_link_threshold=weak_link,
    )
    proposal_groups = [
        g for g in groups
        if g.get("status") in ("accepted", "manual_review") and g.get("size", 0) >= min_size
    ]
    proposal_keys = {tuple(g.get("member_ids") or []) for g in proposal_groups}
    clusters_found = sum(1 for g in groups if g.get("size", 0) >= min_size)
    proposals_created = 0
    applied_count = 0
    failed_count = 0

    processed_groups = 0
    stopped_command = None
    for group in groups[:max_clusters]:
        from services.job_controls import get_command
        stopped_command = get_command("knowledge_hygiene_run")
        if stopped_command in {"pause", "cancel"}:
            logger.info("Hygiene analysis stopped at checkpoint (%s)", stopped_command)
            break
        cluster_id = insert_hygiene_cluster(
            run_id=run_id, category=group["category"], group=group,
            centroid_vec=group.get("centroid"),
        )
        processed_groups += 1
        if progress_run_id:
            from memory_db_writes import update_pipeline_run
            update_pipeline_run(progress_run_id, progress_total=min(len(groups), max_clusters),
                                progress_completed=processed_groups,
                                progress_failed=failed_count,
                                detail={"clusters_found": clusters_found, "proposals_created": proposals_created})
        if mode in ("analysis_only",) or tuple(group.get("member_ids") or []) not in proposal_keys:
            continue
        try:
            result = await preview(
                knowledge_ids=group["member_ids"], origin=origin,
                options={"canonical_strategy": settings.get("knowledge_hygiene_default_canonical_strategy", "update_existing")},
                actor_type=origin, actor_id=actor_id, settings=settings,
            )
            preview_id = result["preview"]["id"]
            proposals_created += 1
            link_cluster_proposal(cluster_id, preview_id)
            if (
                auto_apply
                and group.get("status") == "accepted"
                and _policy_allows_apply(result["proposal"], group["category"], settings)
            ):
                await apply(
                    preview_id=preview_id,
                    approved_canonical=_canonical_from_proposal(result["proposal"]),
                    canonical_strategy=settings.get("knowledge_hygiene_default_canonical_strategy", "update_existing"),
                    canonical_target_id=group["member_ids"][0],
                    actor_type=origin, actor_id=actor_id, origin=origin,
                )
                applied_count += 1
        except Exception as exc:
            failed_count += 1
            logger.warning("Hygiene proposal/apply failed for cluster %s: %s", group.get("member_ids"), exc)
    update_hygiene_run(
        run_id, status="cancelled" if stopped_command == "cancel" else ("paused" if stopped_command == "pause" else "completed"), records_scanned=len(all_records), clusters_found=min(clusters_found, max_clusters),
        proposals_created=proposals_created, applied_count=applied_count, failed_count=failed_count,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    return {
        "run_id": run_id, "mode": mode, "records_scanned": len(all_records),
        "eligible_records": len(records), "incompatible_skipped": incompatible_skipped,
        "clusters_found": clusters_found, "proposals_created": proposals_created,
        "applied_count": applied_count, "failed_count": failed_count,
    }


def _policy_allows_apply(proposal: Optional[Dict[str, Any]], category: str, settings: Dict[str, Any]) -> bool:
    """Apply the configured global/category automation policy deterministically."""
    if not isinstance(proposal, dict):
        return False
    global_mode = settings.get("knowledge_hygiene_mode", "manual_only")
    category_mode = (settings.get("knowledge_hygiene_category_policies") or {}).get(category)
    effective_mode = category_mode or global_mode
    if effective_mode not in ("auto_conservative", "auto_synthesis"):
        return False
    rec = proposal.get("recommendation")
    if effective_mode == "auto_conservative" and rec != "merge":
        return False
    if effective_mode == "auto_synthesis" and rec not in ("merge", "merge_with_warnings"):
        return False
    contradictions = proposal.get("contradictions") or []
    contradiction_policy = settings.get("knowledge_hygiene_contradiction_policy") or "manual_review"
    if contradictions and contradiction_policy != "warn_and_merge":
        return False
    if contradictions and effective_mode == "auto_conservative":
        return False
    min_conf = float(settings.get("knowledge_hygiene_min_auto_confidence", 0.90))
    try:
        conf = float(proposal.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < min_conf:
        return False
    return True


def _canonical_from_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    canonical = proposal.get("canonical") or {}
    return {
        "name": canonical.get("name", ""),
        "summary": canonical.get("summary", ""),
        "content": canonical.get("content", ""),
        "signals": canonical.get("signals") or [],
        "tags": canonical.get("tags") or [],
        "metadata": canonical.get("metadata") or {},
    }


async def creation_time_propose(
    *,
    knowledge_id: str,
    settings: Optional[Dict[str, Any]] = None,
    auto_apply: bool = False,
) -> Dict[str, Any]:
    """Creation-time consolidation: find same-category candidates for a new
    record and generate a preview (never blocks generation).

    Uses nearest-neighbor similarity to gather candidates, then routes through
    the shared :func:`preview`. In automatic modes, applies only when the
    common policy permits. The new record is never merged into a draft, retired,
    protected, or otherwise ineligible target.
    """
    settings = settings if settings is not None else _settings()
    row = load_knowledge_record(knowledge_id)
    if not row or not row.get("embedding"):
        return {"status": "no_embedding", "knowledge_id": knowledge_id}
    if row.get("status") not in ("active", "confirmed") or row.get("merged_into"):
        return {"status": "ineligible", "knowledge_id": knowledge_id}
    configured_version = int(settings.get("knowledge_hygiene_embedding_version", 2))
    if not is_embedding_compatible(row, configured_version, current_embedding_model()):
        return {"status": "embedding_incompatible", "knowledge_id": knowledge_id}

    category = row.get("category")
    threshold = float(settings.get("knowledge_hygiene_similarity_threshold", 0.82))
    candidate_ids = _nearest_neighbors(
        knowledge_id, row["embedding"], category, threshold,
        configured_version=configured_version, limit=4,
    )
    ids = [knowledge_id] + [c for c in candidate_ids if c != knowledge_id]
    if len(ids) < 2:
        return {"status": "no_candidates", "knowledge_id": knowledge_id}

    result = await preview(
        knowledge_ids=ids, origin="creation_time", actor_type="system", actor_id=None,
        settings=settings,
    )
    if auto_apply and _policy_allows_apply(result.get("proposal"), category, settings):
        canonical = _canonical_from_proposal(result.get("proposal") or {})
        try:
            await apply(
                preview_id=result["preview"]["id"], approved_canonical=canonical,
                canonical_strategy=settings.get("knowledge_hygiene_default_canonical_strategy", "update_existing"),
                canonical_target_id=knowledge_id, actor_type="system", origin="creation_time",
            )
            return {"status": "applied", "knowledge_id": knowledge_id, "preview_id": result["preview"]["id"]}
        except Exception as exc:
            logger.warning("Creation-time auto-apply failed for %s: %s", knowledge_id, exc)
    return {"status": "proposed", "knowledge_id": knowledge_id, "preview_id": result["preview"]["id"]}


def _nearest_neighbors(
    knowledge_id: str,
    embedding,
    category: str,
    threshold: float,
    *,
    configured_version: int,
    limit: int = 4,
) -> List[str]:
    """Same-category active nearest neighbors above the candidate threshold."""
    from core.storage import get_memory_db_context
    try:
        with get_memory_db_context() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id FROM knowledge
                WHERE id <> %s
                  AND category = %s
                  AND status = 'active'
                  AND COALESCE(merged_into, '') = ''
                  AND COALESCE(consolidation_protected, FALSE) = FALSE
                  AND embedding IS NOT NULL
                  AND COALESCE(metadata->'embedding'->>'version', '1') = %s
                  AND COALESCE(metadata->'embedding'->>'model', '') = %s
                  AND metadata->'embedding'->>'dimensions' IS NOT DISTINCT FROM vector_dims(embedding)::text
                  AND 1 - (embedding <=> %s::vector) >= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    knowledge_id, category, str(configured_version),
                    current_embedding_model(),
                    list(embedding), threshold, list(embedding), limit,
                ),
            )
            return [r["id"] for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("nearest-neighbor lookup failed for %s: %s", knowledge_id, exc)
        return []
