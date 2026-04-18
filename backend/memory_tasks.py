"""
memory_tasks.py — Background task loop for the Memory System

Tasks:
  1. _background_loop()
     - Schedule-aware: fires at user-configured time (memory_generation_time) once per day
     - Uses memory_job_log to prevent double-firing

  2. run_daily_memory_generation()
     - For each entity with pending interactions older than today:
       * Build NER text payload and run entity extraction (schema-constrained)
       * Build LLM context based on memory_generation_mode:
           'ner_only'     → NER output only → LLM → content_summary
           'ner_and_raw'  → raw interactions + NER output → LLM → content_summary
       * Generate embedding for content_summary
       * Write one memory row per entity per day (once — no upsert if already done)
       * Check compaction (count + days triggers)

  3. compact_entity()
     - PrivateKnowledge generation: N memories → LLM → PrivateKnowledge

  4. run_lesson_check()
     - PublicKnowledge accumulation: N confirmed private_knowledge → PII scrub + LLM → PublicKnowledge

  5. promote_to_lesson()
     - Keep for manual 1:1 admin promotion of a single PrivateKnowledge

  6. check_rate_limit()
     - Per-agent rate limiting (in-memory, single-instance)

Embedding scope: ONLY memories, private_knowledge, and public_knowledge are embedded.
Interactions are never embedded.
"""
import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from core.storage import get_memory_db_context, flush_interaction_cache, cache_interaction
from memory_services import (
    call_llm,
    extract_entities,
    generate_embedding,
    get_llm_config,
    get_memory_settings,
    get_system_prompt,
    scrub_pii,
)
from services.prompt_renderer import inject_variables

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


# ── Ingestion Logic (Worker Flow) ─────────────────────────────────────────────

