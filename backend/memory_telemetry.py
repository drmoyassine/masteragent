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
from memory_dedup import find_similar_existing, compute_quality_score, refine_or_increment_merge
from memory_db_writes import insert_knowledge, log_pipeline_run
from memory_helpers import _get_entity_type_config

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
    "WHAT it is and WHEN to use it.\n\n"
    'Return ONLY a JSON array (empty [] if nothing reusable): '
    '[{"target": "skill|playbook|best_practices|lessons_learned|trade_knowledge", '
    '"name": "...", "summary": "what it is and when to use it (<=1024 chars)", '
    '"content": "the full reusable learning; for playbook include ordered steps", '
    '"skill_type": "soft|hard" (only for skill), '
    '"steps": [{"order": 1, "action": "..."}] (only for playbook), '
    '"confidence": 0.0-1.0}]'
)


async def run_telemetry_reflection(reflection_date: Optional[str] = None):
    """Nightly: reflect on each entity's telemetry for the given date (default:
    yesterday) and emit typed knowledge candidates. Idempotent per (entity, date)
    via the telemetry_reflection_log table."""
    settings = get_memory_settings() or {}
    if not settings.get("telemetry_reflection_enabled", True):
        return 0
    confidence_min = float(settings.get("telemetry_reflection_confidence_min", 0.6))
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
        """, (list(TELEMETRY_TYPES), target_day, target_day))
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
            logger.error(f"Telemetry reflection failed for {e['primary_entity_type']}/{e['primary_entity_id']}: {ex}")
    logger.info(f"Telemetry reflection ({target_day}): {total} candidate(s) created across {len(entities)} entities")
    return total


async def _reflect_entity_day(entity_type: str, entity_id: str, day: str, confidence_min: float) -> int:
    # Fetch the day's telemetry + conversation for outcome context
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT interaction_type, content, timestamp
            FROM interactions
            WHERE primary_entity_type = %s AND primary_entity_id = %s
              AND DATE(timestamp) = %s
            ORDER BY timestamp ASC
        """, (entity_type, entity_id, day))
        rows = [dict(r) for r in cursor.fetchall()]

    telemetry = [r for r in rows if r["interaction_type"] in TELEMETRY_TYPES]
    if not telemetry:
        _mark_reflected(entity_type, entity_id, day, 0)
        return 0

    convo = [r for r in rows if r["interaction_type"] not in TELEMETRY_TYPES]
    telemetry_text = "\n\n".join(
        f"[{r['interaction_type']}] {(r.get('content') or '')[:800]}" for r in telemetry
    )[:6000]
    convo_text = "\n\n".join(
        f"[{r['interaction_type']}] {(r.get('content') or '')[:500]}" for r in convo
    )[:3000]

    user_msg = (
        f"--- AGENT TELEMETRY ({len(telemetry)} events) ---\n{telemetry_text}\n\n"
        f"--- CONVERSATION (outcome context) ---\n{convo_text or '(none)'}"
    )

    settings = get_memory_settings() or {}
    try:
        result_text = await call_llm(
            user_msg,
            system_prompt=_REFLECTION_SYSTEM_PROMPT,
            max_tokens=int(settings.get("telemetry_reflection_max_tokens", 1200)),
            task_type="knowledge_generation",
        )
        candidates = parse_llm_json(result_text, context="telemetry_reflection")
    except Exception as e:
        logger.error(f"Telemetry reflection LLM failed for {entity_type}/{entity_id}: {e}")
        _mark_reflected(entity_type, entity_id, day, 0)
        log_pipeline_run("telemetry_reflection", "failed", reason_code="llm_error",
                         detail={"entity_type": entity_type, "day": day})
        return 0

    if not isinstance(candidates, list):
        candidates = [candidates] if isinstance(candidates, dict) else []

    dedup_threshold = float(settings.get("dedup_similarity_threshold", 0.85))
    config = _get_entity_type_config(entity_type)
    created = 0

    for c in candidates[:5]:
        if not isinstance(c, dict):
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

        # Embed on name+summary (the discovery signal), same as other pathways
        embedding = None
        try:
            embedding = await generate_embedding(f"{name}. {summary or content}")
        except Exception:
            pass

        # Dedup: recurrence strengthens an existing record rather than duplicating
        if embedding:
            existing = await find_similar_existing(embedding, dedup_threshold, category=target)
            if existing:
                await refine_or_increment_merge(existing, new_name=name, new_content=content, new_summary=summary)
                created += 1
                continue

        metadata = {}
        if target == "skill":
            metadata = {"skill_type": c.get("skill_type", "hard"), "trigger_desc": summary,
                        "procedure": content, "entity_types": [entity_type], "playbook_ids": []}
        elif target == "playbook":
            metadata = {"entity_type": entity_type, "signal_type": None,
                        "trigger_conditions": c.get("trigger_conditions", []),
                        "steps": c.get("steps", []), "skill_ids": []}

        from memory_facets import enrich_metadata_with_facets
        metadata = await enrich_metadata_with_facets(metadata or None, name, content, summary)

        auto_activate = config.get("skill_auto_activate", False) if target == "skill" else config.get("playbook_auto_activate", False)
        status = "active" if auto_activate else "draft"
        quality = compute_quality_score(0.1, 0.0, conf, 0, 0.0)
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
            quality_score=quality,
            status=status,
            metadata=metadata,
        )
        created += 1
        logger.info(f"Telemetry reflection created {target} '{name}' [{status}] for {entity_type}/{entity_id}")

    _mark_reflected(entity_type, entity_id, day, created)
    log_pipeline_run("telemetry_reflection", "created" if created else "skipped",
                     reason_code=None if created else "no_reusable_learning",
                     records_created=created,
                     detail={"entity_type": entity_type, "entity_id": entity_id, "day": day,
                             "telemetry_events": len(telemetry)})
    return created


def _mark_reflected(entity_type: str, entity_id: str, day: str, produced: int) -> None:
    """Record that (entity, day) was reflected on — idempotency guard."""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO telemetry_reflection_log (entity_type, entity_id, reflection_date, candidates_created, reflected_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (entity_type, entity_id, reflection_date) DO UPDATE
                    SET candidates_created = EXCLUDED.candidates_created, reflected_at = NOW()
            """, (entity_type, entity_id, day, produced))
    except Exception as e:
        logger.warning(f"_mark_reflected failed for {entity_type}/{entity_id}/{day}: {e}")


async def backfill_telemetry(max_days: int = 30) -> dict:
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
