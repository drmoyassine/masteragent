"""
core/storage.py — Memory-system storage helpers

Provides:
  - get_memory_db_context() : PostgreSQL context manager (the one DB — TASK-257 §4)
  - get_redis_client()      : Redis client for 24h interaction cache
  - interaction cache read/write/flush/scan helpers

The former pluggable Supabase backend was removed: it had no UI wiring, no
configured DSN in any deployment, and both env defaults pointed at the same
compose Postgres. The schema columns stay (dropping them is a §3 owner-gated
cutover); the resolver is core/database.py.
"""
import json
import logging
import os
from contextlib import contextmanager

import redis as redis_lib
from core.db_pool import acquire_connection, return_connection
from core.database import get_database_url

logger = logging.getLogger(__name__)

# Default Redis URL (overridden by env)
_DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Module-level cache for Redis client
_redis_client = None


@contextmanager
def get_memory_db_context():
    """
    Context manager yielding a PostgreSQL connection to the memory database.
    Commits on success, rolls back on exception.
    """
    url = get_database_url()
    conn = acquire_connection(url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        return_connection(url, conn)


def get_redis_client() -> redis_lib.Redis:
    """
    Get or create a shared Redis client.
    Used for the 24h interaction hot-cache.
    """
    global _redis_client
    if _redis_client is None:
        url = _DEFAULT_REDIS_URL
        _redis_client = redis_lib.from_url(url, decode_responses=True)
    return _redis_client


def cache_interaction(interaction_id: str, data: dict, ttl: int = 86400):
    """Write an interaction to Redis with a 24h TTL."""
    try:
        r = get_redis_client()
        r.setex(f"interaction:{interaction_id}", ttl, json.dumps(data))
    except Exception as e:
        logger.warning(f"Redis cache write failed for {interaction_id}: {e}")


def get_cached_interaction(interaction_id: str) -> dict | None:
    """Read a cached interaction from Redis."""
    try:
        r = get_redis_client()
        raw = r.get(f"interaction:{interaction_id}")
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Redis cache read failed for {interaction_id}: {e}")
        return None


def flush_interaction_cache(interaction_id: str):
    """Remove an interaction from Redis after it has been processed into a memory."""
    try:
        r = get_redis_client()
        r.delete(f"interaction:{interaction_id}")
    except Exception as e:
        logger.warning(f"Redis flush failed for {interaction_id}: {e}")


def get_pending_interaction_ids() -> list[str]:
    """
    Return all interaction IDs currently in the Redis hot cache.
    Used by the daily memory generation job to find what needs processing.
    """
    try:
        r = get_redis_client()
        keys = r.keys("interaction:*")
        return [k.replace("interaction:", "") for k in keys]
    except Exception as e:
        logger.warning(f"Redis key scan failed: {e}")
        return []
