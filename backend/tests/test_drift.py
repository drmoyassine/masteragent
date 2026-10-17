"""
test_drift.py — TASK-261 step-4 drift tests.

Structural consistency checks that need no HTTP:
  1. Every memory_settings key READ in code exists as a schema column
     (TASK-257 item 6 — a typo'd/renamed key silently returns its default
     forever; the SELECT * shape makes every read an implicit schema promise).
  2. Every BullMQ job name ENQUEUED anywhere is registered in memory.queue.JOBS
     with a callable handler (TASK-257 item 5 — an unregistered name degrades
     to a warning and its payload is silently dropped).
  3. The seeded canonical entity-type set matches the canonical list in
     memory_system/store/db.py (TASK-258 pins this harder with CHECK
     constraints; until that lands, seed drift is the visible surface).

Scans are AST-based over backend source (tests/scripts excluded) — no import
side effects beyond the hermetic stack the fixtures already boot.
"""
import ast
from pathlib import Path

from core.storage import get_memory_db_context
from memory.queue import JOBS

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Canonical entity types as of TASK-261 (superset assertion: the baseline dump
# may carry admin-added types from prod; the canonical five must always be a
# subset). TASK-258's allowlist work extends this set intentionally.
CANONICAL_ENTITY_TYPES = {"contact", "institution", "program", "supplier", "product"}


def _iter_backend_sources():
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith(("tests/", "scripts/")):
            continue
        yield rel, path.read_text(encoding="utf-8")


def _is_get_memory_settings_call(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "get_memory_settings")


def _bound_from_get_memory_settings(assign: ast.Assign) -> bool:
    value = assign.value
    if _is_get_memory_settings_call(value):
        return True
    # `x = get_memory_settings() or {}`
    return (isinstance(value, ast.BoolOp)
            and any(_is_get_memory_settings_call(v) for v in value.values))


def _literal_str(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_settings_keys(source: str) -> set[str]:
    """Names bound from get_memory_settings(), then every string key read off
    them via .get("k") / ["k"]."""
    tree = ast.parse(source)
    holders: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _bound_from_get_memory_settings(node):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    holders.add(target.id)

    reads: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in holders and node.args:
            key = _literal_str(node.args[0])
            if key is not None:
                reads.add(key)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                and node.value.id in holders:
            key = _literal_str(node.slice)
            if key is not None:
                reads.add(key)
    return reads


def _scan_enqueued_job_names(source: str) -> set[str]:
    """`<...>_queue.add("<job_name>", ...)` first-argument string literals."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id.endswith("_queue") and node.args:
            name = _literal_str(node.args[0])
            if name is not None:
                names.add(name)
    return names


class TestSettingsKeyDrift:
    def test_settings_keys_read_in_code_exist_in_schema(self, base_url):
        read_keys: dict[str, set[str]] = {}
        for rel, source in _iter_backend_sources():
            keys = _scan_settings_keys(source)
            if keys:
                read_keys[rel] = keys

        assert read_keys, "AST scan found no get_memory_settings() key reads — scan is broken"

        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'memory_settings'"
            )
            columns = {row["column_name"] for row in cursor.fetchall()}

        drift = {
            rel: sorted(keys - columns)
            for rel, keys in read_keys.items()
            if keys - columns
        }
        assert not drift, (
            "memory_settings keys read in code but missing from the schema "
            "(a .get() here silently returns its default forever): "
            + "; ".join(f"{rel}: {keys}" for rel, keys in drift.items())
        )


class TestJobRegistryDrift:
    def test_every_enqueued_job_name_is_registered(self, base_url):
        enqueued: dict[str, set[str]] = {}
        for rel, source in _iter_backend_sources():
            names = _scan_enqueued_job_names(source)
            if names:
                enqueued[rel] = names

        assert enqueued, "AST scan found no queue .add() call sites — scan is broken"

        unregistered = {
            rel: sorted(names - set(JOBS))
            for rel, names in enqueued.items()
            if names - set(JOBS)
        }
        assert not unregistered, (
            "job names enqueued but absent from memory.queue.JOBS (their "
            "payloads are dropped with a warning, never executed): "
            + "; ".join(f"{rel}: {names}" for rel, names in unregistered.items())
        )

    def test_every_registered_job_has_a_callable_handler(self):
        broken = {
            name: type(spec.handler).__name__
            for name, spec in JOBS.items()
            if not callable(spec.handler)
        }
        assert not broken, f"JOBS registry entries without handlers: {broken}"


class TestEntityTypeSeedDrift:
    def test_canonical_entity_types_seeded(self, base_url):
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entity_type FROM memory_entity_type_config")
            config_types = {row["entity_type"] for row in cursor.fetchall()}
            cursor.execute("SELECT name FROM memory_entity_types")
            registry_types = {row["name"] for row in cursor.fetchall()}

        missing_config = CANONICAL_ENTITY_TYPES - config_types
        missing_registry = CANONICAL_ENTITY_TYPES - registry_types
        assert not missing_config, f"canonical types missing from memory_entity_type_config: {missing_config}"
        assert not missing_registry, f"canonical types missing from memory_entity_types: {missing_registry}"
