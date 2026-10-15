"""Offline credential-envelope remediation CLI (TASK-257; born from the
2026-10-15 outage).

The startup envelope gate strands boot when envelopes are not rotation-safe —
so the old advice ("POST /admin/rewrap-credentials") pointed at an API that
was unreachable under the very refusal. This CLI runs INSIDE the container
without booting the app:

    python scripts/remediate_credentials.py status
    python scripts/remediate_credentials.py rewrap --apply
    python scripts/remediate_credentials.py quarantine --apply
    python scripts/remediate_credentials.py quarantine --apply --store provider_credentials

It handles the two failure classes the gate distinguishes:

  rewrap-able — decrypts under a fallback chain source but not the current
      primary. Fix = rewrap BEFORE promoting the next DATA_ENCRYPTION_KEY
      (the standing rotation rule). Requires the dedicated key to already be
      the primary; rewrapping under a fallback would be meaningless.

  orphaned — decrypts under NO chain source (e.g. keys rotated without a
      rewrap). Unrecoverable ciphertext: the remedy is quarantine + NULL —
      exactly the 2026-10-15 runbook — then re-enter live keys via the
      admin UI.

Counts only: secret values and plaintexts never reach stdout. Dry-run by
default; pass --apply to write. Exit codes: 0 ok, 1 error, 2 refusal.

Deliberately imports NOTHING from the app boot path (core.db, db_init,
memory_db). core.secrets is imported for the key chain only — its DB access
is function-local, so the module imports clean. That is the whole point of
"offline": the tool must work when the app cannot boot. The DSN resolves in
the same order core/database.py uses (DATABASE_URL → MEMORY_POSTGRES_URL →
compose default) — re-implemented here on purpose, not imported.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
import psycopg2.extras

from core.secrets import (
    _PREFIX,
    _classify_values,
    _decrypts_under,
    _fernet,
    _fernet_from_source,
    _primary_source,
    _sources,
    key_source,
)

_DEFAULT_PG = "postgresql://postgres:postgres@postgres:5432/memory"

# (label, table, envelope column, scan SQL) — same stores the startup gate
# and the admin rewrap endpoint cover.
_STORES = (
    ("provider_credentials", "memory_llm_providers", "api_key_encrypted",
     "SELECT id, api_key_encrypted AS v FROM memory_llm_providers WHERE api_key_encrypted LIKE 'enc:v1:%'"),
    ("supabase_db_url", "memory_settings", "supabase_db_url",
     "SELECT id, supabase_db_url AS v FROM memory_settings WHERE supabase_db_url LIKE 'enc:v1:%'"),
    ("webhook_secrets", "memory_webhook_sources", "secret_encrypted",
     "SELECT id, secret_encrypted AS v FROM memory_webhook_sources WHERE secret_encrypted LIKE 'enc:v1:%'"),
)

_QUARANTINE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS _quarantined_credentials (
    id             BIGSERIAL PRIMARY KEY,
    store          TEXT NOT NULL,
    row            JSONB NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def _dsn() -> str:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("MEMORY_POSTGRES_URL")
        or _DEFAULT_PG
    )


def _connect(readonly: bool):
    conn = psycopg2.connect(_dsn())
    conn.set_session(readonly=readonly, autocommit=False)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute("SET lock_timeout = '5s'")
    return conn


def _scan(cursor, label):
    """(id, v) rows for one store; [] when the table doesn't exist yet."""
    for store_label, _table, _col, query in _STORES:
        if store_label == label:
            try:
                cursor.execute(query)
                return cursor.fetchall()
            except psycopg2.errors.UndefinedTable:
                cursor.connection.rollback()
                return []
    raise ValueError(f"unknown store: {label}")


def _classify_all(cursor):
    sources = _sources()
    fernets = [_fernet_from_source(source) for source in sources]
    primary = _fernet_from_source(_primary_source())
    result = {}
    for label, _table, _col, _query in _STORES:
        rows = _scan(cursor, label)
        counts = _classify_values([row["v"] for row in rows], fernets, primary)
        result[label] = {"total": len(rows), **counts, "ids": {c: [] for c in counts}}
        for row in rows:
            if _decrypts_under(row["v"], primary):
                result[label]["ids"]["current"].append(row["id"])
            elif any(_decrypts_under(row["v"], f) for f in fernets):
                result[label]["ids"]["rewrap_able"].append(row["id"])
            else:
                result[label]["ids"]["orphaned"].append(row["id"])
    return result


def _print_status(classification):
    print(f"primary key source: {key_source()}")
    for label, store in classification.items():
        print(
            f"{label}: total={store['total']} current={store['current']} "
            f"rewrap_able={store['rewrap_able']} orphaned={store['orphaned']}"
        )


