"""
core/storage.py — Pluggable storage factory for the memory system

Provides:
  - get_memory_db_context() : PostgreSQL context manager (local or Supabase)
  - get_redis_client()      : Redis client for 24h interaction cache
  - get_postgres_url()      : Resolves the active PG connection URL

Storage backends:
  - Default: local PostgreSQL + pgvector (MEMORY_POSTGRES_URL env var)
  - Optional: user's Supabase project (when connected via settings UI)
"""
import hashlib
import json
import logging
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import redis as redis_lib

logger = logging.getLogger(__name__)

# Default connection URLs (overridden by env or Supabase settings)
_DEFAULT_POSTGRES_URL = os.environ.get(
    "MEMORY_POSTGRES_URL",
    "postgresql://postgres:postgres@localhost:5432/memory"
)
_DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Module-level cache for Redis client
_redis_client = None

# In-memory cache for resolved PG URL (cleared when Supabase config changes)
_pg_url_cache = None


def get_postgres_url() -> str:
    """
    Resolve the active PostgreSQL connection URL.

    Priority:
      1. Supabase URL from memory_settings (if connected)
      2. MEMORY_POSTGRES_URL env var
      3. Local default (postgres:postgres@localhost/memory)
    """
    global _pg_url_cache
    if _pg_url_cache:
        return _pg_url_cache

    # Try reading Supabase config from local PG settings table
    try:
        conn = psycopg2.connect(
            _DEFAULT_POSTGRES_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=3
        )
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT supabase_url FROM memory_settings WHERE id = 1"
            )
            row = cursor.fetchone()
            if row and row.get("supabase_url"):
                url = row["supabase_url"]
                _pg_url_cache = url
                logger.info("Memory system using Supabase PostgreSQL")
                return url
        finally:
            conn.close()
    except Exception:
        pass

    _pg_url_cache = _DEFAULT_POSTGRES_URL
    return _DEFAULT_POSTGRES_URL


def invalidate_pg_url_cache():
    """Call this after changing Supabase connection settings."""
    global _pg_url_cache
    _pg_url_cache = None


@contextmanager
def get_memory_db_context():
    """
    Context manager yielding a PostgreSQL connection to the memory database.
    Commits on success, rolls back on exception.
    """
    url = get_postgres_url()
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


# ─────────────────────────────────────────────────────────────
# Supabase Connection Management
# ─────────────────────────────────────────────────────────────

def connect_supabase(supabase_url: str, supabase_db_url: str) -> dict:
    """
    Validate + store Supabase PostgreSQL connection.

    Args:
        supabase_url:    Supabase project URL (https://xyz.supabase.co)
        supabase_db_url: Direct PostgreSQL connection URL for the Supabase project
                         (postgresql://postgres:<password>@db.xyz.supabase.co:5432/postgres)

    Returns:
        dict with status, pg_url (redacted), and any error
    """
    # 1. Validate the connection before storing it
    try:
        test_conn = psycopg2.connect(
            supabase_db_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=10
        )
        test_conn.close()
    except Exception as e:
        return {
            "connected": False,
            "error": f"Could not connect to Supabase PostgreSQL: {e}",
        }

    # 2. Store in local memory_settings
    try:
        local_conn = psycopg2.connect(
            _DEFAULT_POSTGRES_URL,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        try:
            cursor = local_conn.cursor()
            cursor.execute("""
                UPDATE memory_settings
                SET supabase_url = %s, supabase_db_url = %s
                WHERE id = 1
            """, (supabase_url, supabase_db_url))
            local_conn.commit()
        finally:
            local_conn.close()
    except Exception as e:
        return {
            "connected": False,
            "error": f"Could not save Supabase settings to local DB: {e}",
        }

    # 3. Invalidate URL cache so next request uses Supabase
    invalidate_pg_url_cache()

    # Redact password from URL for response
    redacted_url = _redact_pg_url(supabase_db_url)
    logger.info(f"Supabase connected: {supabase_url}")
    return {"connected": True, "supabase_url": supabase_url, "db_url_preview": redacted_url}


def disconnect_supabase() -> dict:
    """Disconnect Supabase — revert to local PostgreSQL."""
    try:
        conn = psycopg2.connect(
            _DEFAULT_POSTGRES_URL,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE memory_settings
                SET supabase_url = NULL, supabase_db_url = NULL
                WHERE id = 1
            """)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        return {"disconnected": False, "error": str(e)}

    invalidate_pg_url_cache()
    logger.info("Supabase disconnected — reverted to local PostgreSQL")
    return {"disconnected": True, "active_backend": "local"}


def get_supabase_status() -> dict:
    """Return current storage backend status."""
    try:
        conn = psycopg2.connect(
            _DEFAULT_POSTGRES_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=3
        )
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT supabase_url, supabase_db_url FROM memory_settings WHERE id = 1")
            row = cursor.fetchone()
        finally:
            conn.close()

        if row and row.get("supabase_url"):
            return {
                "backend": "supabase",
                "supabase_url": row["supabase_url"],
                "db_url_preview": _redact_pg_url(row.get("supabase_db_url", "")),
                "connected": True,
            }
    except Exception as e:
        return {"backend": "local", "connected": True, "error": str(e)}

    return {"backend": "local", "connected": True}


def _redact_pg_url(url: str) -> str:
    """Replace the password in a PostgreSQL URL with ***."""
    try:
        import re
        return re.sub(r"(:)[^@]+(@)", r"\1***\2", url)
    except Exception:
        return "***"
