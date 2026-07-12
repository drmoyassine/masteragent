"""Persistent pause/cancel controls for maintenance workers."""
from __future__ import annotations

from typing import Optional

from core.storage import get_memory_db_context


def set_command(job: str, command: str, actor: Optional[str] = None) -> None:
    if command not in {"run", "pause", "cancel"}:
        raise ValueError("invalid maintenance command")
    with get_memory_db_context() as conn:
        conn.cursor().execute(
            """
            INSERT INTO memory_job_controls (job, command, updated_at, updated_by)
            VALUES (%s, %s, NOW(), %s)
            ON CONFLICT (job) DO UPDATE SET command=EXCLUDED.command,
                updated_at=NOW(), updated_by=EXCLUDED.updated_by
            """, (job, command, actor),
        )


def get_command(job: str) -> str:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT command FROM memory_job_controls WHERE job=%s", (job,))
        item = cur.fetchone()
        return (item or {}).get("command", "run") if item else "run"


def is_stopped(job: str) -> bool:
    return get_command(job) in {"pause", "cancel"}
