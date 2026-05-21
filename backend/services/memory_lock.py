"""Per-entity memory-generation lock.

Used to serialize:
  - outbound webhook firing (must wait if a memory job is currently running for
    the same entity, then re-read state on fire)
  - memory job execution (acquires the lock at start, releases on exit)

Implementation: Redis SET NX with TTL. If the memory job crashes without
releasing, the TTL expires and the lock auto-clears.
"""

import logging

from core.storage import get_redis_client

logger = logging.getLogger(__name__)

# How long the lock auto-expires after if the holder never releases (job crashed,
# pod evicted, etc.). Should comfortably exceed the longest memory generation
# run we expect. 5 minutes is generous for a single-entity memory job.
LOCK_TTL_SECONDS = 300


def _lock_key(entity_type: str, entity_id: str) -> str:
    return f"memory_lock:{entity_type}:{entity_id}"


def acquire(entity_type: str, entity_id: str, ttl_seconds: int = LOCK_TTL_SECONDS) -> bool:
    """Try to acquire the memory lock for an entity.

    Returns True if acquired, False if another holder already has it.
    """
    redis = get_redis_client()
    key = _lock_key(entity_type, entity_id)
    # SET NX: only set if not exists. ex: TTL in seconds.
    return bool(redis.set(key, "1", nx=True, ex=ttl_seconds))


def release(entity_type: str, entity_id: str) -> None:
    """Release the memory lock. Safe to call even if not currently held."""
    redis = get_redis_client()
    key = _lock_key(entity_type, entity_id)
    try:
        redis.delete(key)
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
