"""TASK-257 §3/§6 — settings drift guard.

Every key read off the memory_settings row in backend code must exist as a
column in the frozen migration ledger. The oracle is backend/migrations/*.sql:
001_baseline.sql's CREATE TABLE public.memory_settings block, then the
ALTER TABLE memory_settings ADD/DROP COLUMN statements of every later
migration in file order. The response model is NOT the oracle — it is the
GET /config/settings contract filter and has historically lagged the schema
(18 real columns were absent from it), so testing against it would flag real
knobs as phantoms.

A key read via ``settings.get("<literal>")`` with no backing column is a
phantom knob: the column never existed, so the read silently returned its
default forever — the class of bug that let five queue knobs pass as
"configurable" and delayed catching the compaction_threshold rename.

The read scan is deliberately dumb: any ``settings.get("<literal>")`` call
site in backend code counts as a settings read. If a future non-settings dict
named ``settings`` trips it, rename the receiver — the ambiguity is exactly
the kind of thing the guard exists to surface. (github_* / storage_mode reads
use the legacy prompt-console ``settings`` table and were renamed to
``github_settings`` for this reason.)

Since the §3 phase-2 cutover deleted the pre-freeze boot DDL
(_create_* / _run_migrations), NO backend code may provision memory_settings
schema at all — the third test is that permanent guard: any literal
ALTER/CREATE TABLE memory_settings string in backend .py is the resurrection
class (a boot-time column the ledger doesn't know about) and fails the suite.
"""
import ast
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = BACKEND_DIR / "migrations"

# pg_dump renders types lowercase (integer, boolean, jsonb, timestamp with
# time zone, double precision, ...).
_COLUMN_TYPE = re.compile(
    r"^\s+([a-z_]+)\s+"
    r"(?:integer|smallint|bigint|text|boolean|jsonb|json|real|double precision|"
    r"numeric|timestamp with(?:out)? time zone|timestamp|timestamptz|"
    r"character varying|varchar|date|uuid)\b"
)
_MS_CREATE = re.compile(r"CREATE TABLE (?:IF NOT EXISTS )?(?:public\.)?memory_settings")
_MS_ALTER_ADD = re.compile(
    r"ALTER TABLE (?:public\.)?memory_settings\s+ADD COLUMN (?:IF NOT EXISTS )?([a-z_]+)"
)
_MS_ALTER_DROP = re.compile(
    r"ALTER TABLE (?:public\.)?memory_settings\s+DROP COLUMN (?:IF NOT EXISTS )?([a-z_]+)"
)


def _expected_columns() -> set:
    """Columns the migration ledger provisions on memory_settings.

    001_baseline.sql contributes its CREATE TABLE block; every later
    migration's ALTER TABLE memory_settings ADD/DROP COLUMN is applied in
    file order (stem-sorted, same order the runner uses).
    """
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert files, "migration ledger is empty — oracle has no source of truth"
    columns: set = set()
    seen_baseline = False
    for path in files:
        sql = path.read_text(encoding="utf-8")
        if "001_baseline" in path.name:
            seen_baseline = True
            # isolate the CREATE TABLE ... (...) block, then column-scan it
            start = sql.find("CREATE TABLE public.memory_settings (")
            assert start != -1, "001_baseline.sql lost the memory_settings DDL"
            end = sql.find(");", start)
            block = sql[start:end]
            for line in block.splitlines():
                m = _COLUMN_TYPE.match(line)
                if m:
                    columns.add(m.group(1))
        else:
            for m in _MS_ALTER_ADD.finditer(sql):
                columns.add(m.group(1))
            for m in _MS_ALTER_DROP.finditer(sql):
                columns.discard(m.group(1))
    assert seen_baseline, "001_baseline.sql missing from the migration ledger"
    return columns


def _settings_reads() -> set:
    keys = set()
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        if "tests" in path.parts or path.name.startswith("."):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "settings"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)
    return keys


def _code_memory_settings_ddl() -> list:
    """Literal SQL strings in backend .py that mutate memory_settings schema."""
    hits = []
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        if "tests" in path.parts or path.name.startswith("."):
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _MS_CREATE.search(line) or re.search(
                r"ALTER TABLE (?:public\.)?memory_settings", line
            ):
                hits.append(f"{path.relative_to(BACKEND_DIR)}:{lineno}")
    return hits


def test_every_settings_key_read_in_code_exists_in_schema():
    phantom = _settings_reads() - _expected_columns()
    assert not phantom, (
        "settings keys read in code but absent from the migration ledger "
        f"(phantom knobs — add the column via a migration or delete the read): "
        f"{sorted(phantom)}"
    )


def test_oracle_found_the_baseline_columns():
    # Sanity: the ledger parse must find a meaningful schema, not an empty set
    # (a regression in the parser would otherwise make the drift test pass
    # vacuously). auto_knowledge_enabled only exists via 002 — its presence
    # proves the later-migration ALTER pass ran too.
    known = _expected_columns()
    for expected in (
        "memory_threshold",
        "knowledge_hygiene_mode",
        "memory_generation_interaction_types",
        "knowledge_generation_time",
        "auto_knowledge_enabled",
    ):
        assert expected in known, f"oracle lost {expected!r}"


def test_no_code_provisions_memory_settings_schema():
    # TASK-257 §3: schema belongs to the ledger alone. Boot-time DDL outside
    # it is exactly how the pre-freeze fossils formed (columns/columns sets
    # the ledger never recorded, renamed indexes squatting on dropped
    # tables). Any literal ALTER/CREATE TABLE memory_settings in backend
    # code must go through a migration instead.
    hits = _code_memory_settings_ddl()
    assert not hits, (
        "backend code still provisions memory_settings schema outside the "
        f"migration ledger (resurrection class): {hits}"
    )
