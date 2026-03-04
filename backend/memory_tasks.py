"""
memory_tasks.py — Background task loop for the Memory System

Tasks:
  1. run_daily_memory_generation()
     - For each entity with pending interactions from yesterday:
       * Build NER text payload from content + metadata_field_map
       * Run GLiNER NER (if enabled for entity type)
       * Summarize (reuse metadata summary_field or call LLM)
       * Generate embedding
       * Upsert memory record (one per entity per day)
       * Mark interactions as done, flush from Redis
       * Check compaction threshold

  2. run_compaction_check()
     - For each entity where uncompacted memory count >= threshold:
       * Call compact_entity() to generate an Insight

  3. compact_entity()
     - LLM distills N memories into a single Insight (draft)
     - If entity_type.insight_auto_approve → auto-confirm

  4. promote_to_lesson()
     - PII scrub + generalize an Insight into a Lesson

  5. check_rate_limit()
     - Per-agent rate limiting (in-memory, single-instance)
"""
import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from core.storage import get_memory_db_context, flush_interaction_cache
from memory_services import (
    call_llm,
    extract_entities,
    generate_embedding,
    get_llm_config,
    get_memory_settings,
    get_system_prompt,
    scrub_pii,
    summarize_text,
)

logger = logging.getLogger(__name__)

# ── Rate limiting (per-agent, in-memory) ────────────────────────────────────
_rate_limit_counters: dict = defaultdict(lambda: {"count": 0, "window_start": None})

def check_rate_limit(agent_id: str) -> bool:
    """Return True if agent is within rate limit, False if exceeded."""
    settings = get_memory_settings()
    if not settings.get("rate_limit_enabled", False):
        return True

    limit = settings.get("rate_limit_per_minute", 60)
    now = datetime.now(timezone.utc)
    state = _rate_limit_counters[agent_id]

    if state["window_start"] is None or (now - state["window_start"]).seconds >= 60:
        state["count"] = 0
        state["window_start"] = now

    state["count"] += 1
    return state["count"] <= limit


# ── Background task loop control ─────────────────────────────────────────────
_task_handle: Optional[asyncio.Task] = None


async def start_background_tasks():
    """Start the background task loop. Called once during app startup (lifespan)."""
    global _task_handle
    if _task_handle and not _task_handle.done():
        logger.warning("Background tasks already running")
        return
    _task_handle = asyncio.create_task(_background_loop())
    logger.info("Memory system background tasks started")


async def stop_background_tasks():
    """Cancel the background task loop. Called during app shutdown."""
    global _task_handle
    if _task_handle and not _task_handle.done():
        _task_handle.cancel()
        try:
            await _task_handle
        except asyncio.CancelledError:
            pass
    logger.info("Memory system background tasks stopped")


async def _background_loop():
    """
    Main background loop.
    Runs every 5 minutes:
      - generate daily memories from pending interactions
      - check compaction thresholds
    """
    while True:
        try:
            await run_daily_memory_generation()
            await run_compaction_check()
        except Exception as e:
            logger.error(f"Background loop error: {e}", exc_info=True)
        await asyncio.sleep(300)  # 5 minutes


# ── Daily Memory Generation ──────────────────────────────────────────────────

