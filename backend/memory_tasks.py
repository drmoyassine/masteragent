"""
memory_tasks.py — Background task loop for the Memory System

Thin shell that re-exports all public symbols from extracted modules.
Downstream importers (server.py, memory.agent, memory.admin, memory.queue,
test_memory.py) import from this module — no changes needed on their side.

Modules:
  memory_rate_limit    — per-agent rate limiting
  memory_helpers       — entity type config, NER formatting, signal definitions
  memory_ingestion     — process_interaction + entity profile sync
  memory_generation    — daily memory generation pipeline + job log helpers
  memory_compaction    — intelligence extraction (memories → intelligence)
  memory_knowledge     — knowledge generation (intelligence → knowledge)
  memory_db_writes     — INSERT helpers (memories, intelligence, knowledge)
  memory_prior_context — prior-context fetchers (chrono + semantic)
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from memory_services import get_memory_settings
from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)

# ── Rate limiting ─────────────────────────────────────────────────────────────
from memory_rate_limit import check_rate_limit, _rate_limit_counters  # noqa: F401, E402

# ── Helpers ───────────────────────────────────────────────────────────────────
from memory_helpers import (  # noqa: E402, F401
    _get_entity_type_config,
    _format_signal_definitions,
    _format_ner_output,
    _build_ner_text_payload,
)

# ── Ingestion ─────────────────────────────────────────────────────────────────
from memory_ingestion import process_interaction  # noqa: E402, F401

# ── Generation ────────────────────────────────────────────────────────────────
from memory_generation import (  # noqa: E402, F401
    get_job_last_date,
    set_job_last_date,
    run_orphan_sweeper,
    run_daily_memory_generation,
    _generate_memory_for_entity,
    _execute_pipeline_node,
)

# ── Compaction ────────────────────────────────────────────────────────────────
from memory_compaction import (  # noqa: E402, F401
    run_compaction_check,
    _check_compaction_trigger,
    compact_entity,
)

# ── Knowledge ─────────────────────────────────────────────────────────────────
from memory_knowledge import (  # noqa: E402, F401
    run_knowledge_check,
    generate_knowledge_from_intelligence,
    promote_to_knowledge,
)

# ── Prior context (backward-compat alias) ─────────────────────────────────────
from memory_prior_context import fetch_prior_memories  # noqa: E402, F401
_fetch_prior_context = fetch_prior_memories


# ── Background task loop control ─────────────────────────────────────────────
_task_handle: Optional[asyncio.Task] = None


async def start_background_tasks():
    """Start the background task loop. Called once during app startup (lifespan)."""
    global _task_handle
    if _task_handle and not _task_handle.done():
        logger.warning("Background tasks already running")
        return
    _task_handle = asyncio.create_task(_background_loop())
    logger.info("Memory system background tasks started")


async def stop_background_tasks():
    """Cancel the background task loop. Called during app shutdown."""
    global _task_handle
    if _task_handle and not _task_handle.done():
        _task_handle.cancel()
        try:
            await _task_handle
        except asyncio.CancelledError:
            pass
    logger.info("Memory system background tasks stopped")


async def _background_loop():
    """Schedule-aware main background loop.
    Wakes every 60 seconds and checks:
      - Has the configured memory_generation_time passed today?
      - Has the daily memory job already run today?
    Fires once per day at the configured time."""
    while True:
        try:
            settings = get_memory_settings()
            scheduled_time = settings.get("memory_generation_time", "02:00")
            try:
                sched_h, sched_m = map(int, scheduled_time.split(":"))
            except Exception:
                sched_h, sched_m = 2, 0

            now_utc = datetime.now(timezone.utc)
            today = now_utc.date()

            if now_utc.hour > sched_h or (now_utc.hour == sched_h and now_utc.minute >= sched_m):
                last_date = get_job_last_date("daily_memory_generation")
                if last_date != today:
                    logger.info(f"Firing daily memory generation (scheduled={scheduled_time} UTC)")
                    set_job_last_date("daily_memory_generation", today)
                    await run_orphan_sweeper()
                    await run_daily_memory_generation()
                    await run_compaction_check()

                    from memory.queue import knowledge_queue
                    await knowledge_queue.add("generate_knowledge", {}, {"priority": 3})

                    # ── Playbook extraction: weekly + evidence-threshold override ──
                    pb_interval = settings.get("playbook_extraction_interval_days", 7)
                    pb_evidence = settings.get("playbook_extraction_evidence_threshold", 20)
                    last_pb = get_job_last_date("playbook_extraction")
                    days_since_pb = (today - last_pb).days if last_pb else pb_interval

                    # Count unlinked intelligence
                    unlinked_count = 0
                    try:
                        with get_memory_db_context() as conn:
                            cur = conn.cursor()
                            cur.execute("""
                                SELECT COUNT(*) as cnt FROM intelligence i
                                WHERE i.status = 'confirmed' AND i.embedding IS NOT NULL
                                  AND NOT EXISTS (
                                      SELECT 1 FROM knowledge k
                                      WHERE k.category = 'playbook'
                                        AND i.id = ANY(k.source_intelligence_ids)
                                  )
                            """)
                            unlinked_count = cur.fetchone()["cnt"]
                    except Exception:
                        pass

                    if days_since_pb >= pb_interval or unlinked_count >= pb_evidence:
                        logger.info(f"Triggering playbook extraction (days_since={days_since_pb}, unlinked={unlinked_count})")
                        set_job_last_date("playbook_extraction", today)
                        await knowledge_queue.add("extract_playbooks", {}, {"priority": 2})

                    # ── Consolidation: periodic dedup + decay + quality recompute ──
                    consolidation_interval = settings.get("consolidation_run_interval_days", 7)
                    last_consol = get_job_last_date("consolidation")
                    days_since_consol = (today - last_consol).days if last_consol else consolidation_interval
                    if days_since_consol >= consolidation_interval:
                        logger.info(f"Triggering consolidation (days_since={days_since_consol})")
                        set_job_last_date("consolidation", today)
                        await knowledge_queue.add("run_consolidation", {}, {"priority": 4})

        except Exception as e:
            logger.error(f"Background loop error: {e}", exc_info=True)

        await asyncio.sleep(60)
