"""Telemetry reflection: AI agent telemetry → skill / playbook / knowledge (option B).

The playbook pathway (memory_playbooks.py) subordinates telemetry to cross-entity
intelligence clustering — telemetry only enriches a prompt and cannot initiate
anything, so a single-entity discovery is lost. This module gives telemetry a
FIRST-CLASS, per-entity nightly path to knowledge.

Design principles:
  - Reflection before codification: raw telemetry is never dumped into knowledge.
    One LLM reflection per entity-day condenses it into typed candidates.
  - Recurrence builds conviction: each candidate enters as a DRAFT with
    evidence_breadth=1; the existing dedup + refine-on-merge machinery promotes
    and strengthens it as the same pattern recurs (merge_count → quality).
  - Outcome-aware: the day's actual conversation is included so the reflection
    can judge whether the agent's actions/discoveries were effective.

Runs nightly (schedule) after intelligence/knowledge, over each entity that had
telemetry that day and hasn't been reflected on yet.
"""
import logging
import uuid
from datetime import date, timedelta
from typing import Optional

from core.storage import get_memory_db_context
from memory_services import call_llm, generate_embedding, get_memory_settings
from services.llm import parse_llm_json
from memory_db_writes import insert_knowledge, log_pipeline_run
from memory_helpers import _get_entity_type_config
from memory_generation_policy import approval_status, resolve_generation_policy
from memory_facets import facet_prompt_instructions, validate_generated_facets

logger = logging.getLogger(__name__)

TELEMETRY_TYPES = ("internal_ai_thought", "internal_ai_tool_call")
_VALID_TARGETS = ("skill", "playbook", "best_practices", "lessons_learned", "trade_knowledge")

_REFLECTION_SYSTEM_PROMPT = (
    "You are a reflective learning engine for an AI agent. You are given the agent's own "
    "TELEMETRY (its internal thoughts and tool calls) for one entity over one day, plus the "
    "CONVERSATION that occurred, so you can judge what actually worked.\n\n"
    "Reflect: did the agent DO or DISCOVER anything reusable and worth remembering? Extract only "
    "genuinely reusable, generalizable learnings — not play-by-play. Zero is a valid answer.\n\n"
    "For each learning, choose a target type:\n"
    "- skill: a discrete reusable capability the agent exercised (e.g. an effective way to query a tool)\n"
    "- playbook: an ordered procedure that worked (only if a clear multi-step sequence achieved an outcome)\n"
    "- best_practices: a behavioral rule that worked\n"
    "- lessons_learned: something that went wrong + why\n"
    "- trade_knowledge: a durable fact discovered mid-action (e.g. a tool returned a rule/requirement)\n\n"
    "Generalize: strip specific names/IDs. Each learning needs a self-contained description stating "
    "WHAT it is and WHEN to use it. Internal thoughts alone are not durable trade knowledge unless "
    "corroborated by tool output, outcome evidence, or another reliable source.\n\n"
    'Return ONLY a JSON array (empty [] if nothing reusable): '
    '[{"target": "skill|playbook|best_practices|lessons_learned|trade_knowledge", '
    '"name": "...", "summary": "what it is and when to use it (<=1024 chars)", '
    '"content": "the full reusable learning", "signals": [], "tags": [], "facets": {}, '
    '"qualifications": [], "contradictions": [], "source_support": [], '
    '"skill_type": "soft|hard" (only for skill), "trigger_desc": "...", "procedure": "...", '
    '"inputs": [], "outputs": [], "tools": [], "prerequisites": [], "permissions": [], '
    '"environments": [], "agent_types": [], "side_effects": [], "failure_conditions": [], '
    '"recovery": [], "safety_requirements": [] (skill only), '
    '"trigger_conditions": [], "steps": [{"order": 1, "action": "..."}], "branches": [], '
    '"escalation_rules": [], "rollback": [], "completion_criteria": [], "exit_conditions": [] '
    '(playbook only), "confidence": 0.0-1.0, "schema_version": "knowledge-generation-v2"}]'
)