async def run_daily_memory_generation():
    """
    For each entity with pending interactions from yesterday (or older),
    build a NER-enriched, embedded daily memory record.
    """
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT primary_entity_type, primary_entity_id,
                   DATE(timestamp) AS interaction_date
            FROM interactions
            WHERE status = 'pending'
              AND DATE(timestamp) <= %s
            ORDER BY interaction_date
        """, (yesterday,))
        entities_with_pending = cursor.fetchall()

    if not entities_with_pending:
        return

    for row in entities_with_pending:
        entity_type = row["primary_entity_type"]
        entity_id = row["primary_entity_id"]
        interaction_date = str(row["interaction_date"])
        try:
            await _generate_memory_for_entity(entity_type, entity_id, interaction_date)
        except Exception as e:
            logger.error(f"Memory generation failed for {entity_type}/{entity_id} on {interaction_date}: {e}")


async def _generate_memory_for_entity(entity_type: str, entity_id: str, interaction_date: str):
    """Generate a single daily memory record for one entity on one date."""

    # 1. Fetch entity type config
    config = _get_entity_type_config(entity_type)

    # 2. Fetch all pending interactions for this entity+date
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, metadata, metadata_field_map, interaction_type
            FROM interactions
            WHERE primary_entity_type = %s
              AND primary_entity_id = %s
              AND DATE(timestamp) = %s
              AND status = 'pending'
            ORDER BY timestamp
        """, (entity_type, entity_id, interaction_date))
        interactions = [dict(r) for r in cursor.fetchall()]

    if not interactions:
        return

    interaction_ids = [i["id"] for i in interactions]

    # 3. Build NER text payload from content + metadata
    ner_payload = _build_ner_text_payload(interactions)

    # 4. NER extraction (if enabled for this entity type)
    related_entities = []
    intents = []
    relationships = []

    if config.get("ner_enabled", True):
        try:
            threshold = config.get("ner_confidence_threshold", 0.5)
            ner_results = await extract_entities(
                ner_payload,
                confidence_threshold=threshold
            )
            related_entities = ner_results.get("entities", [])
            intents = ner_results.get("intents", [])
            relationships = ner_results.get("relationships", [])
        except Exception as e:
            logger.warning(f"NER failed for {entity_type}/{entity_id}: {e}")

    # 5. Summarization (token-gated: reuse metadata summary if present)
    content_summary = _extract_metadata_summary(interactions)
    if not content_summary:
        combined_text = "\n\n".join(i["content"] for i in interactions if i["content"])
        if combined_text:
            content_summary = await summarize_text(combined_text)

    # 6. Embedding
    embedding = None
    if config.get("embedding_enabled", True) and content_summary:
        try:
            embedding = await generate_embedding(content_summary)
        except Exception as e:
            logger.warning(f"Embedding failed for {entity_type}/{entity_id}: {e}")

    # 7. Upsert memory (one per entity per day — ON CONFLICT UPDATE)
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        # Check if memory already exists for this entity+date
        cursor.execute("""
            SELECT id, interaction_ids, interaction_count
            FROM memories
            WHERE date = %s AND primary_entity_type = %s AND primary_entity_id = %s
        """, (interaction_date, entity_type, entity_id))
        existing = cursor.fetchone()

        if existing:
            # Merge interaction IDs
            existing_ids = list(existing["interaction_ids"] or [])
            merged_ids = list(set(existing_ids + interaction_ids))
            vec_expr = "embedding = %s, " if embedding else ""
            vec_params = [embedding] if embedding else []
            cursor.execute(f"""
                UPDATE memories
                SET interaction_ids = %s, interaction_count = %s,
                    content_summary = %s, related_entities = %s,
                    intents = %s, relationships = %s,
                    {vec_expr}updated_at = NOW()
                WHERE id = %s
            """, [
                merged_ids, len(merged_ids),
                content_summary,
                json.dumps(related_entities),
                intents,
                json.dumps(relationships),
            ] + vec_params + [existing["id"]])
            memory_id = existing["id"]
        else:
            memory_id = str(uuid.uuid4())
            if embedding:
                cursor.execute("""
                    INSERT INTO memories (
                        id, date, primary_entity_type, primary_entity_id,
                        interaction_ids, interaction_count, content_summary,
                        related_entities, intents, relationships, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    memory_id, interaction_date, entity_type, entity_id,
                    interaction_ids, len(interaction_ids), content_summary,
                    json.dumps(related_entities), intents,
                    json.dumps(relationships), embedding,
                ))
            else:
                cursor.execute("""
                    INSERT INTO memories (
                        id, date, primary_entity_type, primary_entity_id,
                        interaction_ids, interaction_count, content_summary,
                        related_entities, intents, relationships
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    memory_id, interaction_date, entity_type, entity_id,
                    interaction_ids, len(interaction_ids), content_summary,
                    json.dumps(related_entities), intents,
                    json.dumps(relationships),
                ))

        # 8. Mark interactions as done
        cursor.execute("""
            UPDATE interactions SET status = 'done'
            WHERE id = ANY(%s)
        """, (interaction_ids,))

    # 9. Flush from Redis
    for iid in interaction_ids:
        flush_interaction_cache(iid)

    logger.info(f"Generated memory {memory_id} for {entity_type}/{entity_id} on {interaction_date} "
                f"({len(interaction_ids)} interactions)")

    # 10. Check compaction threshold
    await _check_compaction_trigger(entity_type, entity_id, config)


# ── Compaction Check ─────────────────────────────────────────────────────────

