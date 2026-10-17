"""TASK-257 §3 — forward-only schema migrations for the memory store.

The frozen schema lives in backend/migrations/ as plain SQL files, applied
once each in filename order and tracked in public.schema_migrations. Boot
behavior (apply_pending, called from store.db.init_memory_db under the init
advisory lock):

  fresh database   (no memory_settings table) -> apply every file
  legacy database  (tables exist, no ledger)  -> stamp 001_baseline as
                     applied WITHOUT executing it (it is a verbatim pg_dump
                     whose CREATE TABLE statements are not IF NOT EXISTS),
                     then apply anything newer
  frozen database  (ledger present)           -> apply only pending files

Each migration commits in its own transaction; a failure rolls it back and
aborts boot loudly. This runner deliberately replaces the per-boot
create-if-not-exists DDL and the warning-swallowed taxonomy migration in
store/db.py — that swallow is what let production drift silently (TASK-257
§3 root cause).

CREATE INDEX CONCURRENTLY cannot run inside a transaction, so operational
indexes stay with store.db._create_operational_indexes_concurrently.

Note on search_path: the pg_dump-generated baseline sets search_path='' for
the session, so every ledger statement here is schema-qualified.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
BASELINE_VERSION = "001_baseline"
LEDGER_TABLE = "public.schema_migrations"


def migration_files(directory: Path = MIGRATIONS_DIR) -> list:
    """Return the migration files in application order (empty dir = error)."""
    files = sorted(p for p in directory.glob("*.sql") if p.is_file())
    if not files:
        raise RuntimeError(f"No migration files found in {directory}")
    return files


def plan(files: list, applied: set, schema_exists: bool) -> list:
    """Decide the boot's migration steps: [(version, execute)].

    execute=False means stamp-only — record the version as applied without
    running its SQL (used to adopt legacy schemas onto the baseline).
    Pure function; unit-tested without a database.
    """
    stems = [f.stem for f in files]
    if schema_exists and not applied:
        if BASELINE_VERSION not in stems:
            raise RuntimeError(
                f"{BASELINE_VERSION} missing from migrations; "
                "cannot stamp a legacy database onto the frozen baseline"
            )
        logger.info(
            "Legacy schema without migration ledger detected; "
            "stamping %s as applied", BASELINE_VERSION
        )
        return [(BASELINE_VERSION, False)] + [(s, True) for s in stems if s != BASELINE_VERSION]
    return [(s, True) for s in stems if s not in applied]


def _ensure_ledger(cursor) -> None:
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
            version    TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def _applied_versions(cursor) -> set:
    cursor.execute(f"SELECT version FROM {LEDGER_TABLE}")
    return {row["version"] for row in cursor.fetchall()}


def _schema_exists(cursor) -> bool:
    cursor.execute("SELECT to_regclass('public.memory_settings') AS tbl")
    return cursor.fetchone()["tbl"] is not None


def apply_pending(conn) -> list:
    """Ensure the ledger exists, then apply (or stamp) pending migrations.

    Runs on the caller's connection; each migration commits in its own
    transaction. Raises on the first failure — boot aborts loudly, the
    failure is never swallowed (TASK-257 §3).
    """
    cursor = conn.cursor()
    _ensure_ledger(cursor)
    conn.commit()

    steps = plan(migration_files(), _applied_versions(cursor), _schema_exists(cursor))

    for version, execute in steps:
        try:
            if execute:
                logger.info("Applying migration %s", version)
                cursor.execute((MIGRATIONS_DIR / f"{version}.sql").read_text(encoding="utf-8"))
                # A pg_dump baseline pins search_path='' for the SESSION while
                # later files use unqualified names (002_reconcile). Restore
                # after every executed file so each migration sees the
                # default path — fresh-DB provisioning was dead on arrival
                # without this (found by the TASK-261 hermetic suite).
                cursor.execute(
                    "SELECT pg_catalog.set_config('search_path', %s, false)",
                    ('"$user", public',),
                )
            else:
                logger.info("Stamping legacy schema as %s", version)
            cursor.execute(
                f"INSERT INTO {LEDGER_TABLE} (version) VALUES (%s)", (version,)
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error("Migration %s failed; boot aborted", version)
            raise

    if steps:
        logger.info("Migrations settled: %s", ", ".join(v for v, _ in steps))

    # The pg_dump baseline sets search_path='' for the SESSION, which would
    # break every unqualified statement the caller runs on this connection
    # afterwards. Restore the server default before handing the connection
    # back (is_local=False so it survives the commit).
    cursor.execute(
        "SELECT pg_catalog.set_config('search_path', %s, false)",
        ('"$user", public',),
    )
    conn.commit()
    return steps