async def run_telemetry_reflection(reflection_date: Optional[str] = None, entity_limit: int = 100):
    """Nightly: reflect on each entity's telemetry for the given date (default:
    yesterday) and emit typed knowledge candidates. Idempotent per (entity, date)
    via the telemetry_reflection_log table."""
    settings = get_memory_settings() or {}
    if not settings.get("telemetry_reflection_enabled", True):
        return 0
    policy = resolve_generation_policy("telemetry_reflection", settings=settings)["values"]
    if not policy["enabled"]:
        return 0
    confidence_min = float(policy["min_confidence"])
    target_day = reflection_date or (date.today() - timedelta(days=1)).isoformat()

    # Entities with unreflected telemetry on target_day
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT primary_entity_type, primary_entity_id
            FROM interactions
            WHERE interaction_type = ANY(%s)
              AND DATE(timestamp) = %s
              AND NOT EXISTS (
                  SELECT 1 FROM telemetry_reflection_log l
                  WHERE l.entity_type = interactions.primary_entity_type
                    AND l.entity_id = interactions.primary_entity_id
                    AND l.reflection_date = %s
              )
            ORDER BY primary_entity_type, primary_entity_id
            LIMIT %s
        """, (list(TELEMETRY_TYPES), target_day, target_day, entity_limit))
        entities = [dict(r) for r in cursor.fetchall()]

    if not entities:
        return 0

    total = 0
    for e in entities:
        try:
            total += await _reflect_entity_day(
                e["primary_entity_type"], e["primary_entity_id"], target_day, confidence_min
            )
        except Exception as ex:
            from services.job_safety import ProviderStopError
            if isinstance(ex, ProviderStopError):
                logger.warning("Telemetry reflection stopped by provider: %s", ex)
                raise
            logger.error(f"Telemetry reflection failed for {e['primary_entity_type']}/{e['primary_entity_id']}: {ex}")
    logger.info(f"Telemetry reflection ({target_day}): {total} candidate(s) created across {len(entities)} entities")
    return total


async def _reflect_entity_day(entity_type: str, entity_id: str, day: str, confidence_min: float) -> int:
    # Fetch the day's telemetry + conversation for outcome context
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, interaction_type, content, timestamp, primary_entity_id,
                   embedding, embedding_model, embedding_version,
                   embedding_dimensions, embedded_at
            FROM interactions
            WHERE primary_entity_type = %s AND primary_entity_id = %s
              AND DATE(timestamp) = %s
            ORDER BY timestamp ASC
        """, (entity_type, entity_id, day))
        rows = [dict(r) for r in cursor.fetchall()]

    telemetry = [r for r in rows if r["interaction_type"] in TELEMETRY_TYPES]
    if not telemetry:
        _mark_reflected(entity_type, entity_id, day, 0, "no_telemetry")
        return 0

    convo = [r for r in rows if r["interaction_type"] not in TELEMETRY_TYPES]
    telemetry_text = "\n\n".join(
        f"[{r['interaction_type']}] {(r.get('content') or '')[:800]}" for r in telemetry
    )[:6000]
    convo_text = "\n\n".join(
        f"[{r['interaction_type']}] {(r.get('content') or '')[:500]}" for r in convo
    )[:3000]

    settings = get_memory_settings() or {}
    config = _get_entity_type_config(entity_type)
    policy = resolve_generation_policy(
        "telemetry_reflection", settings=settings, entity_config=config,
    )["values"]
    sources = [{
        "source_type": "interaction", "source_id": str(r["id"]),
        "entity_id": r.get("primary_entity_id"), "name": r["interaction_type"],
        "summary": "", "content": r.get("content") or "",
        "embedding": r.get("embedding"), "embedding_model": r.get("embedding_model"),
        "embedding_version": r.get("embedding_version"),
        "embedding_dimensions": r.get("embedding_dimensions"),
        "embedded_at": r.get("embedded_at"),
    } for r in telemetry]
    if settings.get("knowledge_evidence_routing_enabled", True):
        try:
            from memory_evidence_service import analyze_evidence, apply_high_similarity_link
            route = analyze_evidence(
                pathway="telemetry_reflection", sources=sources, settings=settings,
                entity_type=entity_type, outcome_signature={"day": day},
            )
            if apply_high_similarity_link(route, sources, settings):
                _mark_reflected(entity_type, entity_id, day, 0, "already_covered")
                return 0
            if (route.get("route") == "revision_assessment" and
                    settings.get("knowledge_evidence_routing_mode") == "enforced"):
                from memory_evidence_revision_service import assess_and_apply
                revision = await assess_and_apply(route=route, sources=sources, settings=settings)
                if revision.get("action") in {"no_change", "revised"}:
                    _mark_reflected(entity_type, entity_id, day, 0, "already_covered")
                    return 0
                if revision.get("action") == "manual_review":
                    log_pipeline_run("telemetry_reflection", "skipped",
                                     reason_code="revision_manual_review")
                    return 0
        except Exception as exc:
            logger.exception("Telemetry evidence routing failed: %s", exc)

    user_msg = (
        f"--- AGENT TELEMETRY ({len(telemetry)} events) ---\n{telemetry_text}\n\n"
        f"--- CONVERSATION (outcome context) ---\n{convo_text or '(none)'}"
    )

    try:
        from services.config_helpers import get_task_system_prompt
        system_prompt = get_task_system_prompt("telemetry_reflection", fallback=_REFLECTION_SYSTEM_PROMPT) or _REFLECTION_SYSTEM_PROMPT
        system_prompt += "\n\n" + facet_prompt_instructions()
        result_text = await call_llm(
            user_msg,
            system_prompt=system_prompt,
            max_tokens=int(policy["max_tokens"]),
            task_type="telemetry_reflection",
        )
        candidates = parse_llm_json(result_text, context="telemetry_reflection")
    except Exception as e:
        from services.job_safety import ProviderStopError
        if isinstance(e, ProviderStopError):
            # Do not mark this day reflected: it must remain safely resumable
            # after the provider issue is resolved.
            raise
        logger.error(f"Telemetry reflection LLM failed for {entity_type}/{entity_id}: {e}")
        log_pipeline_run("telemetry_reflection", "failed", reason_code="llm_error",
                         detail={"entity_type": entity_type, "day": day})
        return 0

    if not isinstance(candidates, list):
        candidates = [candidates] if isinstance(candidates, dict) else []

    created = 0

    for c in candidates[:5]:
        if not isinstance(c, dict):
            continue
        try:
            from memory_generation_contracts import validate_telemetry_candidate
            c = validate_telemetry_candidate(c).model_dump()
            c["target"] = c.get("target") or c.get("category")
        except ValueError as exc:
            logger.warning("Rejected invalid telemetry Knowledge candidate: %s", exc)
            continue
        target = (c.get("target") or "").strip()
        if target not in _VALID_TARGETS:
            continue
        conf = float(c.get("confidence", 0.5) or 0.5)
        if conf < confidence_min:
            continue
        name = (c.get("name") or "").strip()
        content = (c.get("content") or "").strip()
        summary = (c.get("summary") or "").strip()[:1024]
        if not name or not content:
            continue

        # Embed via the canonical category-aware serializer (same path as every
        # other creation pathway) so candidate discovery compares like-for-like.
        embedding = None
        try:
            from memory_embedding import embed_knowledge_fields
            embedding, _model = await embed_knowledge_fields(
                name=name, category=target, content=content, summary=summary,
            )
        except Exception:
            pass

        metadata = {}
        if target == "skill":
            metadata = {"skill_type": c.get("skill_type", "hard"), "trigger_desc": c.get("trigger_desc") or summary,
                        "procedure": c.get("procedure") or content, "purpose": c.get("purpose", ""),
                        "inputs": c.get("inputs", []), "outputs": c.get("outputs", []), "tools": c.get("tools", []),
                        "prerequisites": c.get("prerequisites", []), "permissions": c.get("permissions", []),
                        "environments": c.get("environments", []), "agent_types": c.get("agent_types", []),
                        "side_effects": c.get("side_effects", []), "failure_conditions": c.get("failure_conditions", []),
                        "recovery": c.get("recovery", []), "safety_requirements": c.get("safety_requirements", []),
                        "entity_types": [entity_type], "playbook_ids": []}
        elif target == "playbook":
            metadata = {"entity_type": entity_type, "signal_type": None,
                        "trigger_conditions": c.get("trigger_conditions", []),
                        "steps": c.get("steps", []), "purpose": c.get("purpose", ""),
                        "expected_outcome": c.get("expected_outcome", ""), "prerequisites": c.get("prerequisites", []),
                        "required_inputs": c.get("required_inputs", []), "responsible_roles": c.get("responsible_roles", []),
                        "tools": c.get("tools", []), "branches": c.get("branches", []),
                        "escalation_rules": c.get("escalation_rules", []), "failure_conditions": c.get("failure_conditions", []),
                        "rollback": c.get("rollback", []), "safety_requirements": c.get("safety_requirements", []),
                        "completion_criteria": c.get("completion_criteria", []), "exit_conditions": c.get("exit_conditions", []), "skill_ids": []}

        facets, facet_state = validate_generated_facets(c.get("facets") or {})
        metadata["facets"] = facets
        metadata["facet_extraction"] = facet_state
        status = approval_status(policy["approval_policy"])
        insert_knowledge(
            knowledge_id=str(uuid.uuid4()),
            intelligence_ids=[],
            signals=[],
            category=target,
            name=name,
            content=content,
            summary=summary,
            embedding=embedding,
            tags=[],
            source_pathway="telemetry_reflected",
            extraction_confidence=conf,
            evidence_breadth=1,
            status=status,
            metadata=metadata,
            source_ai_interaction_ids=[s["source_id"] for s in sources],
            source_links=sources,
        )
        created += 1
        logger.info(f"Telemetry reflection created {target} '{name}' [{status}] for {entity_type}/{entity_id}")

    _mark_reflected(entity_type, entity_id, day, created,
                    "knowledge_created" if created else "no_meaningful_knowledge")
    log_pipeline_run("telemetry_reflection", "created" if created else "skipped",
                     reason_code=None if created else "no_reusable_learning",
                     records_created=created,
                     detail={"entity_type": entity_type, "entity_id": entity_id, "day": day,
                             "telemetry_events": len(telemetry)})
    return created


