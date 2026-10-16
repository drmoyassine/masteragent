"""TASK-257 §3 — the migration runner's decision logic (no database).

The runner owns boot-time DDL now, so its fresh/legacy/frozen decision table
is unit-tested here; the transactional half is exercised by the compose
smokes (fresh volume -> 001 applied; existing volume -> stamp-only).
"""
from pathlib import Path

import pytest

from memory_system.store.migrations import BASELINE_VERSION, migration_files, plan


def _files(*stems):
    return [Path(f"{s}.sql") for s in stems]


class TestPlan:
    def test_fresh_database_applies_everything_in_order(self):
        files = _files("001_baseline", "002_reconcile")
        assert plan(files, applied=set(), schema_exists=False) == [
            ("001_baseline", True),
            ("002_reconcile", True),
        ]

    def test_frozen_database_applies_only_pending(self):
        files = _files("001_baseline", "002_reconcile", "003_next")
        assert plan(files, applied={"001_baseline"}, schema_exists=True) == [
            ("002_reconcile", True),
            ("003_next", True),
        ]

    def test_frozen_database_up_to_date_applies_nothing(self):
        assert plan(_files("001_baseline"), applied={"001_baseline"}, schema_exists=True) == []

    def test_legacy_database_stamps_baseline_without_executing(self):
        files = _files("001_baseline", "002_reconcile")
        assert plan(files, applied=set(), schema_exists=True) == [
            ("001_baseline", False),
            ("002_reconcile", True),
        ]

    def test_legacy_database_requires_baseline_file(self):
        with pytest.raises(RuntimeError, match="001_baseline"):
            plan(_files("002_reconcile"), applied=set(), schema_exists=True)


def test_repo_migrations_dir_starts_with_baseline():
    # Repo invariant: the shipped migrations dir is non-empty and ordered.
    files = migration_files()
    assert files[0].stem == BASELINE_VERSION