async def process_interaction(interaction_id: str):
    """
    Worker Task: Fetches a pending interaction, extracts attachments, runs vision AI,
    computes ephemeral embeddings, and flags the interaction as processed or failed.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM interactions WHERE id = %s", (interaction_id,))
        row = cursor.fetchone()
        
    if not row:
        logger.warning(f"process_interaction: Interaction {interaction_id} not found.")
        return
        
    interaction = dict(row)
    # If the interaction is already done or failed, skip processing
    if interaction["status"] not in ["pending", "queued"]:
        logger.info(f"Interaction {interaction_id} is already in status: {interaction['status']}")
        return

    content = interaction.get("content") or ""
    try:
        attachment_refs = json.loads(interaction["attachment_refs"]) if isinstance(interaction.get("attachment_refs"), str) else (interaction.get("attachment_refs") or [])
    except json.JSONDecodeError:
        attachment_refs = []
        
    processing_errors = {}
    if interaction.get("processing_errors"):
        try:
            processing_errors = json.loads(interaction["processing_errors"]) if isinstance(interaction.get("processing_errors"), str) else interaction["processing_errors"]
        except json.JSONDecodeError:
            pass

    # Document OCR parsing logic
    from memory_services import parse_document
    for attachment in attachment_refs:
        if not isinstance(attachment, dict):
            continue
            
        attach_type = attachment.get("type", "base64")
        raw_blob = None
        url = attachment.get("url")
        
        if attach_type == "url":
            if url:
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        raw_blob = resp.content
                except Exception as e:
                    logger.warning(f"Failed to fetch attachment URL {url}: {e}")
        else:
            b64_data = attachment.get("data") or attachment.get("raw_bytes")
            if b64_data:
                import base64
                try:
                    raw_blob = base64.b64decode(b64_data)
                except Exception as e:
                    logger.warning(f"Failed to decode base64 attachment: {e}")

        if not raw_blob:
            continue

        import filetype
        inferred_mime = None
        kind = filetype.guess(raw_blob)
        if kind: inferred_mime = kind.mime
        
        mime_type = inferred_mime or attachment.get("mime_type", "application/octet-stream")
        filename = attachment.get("filename", "attachment")

        try:
            parsed = await parse_document(raw_blob, filename, mime_type)
        except Exception as e:
            logger.error(f"Vision/Processing failed for {filename}: {e}")
            processing_errors["vision"] = str(e)
            parsed = {}
        
        url_context = f" ({url})" if attach_type == "url" and url else ""
        pages_context = f" (Parsed {parsed.get('parsed_pages', parsed.get('pages', 1))} out of {parsed.get('pages', 1)} pages)" if mime_type == "application/pdf" and parsed.get("pages", 0) > 0 else ""
        
        if parsed.get("text"):
            content += f"\n\n---\n[Attachment ({mime_type}): {filename}]{url_context}{pages_context}\n{parsed['text']}"
            attachment["parsed_content"] = parsed["text"]
        else:
            err_msg = processing_errors.get("vision", "Parsing Failed or Document is Empty")
            content += f"\n\n---\n[Attachment ({mime_type}): {filename}]{url_context}{pages_context}\n[Error: {err_msg}]"

        attachment["inferred_mime"] = mime_type

    # Real-time Embeddings generation for Pending Interactions (Ephemeral Vectors)
    embedding = None
    try:
        if content.strip():
            embedding = await generate_embedding(content)
    except Exception as e:
        logger.warning(f"Failed to generate ephemeral interaction embedding: {e}")
        processing_errors["embeddings"] = str(e)
        content += f"\n\n[Processing Error: Embedding Failed - {e}]"

    # Save outputs to Database
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # update query blocks
        if embedding:
            cursor.execute("""
                UPDATE interactions 
                SET content = %s, attachment_refs = %s, embedding = %s, processing_errors = %s, is_enriched = TRUE
                WHERE id = %s
            """, (
                content, json.dumps(attachment_refs, ensure_ascii=False), embedding, 
                json.dumps(processing_errors, ensure_ascii=False), interaction_id
            ))
        else:
            cursor.execute("""
                UPDATE interactions 
                SET content = %s, attachment_refs = %s, processing_errors = %s, is_enriched = TRUE
                WHERE id = %s
            """, (
                content, json.dumps(attachment_refs, ensure_ascii=False), 
                json.dumps(processing_errors, ensure_ascii=False), interaction_id
            ))
            
    # Cache invalidation to reflect accurate embedding in ephemeral searches
    flush_interaction_cache(interaction_id)
    cache_interaction(interaction_id, {
        "id": interaction_id,
        "interaction_type": interaction["interaction_type"],
        "agent_id": interaction.get("agent_id"),
        "content": content,
        "primary_entity_type": interaction["primary_entity_type"],
        "primary_entity_id": interaction["primary_entity_id"],
        "timestamp": str(interaction["timestamp"]),
        "metadata_field_map": json.loads(interaction.get("metadata_field_map") or "{}"),
    })

    # Trigger Outbound Webhooks logic
    try:
        from services.outbound_webhooks import evaluate_outbound_webhooks
        await evaluate_outbound_webhooks(interaction_id)
    except Exception as e:
        logger.error(f"Failed to evaluate outbound webhooks for {interaction_id}: {e}")



# ── Job log helpers (prevent double-firing) ───────────────────────────────────

def get_job_last_date(job_name: str) -> Optional[date]:
    """Return the date the job last ran, or None if never."""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_date FROM memory_job_log WHERE job_name = %s", (job_name,))
            row = cursor.fetchone()
            return row["last_date"] if row else None
    except Exception as e:
        logger.warning(f"get_job_last_date failed: {e}")
        return None


def set_job_last_date(job_name: str, run_date: date):
    """Record that a job ran on run_date."""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_job_log (job_name, last_run, last_date)
                VALUES (%s, NOW(), %s)
                ON CONFLICT (job_name) DO UPDATE SET last_run = NOW(), last_date = EXCLUDED.last_date
            """, (job_name, run_date))
    except Exception as e:
        logger.warning(f"set_job_last_date failed: {e}")


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
    Schedule-aware main background loop.
    Wakes every 60 seconds and checks:
      - Has the configured memory_generation_time passed today?
      - Has the daily memory job already run today?
    Fires once per day at the configured time.
    """
    while True:
        try:
            settings = get_memory_settings()
            scheduled_time = settings.get("memory_generation_time", "02:00")
            try:
                sched_h, sched_m = map(int, scheduled_time.split(":"))
            except Exception:
                sched_h, sched_m = 2, 0

            now_utc = datetime.now(timezone.utc)
            today = now_utc.date()

            # Fire if current time >= scheduled time and job hasn't run today
            if now_utc.hour > sched_h or (now_utc.hour == sched_h and now_utc.minute >= sched_m):
                last_date = get_job_last_date("daily_memory_generation")
                if last_date != today:
                    logger.info(f"Firing daily memory generation (scheduled={scheduled_time} UTC)")
                    set_job_last_date("daily_memory_generation", today)  # mark first to prevent race
                    await run_orphan_sweeper()
                    await run_daily_memory_generation()
                    await run_compaction_check()
                    
                    from memory.queue import knowledge_queue
                    await knowledge_queue.add("generate_lesson", {}, {"priority": 3})

        except Exception as e:
            logger.error(f"Background loop error: {e}", exc_info=True)

        await asyncio.sleep(60)  # check every minute


# ── Daily Memory Generation ──────────────────────────────────────────────────

async def run_orphan_sweeper():
    """Find interactions stuck in pending state for > 6 hours and re-enqueue them."""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            # Compatible with PostgreSQL INTERVAL
            cursor.execute("""
                SELECT id FROM interactions
                WHERE status = 'pending'
                  AND CAST(created_at AS timestamp) < NOW() - INTERVAL '6 hours'
            """)
            orphans = [row["id"] for row in cursor.fetchall()]
            
        if orphans:
            from memory.queue import memory_bulk_queue
            logger.warning(f"Orphan Sweeper: Found {len(orphans)} stuck interactions. Re-enqueueing.")
            for interaction_id in orphans:
                await memory_bulk_queue.add(
                    "ingest_interaction", 
                    {"interaction_id": interaction_id}, 
                    {"attempts": 3, "backoff": {"type": "exponential", "delay": 2000}}
                )
    except Exception as e:
        logger.error(f"Orphan Sweeper failed: {e}")


async def run_daily_memory_generation(include_today: bool = False):
    """
    For each entity with pending interactions from yesterday (or older),
    build a NER-enriched, embedded daily memory record.
    One memory per entity per day — written once (not upserted).
    """
    cutoff_date = date.today().isoformat() if include_today else (date.today() - timedelta(days=1)).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        # Find entity+date combos with pending interactions
        cursor.execute("""
            SELECT DISTINCT primary_entity_type, primary_entity_id,
                   DATE(timestamp) AS interaction_date
            FROM interactions
            WHERE status = 'pending'
              AND DATE(timestamp) <= %s
            ORDER BY interaction_date
        """, (cutoff_date,))
        entities_with_pending = cursor.fetchall()

    if not entities_with_pending:
        return

    for row in entities_with_pending:
        entity_type = row["primary_entity_type"]
        entity_id = row["primary_entity_id"]
        interaction_date = str(row["interaction_date"])

        # Skip if memory already exists for this entity+date (once-per-day guarantee)
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM memories
                WHERE date = %s AND primary_entity_type = %s AND primary_entity_id = %s
            """, (interaction_date, entity_type, entity_id))
            if cursor.fetchone():
                # Memory exists — still mark interactions as done
                cursor.execute("""
                    UPDATE interactions SET status = 'done'
                    WHERE primary_entity_type = %s AND primary_entity_id = %s
                      AND DATE(timestamp) = %s AND status = 'pending'
                """, (entity_type, entity_id, interaction_date))
                continue

        try:
            settings = get_memory_settings()
            retries = int(settings.get("memory_queue_retries", 3))
            delay = int(settings.get("memory_queue_retry_delay", 2000))
            
            from memory.queue import memory_queue
            await memory_queue.add(
                "generate_memory", 
                {"entity_type": entity_type, "entity_id": entity_id, "interaction_date": interaction_date},
                {"priority": 5, "attempts": retries, "backoff": {"type": "exponential", "delay": delay}}
            )
        except Exception as e:
            logger.error(f"Memory enqueue failed for {entity_type}/{entity_id} on {interaction_date}: {e}")


