"""Knowledge learning loop — outcome attribution (docs/plans/knowledge-learning-loop.md §3).

Closes the learn-half of the knowledge tier: usage events captured at
retrieval time (memory/agent.py → record_knowledge_usage) are resolved in
batch against downstream signals that already exist — no online judge, no
ground-truth requirement:

  1. failure  — a lessons_learned record became active whose evidence traces
     to the same entity within the negative window, overlapping the retrieved
     record by shared signal or embedding similarity (the "the record we
     served was wrong" echo).
  2. success  — the same record was retrieved again for the same entity after
     the recurrence window with no failure signal in between (weak but
     directionally safe; the Laplace prior absorbs the noise).
  3. no_signal — the event is marked attributed so it is never rescanned.

Every outcome lands on the event row itself (the table IS the ledger), bumps
the knowledge counters, and re-runs recalculate_knowledge_quality. Skills
crossing knowledge_learning_refine_min_failures raise a refinement PROPOSAL
alert — proposal-only, per the DEC-091 doctrine (no live patching).
"""
import logging
from collections import Counter

from core.storage import get_memory_db_context
from services.config_helpers import get_memory_settings
from services.prompt_safety import emit_safety_alert

logger = logging.getLogger(__name__)


def _negative_echo_hit(cursor, *, knowledge_id, entity_id, start, window_days, min_sim) -> bool:
    """True when a lessons_learned record contradicting K became active in
    [start, start + window_days] with evidence tracing to the same entity and
    overlapping K by shared signal or embedding similarity (§3 signal 2)."""
    cursor.execute(
        """
        SELECT l.id
        FROM knowledge l
        JOIN knowledge k ON k.id = %s
        WHERE l.category = 'lessons_learned'
          AND l.status = 'active'
          AND l.created_at >= %s
          AND l.created_at <= %s + make_interval(days => %s)
          AND EXISTS (
                SELECT 1 FROM intelligence i
                WHERE i.id = ANY(l.source_intelligence_ids)
                  AND i.primary_entity_id = %s
                  AND i.created_at >= %s
                  AND i.created_at <= %s + make_interval(days => %s)
          )
          AND (
                (k.signals IS NOT NULL AND l.signals && k.signals)
                OR (
                    k.embedding IS NOT NULL AND l.embedding IS NOT NULL
                    AND (1 - (l.embedding <=> k.embedding)) >= %s
                )
          )
        LIMIT 1
        """,
        (knowledge_id, start, start, window_days, entity_id, start, start, window_days, min_sim),
    )
    return cursor.fetchone() is not None


