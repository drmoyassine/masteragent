"""Per-agent rate limiting shared across application replicas."""
from collections import defaultdict
from datetime import datetime, timezone

from memory_services import get_memory_settings
from core.storage import get_redis_client

_rate_limit_counters: dict = defaultdict(lambda: {"count": 0, "window_start": None})


def check_rate_limit(agent_id: str) -> bool:
    """Return True if agent is within rate limit, False if exceeded."""
    settings = get_memory_settings()
    if not settings.get("rate_limit_enabled", False):
        return True

    limit = settings.get("rate_limit_per_minute", 60)
    try:
        redis = get_redis_client()
        bucket = int(datetime.now(timezone.utc).timestamp() // 60)
        key = f"rate_limit:{agent_id}:{bucket}"
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 120)
        count, _ = pipe.execute()
        return int(count) <= int(limit)
    except Exception:
        # Redis outages must not take ingestion down. The per-process limiter is
        # retained as a conservative compatibility fallback.
        pass

    now = datetime.now(timezone.utc)
    state = _rate_limit_counters[agent_id]

    if state["window_start"] is None or (now - state["window_start"]).seconds >= 60:
        state["count"] = 0
        state["window_start"] = now

    state["count"] += 1
    return state["count"] <= limit
