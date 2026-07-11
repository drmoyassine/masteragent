"""memory_embedding.py — Deterministic embedding serialization for knowledge.

One canonical path turns a knowledge record (any of the five consolidatable
categories) into the text string that gets embedded, and stamps the resulting
embedding metadata (model / dimensions / version / timestamp) onto the record.

All knowledge creation and update paths — generation, telemetry reflection,
playbook/skill extraction, Hermes, admin CRUD/import, promotion, and
consolidation — ultimately embed through ``serialize_knowledge_for_embedding``
so that candidate discovery compares apples to apples.

Embedding provenance lives in ``knowledge.metadata.embedding``:

    {"model": "...", "dimensions": 1536, "version": 2, "timestamp": "..."}

This never replaces the embedding column; it only records how/when it was made
so the resumable backfill and candidate discovery can decide compatibility
without re-embedding blindly. Legacy rows without this block are treated as
version ``1`` (unknown) and upgraded by the backfill.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from memory_skill_md import SKILL_MD_CATEGORIES, is_skill_md, parse_skill_md

logger = logging.getLogger(__name__)

# Bumped whenever the serialization shape changes so candidate discovery can
# refuse to mix embeddings produced under different shapes. Matches the
# ``knowledge_hygiene_embedding_version`` default setting.
EMBEDDING_VERSION = 2

# Categories that go through the consolidatable pipeline.
CONSOLIDATABLE_KNOWLEDGE_CATEGORIES = {
    "best_practices",
    "lessons_learned",
    "trade_knowledge",
    "skill",
    "playbook",
}


# ─── metadata helpers ────────────────────────────────────────────────────────

def _coerce_metadata(metadata: Any) -> Dict[str, Any]:
    """Return a plain dict for a metadata value that may be JSON text or None."""
    if not metadata:
        return {}
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def get_embedding_version(row: Dict[str, Any]) -> int:
    """Read the recorded embedding version from ``metadata.embedding.version``.

    Returns ``1`` for legacy rows that have no embedding block (treated as the
    pre-versioning shape). Returns ``0`` only when the row has no embedding at
    all — callers use that to decide whether to (re)embed.
    """
    embedding = _coerce_metadata(row.get("metadata")).get("embedding") or {}
    if not isinstance(embedding, dict):
        return 1
    version = embedding.get("version")
    if version is None:
        # Has an embedding block but no version pinned → legacy shape.
        return 1
    try:
        return int(version)
    except (TypeError, ValueError):
        return 1


def get_embedding_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return the ``metadata.embedding`` sub-document (possibly empty)."""
    return _coerce_metadata(_coerce_metadata(row.get("metadata")).get("embedding"))


def is_embedding_compatible(row: Dict[str, Any], configured_version: int) -> bool:
    """True when the row's embedding version matches the configured version.

    A row with no embedding vector is never compatible (there is nothing to
    compare). Used by automated candidate discovery; manual preview reports the
    mismatch as a warning instead of rejecting.
    """
    if not row.get("embedding"):
        return False
    return get_embedding_version(row) == int(configured_version)


