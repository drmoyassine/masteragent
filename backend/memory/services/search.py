"""memory/services/search.py — pgvector semantic search across all memory tiers"""
import logging
from typing import Any, Dict, List, Optional

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)


async def search_memories_by_vector(
    query_vector: List[float],
    entity_id: str = None,
    entity_type: str = None,
    since: str = None,
    until: str = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Semantic search over the memories table using pgvector cosine distance."""
    if not query_vector:
        return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = ["embedding IS NOT NULL"], []
            if entity_id:
                conditions.append("primary_entity_id = %s"); params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s"); params.append(entity_type)
            if since:
                conditions.append("date >= %s"); params.append(since)
            if until:
                conditions.append("date <= %s"); params.append(until)
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, date, primary_entity_type, primary_entity_id,
                       content_summary, related_entities, intents, created_at,
                       1 - (embedding <=> %s::vector) AS score
                FROM memories WHERE {where}
                ORDER BY embedding <=> %s::vector LIMIT %s
            """, params + [query_vector, query_vector, limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector memory search error: {e}")
        return []


async def search_intelligence_by_vector(
    query_vector: List[float],
    entity_id: str = None,
    entity_type: str = None,
    status: str = "confirmed",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Semantic search over the intelligence table."""
    if not query_vector:
        return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = ["embedding IS NOT NULL"], []
            if entity_id:
                conditions.append("primary_entity_id = %s"); params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s"); params.append(entity_type)
            if status:
                conditions.append("status = %s"); params.append(status)
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, primary_entity_type, primary_entity_id,
                       knowledge_type, name, summary, status, created_at,
                       1 - (embedding <=> %s::vector) AS score
                FROM intelligence WHERE {where}
                ORDER BY embedding <=> %s::vector LIMIT %s
            """, params + [query_vector, query_vector, limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector Intelligence search error: {e}")
        return []


async def search_knowledge_by_vector(
    query_vector: List[float],
    knowledge_type: str = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Semantic search over the knowledge table."""
    if not query_vector:
        return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = ["embedding IS NOT NULL", "visibility = 'shared'"], []
            if knowledge_type:
                conditions.append("knowledge_type = %s"); params.append(knowledge_type)
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, knowledge_type, name, summary, visibility, tags, created_at,
                       1 - (embedding <=> %s::vector) AS score
                FROM knowledge WHERE {where}
                ORDER BY embedding <=> %s::vector LIMIT %s
            """, params + [query_vector, query_vector, limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector Knowledge search error: {e}")
        return []


