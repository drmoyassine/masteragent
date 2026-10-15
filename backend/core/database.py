"""Single database-URL resolver for every Postgres namespace (TASK-257 §4).

core/db.py (prompt tables) and core/storage.py (memory tables) used to resolve
connection URLs independently — one honored the memory_settings Supabase
override, the other never did, and their fallback defaults differed. One
resolver feeds both pools so a single setting can never fork the runtime
across two databases.

Resolution order (matches scripts/remediate_credentials.py):
  1. DATABASE_URL env var (SQLite URIs are ignored with a warning)
  2. MEMORY_POSTGRES_URL env var
  3. Compose default (the `postgres` service)

Resolved once at import — the same immutability core/db.py always had.
"""
import logging
import os

logger = logging.getLogger(__name__)

_COMPOSE_DEFAULT = "postgresql://postgres:postgres@postgres:5432/memory"


def _resolve() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url and not url.startswith("sqlite:"):
        return url
    if url.startswith("sqlite:"):
        logger.warning(
            "DATABASE_URL is a SQLite URI — ignoring it. "
            "Set DATABASE_URL=postgresql://... to silence this warning."
        )
    return os.environ.get("MEMORY_POSTGRES_URL", _COMPOSE_DEFAULT)


DATABASE_URL: str = _resolve()


def get_database_url() -> str:
    """The one Postgres URL — every namespace (prompt tables + memory tables)."""
    return DATABASE_URL
