"""memory_consolidation_repository.py — DB layer for knowledge hygiene & consolidation.

All SQL lives here. The service layer (``memory_consolidation_service``)
orchestrates preview/apply via these functions. The apply path is a single
transaction: advisory lock → ``SELECT ... FOR UPDATE`` sources in ID order →
re-validate against the preview snapshot → write canonical/event/audit →
retire sources → mark preview applied → commit. Any failure rolls the whole
thing back, so no source is ever retired unless a valid canonical + audit row
exist in the same committed transaction.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


class ConsolidationError(Exception):
    """Raised inside the apply/reverse transaction; carries an HTTP-friendly code.

    ``code`` maps to a status (see service): ``missing_source``→404,
    ``expired``/``stale_preview``/``already_applied``/``already_merged``/
    ``dependency_conflict``→409, ``invalid_*``→422.
    """

    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value) if value is not None else None


# ─── knowledge reads ─────────────────────────────────────────────────────────

KNOWLEDGE_COLUMNS = (
    "id, source_intelligence_ids, signals, name, content, summary, embedding, "
    "visibility, tags, category, metadata, status, quality_score, merge_count, "
    "last_merged_at, evidence_breadth, outcome_signal, extraction_confidence, "
    "source_pathway, source_ai_interaction_ids, success_count, failure_count, "
    "feedback_notes, version, parent_id, merged_into, merged_from, "
    "consolidation_event_id, consolidation_protected, created_at, updated_at"
)


def load_knowledge_records(knowledge_ids: Sequence[str]) -> List[Dict[str, Any]]:
    if not knowledge_ids:
        return []
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {KNOWLEDGE_COLUMNS} FROM knowledge WHERE id = ANY(%s)",
            (list(knowledge_ids),),
        )
        return [dict(r) for r in cur.fetchall()]


def load_knowledge_record(knowledge_id: str) -> Optional[Dict[str, Any]]:
    rows = load_knowledge_records([knowledge_id])
    return rows[0] if rows else None


def load_active_records_for_categories(categories: Sequence[str]) -> List[Dict[str, Any]]:
    """Active, embedded, non-merged, non-protected records in the allowlist."""
    if not categories:
        return []
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {KNOWLEDGE_COLUMNS} FROM knowledge
            WHERE status = 'active'
              AND embedding IS NOT NULL
              AND COALESCE(merged_into, '') = ''
              AND COALESCE(consolidation_protected, FALSE) = FALSE
              AND category = ANY(%s)
            """,
            (list(categories),),
        )
        return [dict(r) for r in cur.fetchall()]


# ─── hygiene runs ────────────────────────────────────────────────────────────

