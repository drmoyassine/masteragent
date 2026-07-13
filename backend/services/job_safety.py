"""Shared provider-stop and job-safety primitives.

Long-running jobs must stop on a provider hard-stop (credits exhausted or rate
limited), not treat it as a per-record error and continue burning requests.
The persistent alert also provides the foundation for the future job log UI.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class ProviderStopError(RuntimeError):
    def __init__(self, code: str, message: str, *, retry_after_seconds: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


def provider_stop_from_response(status_code: int, body: str, retry_after: Optional[str] = None) -> Optional[ProviderStopError]:
    """Classify only provider responses that require the whole job to stop."""
    text = (body or "").lower()
    if status_code == 429 or "rate limit" in text or "ratelimit" in text:
        try:
            seconds = max(1, int(float(retry_after))) if retry_after else 900
        except (TypeError, ValueError):
            seconds = 900
        return ProviderStopError("provider_rate_limited", "AI provider rate limit reached", retry_after_seconds=seconds)
    credit_markers = ("insufficient_quota", "insufficient quota", "credit", "billing", "quota exceeded")
    if status_code in (402, 403) or any(marker in text for marker in credit_markers):
        return ProviderStopError("provider_credits_exhausted", "AI provider credits or quota are exhausted")
    return None


def record_provider_stop(error: ProviderStopError, *, source: str) -> None:
    """Persist an app-wide sticky alert. Failure to record must not mask the stop."""
    try:
        from core.storage import get_memory_db_context
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            if error.code == "provider_rate_limited":
                cursor.execute("""
                    INSERT INTO memory_system_alerts
                        (code, severity, title, message, source, detail, active, expires_at, first_seen_at, last_seen_at)
                    VALUES (%s, 'warning', 'AI provider rate limit reached', %s, %s, %s::jsonb, TRUE,
                            NOW() + (%s * INTERVAL '1 second'), NOW(), NOW())
                    ON CONFLICT (code) DO UPDATE SET active=TRUE, message=EXCLUDED.message,
                        source=EXCLUDED.source, detail=EXCLUDED.detail, expires_at=EXCLUDED.expires_at,
                        last_seen_at=NOW()
                """, (error.code, str(error), source,
                      json.dumps({"retry_after_seconds": error.retry_after_seconds or 900}),
                      error.retry_after_seconds or 900))
            else:
                cursor.execute("""
                    INSERT INTO memory_system_alerts
                        (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
                    VALUES (%s, 'error', 'AI provider credits exhausted', %s, %s, '{}'::jsonb, TRUE, NOW(), NOW())
                    ON CONFLICT (code) DO UPDATE SET active=TRUE, message=EXCLUDED.message,
                        source=EXCLUDED.source, last_seen_at=NOW()
                """, (error.code, str(error), source))
    except Exception as exc:
        logger.warning("Could not persist provider stop alert: %s", exc)


def active_provider_stop() -> Optional[dict]:
    """Return a current provider block and expire elapsed rate-limit alerts."""
    try:
        from core.storage import get_memory_db_context
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            try:
                stale_minutes = max(5, int(os.getenv("MAINTENANCE_LOCK_STALE_MINUTES", "30")))
            except (TypeError, ValueError):
                stale_minutes = 30
            cursor.execute("""
                UPDATE memory_system_alerts SET active=FALSE
                WHERE code='provider_rate_limited' AND active=TRUE
                  AND expires_at IS NOT NULL AND expires_at <= NOW()
            """)
            cursor.execute("""
                SELECT code, title, message, source, detail, expires_at
                FROM memory_system_alerts
                WHERE active=TRUE AND code IN ('provider_rate_limited', 'provider_credits_exhausted')
                ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END, last_seen_at DESC LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as exc:
        logger.warning("Could not read provider stop state: %s", exc)
        return None


def try_acquire_singleton_job(job_name: str) -> bool:
    """Prevent two long-running maintenance jobs of the same type.

    The lease is deliberately long enough for a large production backfill. A
    process crash can be recovered after expiry; normal completion always
    releases it immediately.
    """
    try:
        from core.storage import get_memory_db_context
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_job_locks (job_name, locked_at, expires_at)
                VALUES (%s, NOW(), NOW() + INTERVAL '12 hours')
                ON CONFLICT (job_name) DO UPDATE SET locked_at=NOW(),
                    expires_at=NOW() + INTERVAL '12 hours'
                WHERE memory_job_locks.expires_at <= NOW()
                   OR NOT EXISTS (
                       SELECT 1 FROM memory_pipeline_runs r
                       WHERE r.job = %s
                         AND r.status IN ('started', 'running', 'paused')
                         AND r.updated_at > NOW() - (%s * INTERVAL '1 minute')
                   )
                RETURNING job_name
            """, (job_name, job_name, stale_minutes))
            return cursor.fetchone() is not None
    except Exception as exc:
        # Do not turn observability-table trouble into a production outage.
        logger.warning("Could not acquire maintenance lock for %s: %s", job_name, exc)
        return True


def release_singleton_job(job_name: str) -> None:
    try:
        from core.storage import get_memory_db_context
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_job_locks WHERE job_name=%s", (job_name,))
    except Exception as exc:
        logger.warning("Could not release maintenance lock for %s: %s", job_name, exc)


def renew_singleton_job(job_name: str) -> None:
    """Extend a healthy maintenance lease when its pipeline reports progress."""
    try:
        from core.storage import get_memory_db_context
        with get_memory_db_context() as conn:
            conn.cursor().execute(
                "UPDATE memory_job_locks SET expires_at=NOW() + INTERVAL '12 hours' WHERE job_name=%s",
                (job_name,),
            )
    except Exception as exc:
        logger.warning("Could not renew maintenance lock for %s: %s", job_name, exc)
