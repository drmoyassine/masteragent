"""Prior-context fetchers for the 3 memory tiers.

Each function performs a chronological lookup + an optional semantic (pgvector)
lookup, dedupes by id, and returns formatted text suitable for LLM context
injection.
"""
import logging
from typing import Optional

from core.storage import get_memory_db_context
from memory_services import generate_embedding, get_memory_settings

logger = logging.getLogger(__name__)


async def fetch_prior_memories(
    entity_type: str,
    entity_id: str,
    interaction_date: str,
    raw_text: str,
) -> str:
    """Fetch prior memories (chronological + semantic) for an entity, before
    the given date. Counts come from memory_settings."""
    settings = get_memory_settings()
    chrono_n = settings.get("prior_context_chrono_count", 2)
    semantic_n = settings.get("prior_context_semantic_count", 2)
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            prior = {}

            cursor.execute("""
                SELECT id, date, content_summary FROM memories
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND date < %s AND content_summary IS NOT NULL
                  AND LENGTH(TRIM(content_summary)) > 20
                ORDER BY date DESC LIMIT %s
            """, (entity_type, entity_id, interaction_date, chrono_n))
            for row in cursor.fetchall():
                prior[row["id"]] = dict(row)

            if semantic_n > 0 and raw_text:
                try:
                    search_emb = await generate_embedding(raw_text[:2000])
                    if search_emb:
                        cursor.execute("""
                            SELECT id, date, content_summary FROM memories
                            WHERE primary_entity_type = %s AND primary_entity_id = %s
                              AND date < %s AND content_summary IS NOT NULL
                              AND LENGTH(TRIM(content_summary)) > 20
                              AND embedding IS NOT NULL
                            ORDER BY embedding <=> %s::vector LIMIT %s
                        """, (entity_type, entity_id, interaction_date,
                              str(search_emb), semantic_n))
                        for row in cursor.fetchall():
                            if row["id"] not in prior:
                                prior[row["id"]] = dict(row)
                except Exception as e:
                    logger.warning(f"Semantic prior memory search failed: {e}")

            if prior:
                sorted_priors = sorted(prior.values(), key=lambda m: str(m["date"]))
                lines = [f"[{m['date']}] {m['content_summary']}" for m in sorted_priors]
                logger.info(f"Injecting {len(prior)} prior memories for {entity_type}/{entity_id}")
                return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Prior memory fetch failed for {entity_type}/{entity_id}: {e}")
    return ""


async def fetch_prior_intelligence(
    entity_type: str,
    entity_id: str,
    query_text: str,
) -> str:
    """Fetch prior intelligence (chronological + semantic) for an entity."""
    settings = get_memory_settings()
    chrono_n = settings.get("prior_intelligence_chrono_count", 3)
    semantic_n = settings.get("prior_intelligence_semantic_count", 2)
    if chrono_n <= 0 and semantic_n <= 0:
        return ""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            prior = {}

            if chrono_n > 0:
                cursor.execute("""
                    SELECT id, name, knowledge_type, content, summary, created_at
                    FROM intelligence
                    WHERE primary_entity_type = %s AND primary_entity_id = %s
                      AND content IS NOT NULL AND LENGTH(TRIM(content)) > 10
                    ORDER BY created_at DESC LIMIT %s
                """, (entity_type, entity_id, chrono_n))
                for row in cursor.fetchall():
                    prior[row["id"]] = dict(row)

            if semantic_n > 0 and query_text:
                try:
                    search_emb = await generate_embedding(query_text[:2000])
                    if search_emb:
                        cursor.execute("""
                            SELECT id, name, knowledge_type, content, summary, created_at
                            FROM intelligence
                            WHERE primary_entity_type = %s AND primary_entity_id = %s
                              AND embedding IS NOT NULL
                              AND content IS NOT NULL AND LENGTH(TRIM(content)) > 10
                            ORDER BY embedding <=> %s::vector LIMIT %s
                        """, (entity_type, entity_id, str(search_emb), semantic_n))
                        for row in cursor.fetchall():
                            if row["id"] not in prior:
                                prior[row["id"]] = dict(row)
                except Exception as e:
                    logger.warning(f"Semantic prior intelligence search failed: {e}")

            if prior:
                sorted_intel = sorted(prior.values(), key=lambda x: str(x.get("created_at", "")))
                lines = [
                    f"[{i.get('knowledge_type', 'other')}] {i.get('name', '')}: "
                    f"{i.get('summary') or i.get('content', '')[:200]}"
                    for i in sorted_intel
                ]
                logger.info(f"Injecting {len(prior)} prior intelligence for {entity_type}/{entity_id}")
                return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Prior intelligence fetch failed: {e}")
    return ""


async def fetch_prior_knowledge_semantic(
    query_text: str,
    count: int,
    *,
    log_label: str = "prior knowledge",
) -> str:
    """Fetch global knowledge via semantic search (no entity filter)."""
    if count <= 0 or not query_text:
        return ""
    try:
        search_emb = await generate_embedding(query_text[:2000])
        if not search_emb:
            return ""
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, knowledge_type, content, summary
                FROM knowledge
                WHERE embedding IS NOT NULL
                  AND content IS NOT NULL AND LENGTH(TRIM(content)) > 10
                ORDER BY embedding <=> %s::vector LIMIT %s
            """, (str(search_emb), count))
            rows = [dict(r) for r in cursor.fetchall()]

        if rows:
            lines = [
                f"[{k.get('knowledge_type', 'other')}] {k.get('name', '')}: "
                f"{k.get('summary') or k.get('content', '')[:200]}"
                for k in rows
            ]
            logger.info(f"Injecting {len(rows)} {log_label} items")
            return "\n".join(lines)
    except Exception as e:
        logger.warning(f"{log_label} fetch failed: {e}")
    return ""