def create_hygiene_run(
    *,
    origin: str,
    mode: str,
    settings_snapshot: Dict[str, Any],
    embedding_version: int,
    categories: Sequence[str],
    created_by: Optional[str] = None,
) -> str:
    run_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO knowledge_hygiene_runs
                (id, origin, mode, status, settings_snapshot, embedding_version,
                 categories, started_at, created_by)
            VALUES (%s, %s, %s, 'running', %s, %s, %s, NOW(), %s)
            """,
            (run_id, origin, mode, _json(settings_snapshot), embedding_version,
             list(categories), created_by),
        )
    return run_id


def update_hygiene_run(run_id: str, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        "status", "records_scanned", "clusters_found", "proposals_created",
        "applied_count", "failed_count", "error", "finished_at",
    }
    sets = []
    params: List[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k} = %s")
        params.append(v)
    if not sets:
        return
    params.append(run_id)
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE knowledge_hygiene_runs SET {', '.join(sets)} WHERE id = %s",
            params,
        )


def link_cluster_proposal(cluster_id: str, proposal_id: Optional[str]) -> None:
    """Record the preview/proposal id generated for a candidate cluster."""
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE knowledge_hygiene_clusters SET proposal_id = %s, updated_at = NOW() WHERE id = %s",
            (proposal_id, cluster_id),
        )


def load_hygiene_run(run_id: str) -> Optional[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM knowledge_hygiene_runs WHERE id = %s", (run_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def load_hygiene_clusters(run_id: str) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.*, m.member_rows
            FROM knowledge_hygiene_clusters c
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(jsonb_build_object(
                    'knowledge_id', cm.knowledge_id,
                    'similarity_to_centroid', cm.similarity_to_centroid,
                    'min_member_similarity', cm.min_member_similarity,
                    'role', cm.role,
                    'decision_reason', cm.decision_reason
                )) AS member_rows
                FROM knowledge_hygiene_cluster_members cm
                WHERE cm.cluster_id = c.id
            ) m ON TRUE
            WHERE c.run_id = %s
            ORDER BY c.category, c.created_at
            """,
            (run_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def insert_hygiene_cluster(
    *,
    run_id: str,
    category: str,
    group: Dict[str, Any],
    centroid_vec: Optional[Sequence[float]] = None,
    proposal_id: Optional[str] = None,
) -> str:
    cluster_id = str(uuid.uuid4())
    metrics = group.get("metrics") or {}
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO knowledge_hygiene_clusters
                (id, run_id, category, member_ids, centroid, min_similarity,
                 avg_similarity, max_similarity, cohesion, weak_links,
                 split_reason, proposal_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (cluster_id, run_id, category, group.get("member_ids") or [],
             list(centroid_vec) if centroid_vec else None,
             metrics.get("pairwise_min"), metrics.get("cohesion"),
             metrics.get("pairwise_max"), metrics.get("cohesion"),
             _json(metrics.get("weak_links") or []),
             group.get("split_reason"), proposal_id, group.get("status")),
        )
        members = group.get("member_ids") or []
        sims = metrics.get("centroid_similarity") or {}
        for mid in members:
            cur.execute(
                """
                INSERT INTO knowledge_hygiene_cluster_members
                    (cluster_id, knowledge_id, run_id, similarity_to_centroid, role)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (cluster_id, knowledge_id) DO NOTHING
                """,
                (cluster_id, mid, run_id, sims.get(mid), "member"),
            )
    return cluster_id


# ─── previews ────────────────────────────────────────────────────────────────

def insert_preview(
    *,
    origin: str,
    actor_type: str,
    actor_id: Optional[str],
    category: str,
    source_ids: Sequence[str],
    source_snapshot: Dict[str, Any],
    metrics: Dict[str, Any],
    options: Dict[str, Any],
    settings_snapshot: Dict[str, Any],
    model_provider: Optional[str],
    model_name: Optional[str],
    prompt_version: str,
    raw_response: Any,
    proposal: Any,
    validation_errors: Optional[List[str]],
    expires_at,
) -> str:
    preview_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        state = "ready" if proposal is not None and not validation_errors else "failed"
        cur.execute(
            """
            INSERT INTO knowledge_consolidation_previews
                (id, origin, actor_type, actor_id, category, state, source_ids,
                 source_snapshot, metrics, options, settings_snapshot,
                 model_provider, model_name, prompt_version, raw_response,
                 proposal, validation_errors, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (preview_id, origin, actor_type, actor_id, category, state,
             list(source_ids), _json(source_snapshot), _json(metrics),
             _json(options), _json(settings_snapshot), model_provider, model_name,
             prompt_version, _json(raw_response), _json(proposal),
             _json(validation_errors or []), expires_at),
        )
        for sid, snap in (source_snapshot or {}).items():
            cur.execute(
                """
                INSERT INTO knowledge_consolidation_preview_sources
                    (preview_id, knowledge_id, source_version, source_updated_at,
                     source_status, source_snapshot)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (preview_id, sid, snap.get("version"), snap.get("updated_at"),
                 snap.get("status"), _json(snap.get("record"))),
            )
    return preview_id


def load_preview(preview_id: str) -> Optional[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM knowledge_consolidation_previews WHERE id = %s", (preview_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def load_preview_sources(preview_id: str) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM knowledge_consolidation_preview_sources WHERE preview_id = %s",
            (preview_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def expire_preview(preview_id: str) -> None:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE knowledge_consolidation_previews SET state = 'expired', updated_at = NOW() WHERE id = %s",
            (preview_id,),
        )


def mark_preview_applied(preview_id: str, event_id: str) -> None:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE knowledge_consolidation_previews
            SET state = 'applied', applied_event_id = %s, updated_at = NOW()
            WHERE id = %s AND state NOT IN ('applied',)
            """,
            (event_id, preview_id),
        )


# ─── events ──────────────────────────────────────────────────────────────────

def load_event(event_id: str) -> Optional[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM knowledge_consolidation_events WHERE id = %s", (event_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def load_event_sources(event_id: str) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM knowledge_consolidation_event_sources WHERE event_id = %s ORDER BY knowledge_id",
            (event_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def load_latest_event_for_canonical(canonical_id: str) -> Optional[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM knowledge_consolidation_events
            WHERE canonical_id = %s AND reversed_event_id IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (canonical_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


# ─── canonical field aggregation (deterministic, §14.4) ──────────────────────

def _union_preserve_order(seqs: Sequence[Sequence[Any]]) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for seq in seqs:
        for item in (seq or []):
            key = json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


def aggregate_canonical_payload(
    *,
    source_rows: Sequence[Dict[str, Any]],
    approved: Dict[str, Any],
    canonical_target_id: Optional[str],
    strategy: str,
    event_id: str,
    preview_id: str,
    model_name: Optional[str],
    prompt_version: str,
    origin: str,
) -> Tuple[Dict[str, Any], List[str], Dict[str, Any]]:
    """Merge LLM/approved content with deterministic system-field aggregation.

    Returns ``(canonical_payload, contradictions, target_pre_merge_snapshot)``.
    The LLM never sets IDs, status, visibility, lineage, audit fields, quality
    counters, or timestamps — those come from deterministic code here.
    """
    contradictions: List[str] = []

    # Union provenance / signals / tags / merged_from, preserving first-seen order.
    intel_ids = _union_preserve_order([r.get("source_intelligence_ids") or [] for r in source_rows])
    ai_ids = _union_preserve_order([r.get("source_ai_interaction_ids") or [] for r in source_rows])
    signals = _union_preserve_order([r.get("signals") or [] for r in source_rows])
    tags = _union_preserve_order([r.get("tags") or [] for r in source_rows])
    source_ids = [r["id"] for r in source_rows]
    merged_from = _union_preserve_order([r.get("merged_from") or [] for r in source_rows] + [source_ids])

    # Governed facets: merge only when values agree; conflicts → metadata.consolidation_conflicts.
    facets: Dict[str, Any] = {}
    facet_conflicts: Dict[str, Any] = {}
    for r in source_rows:
        rmeta = r.get("metadata") or {}
        if isinstance(rmeta, str):
            try:
                rmeta = json.loads(rmeta)
            except Exception:
                rmeta = {}
        rfacets = rmeta.get("facets") if isinstance(rmeta, dict) else None
        if not isinstance(rfacets, dict):
            continue
        for k, v in rfacets.items():
            if k in facets and facets[k] != v:
                facet_conflicts.setdefault(k, []).append({"existing": facets[k], "conflicting": v})
                contradictions.append(f"facet '{k}' has conflicting values across sources")
            else:
                facets[k] = v

    # Sum merge counts + absorbed count (all sources except the kept target).
    total_merge_count = sum(int(r.get("merge_count") or 0) for r in source_rows)
    if strategy == "create_new":
        absorbed = len(source_rows)
    else:
        absorbed = max(0, len(source_rows) - 1)  # target stays active
    merge_count = total_merge_count + absorbed

    # Evidence breadth: at least the count of distinct evidence references.
    evidence_breadth = max([int(r.get("evidence_breadth") or 1) for r in source_rows] + [len(intel_ids) or 1])

    # Target row (for update_existing: its pre-merge snapshot + visibility/status).
    target_row = None
    target_pre_merge = None
    if strategy == "update_existing":
        target_row = next((r for r in source_rows if r["id"] == canonical_target_id), None)
        if target_row is not None:
            target_pre_merge = {
                "id": target_row["id"],
                "name": target_row.get("name"),
                "summary": target_row.get("summary"),
                "content": target_row.get("content"),
                "metadata": target_row.get("metadata"),
                "version": target_row.get("version"),
                "status": target_row.get("status"),
                "visibility": target_row.get("visibility"),
            }

    visibility = (target_row or {}).get("visibility") or "shared"
    status = (target_row or {}).get("status") or "active"
    base_version = int((target_row or source_rows[0]).get("version") or 1)

    # Approved content (LLM/user) — only these content fields come from the proposal.
    name = (approved.get("name") or "").strip() or (target_row or {}).get("name") or "Consolidated Knowledge"
    summary = approved.get("summary") or ""
    content = approved.get("content") or ""
    approved_signals = approved.get("signals") or []
    approved_tags = approved.get("tags") or []
    approved_metadata = approved.get("metadata") or {}

    # Combine approved signals/tags with aggregated ones (approved first, dedup).
    combined_signals = _union_preserve_order([approved_signals, signals])
    combined_tags = _union_preserve_order([approved_tags, tags])

    # Canonical metadata: start from approved, fold in aggregation lineage + facets.
    canonical_meta = dict(approved_metadata) if isinstance(approved_metadata, dict) else {}
    if facets:
        canonical_meta["facets"] = {**canonical_meta.get("facets", {}), **facets}
    canonical_meta["consolidation"] = {
        "event_id": event_id,
        "preview_id": preview_id,
        "source_ids": source_ids,
        "model": model_name,
        "prompt_version": prompt_version,
        "origin": origin,
        "applied_at": _now(),
    }
    if facet_conflicts:
        canonical_meta["consolidation_conflicts"] = facet_conflicts

    payload = {
        "name": name,
        "summary": summary,
        "content": content,
        "signals": combined_signals,
        "tags": combined_tags,
        "metadata": canonical_meta,
        "source_intelligence_ids": intel_ids,
        "source_ai_interaction_ids": ai_ids,
        "merged_from": merged_from,
        "merge_count": merge_count,
        "evidence_breadth": evidence_breadth,
        "version": base_version + 1,
        "visibility": visibility,
        "status": status,
    }
    return payload, contradictions, target_pre_merge


# ─── transactional apply ─────────────────────────────────────────────────────

def apply_consolidation(
    *,
    preview: Dict[str, Any],
    approved_canonical: Dict[str, Any],
    canonical_strategy: str,
    canonical_target_id: Optional[str],
    embedding: Optional[Sequence[float]],
    embedding_model: Optional[str],
    actor_type: str,
    actor_id: Optional[str],
    origin: str,
) -> str:
    """Apply a preview transactionally. Returns the new event_id.

    Raises :class:`ConsolidationError` on any validation or DB failure; the
    context manager rolls the entire transaction back.
    """
    preview_id = preview["id"]
    category = preview["category"]
    source_ids = list(preview.get("source_ids") or [])
    snapshot_rows = load_preview_sources(preview_id)
    snapshot = {row["knowledge_id"]: row for row in snapshot_rows}

    if canonical_strategy not in ("update_existing", "create_new"):
        raise ConsolidationError("invalid_strategy", "canonical_strategy must be update_existing or create_new", 400)
    if canonical_strategy == "update_existing" and canonical_target_id not in source_ids:
        raise ConsolidationError("invalid_target", "canonical_target_id must be one of the source ids", 400)

    event_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        # 1. Global advisory lock so two applies cannot interleave.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('masteragent_knowledge_consolidation'))")

        # 2. Re-read preview under lock to confirm it is still applyable.
        cur.execute("SELECT state, expires_at FROM knowledge_consolidation_previews WHERE id = %s", (preview_id,))
        prow = cur.fetchone()
        if not prow:
            raise ConsolidationError("missing_preview", "Preview not found", 404)
        if prow["state"] == "applied":
            raise ConsolidationError("already_applied", "Preview was already applied", 409)
        if prow["expires_at"] is not None and prow["expires_at"] <= datetime.now(timezone.utc):
            raise ConsolidationError("expired", "Preview has expired", 410)

        # 3. Lock every source row FOR UPDATE in deterministic ID order.
        ordered_ids = sorted(source_ids)
        placeholders = ",".join(["%s"] * len(ordered_ids))
        cur.execute(
            f"SELECT {KNOWLEDGE_COLUMNS} FROM knowledge WHERE id IN ({placeholders}) ORDER BY id FOR UPDATE",
            ordered_ids,
        )
        locked_rows = [dict(r) for r in cur.fetchall()]
        if len(locked_rows) != len(source_ids):
            raise ConsolidationError("missing_source", "One or more source records no longer exist", 404)

        # 4. Re-validate against the preview snapshot (stale/race detection).
        for row in locked_rows:
            snap = snapshot.get(row["id"])
            if row.get("status") not in ("active", "confirmed"):
                raise ConsolidationError("source_not_active",
                                         f"Source {row['id']} is no longer active (status={row.get('status')})", 409)
            if row.get("merged_into"):
                raise ConsolidationError("already_merged",
                                         f"Source {row['id']} was already merged into {row.get('merged_into')}", 409)
            if snap is not None:
                if int(row.get("version") or 1) != int(snap.get("source_version") or 1):
                    raise ConsolidationError("stale_preview",
                                             f"Source {row['id']} changed since preview (version)", 409)
                snap_updated = snap.get("source_updated_at")
                row_updated = row.get("updated_at")
                if snap_updated is not None and row_updated is not None and _normalize_ts(snap_updated) != _normalize_ts(row_updated):
                    raise ConsolidationError("stale_preview",
                                             f"Source {row['id']} changed since preview (updated_at)", 409)

        # 5. Aggregate deterministic system fields + approved content.
        payload, contradictions, target_pre_merge = aggregate_canonical_payload(
            source_rows=locked_rows, approved=approved_canonical,
            canonical_target_id=canonical_target_id, strategy=canonical_strategy,
            event_id=event_id, preview_id=preview_id,
            model_name=preview.get("model_name"), prompt_version=preview.get("prompt_version"),
            origin=origin,
        )

        # 6. Stamp embedding provenance onto canonical metadata.
        canonical_meta = payload["metadata"]
        if embedding:
            try:
                from memory_embedding import merge_embedding_metadata
                canonical_meta = merge_embedding_metadata(canonical_meta, model=embedding_model, vector=embedding)
                payload["metadata"] = canonical_meta
            except Exception:
                pass

        now = _now()

        # 7. Create/update the canonical record.
        if canonical_strategy == "update_existing":
            canonical_id = canonical_target_id
            absorbed_ids = [i for i in source_ids if i != canonical_id]
            _update_canonical(cur, canonical_id, payload, embedding, now)
        else:
            canonical_id = str(uuid.uuid4())
            absorbed_ids = list(source_ids)
            _insert_canonical(cur, canonical_id, category, payload, embedding, now)

        # 8. Insert the audit event + per-source snapshots.
        cur.execute(
            """
            INSERT INTO knowledge_consolidation_events
                (id, preview_id, action, origin, actor_type, actor_id, category,
                 canonical_id, canonical_strategy, model_provider, model_name,
                 prompt_version, similarity_threshold, settings_snapshot,
                 proposed_output, approved_output, user_edits, warnings, contradictions)
            VALUES (%s, %s, 'apply', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (event_id, preview_id, origin, actor_type, actor_id, category, canonical_id,
             canonical_strategy, preview.get("model_provider"), preview.get("model_name"),
             preview.get("prompt_version"), (preview.get("settings_snapshot") or {}).get("knowledge_hygiene_similarity_threshold"),
             _json(preview.get("settings_snapshot")), _json(preview.get("proposal")),
             _json(approved_canonical), _json(_diff_user_edits(preview, approved_canonical)),
             _json((preview.get("proposal") or {}).get("warnings") or []),
             _json(contradictions)),
        )
        for row in locked_rows:
            role = "canonical_target" if (canonical_strategy == "update_existing" and row["id"] == canonical_id) else "absorbed"
            trace = _traceability_for(preview.get("proposal"), row["id"])
            cur.execute(
                """
                INSERT INTO knowledge_consolidation_event_sources
                    (event_id, knowledge_id, role, original_snapshot, source_traceability, merged_into)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (event_id, row["id"], role, _json(_snapshot_row(row)),
                 _json(trace), canonical_id if row["id"] != canonical_id else None),
            )

        # 9. Retire absorbed sources (never the canonical target).
        if absorbed_ids:
            cur.execute(
                """
                UPDATE knowledge
                SET status = 'retired', merged_into = %s,
                    consolidation_event_id = %s, updated_at = %s
                WHERE id = ANY(%s)
                """,
                (canonical_id, event_id, now, absorbed_ids),
            )

        # 10. Mark the preview applied inside the same transaction.
        cur.execute(
            """
            UPDATE knowledge_consolidation_previews
            SET state = 'applied', applied_event_id = %s, updated_at = %s
            WHERE id = %s AND state <> 'applied'
            """,
            (event_id, now, preview_id),
        )
        if cur.rowcount == 0:
            raise ConsolidationError("already_applied", "Preview was already applied concurrently", 409)

    return event_id


def _update_canonical(cur, canonical_id: str, payload: Dict[str, Any], embedding, now: str) -> None:
    cur.execute(
        """
        UPDATE knowledge
        SET name = %s, summary = %s, content = %s, signals = %s, tags = %s,
            metadata = %s, embedding = COALESCE(%s, embedding),
            source_intelligence_ids = %s, source_ai_interaction_ids = %s,
            merged_from = %s, merge_count = %s, evidence_breadth = %s,
            version = %s, last_merged_at = %s, updated_at = %s
        WHERE id = %s
        """,
        (payload["name"], payload["summary"], payload["content"], payload["signals"],
         payload["tags"], _json(payload["metadata"]), list(embedding) if embedding else None,
         payload["source_intelligence_ids"], payload["source_ai_interaction_ids"],
         payload["merged_from"], payload["merge_count"], payload["evidence_breadth"],
         payload["version"], now, now, canonical_id),
    )


def _insert_canonical(cur, canonical_id: str, category: str, payload: Dict[str, Any], embedding, now: str) -> None:
    from memory_skill_md import SKILL_MD_CATEGORIES, is_skill_md, render_skill_md
    content = payload["content"]
    if category in SKILL_MD_CATEGORIES and not is_skill_md(content):
        content = render_skill_md(
            name=payload["name"], category=category,
            description=payload["summary"] or content, body=content,
            metadata=payload["metadata"], signals=payload["signals"],
            tags=payload["tags"], version=payload["version"],
        )
    cur.execute(
        """
        INSERT INTO knowledge (
            id, source_intelligence_ids, signals, name, content, summary, embedding,
            visibility, tags, category, metadata, status, merge_count, evidence_breadth,
            source_ai_interaction_ids, merged_from, version, consolidation_event_id,
            created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (canonical_id, payload["source_intelligence_ids"], payload["signals"], payload["name"],
         content, payload["summary"], list(embedding) if embedding else None,
         payload["visibility"], payload["tags"], category, _json(payload["metadata"]),
         payload["status"], payload["merge_count"], payload["evidence_breadth"],
         payload["source_ai_interaction_ids"], payload["merged_from"], payload["version"],
         None, now, now),
    )


def _snapshot_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """A serializable original-state snapshot for the audit row (no embedding)."""
    out = dict(row)
    out.pop("embedding", None)
    return out


def _traceability_for(proposal: Optional[Dict[str, Any]], source_id: str) -> Dict[str, Any]:
    if not isinstance(proposal, dict):
        return {}
    for entry in proposal.get("source_traceability") or []:
        if isinstance(entry, dict) and entry.get("source_id") == source_id:
            return entry
    return {}


def _diff_user_edits(preview: Dict[str, Any], approved: Dict[str, Any]) -> Dict[str, Any]:
    """Detect which canonical fields the user edited vs the LLM proposal."""
    proposal = preview.get("proposal") or {}
    canonical = proposal.get("canonical") or {}
    edits: Dict[str, Any] = {}
    for field in ("name", "summary", "content"):
        proposed = canonical.get(field)
        actual = approved.get(field)
        if proposed != actual:
            edits[field] = {"proposed": proposed, "approved": actual}
    return edits


def _normalize_ts(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return text


# ─── transactional reversal ──────────────────────────────────────────────────

def reverse_event(event_id: str, *, actor_type: str, actor_id: Optional[str], origin: str = "admin") -> str:
    """Reverse an applied event. Creates a NEW audit event; never deletes the original.

    Restores retired sources to active (clearing merged_into/event) and, for
    update_existing, restores the canonical target's pre-merge snapshot; for
    create_new, retires the created canonical. Aborts (409) if any affected
    record participated in a LATER consolidation.
    """
    reversed_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('masteragent_knowledge_consolidation'))")

        event = load_event(event_id) or {}
        if not event:
            raise ConsolidationError("missing_event", "Event not found", 404)
        if event.get("reversed_event_id"):
            raise ConsolidationError("already_reversed", "Event was already reversed", 409)

        canonical_id = event["canonical_id"]
        sources = load_event_sources(event_id)
        affected_ids = [s["knowledge_id"] for s in sources] + [canonical_id]

        # Dependency guard: none of the affected records may have participated in
        # a later consolidation (as source or canonical).
        cur.execute(
            """
            SELECT DISTINCT e.id FROM knowledge_consolidation_events e
            JOIN knowledge_consolidation_event_sources es ON es.event_id = e.id
            WHERE e.created_at > %s AND es.knowledge_id = ANY(%s) AND e.reversed_event_id IS NULL
            """,
            (event["created_at"], affected_ids),
        )
        if cur.fetchone():
            raise ConsolidationError("dependency_conflict",
                                     "A later consolidation depends on this event's records", 409)
        cur.execute(
            """
            SELECT id FROM knowledge_consolidation_events
            WHERE canonical_id = ANY(%s) AND created_at > %s AND reversed_event_id IS NULL
            AND id <> %s
            """,
            (affected_ids, event["created_at"], event_id),
        )
        if cur.fetchone():
            raise ConsolidationError("dependency_conflict",
                                     "A later consolidation used an affected record as canonical", 409)

        now = _now()

        if event["canonical_strategy"] == "create_new":
            # Retire the created canonical (it did not exist before).
            cur.execute(
                """
                UPDATE knowledge SET status = 'retired', merged_into = NULL,
                    consolidation_event_id = %s, updated_at = %s
                WHERE id = %s
                """,
                (reversed_id, now, canonical_id),
            )
        else:
            # Restore the canonical target's pre-merge snapshot.
            target_snap = None
            for s in sources:
                if s.get("role") == "canonical_target":
                    snap = s.get("original_snapshot") or {}
                    target_snap = snap
                    break
            if target_snap:
                cur.execute(
                    """
                    UPDATE knowledge
                    SET name = %s, summary = %s, content = %s, metadata = %s,
                        version = %s, status = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (target_snap.get("name"), target_snap.get("summary"), target_snap.get("content"),
                     _json(target_snap.get("metadata")), target_snap.get("version"),
                     target_snap.get("status") or "active", now, canonical_id),
                )
            # Clear lineage pointers on the canonical target.
            cur.execute(
                """
                UPDATE knowledge SET consolidation_event_id = %s, updated_at = %s
                WHERE id = %s
                """,
                (reversed_id, now, canonical_id),
            )

        # Restore every absorbed source to active.
        for s in sources:
            if s.get("role") == "absorbed":
                sid = s["knowledge_id"]
                cur.execute(
                    """
                    UPDATE knowledge
                    SET status = 'active', merged_into = NULL,
                        consolidation_event_id = NULL, updated_at = %s
                    WHERE id = %s
                    """,
                    (now, sid),
                )

        # Record the reversal event (audit; original event kept intact).
        cur.execute(
            """
            INSERT INTO knowledge_consolidation_events
                (id, preview_id, action, origin, actor_type, actor_id, category,
                 canonical_id, canonical_strategy, reversed_event_id)
            VALUES (%s, %s, 'reverse', %s, %s, %s, %s, %s, %s, %s)
            """,
            (reversed_id, event.get("preview_id"), origin, actor_type, actor_id,
             event.get("category"), canonical_id, event.get("canonical_strategy"), event_id),
        )
        cur.execute(
            "UPDATE knowledge_consolidation_events SET reversed_event_id = %s WHERE id = %s",
            (reversed_id, event_id),
        )

    return reversed_id
