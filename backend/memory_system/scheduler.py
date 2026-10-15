"""
memory_system/scheduler.py â the 60-second background tier scheduler

Wakes every 60s and fires the scheduled producers (memory generation,
intelligence sweep, knowledge generation, telemetry reflection,
consolidation, interaction retention) through the BullMQ queues, using
per-day claims in memory_job_log so each tier runs at most once a day.
Companion: memory/queue.py, the worker that executes the enqueued jobs.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from services import get_memory_settings
from memory_system.distill.generation import (
    claim_job_date,
    complete_job_date,
    fail_job_date,
    get_job_last_date,
    run_daily_memory_generation,
    run_orphan_sweeper,
)

logger = logging.getLogger(__name__)

# ── Background task loop control ─────────────────────────────────────────────
_task_handle: Optional[asyncio.Task] = None
_scheduler_last_tick: Optional[datetime] = None


def scheduler_last_tick() -> Optional[datetime]:
    """UTC time of the background loop's most recent iteration top — the
    freshness signal /api/health checks (a dead loop stops ticking)."""
    return _scheduler_last_tick


def _loop_done_callback(task: asyncio.Task) -> None:
    """The scheduler loop exited — surface it loudly (log + sticky alert row);
    without this a dead loop stays invisible until tiers silently stop firing."""
    reason = "cancelled"
    try:
        exc = task.exception()
        if exc is not None:
            reason = f"{type(exc).__name__}: {exc}"
    except asyncio.CancelledError:
        pass
    logger.critical(
        f"Memory background scheduler loop DIED ({reason}) — scheduled "
        f"memory/intelligence/knowledge runs stopped until restart"
    )
    try:
        from core.storage import get_memory_db_context
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_system_alerts
                    (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
                VALUES ('scheduler_loop_dead', 'critical', 'Memory scheduler loop died', %s,
                        'memory_system.scheduler', %s::jsonb, TRUE, NOW(), NOW())
                ON CONFLICT (code) DO UPDATE SET active=TRUE, message=EXCLUDED.message,
                    detail=EXCLUDED.detail, last_seen_at=NOW()
            """, (f"Background scheduler loop exited ({reason}); nightly tiers will not fire until restart.",
                  json.dumps({"reason": reason})))
    except Exception as exc:
        logger.critical(f"Failed to persist scheduler-death alert: {exc}")


async def start_background_tasks():
    """Start the background task loop. Called once during app startup (lifespan)."""
    global _task_handle
    if _task_handle and not _task_handle.done():
        logger.warning("Background tasks already running")
        return
    _task_handle = asyncio.create_task(_background_loop())
    _task_handle.add_done_callback(_loop_done_callback)
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


def _parse_hhmm(value: str, default=(2, 0)):
    try:
        h, m = map(int, str(value).split(":"))
        return h, m
    except Exception:
        return default


def _time_reached(now_utc: datetime, hhmm: str, default=(2, 0)) -> bool:
    """True if the configured HH:MM has been reached for today (UTC)."""
    sched_h, sched_m = _parse_hhmm(hhmm, default)
    return now_utc.hour > sched_h or (now_utc.hour == sched_h and now_utc.minute >= sched_m)


