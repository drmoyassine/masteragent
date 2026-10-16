"""TASK-257 §6 — settings drift guard.

Every key read off the memory_settings row in backend code must exist as a
column in the schema memory_system/store/db.py actually provisions. The oracle is the DDL,
not MemorySettingsResponse — the response model is the GET /config/settings
contract filter and has historically lagged the schema (18 real columns were
absent from it), so testing against it would flag real knobs as phantoms.

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
"""
import ast
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

_COLUMN_TYPE = re.compile(r"^\s+([a-z_]+)\s+(?:INT|TEXT|BOOLEAN|JSONB|TIMESTAMPTZ|FLOAT)\b")
_ONE_OFF_ALTER = re.compile(
    r"ALTER TABLE memory_settings ADD COLUMN (?:IF NOT EXISTS )?([a-z_]+)"
)
_LOOP_MARKER = "ALTER TABLE memory_settings ADD COLUMN"


def _literal_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _tuple_first_elements(seq) -> set:
    out = set()
    for elt in seq.elts:
        if isinstance(elt, ast.Tuple) and elt.elts:
            name = _literal_str(elt.elts[0])
            if name:
                out.add(name)
    return out


def _loop_columns(loop: ast.For, tree: ast.Module) -> set:
    """Column names from a ``for col, col_def in <iter>`` loop.

    Handles inline lists and named lists (e.g. ``settings_gauge_cols``),
    resolving the name anywhere in the module.
    """
    if isinstance(loop.iter, (ast.List, ast.Tuple)):
        return _tuple_first_elements(loop.iter)
    if isinstance(loop.iter, ast.Name):
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == loop.iter.id for t in node.targets)
                    and isinstance(node.value, (ast.List, ast.Tuple))):
                return _tuple_first_elements(node.value)
    return set()


def _schema_columns() -> set:
    """Columns provisioned on memory_settings by backend code.

    Three sources, matching how the schema is actually built:
      1. the ``CREATE TABLE IF NOT EXISTS memory_settings (...)`` block;
      2. every ``for col, col_def in ...`` loop whose body executes the
         ``ALTER TABLE memory_settings ADD COLUMN`` f-string (this is what
         excludes the knowledge / memory_entity_type_config /
         memory_outbound_webhooks loops with identical shapes);
      3. one-off literal ``ALTER TABLE memory_settings ADD COLUMN <name>``
         strings anywhere in backend code.
    """
    columns = set()
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        if "tests" in path.parts or path.name.startswith("."):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", None) == "execute"
                    and node.args):
                sql = _literal_str(node.args[0])
                if sql and "CREATE TABLE IF NOT EXISTS memory_settings" in sql:
                    for line in sql.splitlines():
                        m = _COLUMN_TYPE.match(line)
                        if m:
                            columns.add(m.group(1))
                continue
            if (isinstance(node, ast.For)
                    and isinstance(node.target, ast.Tuple)
                    and len(node.target.elts) == 2
                    and any(
                        isinstance(sub, ast.JoinedStr)
                        and any(isinstance(p, ast.Constant) and _LOOP_MARKER in str(p.value or "")
                                for p in sub.values)
                        for sub in ast.walk(node)
                    )):
                columns |= _loop_columns(node, tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                m = _ONE_OFF_ALTER.search(node.value)
                if m:
                    columns.add(m.group(1))
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


def test_every_settings_key_read_in_code_exists_in_schema():
    phantom = _settings_reads() - _schema_columns()
    assert not phantom, (
        "settings keys read in code but absent from the memory_settings DDL "
        f"(phantom knobs — add the column or delete the read): {sorted(phantom)}"
    )


def test_schema_oracle_found_the_baseline_columns():
    # Sanity: the DDL parse must find a meaningful schema, not an empty set
    # (a regression in the parser would otherwise make the drift test pass
    # vacuously).
    known = _schema_columns()
    for expected in (
        "memory_threshold",
        "knowledge_hygiene_mode",
        "memory_generation_interaction_types",
        "knowledge_generation_time",
    ):
        assert expected in known, f"oracle lost {expected!r}"