async def _generate_memory_for_entity(entity_type: str, entity_id: str, interaction_date: str):
    """Generate a single daily memory record for one entity on one date."""

    # 1. Fetch entity type config + global settings
    config = _get_entity_type_config(entity_type)
    settings = get_memory_settings()

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

    # 3. Build NER text payload
    ner_payload = _build_ner_text_payload(interactions)

    # 4. NER extraction (schema-constrained if configured)
    related_entities = []
    intents = []
    relationships = []

    if config.get("ner_enabled", True):
        try:
            threshold = config.get("ner_confidence_threshold", 0.5)
            ner_schema = config.get("ner_schema")  # None = use defaults
            ner_results = await extract_entities(
                ner_payload,
                confidence_threshold=threshold,
                ner_schema=ner_schema,
            )
            related_entities = ner_results.get("entities", [])
            intents = ner_results.get("intents", [])
            relationships = ner_results.get("relationships", [])
        except Exception as e:
            logger.warning(f"NER failed for {entity_type}/{entity_id}: {e}")

    # 5. Build LLM context
    ner_summary = _format_ner_output(related_entities, intents, relationships)

    raw_text = "\n\n---\n\n".join(
        i["content"] for i in interactions if i.get("content")
    )
    base_context = (
        f"Entity: {entity_type} / {entity_id}\n"
        f"Date: {interaction_date}\n"
        f"Interaction count: {len(interactions)}\n\n"
        f"--- Raw Interactions ---\n{raw_text}\n\n"
        f"--- Extracted Signals ---\n{ner_summary}"
    )

    # 5.5 Fetch prior memories for context continuity (hardcoded 2+2)
    PRIOR_CHRONO_COUNT = 2
    PRIOR_SEMANTIC_COUNT = 2
    prior_context = ""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            prior_memories = {}

            # Chronological: last 2 memories for this entity
            cursor.execute("""
                SELECT id, date, content_summary FROM memories
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND date < %s AND content_summary IS NOT NULL
                  AND LENGTH(TRIM(content_summary)) > 20
                ORDER BY date DESC LIMIT %s
            """, (entity_type, entity_id, interaction_date, PRIOR_CHRONO_COUNT))
            for row in cursor.fetchall():
                prior_memories[row["id"]] = dict(row)

            # Semantic: top 2 most similar to today's raw text
            if PRIOR_SEMANTIC_COUNT > 0:
                search_text = raw_text or ner_summary
                if search_text:
                    try:
                        search_embedding = await generate_embedding(search_text[:2000])
                        if search_embedding:
                            cursor.execute("""
                                SELECT id, date, content_summary FROM memories
                                WHERE primary_entity_type = %s AND primary_entity_id = %s
                                  AND date < %s AND content_summary IS NOT NULL
                                  AND LENGTH(TRIM(content_summary)) > 20
                                  AND embedding IS NOT NULL
                                ORDER BY embedding <=> %s::vector LIMIT %s
                            """, (entity_type, entity_id, interaction_date,
                                  str(search_embedding), PRIOR_SEMANTIC_COUNT))
                            for row in cursor.fetchall():
                                if row["id"] not in prior_memories:
                                    prior_memories[row["id"]] = dict(row)
                    except Exception as e:
                        logger.warning(f"Semantic prior memory search failed: {e}")

            # Format deduplicated prior memories
            if prior_memories:
                sorted_priors = sorted(prior_memories.values(), key=lambda m: str(m["date"]))
                prior_lines = [f"[{m['date']}] {m['content_summary']}" for m in sorted_priors]
                prior_context = "\n".join(prior_lines)
                logger.info(f"Injecting {len(prior_memories)} prior memories for {entity_type}/{entity_id}")
    except Exception as e:
        logger.warning(f"Prior memory fetch failed for {entity_type}/{entity_id}: {e}")

    # Build final LLM context with prior memories injected
    if prior_context:
        llm_context = (
            f"Entity: {entity_type} / {entity_id}\n"
            f"Date: {interaction_date}\n"
            f"Interaction count: {len(interactions)}\n\n"
            f"--- Prior Context (established facts, do NOT repeat) ---\n{prior_context}\n\n"
        )
        llm_context += f"--- Raw Interactions ---\n{raw_text}\n\n--- Extracted Signals ---\n{ner_summary}"
    else:
        llm_context = base_context

    # 6. LLM generates memory content_summary
    system_prompt = await get_system_prompt("memory_generation")
    if not system_prompt:
        system_prompt = "You are an AI memory system. Extract new factual information." # absolute bare minimum safety fallback

    system_prompt = inject_variables(system_prompt, {
        "entity": {"type": entity_type, "id": entity_id},
        "date": interaction_date  # Already a string in ISO format from the queue
    })
    
    content_summary = ""
    processing_errors = {}
    try:
        content_summary = await call_llm(
            llm_context[:10000],
            system_prompt=system_prompt,
            max_tokens=1200,
            task_type="memory_generation",
        )
    except Exception as e:
        processing_errors["memory_generation"] = str(e)
        logger.warning(f"Memory LLM call failed for {entity_type}/{entity_id}: {e}")

    # 7. Embedding (memories only — no interaction embedding)
    embedding = None
    if config.get("embedding_enabled", True) and content_summary:
        try:
            embed_text = content_summary
            if related_entities or intents:
                entity_names = ", ".join(
                    e.get("name", "") for e in related_entities if isinstance(e, dict)
                )
                signals = ", ".join(intents)
                embed_text = f"{content_summary}\nEntities: {entity_names}\nSignals: {signals}"
            embedding = await generate_embedding(embed_text)
        except Exception as e:
            processing_errors["embeddings"] = str(e)
            logger.warning(f"Embedding failed for {entity_type}/{entity_id}: {e}")

    # 8. Write memory (INSERT only — skip if exists, checked above)
    memory_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
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
                json.dumps(relationships), embedding, json.dumps(processing_errors)
            ))
        else:
            cursor.execute("""
                INSERT INTO memories (
                    id, date, primary_entity_type, primary_entity_id,
                    interaction_ids, interaction_count, content_summary,
                    related_entities, intents, relationships, processing_errors
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, primary_entity_type, primary_entity_id) DO NOTHING
            """, (
                memory_id, interaction_date, entity_type, entity_id,
                interaction_ids, len(interaction_ids), content_summary,
                json.dumps(related_entities), intents,
                json.dumps(relationships), json.dumps(processing_errors)
            ))

        # 9. Mark interactions as done and clear ephemeral embeddings to prevent DB bloat
        cursor.execute("""
            UPDATE interactions SET status = 'done', embedding = NULL
            WHERE id = ANY(%s)
        """, (interaction_ids,))

    # 10. Flush from Redis
    for iid in interaction_ids:
        flush_interaction_cache(iid)

    logger.info(
        f"Generated memory {memory_id} for {entity_type}/{entity_id} on {interaction_date} "
        f"({len(interaction_ids)} interactions)"
    )

    # 11. Check compaction threshold
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
        config = _get_entity_type_config(entity_type)
        try:
            await _check_compaction_trigger(entity_type, entity_id, config)
        except Exception as e:
            logger.error(f"Compaction check failed for {entity_type}/{entity_id}: {e}")


