"""DB write helpers for memory tier inserts.

Collapses the embed/no-embed branches that used to live inline in
memory_tasks.py. Pgvector accepts NULL for the embedding column, so we
always pass it as a single parameter.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from core.storage import get_memory_db_context


def insert_memory(
    *,
    memory_id: str,
    interaction_date: str,
    entity_type: str,
    entity_id: str,
    interaction_ids: list,
    content_summary: str,
    related_entities: list,
    intents: list,
    relationships: list,
    embedding: Optional[list],
    processing_errors: dict,
) -> None:
    """INSERT a row into memories. Marks source interactions as done and
    clears their ephemeral embeddings. Idempotent on (date, entity_type, entity_id)."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memories (
                id, date, primary_entity_type, primary_entity_id,
                interaction_ids, interaction_count, content_summary,
                related_entities, intents, relationships, embedding, processing_errors
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, primary_entity_type, primary_entity_id) DO NOTHING
        """, (
            memory_id, interaction_date, entity_type, entity_id,
            interaction_ids, len(interaction_ids), content_summary,
            json.dumps(related_entities), intents,
            json.dumps(relationships), embedding, json.dumps(processing_errors),
        ))

        cursor.execute("""
            UPDATE interactions SET status = 'done', embedding = NULL
            WHERE id = ANY(%s) AND status IN ('pending', 'failed')
        """, (interaction_ids,))


def insert_intelligence(
    *,
    insight_id: str,
    entity_type: str,
    entity_id: str,
    memory_ids: list,
    knowledge_type: str,
    name: str,
    content: str,
    summary: str,
    embedding: Optional[list],
    auto_approve: bool,
) -> None:
    """INSERT a row into intelligence and mark source memories as compacted."""
    status = "confirmed" if auto_approve else "draft"
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO intelligence (
                id, primary_entity_type, primary_entity_id, source_memory_ids,
                knowledge_type, name, content, summary, embedding,
                status, created_by, confirmed_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            insight_id, entity_type, entity_id, memory_ids,
            knowledge_type, name, content, summary, embedding,
            status, "auto", now if auto_approve else None, now, now,
        ))

        cursor.execute("""
            UPDATE memories SET compacted = TRUE, compaction_count = compaction_count + 1
            WHERE id = ANY(%s)
        """, (memory_ids,))


def insert_knowledge(
    *,
    knowledge_id: str,
    intelligence_ids: list,
    knowledge_type: str,
    name: str,
    content: str,
    summary: str,
    embedding: Optional[list],
    tags: list,
    visibility: str = "shared",
) -> None:
    """INSERT a row into knowledge."""
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO knowledge (
                id, source_intelligence_ids, knowledge_type, name, content, summary,
                embedding, visibility, tags, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            knowledge_id, intelligence_ids, knowledge_type, name, content, summary,
            embedding, visibility, tags, now, now,
        ))
