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
    run_lesson_check,
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
                    await knowledge_queue.add("generate_lesson", {}, {"priority": 3})

        except Exception as e:
            logger.error(f"Background loop error: {e}", exc_info=True)

        await asyncio.sleep(60)
