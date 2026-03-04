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
from contextlib import contextmanager
from typing import Optional, Dict, Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# Connection URL from DATABASE_URL env var.
# Default: same postgres instance as the memory system.
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/memory"
)

# Strip sqlite:// prefix if someone still passes a sqlite URL (safety net)
if DATABASE_URL.startswith("sqlite:"):
    logger.warning(
        "DATABASE_URL is a SQLite URI — falling back to default PostgreSQL. "
        "Set DATABASE_URL=postgresql://... to silence this warning."
    )
    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/memory"

# Expose DB_PATH as a string alias for startup logging compatibility
DB_PATH = DATABASE_URL


def get_db() -> psycopg2.extensions.connection:
    """Open and return a raw psycopg2 connection."""
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


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
        conn.close()


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
                return dict(row)
    except Exception as e:
        logger.error(f"Failed to fetch settings from DB: {e}")
    return None
