import pytest
from psycopg2.pool import PoolError

import core.db_pool as db_pool


def test_acquire_connection_waits_then_reports_a_bounded_error(monkeypatch):
    class ExhaustedPool:
        def getconn(self):
            raise PoolError("connection pool exhausted")

    monkeypatch.setattr(db_pool, "get_pool", lambda url: ExhaustedPool())

    with pytest.raises(PoolError, match="after waiting"):
        db_pool.acquire_connection("postgresql://example", timeout=0.001)
