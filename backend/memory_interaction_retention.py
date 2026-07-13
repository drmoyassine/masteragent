"""Bounded cleanup of raw interactions after their processing outcome is known."""
from datetime import datetime, timezone, timedelta
import logging

from core.storage import get_memory_db_context
from memory_services import get_memory_settings
from memory_db_writes import log_pipeline_run

logger = logging.getLogger(__name__)
TELEMETRY_TYPES = ("internal_ai_thought", "internal_ai_tool_call")
TERMINAL_TELEMETRY_OUTCOMES = ("knowledge_created", "no_meaningful_knowledge", "already_covered", "no_telemetry")


def run_interaction_retention(*, batch_size: int = 500, max_records: int = 5000,
                              progress_run_id: str | None = None) -> dict:
    """Delete age-qualified interactions in bounded batches.

    By default normal interactions require status=done and telemetry requires a
    successful reflection-log terminal outcome. Failed/unfinished telemetry is
    retained for retry or investigation.
    """
    settings = get_memory_settings() or {}
    days = max(1, int(settings.get("interaction_retention_days", 30) or 30))
    retain = bool(settings.get("interaction_retain_until_processed", True))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    batch_size = max(1, min(int(batch_size), 5000))
    max_records = max(1, min(int(max_records), 1000000))
    processed = 0
    while processed < max_records:
        limit = min(batch_size, max_records - processed)
        completion = """
            AND (
              (i.interaction_type = ANY(%s) AND EXISTS (
                SELECT 1 FROM telemetry_reflection_log l
                WHERE l.entity_type = i.primary_entity_type
                  AND l.entity_id = i.primary_entity_id
                  AND l.reflection_date = DATE(i.timestamp)
                  AND l.outcome = ANY(%s)
              ))
              OR (i.interaction_type <> ALL(%s) AND i.status = 'done')
            )
        """ if retain else ""
        params = [cutoff]
        if retain:
            params.extend([list(TELEMETRY_TYPES), list(TERMINAL_TELEMETRY_OUTCOMES), list(TELEMETRY_TYPES)])
        params.append(limit)
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                WITH eligible AS (
                    SELECT i.id FROM interactions i
                    WHERE i.timestamp < %s {completion}
                    ORDER BY i.timestamp, i.id LIMIT %s
                )
                DELETE FROM interactions i USING eligible e
                WHERE i.id = e.id RETURNING i.id
            """, params)
            deleted = cursor.fetchall()
        count = len(deleted or [])
        processed += count
        if count < limit:
            break
    result = {"processed": processed, "deleted": processed, "retention_days": days,
              "retain_until_processed": retain, "cutoff": cutoff.isoformat()}
    log_pipeline_run("interaction_retention", "completed", records_created=processed,
                     detail=result, trigger="manual")
    logger.info("Interaction retention complete: %s", result)
    return result