async def _check_compaction_trigger(entity_type: str, entity_id: str, config: dict):
    """
    Check whether compaction should trigger for this entity.
    Fires if:
      - Uncompacted memory count >= compaction_threshold (count trigger), OR
      - insight_trigger_days is set AND oldest uncompacted memory is >= that many days old
        (minimum 2 memories to avoid generating private_knowledge from a single data point)
    """
    threshold = config.get("compaction_threshold", 10)
    trigger_days = config.get("insight_trigger_days")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt, MIN(date) as oldest_date
            FROM memories
            WHERE primary_entity_type = %s AND primary_entity_id = %s AND compacted = FALSE
        """, (entity_type, entity_id))
        row = cursor.fetchone()

    count = row["cnt"]
    oldest_date = row["oldest_date"]

    count_trigger = count >= threshold
    days_trigger = (
        trigger_days is not None
        and oldest_date is not None
        and (date.today() - oldest_date).days >= trigger_days
        and count >= 2
    )

    if count_trigger or days_trigger:
        reason = "count" if count_trigger else "days"
        logger.info(f"Compaction trigger enqueue ({reason}) for {entity_type}/{entity_id}: {count} memories, oldest={oldest_date}")
        from memory.queue import knowledge_queue
        await knowledge_queue.add(
            "generate_insight", 
            {"entity_type": entity_type, "entity_id": entity_id},
            {"priority": 4}
        )


# ── Compaction: PrivateKnowledge Generation ───────────────────────────────────────────

async def compact_entity(entity_type: str, entity_id: str):
    """
    Generate an PrivateKnowledge from the N most recent uncompacted memories.
    Embedding is generated for the PrivateKnowledge (not for interactions).
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

    # Build LLM context from memory summaries
    context_parts = []
    for m in memories:
        related = m.get("related_entities") or []
        if isinstance(related, str):
            related = json.loads(related)
        signals = m.get("intents") or []
        context_parts.append(
            f"[{m['date']}] {m.get('content_summary', '')}\n"
            f"  Entities: {', '.join(e.get('name', '') for e in related if isinstance(e, dict))}\n"
            f"  Signals: {', '.join(signals)}"
        )

    context = "\n\n".join(context_parts)
    system_prompt = await get_system_prompt("insight_generation") or (
        "You are an AI analyst. Based on the provided memory summaries, identify a meaningful pattern, "
        "risk, opportunity, or behavioral PrivateKnowledge. Return JSON only: "
        "{\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\"}"
    )
    system_prompt = inject_variables(system_prompt, {
        "entity": {"type": entity_type, "id": entity_id}
    })

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
        logger.error(f"PrivateKnowledge LLM call failed: {e}")
        return

    name = result.get("name", "Unnamed PrivateKnowledge")
    knowledge_type = result.get("knowledge_type", "other")
    content = result.get("content", "")
    summary = result.get("summary", "")

    if not content:
        return

    # Generate embedding for the PrivateKnowledge
    embedding = None
    try:
        embedding = await generate_embedding(f"{name}. {summary or content}")
    except Exception as e:
        logger.warning(f"PrivateKnowledge embedding failed: {e}")

    auto_approve = config.get("insight_auto_approve", False)
    status = "confirmed" if auto_approve else "draft"
    insight_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
            cursor.execute("""
                INSERT INTO private_knowledge (
                    id, primary_entity_type, primary_entity_id, source_memory_ids,
                    knowledge_type, name, content, summary, embedding,
                    status, created_by, confirmed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                insight_id, entity_type, entity_id, memory_ids,
                knowledge_type, name, content, summary, embedding,
                status, "auto", now if auto_approve else None, now, now,
            ))
        else:
            cursor.execute("""
                INSERT INTO private_knowledge (
                    id, primary_entity_type, primary_entity_id, source_memory_ids,
                    knowledge_type, name, content, summary,
                    status, created_by, confirmed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                insight_id, entity_type, entity_id, memory_ids,
                knowledge_type, name, content, summary,
                status, "auto", now if auto_approve else None, now, now,
            ))

        # Mark source memories as compacted
        cursor.execute("""
            UPDATE memories SET compacted = TRUE, compaction_count = compaction_count + 1
            WHERE id = ANY(%s)
        """, (memory_ids,))

    logger.info(f"Created PrivateKnowledge {insight_id} ({status}) for {entity_type}/{entity_id} from {len(memory_ids)} memories")