def _mark_reflected(entity_type: str, entity_id: str, day: str, produced: int,
                    outcome: str = "knowledge_created") -> None:
    """Record that (entity, day) was reflected on — idempotency guard."""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO telemetry_reflection_log (entity_type, entity_id, reflection_date, candidates_created, outcome, reflected_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (entity_type, entity_id, reflection_date) DO UPDATE
                    SET candidates_created = EXCLUDED.candidates_created, outcome = EXCLUDED.outcome, reflected_at = NOW()
            """, (entity_type, entity_id, day, produced, outcome))
    except Exception as e:
        logger.warning(f"_mark_reflected failed for {entity_type}/{entity_id}/{day}: {e}")


async def backfill_telemetry(max_days: int = 7) -> dict:
    """Process the accumulated AI-telemetry backlog by reflecting on each
    historical day that still has unreflected telemetry, oldest-first.

    Idempotent + resumable: run_telemetry_reflection skips any (entity, day)
    already in telemetry_reflection_log, so re-running picks up where it left off.
    Processes at most `max_days` days per invocation (most-recent window) to keep
    the job bounded; re-trigger to continue if more history remains.

    Hooked into the same 'Drain Backlog' trigger as the intelligence→knowledge
    drain so one click backfills both experiential backlogs."""
    from memory_db_writes import log_pipeline_run

    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MIN(DATE(timestamp)) AS min_d, MAX(DATE(timestamp)) AS max_d
                FROM interactions
                WHERE interaction_type = ANY(%s)
            """, (list(TELEMETRY_TYPES),))
            row = cursor.fetchone()
    except Exception as e:
        logger.error(f"backfill_telemetry range query failed: {e}")
        return {"days_processed": 0, "candidates": 0}

    min_d = row["min_d"] if row else None
    max_d = row["max_d"] if row else None
    if not min_d:
        logger.info("Telemetry backfill: no telemetry interactions found")
        log_pipeline_run("telemetry_reflection_backfill", "skipped", reason_code="no_telemetry")
        return {"days_processed": 0, "candidates": 0}

    yesterday = date.today() - timedelta(days=1)
    if max_d > yesterday:
        max_d = yesterday
    # Most-recent window of max_days (oldest-first iteration within the window)
    start = max(min_d, max_d - timedelta(days=max_days - 1))
    if start > max_d:
        logger.info("Telemetry backfill: backlog fully within future window, nothing to do")
        return {"days_processed": 0, "candidates": 0}

    days_processed = 0
    total_candidates = 0
    cur = start
    while cur <= max_d:
        try:
            n = await run_telemetry_reflection(cur.isoformat())
            total_candidates += n
        except Exception as e:
            from services.job_safety import ProviderStopError
            if isinstance(e, ProviderStopError):
                logger.warning("Telemetry backfill stopped by provider: %s", e)
                raise
            logger.error(f"Telemetry backfill day {cur} failed: {e}")
        days_processed += 1
        if days_processed % 5 == 0:
            logger.info(f"Telemetry backfill progress: {days_processed} day(s) processed, {total_candidates} candidate(s)")
        cur += timedelta(days=1)

    logger.info(f"Telemetry backfill complete: {days_processed} day(s), {total_candidates} candidate(s) "
                f"(window {start} → {max_d})")
    log_pipeline_run(
        "telemetry_reflection_backfill", "created" if total_candidates else "skipped",
        reason_code=None if total_candidates else "no_reusable_learning",
        records_created=total_candidates,
        detail={"days_processed": days_processed, "window_start": str(start), "window_end": str(max_d)},
        trigger="manual",
    )
    return {"days_processed": days_processed, "candidates": total_candidates,
            "window_start": str(start), "window_end": str(max_d)}
