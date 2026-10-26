"""Consolidation, decay, and quality score recomputation for unified knowledge.

Runs periodically (configurable interval) to:
1. Merge semantically similar knowledge records
2. Retire stale records based on decay gauges
3. Recompute quality scores for all active records
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from core.storage import get_memory_db_context
from services import get_memory_settings
from memory_system.store.helpers import _get_entity_type_config

logger = logging.getLogger(__name__)


async def run_consolidation(*, max_records: int = 20000, max_clusters: int = 100,
                            progress_run_id: Optional[str] = None):
    """Run hygiene + decay + quality maintenance.

    The destructive pairwise retirement loop is GONE. Candidate discovery and
    consolidation proposals now go through the shared hygiene service
    (``memory_system.maintain.consolidation_service.discover_and_propose``), which respects the
    configured mode and never applies unless policy gates pass. Decay and
    quality-score recompute remain as non-destructive maintenance.
    """
    settings = get_memory_settings()
    logger.info("Starting consolidation run (hygiene mode)")

    # Knowledge hygiene discovery + proposals (mode-gated; manual_only never applies).
    hygiene_error = None
    if settings.get("knowledge_hygiene_enabled", True):
        try:
            from memory_system.maintain.consolidation_service import discover_and_propose
            mode = settings.get("knowledge_hygiene_mode", "manual_only")
            await discover_and_propose(
                origin="scheduled", mode=mode,
                auto_apply=mode in ("auto_conservative", "auto_synthesis"),
                max_records=max_records, max_clusters=max_clusters,
                progress_run_id=progress_run_id,
            )
        except Exception as exc:
            hygiene_error = exc
            logger.exception("Hygiene discovery failed during consolidation run")

    _apply_decay()
    _recompute_quality_scores()
    if hygiene_error is not None:
        # Let the queue retry/DLQ policy observe the failure instead of silently
        # reporting a successful scheduled run. Maintenance above remains safe
        # and idempotent if the job is retried.
        raise hygiene_error
    logger.info("Consolidation run complete")


# Legacy pairwise retirement removed — see run_consolidation above. The shared
# hygiene service is the single consolidation path (preview + transactional apply).
async def _consolidate_duplicates(threshold: float):  # pragma: no cover - legacy shim
    """Deprecated: retained only as a no-op shim for any stale callers."""
    logger.warning("_consolidate_duplicates is deprecated; hygiene service handles consolidation")
    return


def _apply_decay():
    """Retire stale knowledge records based on configurable decay gauges."""
    now = datetime.now(timezone.utc)

    # Get all entity types with their decay configs
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT entity_type FROM memory_entity_type_config")
        entity_types = [r["entity_type"] for r in cursor.fetchall()]

    retired = 0
    for entity_type in entity_types:
        config = _get_entity_type_config(entity_type)
        max_inactive_days = config.get("decay_max_inactive_days", 90)
        min_interactions = config.get("decay_min_interactions_since_trigger", 100)

        cutoff = (now - __import__('datetime').timedelta(days=max_inactive_days)).isoformat()

        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            # Retire skill-category records for this entity type that haven't been updated
            cursor.execute("""
                UPDATE knowledge
                SET status = 'retired', updated_at = %s
                WHERE status = 'active'
                  AND category = 'skill'
                  AND metadata->>'entity_type' = %s
                  AND updated_at < %s
            """, (now.isoformat(), entity_type, cutoff))
            retired += cursor.rowcount

    if retired:
        logger.info(f"Decay retired {retired} stale records")


def _recompute_quality_scores():
    """Batch recompute every record with the canonical explainable v2 model."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM knowledge")
        total = int(cursor.fetchone()["n"] or 0)
    from memory_system.maintain.quality import backfill_quality_v2
    updated = 0
    while updated < total:
        result = backfill_quality_v2(limit=500)
        updated += result["updated"]
        if result["processed"] == 0 or result["updated"] == 0:
            break

    if updated:
        logger.info(f"Recomputed quality scores for {updated} active records")