async def _background_loop():
    """Per-tier schedule-aware background loop.

    Wakes every 60s. Memory and Intelligence keep their tier schedules. All
    Knowledge producers share one global schedule and one idempotency claim:

      memory_generation_time      (default 02:00) → memories + intra-day intel trigger
      intelligence_generation_time(default 02:30) → intelligence schedule sweep (floor)
      knowledge_generation_time   (default 03:00) → all enabled Knowledge pathways
      interaction retention       (02:00 window) → raw-tier age cutoff (Tier 0 hygiene)

    Threshold valves still fire intra-day (independent of this loop). Consolidation
    stays a periodic (weekly) maintenance job — pruning, not learning.

    Scheduled claims ride the job payload (job_claim) and the queue runner
    completes them after the work — completing at enqueue let a job lost between
    enqueue and pickup silently skip the day."""
    global _scheduler_last_tick
    while True:
        _scheduler_last_tick = datetime.now(timezone.utc)
        try:
            settings = get_memory_settings() or {}
            now_utc = datetime.now(timezone.utc)
            today = now_utc.date()
            from memory.queue import interactions_queue, job_options, knowledge_queue

            # ── Tier 0→1: Memory generation (true nightly flush) ──────────────
            if _time_reached(now_utc, settings.get("memory_generation_time", "02:00"), (2, 0)):
                if claim_job_date("daily_memory_generation", today):
                    logger.info("Firing daily memory generation")
                    try:
                        await run_orphan_sweeper()
                        await run_daily_memory_generation()
                        complete_job_date("daily_memory_generation", today)
                    except Exception as exc:
                        fail_job_date("daily_memory_generation", today, exc)
                        raise
                    # run_daily_memory_generation → per-entity memory jobs →
                    # _check_compaction_trigger (intra-day intelligence threshold valve)

            # ── Tier 1→2: Intelligence SCHEDULE sweep (floor) ─────────────────
            if settings.get("intelligence_schedule_enabled", True) and \
               _time_reached(now_utc, settings.get("intelligence_generation_time", "02:30"), (2, 30)):
                if claim_job_date("intelligence_schedule", today):
                    floor = int(settings.get("intelligence_schedule_floor", 2))
                    logger.info(f"Firing nightly intelligence sweep (floor={floor})")
                    try:
                        await knowledge_queue.add(
                            "run_intelligence_sweep",
                            {"min_count": floor,
                             "job_claim": {"name": "intelligence_schedule", "date": today.isoformat()}},
                            job_options("run_intelligence_sweep", priority=3))
                    except Exception as exc:
                        fail_job_date("intelligence_schedule", today, exc)
                        raise

            # ── Tier 2→3: one schedule for every Knowledge producer ──────────
            if settings.get("knowledge_schedule_enabled", True) and \
               _time_reached(now_utc, settings.get("knowledge_generation_time", "03:00"), (3, 0)):
                if claim_job_date("knowledge_generation_all", today):
                    floor = int(settings.get("knowledge_schedule_floor", 2))
                    logger.info(f"Firing nightly knowledge sweep (floor={floor})")
                    try:
                        await knowledge_queue.add(
                            "run_all_knowledge_generation",
                            {"min_count": floor,
                             "job_claim": {"name": "knowledge_generation_all", "date": today.isoformat()}},
                            job_options("run_all_knowledge_generation", priority=3))
                    except Exception as exc:
                        fail_job_date("knowledge_generation_all", today, exc)
                        raise

            # ── Telemetry reflection: daily at telemetry_reflection_time ─────
            # The worker handles `reflect_telemetry` but nothing scheduled it —
            # these settings advertised a time no code consumed, so the pathway
            # only ever ran via the manual admin trigger (last: 2026-07-12).
            # Wired here with the same claim-ledger idiom as the sweep above.
            if settings.get("telemetry_reflection_enabled", True) and \
               _time_reached(now_utc, settings.get("telemetry_reflection_time", "04:00"), (4, 0)):
                if claim_job_date("telemetry_reflection_schedule", today):
                    logger.info("Firing nightly telemetry reflection")
                    try:
                        await knowledge_queue.add(
                            "reflect_telemetry",
                            {"job_claim": {"name": "telemetry_reflection_schedule",
                                           "date": today.isoformat()}},
                            job_options("reflect_telemetry", priority=3))
                    except Exception as exc:
                        fail_job_date("telemetry_reflection_schedule", today, exc)
                        raise

            # ── Consolidation: periodic maintenance (weekly, not nightly) ─────
            consolidation_interval = settings.get("consolidation_run_interval_days", 7)
            last_consol = get_job_last_date("consolidation")
            days_since_consol = (today - last_consol).days if last_consol else consolidation_interval
            if _time_reached(now_utc, settings.get("memory_generation_time", "02:00"), (2, 0)) and \
               days_since_consol >= consolidation_interval and claim_job_date("consolidation", today):
                logger.info(f"Triggering consolidation (days_since={days_since_consol})")
                try:
                    await knowledge_queue.add(
                        "run_consolidation",
                        {"job_claim": {"name": "consolidation", "date": today.isoformat()}},
                        job_options("run_consolidation", priority=4))
                except Exception as exc:
                    fail_job_date("consolidation", today, exc)
                    raise

            # ── Tier 0 hygiene: raw interaction retention (daily) ─────────────
            # Age-qualified cleanup of the raw interactions tier. Nothing else
            # in the codebase schedules this — without it the table grows
            # unbounded (the 16 GB incident). Days<=0 disables the schedule.
            retention_days = int(settings.get("interaction_retention_days", 30) or 0)
            if retention_days > 0 and \
               _time_reached(now_utc, settings.get("memory_generation_time", "02:00"), (2, 0)) and \
               claim_job_date("interaction_retention", today):
                logger.info(f"Firing daily interaction retention (days={retention_days})")
                try:
                    await interactions_queue.add(
                        "interaction_retention",
                        {"batch_size": 500, "max_records": 50000,
                         "job_claim": {"name": "interaction_retention", "date": today.isoformat()}},
                        job_options("interaction_retention", priority=5),
                    )
                except Exception as exc:
                    fail_job_date("interaction_retention", today, exc)
                    raise

        except Exception as e:
            logger.error(f"Background loop error: {e}", exc_info=True)

        await asyncio.sleep(60)
