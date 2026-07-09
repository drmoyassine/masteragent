"""Small lazy psycopg2 connection-pool registry."""
import os
import threading

import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

_lock = threading.Lock()
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


def close_all_pools() -> None:
    with _lock:
        for pool in _pools.values():
            pool.closeall()
        _pools.clear()
