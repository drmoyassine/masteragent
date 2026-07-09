"""Per-entity memory-generation lock.

Used to serialize:
  - outbound webhook firing (must wait if a memory job is currently running for
    the same entity, then re-read state on fire)
  - memory job execution (acquires the lock at start, releases on exit)

Implementation: Redis SET NX with TTL. If the memory job crashes without
releasing, the TTL expires and the lock auto-clears.
"""

import logging
import secrets

from core.storage import get_redis_client

logger = logging.getLogger(__name__)

# How long the lock auto-expires after if the holder never releases (job crashed,
# pod evicted, etc.). Should comfortably exceed the longest memory generation
# run we expect. 5 minutes is generous for a single-entity memory job.
LOCK_TTL_SECONDS = 300


def _lock_key(entity_type: str, entity_id: str) -> str:
    return f"memory_lock:{entity_type}:{entity_id}"


def acquire(entity_type: str, entity_id: str, ttl_seconds: int = LOCK_TTL_SECONDS) -> str | None:
    """Try to acquire the memory lock for an entity.

    Returns True if acquired, False if another holder already has it.
    """
    redis = get_redis_client()
    key = _lock_key(entity_type, entity_id)
    token = secrets.token_urlsafe(24)
    return token if redis.set(key, token, nx=True, ex=ttl_seconds) else None


def release(entity_type: str, entity_id: str, token: str | None = None) -> None:
    """Release the memory lock. Safe to call even if not currently held."""
    redis = get_redis_client()
    key = _lock_key(entity_type, entity_id)
    try:
        if token is None:
            # Compatibility path for older callers. New code always supplies the
            # ownership token so it cannot delete a successor's lock.
            redis.delete(key)
        else:
            redis.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end",
                1,
                key,
                token,
            )
    except Exception as e:
        logger.warning(f"memory_lock.release failed for {entity_type}/{entity_id}: {e}")


def is_locked(entity_type: str, entity_id: str) -> bool:
    """Check whether the memory lock is currently held for an entity."""
    redis = get_redis_client()
    key = _lock_key(entity_type, entity_id)
    try:
        return bool(redis.exists(key))
    except Exception as e:
        logger.warning(f"memory_lock.is_locked failed for {entity_type}/{entity_id}: {e}")
        return False
