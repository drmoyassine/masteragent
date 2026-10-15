"""Unified Knowledge generation settings and inheritance resolution."""
from __future__ import annotations

from typing import Any, Dict, Optional


PATHWAYS = {
    "declarative_knowledge",
    "telemetry_reflection",
    "playbook_extraction",
    "skill_extraction",
    "manual_creation",
    "import",
}

GLOBAL_FIELDS = {
    "enabled": ("knowledge_generation_enabled", True),
    "schedule_time": ("knowledge_generation_time", "03:00"),
    "max_tokens": ("knowledge_generation_max_tokens", 1200),
    "min_confidence": ("knowledge_generation_min_confidence", 0.60),
    "evidence_threshold": ("knowledge_generation_evidence_threshold", 5),
    "approval_policy": ("knowledge_generation_approval_policy", "approve_immediately"),
}


def resolve_generation_policy(
    pathway: str,
    *,
    settings: Optional[Dict[str, Any]] = None,
    entity_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve entity → pathway → global → default values with source labels."""
    if pathway not in PATHWAYS:
        raise ValueError(f"Unsupported Knowledge generation pathway: {pathway}")
    settings = settings or {}
    entity_config = entity_config or {}
    pathway_values = (settings.get("knowledge_generation_pathway_overrides") or {}).get(pathway) or {}
    entity_values = (entity_config.get("knowledge_generation_overrides") or {}).get(pathway) or {}
    # Legacy declarative threshold remains a read-compatible fallback until all
    # production entity configs have been migrated to the canonical JSONB map.
    if pathway == "declarative_knowledge" and entity_values.get("evidence_threshold") is None:
        legacy_threshold = entity_config.get("knowledge_extraction_threshold")
        if legacy_threshold is not None:
            entity_values = {**entity_values, "evidence_threshold": legacy_threshold}
    values: Dict[str, Any] = {}
    sources: Dict[str, str] = {}
    for field, (global_key, default) in GLOBAL_FIELDS.items():
        if entity_values.get(field) not in (None, "inherit"):
            values[field] = entity_values[field]
            sources[field] = "entity"
        elif pathway_values.get(field) not in (None, "inherit"):
            values[field] = pathway_values[field]
            sources[field] = "pathway"
        elif settings.get(global_key) is not None:
            values[field] = settings[global_key]
            sources[field] = "global"
        else:
            values[field] = default
            sources[field] = "default"
    return {"pathway": pathway, "values": values, "sources": sources}


def approval_status(policy: str) -> str:
    if policy == "approve_immediately":
        return "active"
    if policy == "create_as_draft":
        return "draft"
    raise ValueError(f"Unsupported approval policy: {policy}")
