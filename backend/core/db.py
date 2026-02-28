"""
core/db.py — Shared database utilities for prompt_manager.db

Single source of truth for:
  - DB path resolution
  - get_db_context() context manager
  - get_github_settings() helper

Previously duplicated across server.py, storage_service.py, and memory_routes.py.
"""
import os
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Resolve paths relative to the backend/ directory (parent of this core/ package)
BACKEND_DIR = Path(__file__).parent.parent
DB_DIR = BACKEND_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "prompt_manager.db"


def get_db() -> sqlite3.Connection:
    """Open and return a raw SQLite connection to prompt_manager.db."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db_context():
    """
    Context manager that opens a DB connection, commits on success,
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
    Previously defined independently in server.py AND storage_service.py.
    """
    try:
        with get_db_context() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("SELECT * FROM settings WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return dict(row)
    except Exception as e:
        logger.error(f"Failed to fetch settings from DB (possible auth race condition): {e}")
    return None
