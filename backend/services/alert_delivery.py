"""TASK-260 — outbound alert delivery.

memory_system_alerts and failed memory_pipeline_runs are DB rows no human
is ever notified about (poll-only surfaces). This poller — driven by the
scheduler's 60s background loop — POSTs undelivered alerts to
ALERT_WEBHOOK_URL (an n8n webhook, which routes by severity: error →
immediate ping, warning → digest) and marks delivered_at on success only,
so a dead webhook loses nothing (delivery retries on the next tick).

Windowing: one POST per alert code per ALERT_DELIVERY_WINDOW_SECONDS
(default 900), keyed on the alert's own delivered_at — an alert that keeps
re-firing (last_seen_at bumping) re-sends at most once per window, so a
dead loop must not become a webhook storm. Kill-switch: the
alerts_delivery_enabled memory setting (default on).
"""
from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

DELIVERY_TIMEOUT_SECONDS = 10.0
_FAILURES_WATERMARK = "pipeline_run_failures"


def _webhook_url() -> str:
    return (os.getenv("ALERT_WEBHOOK_URL") or "").strip()


def _window_seconds() -> int:
    try:
        return max(60, int(os.getenv("ALERT_DELIVERY_WINDOW_SECONDS", "900")))
    except (TypeError, ValueError):
        return 900


def _delivery_enabled() -> bool:
    try:
        from core.storage import get_memory_db_context

        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT alerts_delivery_enabled FROM memory_settings WHERE id = 1")
            row = cursor.fetchone()
            return bool(row["alerts_delivery_enabled"]) if row else True
    except Exception as exc:
        logger.warning("Could not read alerts_delivery_enabled (defaulting on): %s", exc)
        return True


def scan_pipeline_failures() -> None:
    """Upsert ONE aggregated alert for new failed pipeline runs.

    Watermarked on memory_pipeline_runs.seq_id (monotonic). The first boot
    sets the baseline without alerting on history; every later batch of new
    failures bumps last_seen_at, which is the re-delivery signal."""
    from core.storage import get_memory_db_context

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT last_seen_id FROM alert_delivery_state WHERE watermark = %s",
            (_FAILURES_WATERMARK,),
        )
        row = cursor.fetchone()
        if not row or row["last_seen_id"] is None:
            cursor.execute("SELECT COALESCE(MAX(seq_id), 0) AS seq FROM memory_pipeline_runs")
            baseline = str(cursor.fetchone()["seq"])
            cursor.execute(
                """
                INSERT INTO alert_delivery_state (watermark, last_seen_id, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (watermark) DO UPDATE
                    SET last_seen_id=EXCLUDED.last_seen_id, updated_at=NOW()
                """,
                (_FAILURES_WATERMARK, baseline),
            )
            logger.info("Pipeline-failure watcher baseline set at seq_id=%s", baseline)
            return

        try:
            since = int(row["last_seen_id"])
        except (TypeError, ValueError):
            return
        cursor.execute(
            """
            SELECT seq_id, job, reason_code, created_at
            FROM memory_pipeline_runs
            WHERE status='failed' AND seq_id > %s
            ORDER BY seq_id
            LIMIT 200
            """,
            (since,),
        )
        failures = [dict(r) for r in cursor.fetchall()]
        if not failures:
            return

        last_seq = str(failures[-1]["seq_id"])
        jobs = sorted({f["job"] for f in failures})
        recent = [
            {"job": f["job"], "reason_code": f.get("reason_code"),
             "at": f["created_at"].isoformat() if f.get("created_at") else None}
            for f in failures[-10:]
        ]
        message = (
            f"{len(failures)} failed pipeline run(s): {', '.join(jobs)}"
            if len(failures) <= 5 else
            f"{len(failures)} failed pipeline run(s) across {len(jobs)} jobs "
            f"(latest: {', '.join(jobs[:5])}{'…' if len(jobs) > 5 else ''})"
        )
        cursor.execute(
            """
            INSERT INTO memory_system_alerts
                (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
            VALUES ('pipeline_run_failed', 'error',
                    'Memory pipeline run failed', %s, 'alert_delivery',
                    %s::jsonb, TRUE, NOW(), NOW())
            ON CONFLICT (code) DO UPDATE SET
                active=TRUE, message=EXCLUDED.message, detail=EXCLUDED.detail,
                last_seen_at=NOW()
            """,
            (message, json.dumps({"count": len(failures), "last_seq_id": last_seq,
                                  "jobs": jobs, "recent": recent})),
        )
        cursor.execute(
            """
            INSERT INTO alert_delivery_state (watermark, last_seen_id, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (watermark) DO UPDATE
                SET last_seen_id=EXCLUDED.last_seen_id, updated_at=NOW()
            """,
            (_FAILURES_WATERMARK, last_seq),
        )
        logger.warning("Recorded %d failed pipeline run(s) as alert", len(failures))


def deliver_pending_alerts() -> int:
    """POST undelivered active alerts to the webhook; stamp delivered_at
    on success only. Returns the number delivered."""
    url = _webhook_url()
    if not url:
        return 0
    if not _delivery_enabled():
        return 0

    from core.storage import get_memory_db_context

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT code, severity, title, message, source, detail,
                   first_seen_at, last_seen_at
            FROM memory_system_alerts
            WHERE active=TRUE
              AND (delivered_at IS NULL OR delivered_at < last_seen_at)
              AND (delivered_at IS NULL
                   OR delivered_at <= NOW() - (%s * INTERVAL '1 second'))
            ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END, last_seen_at
            LIMIT 20
            """,
            (_window_seconds(),),
        )
        pending = [dict(r) for r in cursor.fetchall()]

    delivered = 0
    for alert in pending:
        payload = {
            "service": "masteragent",
            "code": alert["code"],
            "severity": alert["severity"],
            "title": alert["title"],
            "message": alert["message"],
            "source": alert["source"],
            "detail": alert["detail"] or {},
            "first_seen_at": alert["first_seen_at"].isoformat() if alert["first_seen_at"] else None,
            "last_seen_at": alert["last_seen_at"].isoformat() if alert["last_seen_at"] else None,
        }
        try:
            response = httpx.post(url, json=payload, timeout=DELIVERY_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning("Alert delivery to webhook failed for %s: %s", alert["code"], exc)
            break  # webhook unreachable — retry the whole batch next tick
        if 200 <= response.status_code < 300:
            delivered += 1
            try:
                from core.storage import get_memory_db_context

                with get_memory_db_context() as conn:
                    conn.cursor().execute(
                        "UPDATE memory_system_alerts SET delivered_at=NOW() WHERE code=%s",
                        (alert["code"],),
                    )
            except Exception as exc:
                logger.warning("Could not stamp delivered_at for %s: %s", alert["code"], exc)
        else:
            logger.warning(
                "Alert delivery webhook returned %s for %s — will retry",
                response.status_code, alert["code"],
            )
            break  # don't burn the window on a misbehaving receiver
    if delivered:
        logger.info("Delivered %d alert(s) to webhook", delivered)
    return delivered


def poll_alert_delivery() -> None:
    """One scheduler tick: scan for new failures, then deliver. Never raises."""
    try:
        scan_pipeline_failures()
    except Exception as exc:
        logger.warning("Pipeline-failure scan failed: %s", exc)
    try:
        deliver_pending_alerts()
    except Exception as exc:
        logger.warning("Alert delivery pass failed: %s", exc)