def cmd_status(cursor, _args) -> int:
    _print_status(_classify_all(cursor))
    return 0


def cmd_rewrap(cursor, args) -> int:
    if key_source() != "data_key":
        print(
            "REFUSED: the primary key source is not the dedicated DATA_ENCRYPTION_KEY "
            f"(currently: {key_source()}). Set DATA_ENCRYPTION_KEY first — rewrapping "
            "under a fallback source would not survive the next rotation."
        )
        return 2
    classification = _classify_all(cursor)
    _print_status(classification)
    primary = _fernet()
    rewrapped = 0
    for label, table, col, _query in _STORES:
        ids = classification[label]["ids"]["rewrap_able"]
        if not ids:
            continue
        if not args.apply:
            print(f"{label}: would rewrap {len(ids)} envelope(s) under the primary key")
            continue
        id_list = tuple(ids)
        cursor.execute(
            f"SELECT id, {col} AS v FROM {table} WHERE id IN %s",
            (id_list,),
        )
        for row in cursor.fetchall():
            # Chain-walk again per row: the CLI never holds plaintext longer
            # than one statement, and nothing is ever printed.
            plaintext = None
            for fernet in (_fernet_from_source(s) for s in _sources()):
                try:
                    plaintext = fernet.decrypt(row["v"][len(_PREFIX):].encode("ascii")).decode("utf-8")
                    break
                except Exception:
                    continue
            if plaintext is None:
                continue
            cursor.execute(
                f"UPDATE {table} SET {col} = %s WHERE id = %s",
                (f"{_PREFIX}{primary.encrypt(plaintext.encode('utf-8')).decode('ascii')}", row["id"]),
            )
            rewrapped += 1
    if args.apply:
        print(f"rewrapped {rewrapped} envelope(s) under the primary key")
    else:
        print("dry run — re-run with --apply to write")
    return 0


def cmd_quarantine(cursor, args) -> int:
    classification = _classify_all(cursor)
    _print_status(classification)
    selected = _STORES if not args.store else tuple(
        s for s in _STORES if s[0] in args.store
    )
    unknown = set(args.store or []) - {s[0] for s in _STORES}
    if unknown:
        print(f"REFUSED: unknown store(s): {sorted(unknown)}")
        return 2
    quarantined = 0
    for label, table, col, _query in selected:
        ids = classification[label]["ids"]["orphaned"]
        if not ids:
            continue
        if not args.apply:
            print(f"{label}: would quarantine {len(ids)} orphaned envelope(s) "
                  f"(copy row to _quarantined_credentials, then NULL {col})")
            continue
        id_list = tuple(ids)
        cursor.execute(_QUARANTINE_TABLE_DDL)
        cursor.execute(
            f"SELECT to_jsonb(t.*) AS row FROM {table} t WHERE t.id IN %s",
            (id_list,),
        )
        for row in cursor.fetchall():
            cursor.execute(
                "INSERT INTO _quarantined_credentials (store, row) VALUES (%s, %s)",
                (label, psycopg2.extras.Json(row["row"])),
            )
        cursor.execute(
            f"UPDATE {table} SET {col} = NULL WHERE id IN %s",
            (id_list,),
        )
        quarantined += len(ids)
        print(f"{label}: quarantined {len(ids)} orphaned envelope(s); NULLed {col}")
    if not args.apply:
        print("dry run — re-run with --apply to write")
    else:
        print(f"quarantined {quarantined} envelope(s) total; re-enter live keys via the admin UI")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="counts-only envelope classification")
    p_rewrap = sub.add_parser("rewrap", help="re-encrypt rewrap-able envelopes under the primary key")
    p_quarantine = sub.add_parser("quarantine", help="quarantine + NULL orphaned envelopes")
    for p in (p_rewrap, p_quarantine):
        p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p_quarantine.add_argument(
        "--store", action="append",
        help="restrict to one store (repeatable): " + ", ".join(s[0] for s in _STORES),
    )
    args = parser.parse_args()

    readonly = args.command == "status"
    try:
        conn = _connect(readonly=readonly)
    except psycopg2.OperationalError as exc:
        print(f"ERROR: cannot reach the database ({exc.__class__.__name__})")
        return 1
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            handler = {"status": cmd_status, "rewrap": cmd_rewrap, "quarantine": cmd_quarantine}[args.command]
            code = handler(cursor, args)
        if args.command != "status" and args.apply:
            conn.commit()
        elif args.command != "status":
            conn.rollback()
        return code
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc.__class__.__name__}: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