def build_embedding_metadata(
    *,
    model: Optional[str],
    vector: Optional[List[float]],
    version: int = EMBEDDING_VERSION,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct the ``metadata.embedding`` sub-document for a freshly embedded row."""
    return {
        "model": model or "",
        "dimensions": len(vector) if vector else 0,
        "version": int(version),
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }


def merge_embedding_metadata(
    metadata: Optional[Dict[str, Any]],
    *,
    model: Optional[str],
    vector: Optional[List[float]],
    version: int = EMBEDDING_VERSION,
) -> Dict[str, Any]:
    """Return a copy of ``metadata`` with an updated ``embedding`` block.

    Never mutates the caller's dict. Preserves all other metadata keys
    (facets, consolidation lineage, always_inject, …).
    """
    base = dict(_coerce_metadata(metadata))
    base["embedding"] = build_embedding_metadata(
        model=model, vector=vector, version=version
    )
    return base


# ─── serialization ───────────────────────────────────────────────────────────

def _format_list(items: Any) -> str:
    """Best-effort comma join over something that might be a list/tuple/scalar."""
    if items is None:
        return ""
    if isinstance(items, (list, tuple, set)):
        return ", ".join(str(i).strip() for i in items if str(i).strip())
    return str(items).strip()


def _facet_text(metadata: Dict[str, Any]) -> str:
    """Render governed facets as ``key: value`` lines for embedding context."""
    facets = metadata.get("facets")
    if not isinstance(facets, dict) or not facets:
        return ""
    parts = []
    for key in sorted(facets.keys()):
        value = facets[key]
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        if value in (None, "", []):
            continue
        parts.append(f"{key}: {value}")
    return "; ".join(parts)


def _serialize_skill_playbook(row: Dict[str, Any]) -> str:
    """Serialize a skill/playbook record deterministically.

    SKILL.md body + structured operational fields (steps, triggers, procedure,
    prerequisites, tools, …) all carry operational signal that two records must
    share to be considered the same skill/playbook.
    """
    name = (row.get("name") or "").strip()
    summary = (row.get("summary") or "").strip()
    content = (row.get("content") or "").strip()
    metadata = _coerce_metadata(row.get("metadata"))

    description = summary
    body = content
    if is_skill_md(content):
        try:
            parsed = parse_skill_md(content)
            description = description or parsed.get("description", "")
            body = parsed.get("body", "") or content
        except ValueError:
            body = content

    category = row.get("category") or "skill"
    parts: List[str] = [f"[{category}] {name}".strip()]
    if description:
        parts.append(description)

    # Operational fields that distinguish one skill/playbook from another.
    triggers = metadata.get("trigger_conditions") or metadata.get("triggers") or metadata.get("trigger_desc") or []
    steps = metadata.get("steps") or []
    procedure = metadata.get("procedure") or ""
    prerequisites = metadata.get("prerequisites") or metadata.get("preconditions") or []
    tools = metadata.get("tools") or metadata.get("integrations") or []
    permissions = metadata.get("permissions") or metadata.get("required_permissions") or []
    side_effects = metadata.get("side_effects") or []
    failure_conditions = metadata.get("failure_conditions") or []
    safety = metadata.get("safety") or metadata.get("safety_requirements") or []
    applies_to = metadata.get("applies_to") or metadata.get("agents") or metadata.get("environments") or []
    completion = metadata.get("completion_criteria") or metadata.get("exit_conditions") or []
    rollback = metadata.get("rollback") or ""

    if triggers:
        parts.append("When to use: " + _format_list(triggers))
    if prerequisites:
        parts.append("Prerequisites: " + _format_list(prerequisites))
    if permissions:
        parts.append("Permissions: " + _format_list(permissions))
    if tools:
        parts.append("Tools: " + _format_list(tools))
    if applies_to:
        parts.append("Applies to: " + _format_list(applies_to))
    if side_effects:
        parts.append("Side effects: " + _format_list(side_effects))
    if failure_conditions:
        parts.append("Failure conditions: " + _format_list(failure_conditions))
    if safety:
        parts.append("Safety: " + _format_list(safety))
    if completion:
        parts.append("Completion: " + _format_list(completion))
    if rollback:
        parts.append("Rollback: " + str(rollback).strip())
    if procedure:
        parts.append("Procedure: " + str(procedure).strip())
    if steps:
        step_lines = []
        for s in sorted(steps, key=lambda x: x.get("order", 0) if isinstance(x, dict) else 0):
            if isinstance(s, dict):
                step_lines.append(f"{s.get('order', '')}. {s.get('action', '')}".strip())
            else:
                step_lines.append(str(s))
        parts.append("Steps: " + " | ".join(step_lines))
    if body and body != description:
        parts.append(body)

    signals = _format_list(row.get("signals"))
    if signals:
        parts.append("Signals: " + signals)
    tags = _format_list(row.get("tags"))
    if tags:
        parts.append("Tags: " + tags)
    facet_text = _facet_text(metadata)
    if facet_text:
        parts.append("Context: " + facet_text)
    return "\n".join(p for p in parts if p)


def _serialize_declarative(row: Dict[str, Any]) -> str:
    """Serialize best_practices / lessons_learned / trade_knowledge deterministically."""
    category = row.get("category") or "trade_knowledge"
    name = (row.get("name") or "").strip()
    summary = (row.get("summary") or "").strip()
    content = (row.get("content") or "").strip()
    metadata = _coerce_metadata(row.get("metadata"))

    parts: List[str] = [f"[{category}] {name}".strip()]
    if summary:
        parts.append(summary)
    if content:
        parts.append(content)

    signals = _format_list(row.get("signals"))
    if signals:
        parts.append("Signals: " + signals)
    tags = _format_list(row.get("tags"))
    if tags:
        parts.append("Tags: " + tags)
    facet_text = _facet_text(metadata)
    if facet_text:
        parts.append("Context: " + facet_text)
    return "\n".join(p for p in parts if p)


def serialize_knowledge_for_embedding(row: Dict[str, Any]) -> str:
    """Deterministic text serialization of a knowledge record for embedding.

    Category-aware: skills/playbooks include their parsed operational fields;
    declarative categories serialize name + summary + content + signals/tags/
    facets. The output is stable for a given record state so two identical
    records produce identical embeddings.
    """
    category = row.get("category") or "trade_knowledge"
    if category in SKILL_MD_CATEGORIES:
        return _serialize_skill_playbook(row)
    return _serialize_declarative(row)


# ─── end-to-end embed ────────────────────────────────────────────────────────

def current_embedding_model() -> str:
    """The configured embedding model name (empty when unconfigured)."""
    from services.config_helpers import get_llm_config
    config = get_llm_config("embedding") or {}
    return config.get("model_name", "") or ""


async def embed_knowledge_text(row: Dict[str, Any]) -> Tuple[Optional[List[float]], str]:
    """Serialize + embed a knowledge record.

    Returns ``(vector, model_name)``. ``vector`` is ``None`` on any failure so
    callers can fall back to inserting without an embedding. Never raises on
    embedding errors (the whole point is zero-regression on existing paths).
    Provenance stamping is intentionally NOT done here — the DB write
    chokepoint (``insert_knowledge`` / update paths) stamps ``metadata.embedding``
    so every record is covered regardless of which path made it.
    """
    from memory_services import generate_embedding

    text = serialize_knowledge_for_embedding(row)
    model_name = current_embedding_model()
    try:
        vector = await generate_embedding(text)
    except Exception as exc:
        logger.warning("Embedding failed for knowledge %s: %s", row.get("id"), exc)
        return None, model_name
    if not vector:
        return None, model_name
    return vector, model_name


async def embed_knowledge_fields(
    *,
    name: str,
    category: str = "trade_knowledge",
    content: str = "",
    summary: str = "",
    signals: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[List[float]], str]:
    """Convenience wrapper: build a row dict from loose fields and embed it.

    Lets the existing creation paths (generation, telemetry, playbooks, skills,
    Hermes, admin import) route through the canonical serializer without
    constructing a full row dict at every site.
    """
    row = {
        "name": name,
        "category": category,
        "content": content,
        "summary": summary,
        "signals": signals or [],
        "tags": tags or [],
        "metadata": metadata or {},
    }
    return await embed_knowledge_text(row)


async def embed_knowledge_record(
    row: Dict[str, Any],
    *,
    version: int = EMBEDDING_VERSION,
) -> Tuple[Optional[List[float]], Optional[str], Dict[str, Any]]:
    """Serialize + embed a knowledge record and stamp provenance metadata.

    Returns ``(vector, model_name, updated_metadata)``. Used by the
    consolidation apply path and the embedding backfill, where the caller owns
    the metadata write. On embedding failure returns ``(None, model_name,
    metadata_unchanged)``.
    """
    vector, model_name = await embed_knowledge_text(row)
    metadata = _coerce_metadata(row.get("metadata"))
    if not vector:
        return None, model_name, metadata
    updated_metadata = merge_embedding_metadata(
        metadata, model=model_name, vector=vector, version=version
    )
    return vector, model_name, updated_metadata


def embedding_coverage_stats(rows: List[Dict[str, Any]], configured_version: int) -> Dict[str, Any]:
    """Summarize embedding-version coverage for the settings UI / backfill gate.

    Pure function — used both by the settings endpoint and by tests.
    """
    total = len(rows)
    current = 0
    stale = 0
    missing = 0
    by_version: Dict[int, int] = {}
    for row in rows:
        if not row.get("embedding"):
            missing += 1
            continue
        version = get_embedding_version(row)
        by_version[version] = by_version.get(version, 0) + 1
        if version == int(configured_version):
            current += 1
        else:
            stale += 1
    return {
        "total": total,
        "current_version": int(configured_version),
        "compatible": current,
        "stale": stale,
        "missing": missing,
        "coverage": round(current / total, 4) if total else 0.0,
        "by_version": by_version,
    }