async def run_compaction_check():
    """Check all entities for compaction threshold and trigger if needed."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT primary_entity_type, primary_entity_id, COUNT(*) as uncompacted_count
            FROM memories
            WHERE compacted = FALSE
            GROUP BY primary_entity_type, primary_entity_id
        """)
        entities = cursor.fetchall()

    for row in entities:
        entity_type = row["primary_entity_type"]
        entity_id = row["primary_entity_id"]
        count = row["uncompacted_count"]
        config = _get_entity_type_config(entity_type)
        threshold = config.get("compaction_threshold", 10)
        if count >= threshold:
            try:
                await compact_entity(entity_type, entity_id)
            except Exception as e:
                logger.error(f"Compaction failed for {entity_type}/{entity_id}: {e}")


async def _check_compaction_trigger(entity_type: str, entity_id: str, config: dict):
    """Check whether compaction should trigger for this entity right now."""
    threshold = config.get("compaction_threshold", 10)
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM memories
            WHERE primary_entity_type = %s AND primary_entity_id = %s AND compacted = FALSE
        """, (entity_type, entity_id))
        count = cursor.fetchone()["cnt"]

    if count >= threshold:
        await compact_entity(entity_type, entity_id)


# ── Compaction: Insight Generation ───────────────────────────────────────────

async def compact_entity(entity_type: str, entity_id: str):
    """
    Generate an Insight from the N most recent uncompacted memories.
    """
    config = _get_entity_type_config(entity_type)
    threshold = config.get("compaction_threshold", 10)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, content_summary, related_entities, intents
            FROM memories
            WHERE primary_entity_type = %s AND primary_entity_id = %s
              AND compacted = FALSE
            ORDER BY date ASC
            LIMIT %s
        """, (entity_type, entity_id, threshold))
        memories = [dict(r) for r in cursor.fetchall()]

    if not memories:
        return

    memory_ids = [m["id"] for m in memories]

    # Build LLM context
    context_parts = []
    for m in memories:
        related = m.get("related_entities") or []
        if isinstance(related, str):
            related = json.loads(related)
        intents = m.get("intents") or []
        context_parts.append(
            f"[{m['date']}] {m.get('content_summary', '')}\n"
            f"  Entities: {', '.join(e.get('name', '') for e in related if isinstance(e, dict))}\n"
            f"  Signals: {', '.join(intents)}"
        )

    context = "\n\n".join(context_parts)
    system_prompt = get_system_prompt("insight_generation") or (
        "You are an AI analyst. Based on the provided memory summaries, identify a meaningful pattern, "
        "risk, opportunity, or behavioral insight. Return JSON only: "
        "{\"name\": \"...\", \"insight_type\": \"...\", \"content\": \"...\", \"summary\": \"...\"}"
    )

    llm_config = get_llm_config("insight_generation")
    if not llm_config:
        logger.warning(f"No LLM config for insight_generation — skipping compaction for {entity_type}/{entity_id}")
        return

    try:
        user_msg = f"Entity: {entity_type} / {entity_id}\n\n{context}"
        result_text = await call_llm(
            user_msg,
            system_prompt=system_prompt,
            max_tokens=800,
            task_type="insight_generation"
        )
        result = json.loads(result_text)
    except Exception as e:
        logger.error(f"Insight LLM call failed: {e}")
        return

    name = result.get("name", "Unnamed Insight")
    insight_type = result.get("insight_type", "other")
    content = result.get("content", "")
    summary = result.get("summary", "")

    if not content:
        return

    # Generate embedding for insight
    embedding = None
    try:
        embedding = await generate_embedding(f"{name}. {summary or content}")
    except Exception as e:
        logger.warning(f"Insight embedding failed: {e}")

    auto_approve = config.get("insight_auto_approve", False)
    status = "confirmed" if auto_approve else "draft"
    insight_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        if embedding:
            cursor.execute("""
                INSERT INTO insights (
                    id, primary_entity_type, primary_entity_id, source_memory_ids,
                    insight_type, name, content, summary, embedding,
                    status, created_by, confirmed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                insight_id, entity_type, entity_id, memory_ids,
                insight_type, name, content, summary, embedding,
                status, "auto", now if auto_approve else None, now, now,
            ))
        else:
            cursor.execute("""
                INSERT INTO insights (
                    id, primary_entity_type, primary_entity_id, source_memory_ids,
                    insight_type, name, content, summary,
                    status, created_by, confirmed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                insight_id, entity_type, entity_id, memory_ids,
                insight_type, name, content, summary,
                status, "auto", now if auto_approve else None, now, now,
            ))

        # Mark source memories as compacted
        cursor.execute("""
            UPDATE memories SET compacted = TRUE, compaction_count = compaction_count + 1
            WHERE id = ANY(%s)
        """, (memory_ids,))

    logger.info(f"Created insight {insight_id} ({status}) for {entity_type}/{entity_id} from {len(memory_ids)} memories")

    # Auto-promote to lesson if configured
    lesson_auto_promote = config.get("lesson_auto_promote", False)
    if auto_approve and lesson_auto_promote:
        await promote_to_lesson(insight_id)


