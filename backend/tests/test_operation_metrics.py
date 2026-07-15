from datetime import datetime, timezone

import memory_operation_metrics as metrics


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append((statement, params))

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _Context:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


def test_snapshot_read_never_counts_source_tables(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        {
            "operation_key": key,
            "eligible_count": index,
            "status": "ready",
            "calculated_at": now,
            "refresh_started_at": None,
            "last_error": None,
            "updated_at": now,
        }
        for index, key in enumerate(metrics.OPERATIONS, start=1)
    ]
    cursor = _Cursor(rows)
    monkeypatch.setattr(metrics, "get_memory_db_context", lambda: _Context(_Connection(cursor)))

    result = metrics.get_snapshot()

    assert result["embedding_backfill"] == 1
    assert result["available"] is True
    assert result["status"] == "ready"
    assert result["stale"] is False
    executed_sql = " ".join(statement for statement, _ in cursor.statements).lower()
    assert "memory_operation_metrics" in executed_sql
    assert "interactions" not in executed_sql
    assert "memories" not in executed_sql
    assert "intelligence" not in executed_sql
    assert "knowledge where" not in executed_sql


def test_refreshing_snapshot_keeps_last_value_and_reports_spinner_state(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [{
        "operation_key": "embedding_backfill",
        "eligible_count": 42,
        "status": "refreshing",
        "calculated_at": now,
        "refresh_started_at": now,
        "last_error": None,
        "updated_at": now,
    }]
    monkeypatch.setattr(metrics, "get_memory_db_context", lambda: _Context(_Connection(_Cursor(rows))))

    result = metrics.get_snapshot()

    assert result["embedding_backfill"] == 42
    assert result["status"] == "refreshing"
    assert result["available"] is False
    assert result["refresh_started_at"] is not None
