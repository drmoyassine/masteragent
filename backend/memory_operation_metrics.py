"""Cheap, persisted eligibility snapshots for Knowledge operations.

Exact eligibility counts can touch the multi-gigabyte interactions table.  They
must never run in a read endpoint or on a UI polling timer.  This module keeps
the last completed values in PostgreSQL and coordinates an explicit background
refresh through the Knowledge queue.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from core.storage import get_memory_db_context


OPERATIONS = {
    "embedding_backfill": "knowledge_embedding_backfill",
    "knowledge_generation": "run_all_knowledge_generation",
    "hygiene_analysis": "knowledge_hygiene_run",
    "facet_backfill": "backfill_facets",
}


def get_snapshot() -> Dict[str, Any]:
    """Return stored metrics only.  This function deliberately performs no counts."""
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT operation_key, eligible_count, status, calculated_at,
                   refresh_started_at, last_error, updated_at
            FROM memory_operation_metrics
            WHERE operation_key = ANY(%s)
        """, (list(OPERATIONS),))
        rows = {row["operation_key"]: dict(row) for row in cur.fetchall()}

    values: Dict[str, Any] = {
        key: (int(rows[key]["eligible_count"]) if rows.get(key, {}).get("eligible_count") is not None else None)
        for key in OPERATIONS
    }
    present = [row for row in rows.values() if row.get("calculated_at")]
    refreshing = any(row.get("status") == "refreshing" for row in rows.values())
    errors = [row.get("last_error") for row in rows.values() if row.get("status") == "error" and row.get("last_error")]
    latest = max((row["calculated_at"] for row in present), default=None)
    oldest = min((row["calculated_at"] for row in present), default=None)
    started = min((row["refresh_started_at"] for row in rows.values() if row.get("status") == "refreshing" and row.get("refresh_started_at")), default=None)
    try:
        stale_minutes = max(5, int(os.getenv("OPERATION_METRICS_STALE_MINUTES", "60")))
    except (TypeError, ValueError):
        stale_minutes = 60
    stale = not oldest or oldest < datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    values.update({
        "status": "refreshing" if refreshing else ("error" if errors else ("ready" if len(present) == len(OPERATIONS) else "unavailable")),
        "available": len(present) == len(OPERATIONS),
        "snapshot_at": oldest.isoformat() if oldest else None,
        "latest_calculated_at": latest.isoformat() if latest else None,
        "refresh_started_at": started.isoformat() if started else None,
        "error": errors[0] if errors else None,
        "stale": stale,
        "stale_after_minutes": stale_minutes,
    })
    return values


def request_refresh() -> bool:
    """Atomically mark a refresh requested; return False for a live duplicate."""
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM memory_operation_metrics
            WHERE status='refreshing'
              AND refresh_started_at > NOW() - INTERVAL '30 minutes'
            LIMIT 1
        """)
        if cur.fetchone():
            return False
        for operation_key in OPERATIONS:
            cur.execute("""
                INSERT INTO memory_operation_metrics
                    (operation_key, status, refresh_started_at, last_error, updated_at)
                VALUES (%s, 'refreshing', NOW(), NULL, NOW())
                ON CONFLICT (operation_key) DO UPDATE SET
                    status='refreshing', refresh_started_at=NOW(),
                    last_error=NULL, updated_at=NOW()
            """, (operation_key,))
    return True


def mark_refresh_error(message: str) -> None:
    safe_message = str(message)[:2000]
    with get_memory_db_context() as conn:
        conn.cursor().execute("""
            UPDATE memory_operation_metrics
            SET status='error', last_error=%s, updated_at=NOW()
            WHERE status='refreshing'
        """, (safe_message,))


def refresh_snapshots() -> Dict[str, Any]:
    """Calculate exact values in a worker and persist each completed result."""
    from memory_operation_service import _eligible_source_count

    results: Dict[str, int] = {}
    try:
        for operation_key, job_name in OPERATIONS.items():
            count = int(_eligible_source_count(job_name))
            results[operation_key] = count
            with get_memory_db_context() as conn:
                conn.cursor().execute("""
                    INSERT INTO memory_operation_metrics
                        (operation_key, eligible_count, status, calculated_at,
                         refresh_started_at, last_error, updated_at)
                    VALUES (%s, %s, 'ready', NOW(), NULL, NULL, NOW())
                    ON CONFLICT (operation_key) DO UPDATE SET
                        eligible_count=EXCLUDED.eligible_count, status='ready',
                        calculated_at=NOW(), refresh_started_at=NULL,
                        last_error=NULL, updated_at=NOW()
                """, (operation_key, count))
        return {**results, "snapshot_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        mark_refresh_error(str(exc))
        raise