# ── Lesson Promotion ─────────────────────────────────────────────────────────

async def promote_to_lesson(insight_id: str):
    """
    PII scrub + generalize an Insight and write it as a Lesson.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, primary_entity_type, primary_entity_id, source_memory_ids,
                   insight_type, name, content, summary
            FROM insights WHERE id = %s
        """, (insight_id,))
        insight = cursor.fetchone()

    if not insight:
        logger.warning(f"promote_to_lesson: insight {insight_id} not found")
        return

    content = insight["content"]
    summary = insight["summary"] or ""

    # PII scrub
    try:
        content = await scrub_pii(content)
        summary = await scrub_pii(summary) if summary else ""
    except Exception as e:
        logger.warning(f"PII scrub failed for insight {insight_id}: {e}")

    # Generalize (remove entity-specific references)
    system_prompt = (
        "You are an AI editor. Remove all specific entity names, organization names, and other "
        "identifying information from the following text, replacing with generic terms (e.g., 'the client', "
        "'the institution'). Preserve the insight's meaning. Return only the edited text."
    )
    try:
        generalize_prompt = (
            "You are an AI editor. Remove all specific entity names, organization names, and other "
            "identifying information from the following text, replacing with generic terms (e.g., 'the client', "
            "'the institution'). Preserve the insight's meaning. Return only the edited text."
        )
        content = await call_llm(
            content,
            system_prompt=generalize_prompt,
            max_tokens=600,
            task_type="summarization"
        )
    except Exception as e:
        logger.warning(f"Lesson generalization failed: {e}")

    # Embed lesson
    embedding = None
    try:
        embedding = await generate_embedding(f"{insight['name']}. {summary or content}")
    except Exception as e:
        logger.warning(f"Lesson embedding failed: {e}")

    lesson_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
            cursor.execute("""
                INSERT INTO lessons (
                    id, source_insight_ids, lesson_type, name, content, summary,
                    embedding, visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                lesson_id, [insight_id], insight["insight_type"],
                insight["name"], content, summary, embedding,
                "shared", [], now, now,
            ))
        else:
            cursor.execute("""
                INSERT INTO lessons (
                    id, source_insight_ids, lesson_type, name, content, summary,
                    visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                lesson_id, [insight_id], insight["insight_type"],
                insight["name"], content, summary,
                "shared", [], now, now,
            ))

    logger.info(f"Promoted insight {insight_id} to lesson {lesson_id}")


# ── Helper Functions ─────────────────────────────────────────────────────────

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
        "compaction_threshold": 10,
        "insight_auto_approve": False,
        "lesson_auto_promote": False,
        "ner_enabled": True,
        "ner_confidence_threshold": 0.5,
        "embedding_enabled": True,
        "pii_scrub_lessons": True,
        "metadata_field_map": {},
    }


def _extract_metadata_summary(interactions: list) -> Optional[str]:
    """
    Try to extract a pre-computed summary from interaction metadata
    using the metadata_field_map. Avoids an LLM call if summary exists.
    """
    for interaction in interactions:
        field_map = interaction.get("metadata_field_map") or {}
        if isinstance(field_map, str):
            field_map = json.loads(field_map)
        metadata = interaction.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        summary_field = field_map.get("summary_field") or "ai_summary"
        value = metadata.get(summary_field)
        if value and isinstance(value, str) and len(value.strip()) > 20:
            return value.strip()

    return None


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
            # Fallback: concatenate all string leaf values
            meta_text_parts = [
                str(v) for v in metadata.values()
                if isinstance(v, str) and len(v) > 2
            ]

        if meta_text_parts:
            parts.append(" | ".join(meta_text_parts))
        if content:
            parts.append(content)

    return "\n\n".join(parts)