def run_outcome_attribution(*, trigger: str = "scheduled", batch_size: int = 1000) -> dict:
    """Resolve unattributed usage events into outcomes. Sync (plain SQL) —
    callers wrap in asyncio.to_thread per the 504 doctrine. Idempotent:
    `attributed_at IS NULL` is the cursor, so re-runs resume rather than
    repeat, and the per-day job claim keeps the schedule single-shot."""
    settings = get_memory_settings() or {}
    if not settings.get("knowledge_learning_attribution_enabled", True):
        return {"status": "disabled", "trigger": trigger, "events_seen": 0}

    min_age_hours = int(settings.get("knowledge_learning_min_signal_age_hours", 6) or 6)
    window_days = int(settings.get("knowledge_learning_negative_window_days", 7) or 7)
    min_sim = float(settings.get("knowledge_learning_negative_similarity", 0.80) or 0.80)
    refine_min = int(settings.get("knowledge_learning_refine_min_failures", 2) or 2)
    recurrence_days = 7  # §3 signal 3 / §11.2 — revisit after phase-0 data

    outcomes: Counter = Counter()
    touched: dict = {}  # knowledge_id -> {"success": n, "failure": n}

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, knowledge_id, entity_id, created_at
            FROM knowledge_usage_events
            WHERE attributed_at IS NULL
              AND created_at <= NOW() - make_interval(hours => %s)
            ORDER BY created_at
            LIMIT %s
            """,
            (min_age_hours, batch_size),
        )
        events = cursor.fetchall()
        events_seen = len(events)

        for ev in events:
            knowledge_id = ev["knowledge_id"]
            entity_id = ev["entity_id"]

            # Positive-recurrence probe: a later retrieval of the same record
            # for the same entity beyond the recurrence window.
            later = None
            if entity_id:
                cursor.execute(
                    """
                    SELECT created_at FROM knowledge_usage_events
                    WHERE knowledge_id = %s AND entity_id = %s AND id <> %s
                      AND created_at >= %s + make_interval(days => %s)
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    (knowledge_id, entity_id, ev["id"], ev["created_at"], recurrence_days),
                )
                later = cursor.fetchone()

            # Negative echo probe — needs an entity to trace evidence to.
            failure = False
            if entity_id:
                failure = _negative_echo_hit(
                    cursor, knowledge_id=knowledge_id, entity_id=entity_id,
                    start=ev["created_at"], window_days=window_days, min_sim=min_sim,
                )

            if failure:
                outcome = "failure"
            elif later:
                outcome = "success"
            else:
                outcome = "no_signal"

            cursor.execute(
                "UPDATE knowledge_usage_events SET outcome = %s, attributed_at = NOW() WHERE id = %s",
                (outcome, ev["id"]),
            )
            outcomes[outcome] += 1
            if outcome in ("success", "failure"):
                counters = touched.setdefault(knowledge_id, {"success": 0, "failure": 0})
                counters[outcome] += 1

        # Counter bumps per touched record — deltas only, so manual feedback
        # (which increments the same counters) composes instead of colliding.
        for knowledge_id, counters in touched.items():
            cursor.execute(
                """
                UPDATE knowledge
                SET success_count = COALESCE(success_count, 0) + %s,
                    failure_count = COALESCE(failure_count, 0) + %s
                WHERE id = %s
                """,
                (counters["success"], counters["failure"], knowledge_id),
            )

    # Quality recompute opens its own connection (writes.py idiom).
    from memory_system.maintain.quality import recalculate_knowledge_quality
    for knowledge_id in touched:
        try:
            recalculate_knowledge_quality(knowledge_id)
        except Exception as exc:
            logger.warning(f"outcome attribution: quality recompute failed for {knowledge_id}: {exc}")

    # §4.3 — skill refinement PROPOSALS. emit_safety_alert upserts on code, so
    # the per-skill code doubles as the dedup key: the alert re-arms only when
    # a NEW failure lands on an already-flagged skill.
    alerted = 0
    if outcomes.get("failure"):
        try:
            with get_memory_db_context() as conn:
                cursor = conn.cursor()
                for knowledge_id, counters in touched.items():
                    if not counters.get("failure"):
                        continue
                    cursor.execute(
                        """
                        SELECT id, name, COALESCE(failure_count, 0) AS failures
                        FROM knowledge
                        WHERE id = %s AND category = 'skill' AND status = 'active'
                        """,
                        (knowledge_id,),
                    )
                    row = cursor.fetchone()
                    if not row or row["failures"] < refine_min:
                        continue
                    emit_safety_alert(
                        cursor,
                        code=f"skill_refinement_proposed:{row['id']}",
                        title="Skill refinement proposed",
                        message=(
                            f"Skill '{row['name']}' has {row['failures']} attributed "
                            f"failures contradicted by a lessons_learned record — "
                            f"review and revise its trigger/procedure (proposal only)."
                        ),
                        detail={
                            "knowledge_id": row["id"], "knowledge_name": row["name"],
                            "failures": row["failures"],
                            "proposal_type": "skill_refinement",
                        },
                        severity="warning",
                    )
                    alerted += 1
        except Exception as exc:
            logger.warning(f"outcome attribution: refinement alert pass failed: {exc}")

    from memory_system.store.writes import log_pipeline_run
    log_pipeline_run(
        "knowledge_outcome_attribution",
        "success",
        records_created=sum(outcomes.values()),
        detail={"outcomes": dict(outcomes), "skills_flagged": alerted, "batch_size": batch_size},
        trigger=trigger,
    )

    return {
        "status": "ok", "trigger": trigger, "events_seen": events_seen,
        "attributed": sum(outcomes.values()), "outcomes": dict(outcomes),
        "skills_flagged": alerted,
    }
