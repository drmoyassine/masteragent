"""Small lazy psycopg2 connection-pool registry."""
import os
import threading
import time

import psycopg2.extras
from psycopg2.pool import PoolError, ThreadedConnectionPool

_lock = threading.Lock()
_returned = threading.Condition()
_pools: dict[str, ThreadedConnectionPool] = {}


def get_pool(url: str) -> ThreadedConnectionPool:
    pool = _pools.get(url)
    if pool:
        return pool
    with _lock:
        pool = _pools.get(url)
        if not pool:
            pool = ThreadedConnectionPool(
                int(os.environ.get("DB_POOL_MIN", "1")),
                int(os.environ.get("DB_POOL_MAX", "20")),
                dsn=url,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            _pools[url] = pool
        return pool


def return_connection(url: str, connection) -> None:
    get_pool(url).putconn(connection, close=bool(connection.closed))
    with _returned:
        _returned.notify()


def acquire_connection(url: str, timeout: float | None = None):
    """Borrow a connection, briefly waiting through transient request bursts."""
    if timeout is None:
        try:
            timeout = max(0.0, float(os.environ.get("DB_POOL_ACQUIRE_TIMEOUT_SECONDS", "5")))
        except (TypeError, ValueError):
            timeout = 5.0
    deadline = time.monotonic() + timeout
    while True:
        try:
            return get_pool(url).getconn()
        except PoolError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PoolError(f"connection pool exhausted after waiting {timeout:g}s") from exc
            with _returned:
                _returned.wait(timeout=min(0.1, remaining))


def close_all_pools() -> None:
    with _lock:
        for pool in _pools.values():
            pool.closeall()
        _pools.clear()
