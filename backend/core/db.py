"""
core/db.py — Shared database utilities (PostgreSQL)

Single source of truth for:
  - DB connection via DATABASE_URL env var (postgresql://)
  - get_db_context() context manager
  - get_github_settings() helper

Both the prompt manager and memory system use the same PostgreSQL instance.
"""
import os
import logging
import re
from contextlib import contextmanager
from typing import Optional, Dict, Any

import psycopg2
import psycopg2.extras
from core.secrets import decrypt_secret
from core.db_pool import acquire_connection, return_connection
from core.database import get_database_url

logger = logging.getLogger(__name__)

# TASK-257 §4: the one resolver (core/database.py) — previously this module
# resolved its own URL and never consulted the same chain storage.py used.
DATABASE_URL: str = get_database_url()

# Expose DB_PATH as a string alias for startup logging compatibility
DB_PATH = DATABASE_URL


def redact_database_url(url: str) -> str:
    return re.sub(r"(:)[^:@/]+(@)", r"\1***\2", url or "")


def get_db() -> psycopg2.extensions.connection:
    """Borrow and return a psycopg2 connection from the process pool."""
    return acquire_connection(DATABASE_URL)


@contextmanager
def get_db_context():
    """
    Context manager that opens a PostgreSQL connection, commits on success,
    and closes on exit (even on error).

    Usage:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
    """
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        return_connection(DATABASE_URL, conn)


def get_github_settings(user_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Fetch GitHub / storage settings from the settings table.

    If user_id is provided, fetches settings for that specific user.
    Otherwise fetches the first/default row (id=1).

    Returns a dict of the row or None if no row exists.
    """
    try:
        with get_db_context() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM settings WHERE user_id = %s", (user_id,))
            else:
                cursor.execute("SELECT * FROM settings WHERE id = 1")
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("github_token"):
                    result["github_token"] = decrypt_secret(result["github_token"])
                return result
    except Exception as e:
        logger.error(f"Failed to fetch settings from DB: {e}")
    return None
