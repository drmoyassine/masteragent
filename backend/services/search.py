"""services/search.py — pgvector semantic search & multi-lingual full text search across all memory tiers"""
import logging
from typing import Any, Dict, List

from core.storage import get_memory_db_context

logger = logging.getLogger(__name__)

# The daily penalty for chronological time decay on vector search scores (0.005 = 0.5% drop per day)
DECAY_RATE = 0.005

# ============================================
# TIER 0: Interactions (Pending)
# ============================================

async def search_interactions_by_vector(
    query_vector: List[float],
    entity_id: str = None,
    entity_type: str = None,
    entity_subtype: str = None,
    since: str = None,
    until: str = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if not query_vector: return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = ["embedding IS NOT NULL", "status = 'pending'"], []
            if entity_id:
                conditions.append("primary_entity_id = %s"); params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s"); params.append(entity_type)
            if entity_subtype:
                conditions.append("primary_entity_subtype = %s"); params.append(entity_subtype)
            if since:
                conditions.append("timestamp >= %s"); params.append(since)
            if until:
                conditions.append("timestamp <= %s"); params.append(until)
            
            where = " AND ".join(conditions)
            decay_sql = f"(EXTRACT(EPOCH FROM (NOW() - timestamp))/86400) * {DECAY_RATE}"
            
            cursor.execute(f"""
                SELECT id, timestamp as date, primary_entity_type, primary_entity_id,
                       content as content_summary, created_at,
                       GREATEST(0, (1 - (embedding <=> %s::vector)) - {decay_sql}) AS score
                FROM interactions WHERE {where}
                ORDER BY score DESC LIMIT %s
            """, [query_vector] + params + [limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector interaction search error: {e}")
        return []

async def search_interactions_by_fulltext(
    query: str,
    entity_id: str = None,
    entity_type: str = None,
    entity_subtype: str = None,
    since: str = None,
    until: str = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if not query: return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = ["status = 'pending'"], []
            if entity_id:
                conditions.append("primary_entity_id = %s"); params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s"); params.append(entity_type)
            if entity_subtype:
                conditions.append("primary_entity_subtype = %s"); params.append(entity_subtype)
            if since:
                conditions.append("timestamp >= %s"); params.append(since)
            if until:
                conditions.append("timestamp <= %s"); params.append(until)
            
            conditions.append("to_tsvector('simple', coalesce(content, '')) @@ websearch_to_tsquery('simple', %s)")
            params.append(query)
            
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, timestamp as date, primary_entity_type, primary_entity_id,
                       content as content_summary, created_at,
                       ts_rank(to_tsvector('simple', coalesce(content, '')), websearch_to_tsquery('simple', %s)) AS score
                FROM interactions WHERE {where}
                ORDER BY score DESC LIMIT %s
            """, [query] + params + [limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"fulltext interaction search error: {e}")
        return []

# ============================================
# TIER 1: Memories
# ============================================

async def search_memories_by_vector(
    query_vector: List[float],
    entity_id: str = None,
    entity_type: str = None,
    entity_subtype: str = None,
    since: str = None,
    until: str = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    if not query_vector: return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = ["embedding IS NOT NULL"], []
            if entity_id:
                conditions.append("primary_entity_id = %s"); params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s"); params.append(entity_type)
            # Tier 1 doesn't store subtype directly in schema, ignore entity_subtype for now
            if since:
                conditions.append("date >= %s"); params.append(since)
            if until:
                conditions.append("date <= %s"); params.append(until)
            
            where = " AND ".join(conditions)
            decay_sql = f"(EXTRACT(EPOCH FROM (NOW() - date::timestamp))/86400) * {DECAY_RATE}"
            
            cursor.execute(f"""
                SELECT id, date, primary_entity_type, primary_entity_id,
                       content_summary, related_entities, intents, created_at,
                       GREATEST(0, (1 - (embedding <=> %s::vector)) - {decay_sql}) AS score
                FROM memories WHERE {where}
                ORDER BY score DESC LIMIT %s
            """, [query_vector] + params + [limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector memory search error: {e}")
        return []

async def search_memories_by_fulltext(
    query: str,
    entity_id: str = None,
    entity_type: str = None,
    entity_subtype: str = None,
    since: str = None,
    until: str = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    if not query: return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = [], []
            if entity_id:
                conditions.append("primary_entity_id = %s"); params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s"); params.append(entity_type)
            if since:
                conditions.append("date >= %s"); params.append(since)
            if until:
                conditions.append("date <= %s"); params.append(until)
            
            conditions.append("to_tsvector('simple', coalesce(content_summary, '')) @@ websearch_to_tsquery('simple', %s)")
            params.append(query)
            
            where = " AND ".join(conditions) if conditions else "1=1"
            cursor.execute(f"""
                SELECT id, date, primary_entity_type, primary_entity_id,
                       content_summary, related_entities, intents, created_at,
                       ts_rank(to_tsvector('simple', coalesce(content_summary, '')), websearch_to_tsquery('simple', %s)) AS score
                FROM memories WHERE {where}
                ORDER BY score DESC LIMIT %s
            """, [query] + params + [limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"fulltext memory search error: {e}")
        return []


# ============================================
# TIER 2: intelligence
# ============================================

async def search_intelligence_by_vector(
    query_vector: List[float],
    entity_id: str = None,
    entity_type: str = None,
    entity_subtype: str = None,
    since: str = None,
    until: str = None,
    status: str = "confirmed",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if not query_vector: return []
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
            if since:
                conditions.append("created_at >= %s"); params.append(since)
            if until:
                conditions.append("created_at <= %s"); params.append(until)
                
            where = " AND ".join(conditions)
            decay_sql = f"(EXTRACT(EPOCH FROM (NOW() - created_at))/86400) * {DECAY_RATE}"
            
            cursor.execute(f"""
                SELECT id, primary_entity_type, primary_entity_id,
                       knowledge_type, name, summary, status, created_at,
                       GREATEST(0, (1 - (embedding <=> %s::vector)) - {decay_sql}) AS score
                FROM intelligence WHERE {where}
                ORDER BY score DESC LIMIT %s
            """, [query_vector] + params + [limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector Intelligence search error: {e}")
        return []

async def search_intelligence_by_fulltext(
    query: str,
    entity_id: str = None,
    entity_type: str = None,
    entity_subtype: str = None,
    since: str = None,
    until: str = None,
    status: str = "confirmed",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if not query: return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = [], []
            if entity_id:
                conditions.append("primary_entity_id = %s"); params.append(entity_id)
            if entity_type:
                conditions.append("primary_entity_type = %s"); params.append(entity_type)
            if status:
                conditions.append("status = %s"); params.append(status)
            if since:
                conditions.append("created_at >= %s"); params.append(since)
            if until:
                conditions.append("created_at <= %s"); params.append(until)
                
            conditions.append("to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')) @@ websearch_to_tsquery('simple', %s)")
            params.append(query)
            
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, primary_entity_type, primary_entity_id,
                       knowledge_type, name, summary, status, created_at,
                       ts_rank(to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')), websearch_to_tsquery('simple', %s)) AS score
                FROM intelligence WHERE {where}
                ORDER BY score DESC LIMIT %s
            """, [query] + params + [limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"fulltext Intelligence search error: {e}")
        return []


# ============================================
# TIER 3: knowledge
# ============================================

async def search_knowledge_by_vector(
    query_vector: List[float],
    knowledge_type: str = None,
    entity_type: str = None,
    entity_subtype: str = None,
    since: str = None,
    until: str = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if not query_vector: return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = ["embedding IS NOT NULL", "visibility = 'shared'"], []
            if knowledge_type:
                conditions.append("knowledge_type = %s"); params.append(knowledge_type)
            if since:
                conditions.append("created_at >= %s"); params.append(since)
            if until:
                conditions.append("created_at <= %s"); params.append(until)
                
            # Note: knowledge implicitly ignore entity_id per schema, but 
            # tags or metadata could eventually store entity_type natively if we wanted.
            
            where = " AND ".join(conditions)
            decay_sql = f"(EXTRACT(EPOCH FROM (NOW() - created_at))/86400) * {DECAY_RATE}"
            
            cursor.execute(f"""
                SELECT id, knowledge_type, name, summary, visibility, tags, created_at,
                       GREATEST(0, (1 - (embedding <=> %s::vector)) - {decay_sql}) AS score
                FROM knowledge WHERE {where}
                ORDER BY score DESC LIMIT %s
            """, [query_vector] + params + [limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"pgvector Knowledge search error: {e}")
        return []

async def search_knowledge_by_fulltext(
    query: str,
    knowledge_type: str = None,
    entity_type: str = None,
    entity_subtype: str = None,
    since: str = None,
    until: str = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if not query: return []
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            conditions, params = ["visibility = 'shared'"], []
            if knowledge_type:
                conditions.append("knowledge_type = %s"); params.append(knowledge_type)
            if since:
                conditions.append("created_at >= %s"); params.append(since)
            if until:
                conditions.append("created_at <= %s"); params.append(until)
                
            conditions.append("to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')) @@ websearch_to_tsquery('simple', %s)")
            params.append(query)
            
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT id, knowledge_type, name, summary, visibility, tags, created_at,
                       ts_rank(to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')), websearch_to_tsquery('simple', %s)) AS score
                FROM knowledge WHERE {where}
                ORDER BY score DESC LIMIT %s
            """, [query] + params + [limit])
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"fulltext Knowledge search error: {e}")
        return []

