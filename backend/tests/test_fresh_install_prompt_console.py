"""
test_fresh_install_prompt_console.py — migration 009 regression.

A fresh benchmark deploy (2026-10-26) found that databases initialized after
TASK-257 §3 phase-2 boot WITHOUT the eight prompt-console tables —
db_init.init_db() dropped the DDL and nothing in migrations/ replaced it, so
/api/keys et al. 500'd with UndefinedTable. Migration 009 restores the tables
inside the ledger. The hermetic suite IS the fresh-install scenario: its
throwaway Postgres boots through the real initialize_application() and the
full 001..009 chain, so these tests fail without the migration.
"""
import os
from pathlib import Path

import pytest

from conftest import BASE_URL, HERMETIC


def test_api_keys_work_on_fresh_install(authenticated_client):
    """POST /api/keys was the exact 500 (UndefinedTable: relation "api_keys")."""
    r = authenticated_client.post(f"{BASE_URL}/api/keys", json={"name": "fresh-install-regression"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key"].startswith("pm_")
    assert body["key_preview"].endswith(body["key"][-4:])


def test_default_templates_seeded(authenticated_client):
    """Pre-§3 fresh installs seeded four default templates at boot; 009
    restores the library (byte-identical sections from the old _seed_templates)."""
    r = authenticated_client.get(f"{BASE_URL}/api/templates")
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()}
    assert {"Agent Persona", "Task Executor", "Knowledge Expert", "Minimal Prompt"} <= names


def test_prompts_route_responds(authenticated_client):
    r = authenticated_client.get(f"{BASE_URL}/api/prompts")
    assert r.status_code == 200, r.text


@pytest.mark.skipif(not HERMETIC, reason="re-runs migration SQL; live-stack mode points at a real deployment")
def test_migration_009_is_idempotent():
    """Legacy deployments apply 009 on top of tables that already exist —
    re-running the file against the already-migrated hermetic DB must be a
    clean no-op (all DDL IF NOT EXISTS, seed guarded by NOT EXISTS)."""
    import psycopg2

    sql = (Path(__file__).resolve().parents[1] / "migrations" / "009_prompt_console.sql").read_text(encoding="utf-8")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM templates")
            row = cur.fetchone()
            assert row is not None
            before = row[0]
            cur.execute(sql)  # second application, as one batch like the runner
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM templates")
            row = cur.fetchone()
            assert row is not None
            assert row[0] == before
    finally:
        conn.close()