# ── PublicKnowledge Check: Accumulation-Based ─────────────────────────────────────────

async def run_lesson_check():
    """
    Check if enough confirmed private_knowledge have accumulated to generate a PublicKnowledge.
    Triggers on count (lesson_threshold) OR days since oldest unused PrivateKnowledge (lesson_trigger_days).
    Mirrors the memory → PrivateKnowledge compaction pattern.
    """
    settings = get_memory_settings()
    threshold = settings.get("lesson_threshold", 5)
    trigger_days = settings.get("lesson_trigger_days")

    # Find confirmed private_knowledge not yet used in any PublicKnowledge
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.id, i.name, i.content, i.summary, i.knowledge_type, i.created_at
            FROM private_knowledge i
            WHERE i.status = 'confirmed'
              AND NOT EXISTS (
                  SELECT 1 FROM public_knowledge l
                  WHERE i.id = ANY(l.source_private_knowledge_ids)
              )
            ORDER BY i.created_at ASC
        """)
        unused_insights = [dict(r) for r in cursor.fetchall()]

    count = len(unused_insights)
    if count == 0:
        return

    oldest_dt = unused_insights[0].get("created_at")
    oldest_date = oldest_dt.date() if hasattr(oldest_dt, "date") else None

    count_trigger = count >= threshold
    days_trigger = (
        trigger_days is not None
        and oldest_date is not None
        and (date.today() - oldest_date).days >= trigger_days
        and count >= 2
    )

    if not (count_trigger or days_trigger):
        return

    reason = "count" if count_trigger else "days"
    logger.info(f"PublicKnowledge trigger ({reason}): {count} unused confirmed private_knowledge")
    batch = unused_insights[:threshold] if count_trigger else unused_insights
    await generate_lesson_from_insights(batch)


async def generate_lesson_from_insights(private_knowledge: list):
    """
    Generate a PublicKnowledge from a batch of confirmed private_knowledge.
    Steps: PII scrub each PrivateKnowledge → build LLM context → generalize → embed → write.
    """
    if not private_knowledge:
        return

    # PII scrub all PrivateKnowledge content before using as LLM context
    scrubbed_parts = []
    for ins in private_knowledge:
        content = ins.get("content", "")
        summary = ins.get("summary", "")
        try:
            content = await scrub_pii(content)
            summary = await scrub_pii(summary) if summary else ""
        except Exception as e:
            logger.warning(f"PII scrub failed for PrivateKnowledge {ins['id']}: {e}")
        scrubbed_parts.append(
            f"[{ins.get('knowledge_type', 'other')}] {ins.get('name', '')}\n{content}"
        )

    context = "\n\n---\n\n".join(scrubbed_parts)
    insight_ids = [ins["id"] for ins in private_knowledge]

    system_prompt = await get_system_prompt("public_knowledge_generation")
    if not system_prompt:
        system_prompt = "You are an AI knowledge curator. Synthesize into generalizable PublicKnowledge. Return JSON: {\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\", \"tags\": [...]}"

    try:
        result_text = await call_llm(
            context[:8000],
            system_prompt=system_prompt,
            max_tokens=600,
            task_type="lesson_generation",
        )
        result = json.loads(result_text)
    except Exception as e:
        logger.error(f"PublicKnowledge generation LLM call failed: {e}")
        return

    name = result.get("name", "Unnamed PublicKnowledge")
    knowledge_type = result.get("knowledge_type", "other")
    content = result.get("content", "")
    summary = result.get("summary", "")
    tags = result.get("tags", [])

    if not content:
        return

    # Embed the PublicKnowledge
    embedding = None
    try:
        embedding = await generate_embedding(f"{name}. {summary or content}")
    except Exception as e:
        logger.warning(f"PublicKnowledge embedding failed: {e}")

    lesson_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
            cursor.execute("""
                INSERT INTO public_knowledge (
                    id, source_private_knowledge_ids, knowledge_type, name, content, summary,
                    embedding, visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                lesson_id, insight_ids, knowledge_type, name, content, summary,
                embedding, "shared", tags, now, now,
            ))
        else:
            cursor.execute("""
                INSERT INTO public_knowledge (
                    id, source_private_knowledge_ids, knowledge_type, name, content, summary,
                    visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                lesson_id, insight_ids, knowledge_type, name, content, summary,
                "shared", tags, now, now,
            ))

    logger.info(f"Generated PublicKnowledge {lesson_id} from {len(insight_ids)} private_knowledge")


# ── PublicKnowledge Promotion (Manual 1:1 admin use) ───────────────────────────────────

async def promote_to_lesson(insight_id: str):
    """
    PII scrub + generalize a single PrivateKnowledge and write it as a PublicKnowledge.
    Kept for manual admin promotion — not used by the automatic PublicKnowledge accumulation path.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, primary_entity_type, primary_entity_id, source_memory_ids,
                   knowledge_type, name, content, summary
            FROM private_knowledge WHERE id = %s
        """, (insight_id,))
        PrivateKnowledge = cursor.fetchone()

    if not PrivateKnowledge:
        logger.warning(f"promote_to_lesson: PrivateKnowledge {insight_id} not found")
        return

    content = PrivateKnowledge["content"]
    summary = PrivateKnowledge["summary"] or ""

    # PII scrub
    try:
        content = await scrub_pii(content)
        summary = await scrub_pii(summary) if summary else ""
    except Exception as e:
        logger.warning(f"PII scrub failed for PrivateKnowledge {insight_id}: {e}")

    # Generalize entity names
    generalize_prompt = (
        "You are an AI editor. Remove all specific entity names, organization names, and other "
        "identifying information from the following text, replacing with generic terms (e.g., 'the client', "
        "'the institution'). Preserve the PrivateKnowledge's meaning. Return only the edited text."
    )
    try:
        content = await call_llm(
            content,
            system_prompt=generalize_prompt,
            max_tokens=600,
            task_type="lesson_generation"
        )
    except Exception as e:
        logger.warning(f"PublicKnowledge generalization failed: {e}")

    # Embed PublicKnowledge
    embedding = None
    try:
        embedding = await generate_embedding(f"{PrivateKnowledge['name']}. {summary or content}")
    except Exception as e:
        logger.warning(f"PublicKnowledge embedding failed: {e}")

    lesson_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
            cursor.execute("""
                INSERT INTO public_knowledge (
                    id, source_private_knowledge_ids, knowledge_type, name, content, summary,
                    embedding, visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                lesson_id, [insight_id], PrivateKnowledge["knowledge_type"],
                PrivateKnowledge["name"], content, summary, embedding,
                "shared", [], now, now,
            ))
        else:
            cursor.execute("""
                INSERT INTO public_knowledge (
                    id, source_private_knowledge_ids, knowledge_type, name, content, summary,
                    visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                lesson_id, [insight_id], PrivateKnowledge["knowledge_type"],
                PrivateKnowledge["name"], content, summary,
                "shared", [], now, now,
            ))

    logger.info(f"Promoted PrivateKnowledge {insight_id} to PublicKnowledge {lesson_id}")


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
        "ner_schema": None,
        "insight_trigger_days": None,
        "embedding_enabled": True,
        "pii_scrub_lessons": True,
        "metadata_field_map": {},
    }


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


