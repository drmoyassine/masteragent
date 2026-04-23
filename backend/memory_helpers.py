"""Pure helpers: entity-type config loader, NER formatters, signal formatter."""
import json
import logging

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


def _get_entity_type_config(entity_type: str) -> dict:
    """Load per-entity-type config from DB, with defaults."""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM memory_entity_type_config WHERE entity_type = %s",
                (entity_type,)
            )
            row = cursor.fetchone()
            if row:
                config = dict(row)
                if isinstance(config.get("metadata_field_map"), str):
                    config["metadata_field_map"] = json.loads(config["metadata_field_map"])
                return config
    except Exception as e:
        logger.warning(f"Could not load entity type config for {entity_type}: {e}")
    return {
        "intelligence_extraction_threshold": 10,
        "intelligence_auto_approve": False,
        "knowledge_auto_promote": False,
        "ner_enabled": True,
        "ner_confidence_threshold": 0.5,
        "ner_schema": None,
        "knowledge_extraction_threshold": None,
        "embedding_enabled": True,
        "pii_scrub_knowledge": True,
        "metadata_field_map": {},
    }


def _format_signal_definitions(signals: list) -> str:
    """Format entity-type signal definitions into a text block for LLM prompt injection.

    Input:  [{"name": "Budget & Readiness", "description": "Evidence of confirmed budget, approved spending"}]
    Output:
      BUDGET & READINESS
      - Evidence of confirmed budget
      - Approved spending
    """
    if not signals:
        return ""
    parts = []
    for signal in signals:
        name = signal.get("name", "Unnamed Signal").upper()
        desc = signal.get("description", "")
        if desc:
            bullets = [f"- {b.strip()}" for b in desc.split(",") if b.strip()]
            parts.append(f"{name}\n" + "\n".join(bullets))
        else:
            parts.append(name)
    return "\n\n".join(parts)


def _format_ner_output(entities: list, intents: list, relationships: list) -> str:
    """Format NER output as readable text for LLM context."""
    parts = []
    if entities:
        entity_lines = [
            f"  - {e.get('name', '?')} ({e.get('entity_type', '?')}, role: {e.get('role', '?')})"
            for e in entities if isinstance(e, dict)
        ]
        parts.append("Entities:\n" + "\n".join(entity_lines))
    if intents:
        parts.append("Signals: " + ", ".join(intents))
    if relationships:
        rel_lines = [
            f"  - {r.get('from', '?')} → {r.get('relation', '?')} → {r.get('to', '?')}"
            for r in relationships if isinstance(r, dict)
        ]
        if rel_lines:
            parts.append("Relationships:\n" + "\n".join(rel_lines))
    return "\n".join(parts) if parts else "(no structured signals extracted)"


def _build_ner_text_payload(interactions: list) -> str:
    """
    Build a text string from interaction content + metadata for NER.
    Uses metadata_field_map to extract relevant fields; falls back to
    concatenating all string-type leaf values.
    """
    parts = []
    for interaction in interactions:
        content = interaction.get("content", "")
        field_map = interaction.get("metadata_field_map") or {}
        if isinstance(field_map, str):
            field_map = json.loads(field_map)
        metadata = interaction.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        meta_text_parts = []
        if field_map:
            for key in ("name_field", "status_field", "summary_field"):
                field_name = field_map.get(key)
                if field_name and metadata.get(field_name):
                    meta_text_parts.append(str(metadata[field_name]))
        else:
            meta_text_parts = [
                str(v) for v in metadata.values()
                if isinstance(v, str) and len(v) > 2
            ]

        if meta_text_parts:
            parts.append(" | ".join(meta_text_parts))
        if content:
            parts.append(content)

    return "\n\n".join(parts)
