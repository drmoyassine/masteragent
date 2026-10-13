"""Per-entity (+date) memory-generation lock.

Used to serialize:
  - outbound webhook firing (must wait if a memory job is currently running for
    the same entity — on ANY date — then re-read state on fire)
  - memory job execution (acquires the per-entity+date lock at start, releases
    on exit; one entity may generate several dates concurrently)

Implementation: each dated lock is a Redis SET NX key with TTL, plus an
entity-level companion counter (memory_lock_e:{et}:{id}) maintained in the
same Lua scripts, so the dateless webhook gate is an O(1) GET instead of a
keyspace SCAN. If a holder crashes without releasing, both keys expire within
LOCK_TTL_SECONDS and the lock auto-clears.
"""

import logging
import secrets

from core.storage import get_redis_client

logger = logging.getLogger(__name__)

# How long the lock auto-expires after if the holder never releases (job crashed,
# pod evicted, etc.). Should comfortably exceed the longest memory generation
# run we expect. 5 minutes is generous for a single-entity memory job.
LOCK_TTL_SECONDS = 300

# Acquire: SET the dated key NX+EX, and on success INCR the entity companion
# the dateless gate reads — atomically, so the two writes cannot diverge.
_ACQUIRE_LUA = """
if redis.call('set', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2]) then
  redis.call('incr', KEYS[2])
  redis.call('expire', KEYS[2], ARGV[2])
  return 1
else
  return 0
end
"""

# Release: token-checked DEL of the dated key, and on success DECR the
# companion, floored at 0 (a TTL-expired dated key can leave the counter high).
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  redis.call('del', KEYS[1])
  local n = redis.call('decr', KEYS[2])
  if n < 0 then
    redis.call('set', KEYS[2], 0, 'EX', ARGV[2])
  end
  return 1
else
  return 0
end
"""


def _lock_key(entity_type: str, entity_id: str, lock_date: str | None = None) -> str:
    if lock_date is None:
        return f"memory_lock:{entity_type}:{entity_id}"
    return f"memory_lock:{entity_type}:{entity_id}:{lock_date}"


def _companion_key(entity_type: str, entity_id: str) -> str:
    # Distinct prefix so a companion key can never collide with a dated key
    # whose entity_id/date strings happen to concatenate identically.
    return f"memory_lock_e:{entity_type}:{entity_id}"


def acquire(
    entity_type: str,
    entity_id: str,
    lock_date: str | None = None,
    ttl_seconds: int = LOCK_TTL_SECONDS,
) -> str | None:
    """Try to acquire the memory lock for an entity (optionally one date).

    lock_date scopes the lock to a single entity-day so a backlog drain can
    generate several dates of the same entity without mutually skipping. The
    dateless form is the entity-wide key (webhook gate semantics).

    Returns the ownership token if acquired, None if another holder already
    has it.
    """
    redis = get_redis_client()
    key = _lock_key(entity_type, entity_id, lock_date)
    companion = _companion_key(entity_type, entity_id)
    token = secrets.token_urlsafe(24)
    acquired = redis.eval(_ACQUIRE_LUA, 2, key, companion, token, ttl_seconds)
    return token if acquired else None


def release(
    entity_type: str,
    entity_id: str,
    token: str | None = None,
    lock_date: str | None = None,
) -> None:
    """Release the memory lock. Safe to call even if not currently held."""
    redis = get_redis_client()
    key = _lock_key(entity_type, entity_id, lock_date)
    companion = _companion_key(entity_type, entity_id)
    try:
        if token is None:
            # Compatibility path for older callers. New code always supplies the
            # ownership token so it cannot delete a successor's lock. The
            # companion counter is left alone; its TTL bounds any drift.
            logger.warning(
                f"memory_lock.release without token for {entity_type}/{entity_id} "
                f"— companion counter not decremented (TTL self-heals)"
            )
            redis.delete(key)
        else:
            redis.eval(_RELEASE_LUA, 2, key, companion, token, LOCK_TTL_SECONDS)
    except Exception as e:
        logger.warning(f"memory_lock.release failed for {entity_type}/{entity_id}: {e}")


def is_locked(entity_type: str, entity_id: str, lock_date: str | None = None) -> bool:
    """Check whether the memory lock is currently held.

    With lock_date: exact entity-day check (threshold-trigger gate — the job it
    guards always targets today's bucket).

    Without lock_date (outbound-webhook gate): date-agnostic by design — true
    while ANY generation job for this entity holds a lock on any date, so the
    webhook defers until freshly-generated memory is readable. Served by the
    entity-level companion counter (O(1) GET, maintained atomically by the
    acquire/release scripts); a crashed holder self-heals within LOCK_TTL via
    the counter's own TTL.
    """
    redis = get_redis_client()
    try:
        if lock_date is not None:
            return bool(redis.exists(_lock_key(entity_type, entity_id, lock_date)))
        value = redis.get(_companion_key(entity_type, entity_id))
        return bool(value) and int(value) > 0
    except Exception as e:
        logger.warning(f"memory_lock.is_locked failed for {entity_type}/{entity_id}: {e}")
        return False
