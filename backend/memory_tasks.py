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
     - Intelligence generation: N memories → LLM → Intelligence

  4. run_lesson_check()
     - Knowledge accumulation: N confirmed intelligence → PII scrub + LLM → Knowledge

  5. promote_to_knowledge()
     - Keep for manual 1:1 admin promotion of a single Intelligence

  6. check_rate_limit()
     - Per-agent rate limiting (in-memory, single-instance)

Embedding scope: ONLY memories, intelligence, and knowledge are embedded.
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
from services.config_helpers import get_pipeline_configs, get_system_prompt_by_config_id, get_schema_by_config_id
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
    """Generate a single daily memory record for one entity on one date.
    Uses the sequential pipeline executor to process nodes in DB-defined order."""

    # 1. Fetch entity type config + interactions
    config = _get_entity_type_config(entity_type)

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
    raw_text = "\n\n---\n\n".join(i["content"] for i in interactions if i.get("content"))
    ner_payload = _build_ner_text_payload(interactions)

    # 2. Build prior memory context (chrono 2 + semantic 2)
    prior_context = await _fetch_prior_context(entity_type, entity_id, interaction_date, raw_text)

    # 3. Initialize the pipeline context object
    ctx = {
        "raw_text": raw_text,
        "derived_text": raw_text,
        "ner_text": ner_payload,
        "ner_results": {"entities": [], "intents": [], "relationships": []},
        "embedding": None,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "interaction_date": interaction_date,
        "interactions": interactions,
        "prior_context": prior_context,
        "processing_errors": {},
        "config": config,
    }

    # 4. Execute the memories pipeline — nodes in DB-defined order
    pipeline_nodes = get_pipeline_configs("memories")
    if not pipeline_nodes:
        logger.warning(f"No active pipeline nodes for 'memories' stage — skipping {entity_type}/{entity_id}")
        return

    for node in pipeline_nodes:
        try:
            await _execute_pipeline_node(node, ctx)
        except Exception as e:
            node_id = node.get("id", "unknown")
            ctx["processing_errors"][node_id] = str(e)
            logger.error(f"Pipeline node {node.get('task_type')}/{node_id} failed: {e}", exc_info=True)

    # 5. Write memory record from pipeline results
    content_summary = ctx["derived_text"] if ctx["derived_text"] != raw_text else ""
    embedding = ctx["embedding"]
    related_entities = ctx["ner_results"]["entities"]
    intents = ctx["ner_results"]["intents"]
    relationships = ctx["ner_results"]["relationships"]
    processing_errors = ctx["processing_errors"]

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

        # Mark interactions as done and clear ephemeral embeddings
        cursor.execute("""
            UPDATE interactions SET status = 'done', embedding = NULL
            WHERE id = ANY(%s)
        """, (interaction_ids,))

    # Flush from Redis
    for iid in interaction_ids:
        flush_interaction_cache(iid)

    logger.info(
        f"Generated memory {memory_id} for {entity_type}/{entity_id} on {interaction_date} "
        f"({len(interaction_ids)} interactions, {len(pipeline_nodes)} pipeline nodes)"
    )

    # Check compaction threshold
    await _check_compaction_trigger(entity_type, entity_id, config)


# ── Sequential Pipeline Node Executor ─────────────────────────────────────────

async def _execute_pipeline_node(node: dict, ctx: dict):
    """Execute a single pipeline node against the mutable context."""
    task_type = node["task_type"]
    node_id = node["id"]
    provider = node.get("provider", "")

    if task_type == "entity_extraction":
        threshold = ctx["config"].get("ner_confidence_threshold", 0.5)
        # Read schema from this specific node
        schema_raw = get_schema_by_config_id(node_id)
        ner_schema = None
        if schema_raw:
            try:
                ner_schema = json.loads(schema_raw)
            except Exception:
                pass
        ner_results = await extract_entities(
            ctx["ner_text"][:4000],
            confidence_threshold=threshold,
            ner_schema=ner_schema,
        )
        ctx["ner_results"]["entities"].extend(ner_results.get("entities", []))
        ctx["ner_results"]["intents"].extend(ner_results.get("intents", []))
        ctx["ner_results"]["relationships"].extend(ner_results.get("relationships", []))
        logger.info(f"NER node {node_id}: extracted {len(ner_results.get('entities', []))} entities")

    elif task_type == "embedding":
        embed_text = ctx["derived_text"]
        entities = ctx["ner_results"]["entities"]
        intents = ctx["ner_results"]["intents"]
        if entities or intents:
            entity_names = ", ".join(e.get("name", "") for e in entities if isinstance(e, dict))
            signals = ", ".join(intents)
            embed_text = f"{embed_text}\nEntities: {entity_names}\nSignals: {signals}"
        ctx["embedding"] = await generate_embedding(embed_text)
        logger.info(f"Embedding node {node_id}: generated vector")

    elif task_type == "memory_generation":
        ner_summary = _format_ner_output(
            ctx["ner_results"]["entities"],
            ctx["ner_results"]["intents"],
            ctx["ner_results"]["relationships"]
        )
        if ctx["prior_context"]:
            llm_context = (
                f"Entity: {ctx['entity_type']} / {ctx['entity_id']}\n"
                f"Date: {ctx['interaction_date']}\n"
                f"Interaction count: {len(ctx['interactions'])}\n\n"
                f"--- Prior Context (established facts, do NOT repeat) ---\n{ctx['prior_context']}\n\n"
                f"--- Raw Interactions ---\n{ctx['raw_text']}\n\n"
                f"--- Extracted Signals ---\n{ner_summary}"
            )
        else:
            llm_context = (
                f"Entity: {ctx['entity_type']} / {ctx['entity_id']}\n"
                f"Date: {ctx['interaction_date']}\n"
                f"Interaction count: {len(ctx['interactions'])}\n\n"
                f"--- Raw Interactions ---\n{ctx['raw_text']}\n\n"
                f"--- Extracted Signals ---\n{ner_summary}"
            )
        system_prompt = get_system_prompt_by_config_id(node_id)
        if not system_prompt:
            system_prompt = "You are an AI memory system. Extract new factual information."
        system_prompt = inject_variables(system_prompt, {
            "entity": {"type": ctx["entity_type"], "id": ctx["entity_id"]},
            "date": ctx["interaction_date"]
        })
        ctx["derived_text"] = await call_llm(
            llm_context[:10000],
            system_prompt=system_prompt,
            max_tokens=1200,
            config_id=node_id,
        )
        logger.info(f"Memory generation node {node_id}: produced summary")

    elif task_type == "summarization":
        system_prompt = get_system_prompt_by_config_id(node_id) or "Summarize this in 1-2 sentences:\n\n{{text}}"
        prompt = system_prompt.replace("{{text}}", ctx["derived_text"][:4000])
        ctx["derived_text"] = await call_llm(
            prompt, max_tokens=200, config_id=node_id,
        )
        logger.info(f"Summarization node {node_id}: summarized text")

    elif task_type == "pii_scrubbing":
        if provider == "zendata":
            ctx["derived_text"] = await scrub_pii(ctx["derived_text"])
        else:
            system_prompt = get_system_prompt_by_config_id(node_id) or "Remove all PII from the following text. Return only the scrubbed text."
            ctx["derived_text"] = await call_llm(
                ctx["derived_text"][:8000],
                system_prompt=system_prompt,
                max_tokens=2000,
                config_id=node_id,
            )
        logger.info(f"PII scrubbing node {node_id}: scrubbed text")

    elif task_type in ("intelligence_generation", "knowledge_generation"):
        system_prompt = get_system_prompt_by_config_id(node_id)
        if not system_prompt:
            system_prompt = "You are an AI analyst. Identify a meaningful pattern or insight. Return JSON."
        system_prompt = inject_variables(system_prompt, {
            "entity": {"type": ctx.get("entity_type", ""), "id": ctx.get("entity_id", "")}
        })
        ctx["derived_text"] = await call_llm(
            ctx["derived_text"][:8000],
            system_prompt=system_prompt,
            max_tokens=800,
            config_id=node_id,
        )
        logger.info(f"{task_type} node {node_id}: generated knowledge")

    elif task_type == "vision":
        # Vision only runs during process_interaction, not in daily pipeline
        logger.debug(f"Vision node {node_id} skipped (only runs during interaction ingestion)")

    else:
        logger.warning(f"Unknown pipeline task_type '{task_type}' for node {node_id} — skipped")


# ── Prior Memory Context Fetcher ──────────────────────────────────────────────

async def _fetch_prior_context(entity_type: str, entity_id: str, interaction_date: str, raw_text: str) -> str:
    """Fetch prior memories (chronological + semantic) for context continuity.
    Counts are user-configurable via memory_settings."""
    settings = get_memory_settings()
    PRIOR_CHRONO_COUNT = settings.get("prior_context_chrono_count", 2)
    PRIOR_SEMANTIC_COUNT = settings.get("prior_context_semantic_count", 2)
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            prior_memories = {}

            cursor.execute("""
                SELECT id, date, content_summary FROM memories
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND date < %s AND content_summary IS NOT NULL
                  AND LENGTH(TRIM(content_summary)) > 20
                ORDER BY date DESC LIMIT %s
            """, (entity_type, entity_id, interaction_date, PRIOR_CHRONO_COUNT))
            for row in cursor.fetchall():
                prior_memories[row["id"]] = dict(row)

            if PRIOR_SEMANTIC_COUNT > 0 and raw_text:
                try:
                    search_embedding = await generate_embedding(raw_text[:2000])
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

            if prior_memories:
                sorted_priors = sorted(prior_memories.values(), key=lambda m: str(m["date"]))
                prior_lines = [f"[{m['date']}] {m['content_summary']}" for m in sorted_priors]
                logger.info(f"Injecting {len(prior_memories)} prior memories for {entity_type}/{entity_id}")
                return "\n".join(prior_lines)
    except Exception as e:
        logger.warning(f"Prior memory fetch failed for {entity_type}/{entity_id}: {e}")
    return ""


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
    Fires if Uncompacted memory count >= intelligence_extraction_threshold.
    """
    
    settings = get_memory_settings()
    global_threshold = settings.get("intelligence_extraction_threshold", 10)
    threshold = config.get("intelligence_extraction_threshold") or global_threshold

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt
            FROM memories
            WHERE primary_entity_type = %s AND primary_entity_id = %s AND compacted = FALSE
        """, (entity_type, entity_id))
        count = cursor.fetchone()["cnt"]

    if count >= threshold:
        logger.info(f"Intelligence extraction trigger enqueue for {entity_type}/{entity_id}: {count} memories")
        from memory.queue import knowledge_queue
        await knowledge_queue.add(
            "generate_insight", 
            {"entity_type": entity_type, "entity_id": entity_id},
            {"priority": 4}
        )

# ── Compaction: Intelligence Generation ───────────────────────────────────────────

async def compact_entity(entity_type: str, entity_id: str):
    """
    Generate a Intelligence from the N most recent uncompacted memories.
    Uses intelligence pipeline nodes. Embedding is generated for the Intelligence.
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

    # Fetch prior intelligence for this entity to avoid duplication
    settings = get_memory_settings()
    prior_intel_chrono = settings.get("prior_intelligence_chrono_count", 3)
    prior_intel_semantic = settings.get("prior_intelligence_semantic_count", 2)
    prior_intelligence_text = ""

    if prior_intel_chrono > 0 or prior_intel_semantic > 0:
        try:
            with get_memory_db_context() as conn:
                cursor = conn.cursor()
                prior_intel = {}

                # Chronological prior intelligence
                if prior_intel_chrono > 0:
                    cursor.execute("""
                        SELECT id, name, knowledge_type, content, summary, created_at
                        FROM intelligence
                        WHERE primary_entity_type = %s AND primary_entity_id = %s
                          AND content IS NOT NULL AND LENGTH(TRIM(content)) > 10
                        ORDER BY created_at DESC LIMIT %s
                    """, (entity_type, entity_id, prior_intel_chrono))
                    for row in cursor.fetchall():
                        prior_intel[row["id"]] = dict(row)

                # Semantic prior intelligence
                if prior_intel_semantic > 0 and context:
                    try:
                        search_emb = await generate_embedding(context[:2000])
                        if search_emb:
                            cursor.execute("""
                                SELECT id, name, knowledge_type, content, summary, created_at
                                FROM intelligence
                                WHERE primary_entity_type = %s AND primary_entity_id = %s
                                  AND embedding IS NOT NULL
                                  AND content IS NOT NULL AND LENGTH(TRIM(content)) > 10
                                ORDER BY embedding <=> %s::vector LIMIT %s
                            """, (entity_type, entity_id, str(search_emb), prior_intel_semantic))
                            for row in cursor.fetchall():
                                if row["id"] not in prior_intel:
                                    prior_intel[row["id"]] = dict(row)
                    except Exception as e:
                        logger.warning(f"Semantic prior intelligence search failed: {e}")

                if prior_intel:
                    sorted_intel = sorted(prior_intel.values(), key=lambda x: str(x.get("created_at", "")))
                    lines = [f"[{i.get('knowledge_type', 'other')}] {i.get('name', '')}: {i.get('summary') or i.get('content', '')[:200]}" for i in sorted_intel]
                    prior_intelligence_text = "\n".join(lines)
                    logger.info(f"Injecting {len(prior_intel)} prior intelligence for {entity_type}/{entity_id}")
        except Exception as e:
            logger.warning(f"Prior intelligence fetch failed: {e}")

    # Fetch prior knowledge (global, semantic) so intelligence is aware of established patterns
    prior_knowledge_in_intel = settings.get("prior_knowledge_in_intelligence_count", 2)
    prior_knowledge_text = ""

    if prior_knowledge_in_intel > 0 and context:
        try:
            search_emb = await generate_embedding(context[:2000])
            if search_emb:
                with get_memory_db_context() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, name, knowledge_type, content, summary
                        FROM knowledge
                        WHERE embedding IS NOT NULL
                          AND content IS NOT NULL AND LENGTH(TRIM(content)) > 10
                        ORDER BY embedding <=> %s::vector LIMIT %s
                    """, (str(search_emb), prior_knowledge_in_intel))
                    prior_k = [dict(r) for r in cursor.fetchall()]

                if prior_k:
                    lines = [f"[{k.get('knowledge_type', 'other')}] {k.get('name', '')}: {k.get('summary') or k.get('content', '')[:200]}" for k in prior_k]
                    prior_knowledge_text = "\n".join(lines)
                    logger.info(f"Injecting {len(prior_k)} prior knowledge items into intelligence generation for {entity_type}/{entity_id}")
        except Exception as e:
            logger.warning(f"Prior knowledge fetch for intelligence failed: {e}")

    # Use pipeline-driven config lookup
    pipeline_nodes = get_pipeline_configs("intelligence")
    pk_gen_node = next((n for n in pipeline_nodes if n["task_type"] == "intelligence_generation"), None)

    if pk_gen_node:
        system_prompt = get_system_prompt_by_config_id(pk_gen_node["id"])
        node_id = pk_gen_node["id"]
    else:
        # Fallback to legacy task_type lookup
        system_prompt = await get_system_prompt("intelligence_generation")
        node_id = None

    if not system_prompt:
        system_prompt = (
            "You are an AI analyst. Based on the provided memory summaries, identify a meaningful pattern, "
            "risk, opportunity, or behavioral Intelligence. Return JSON only: "
            "{\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\"}"
        )
    system_prompt = inject_variables(system_prompt, {
        "entity": {"type": entity_type, "id": entity_id}
    })

    if not pk_gen_node:
        # Also try legacy key as absolute last resort
        llm_config = get_llm_config("intelligence_generation") or get_llm_config("intelligence_generation")
        if not llm_config:
            logger.warning(f"No LLM config for intelligence_generation — skipping compaction for {entity_type}/{entity_id}")
            return

    try:
        user_msg_parts = [f"Entity: {entity_type} / {entity_id}"]
        if prior_knowledge_text:
            user_msg_parts.append(f"--- Established Knowledge (organizational patterns already known) ---\n{prior_knowledge_text}")
        if prior_intelligence_text:
            user_msg_parts.append(f"--- Existing Intelligence for this entity (do NOT duplicate) ---\n{prior_intelligence_text}")
        user_msg_parts.append(f"--- Memory Summaries to Analyze ---\n{context}")
        user_msg = "\n\n".join(user_msg_parts)
        result_text = await call_llm(
            user_msg,
            system_prompt=system_prompt,
            max_tokens=800,
            config_id=node_id,
            task_type="intelligence_generation"
        )
        result = json.loads(result_text)
    except Exception as e:
        logger.error(f"Intelligence LLM call failed: {e}")
        return

    name = result.get("name", "Unnamed Intelligence")
    knowledge_type = result.get("knowledge_type", "other")
    content = result.get("content", "")
    summary = result.get("summary", "")

    if not content:
        return

    # Generate embedding for the Intelligence
    embedding = None
    try:
        embedding = await generate_embedding(f"{name}. {summary or content}")
    except Exception as e:
        logger.warning(f"Intelligence embedding failed: {e}")

    auto_approve = config.get("insight_auto_approve", False)
    status = "confirmed" if auto_approve else "draft"
    insight_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
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
        else:
            cursor.execute("""
                INSERT INTO intelligence (
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

    logger.info(f"Created Intelligence {insight_id} ({status}) for {entity_type}/{entity_id} from {len(memory_ids)} memories")


# ── Knowledge Check: Accumulation-Based ─────────────────────────────────────────

async def run_lesson_check():
    """
    Check if enough confirmed intelligence have accumulated to generate a Knowledge.
    Triggers based on unpromoted intelligence counts per entity type.
    """
    settings = get_memory_settings()
    global_knowledge_threshold = settings.get("knowledge_threshold", 5)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # 1. Group unpromoted intelligence by primary_entity_type
        cursor.execute("""
            SELECT primary_entity_type, COUNT(*) as unused_count
            FROM intelligence i
            WHERE i.status = 'confirmed'
              AND NOT EXISTS (
                  SELECT 1 FROM knowledge l
                  WHERE i.id = ANY(l.source_intelligence_ids)
              )
            GROUP BY primary_entity_type
        """)
        entities = cursor.fetchall()
        
        for row in entities:
            entity_type = row["primary_entity_type"]
            count = row["unused_count"]
            
            # 2. Resolve the threshold for this specific entity type
            config = _get_entity_type_config(entity_type)
            threshold = config.get("knowledge_extraction_threshold") or global_knowledge_threshold
            
            if count >= threshold:
                # 3. Fetch exact batch for this entity type
                cursor.execute("""
                    SELECT i.id, i.name, i.content, i.summary, i.knowledge_type, i.created_at
                    FROM intelligence i
                    WHERE i.status = 'confirmed'
                      AND primary_entity_type = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM knowledge l
                          WHERE i.id = ANY(l.source_intelligence_ids)
                      )
                    ORDER BY i.created_at ASC
                    LIMIT %s
                """, (entity_type, threshold))
                
                batch = [dict(r) for r in cursor.fetchall()]
                logger.info(f"Knowledge extraction trigger (count) for {entity_type}: {len(batch)} unused intelligence items")
                # Immediately execute for this entity (run_lesson_check is inherently processed background asynchronously inside Queue worker)
                await generate_knowledge_from_intelligence(batch)


async def generate_knowledge_from_intelligence(intelligence: list):
    """
    Generate a Knowledge from a batch of confirmed intelligence.
    Steps: PII scrub each Intelligence → build LLM context → generalize → embed → write.
    """
    if not intelligence:
        return

    # PII scrub all Intelligence content before using as LLM context
    scrubbed_parts = []
    for ins in intelligence:
        content = ins.get("content", "")
        summary = ins.get("summary", "")
        try:
            content = await scrub_pii(content)
            summary = await scrub_pii(summary) if summary else ""
        except Exception as e:
            logger.warning(f"PII scrub failed for Intelligence {ins['id']}: {e}")
        scrubbed_parts.append(
            f"[{ins.get('knowledge_type', 'other')}] {ins.get('name', '')}\n{content}"
        )

    context = "\n\n---\n\n".join(scrubbed_parts)
    intelligence_ids = [ins["id"] for ins in intelligence]

    # Fetch prior knowledge via semantic search to avoid duplication
    settings = get_memory_settings()
    prior_knowledge_count = settings.get("prior_knowledge_semantic_count", 3)
    prior_knowledge_text = ""

    if prior_knowledge_count > 0 and context:
        try:
            search_emb = await generate_embedding(context[:2000])
            if search_emb:
                with get_memory_db_context() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, name, knowledge_type, content, summary, tags
                        FROM knowledge
                        WHERE embedding IS NOT NULL
                          AND content IS NOT NULL AND LENGTH(TRIM(content)) > 10
                        ORDER BY embedding <=> %s::vector LIMIT %s
                    """, (str(search_emb), prior_knowledge_count))
                    prior_items = [dict(r) for r in cursor.fetchall()]

                if prior_items:
                    lines = [
                        f"[{k.get('knowledge_type', 'other')}] {k.get('name', '')}: {k.get('summary') or k.get('content', '')[:200]}"
                        for k in prior_items
                    ]
                    prior_knowledge_text = "\n".join(lines)
                    logger.info(f"Injecting {len(prior_items)} prior knowledge items for deduplication")
        except Exception as e:
            logger.warning(f"Prior knowledge fetch failed: {e}")

    # Use pipeline-driven config lookup
    pipeline_nodes = get_pipeline_configs("knowledge")
    pk_gen_node = next((n for n in pipeline_nodes if n["task_type"] == "knowledge_generation"), None)
    node_id = pk_gen_node["id"] if pk_gen_node else None

    if pk_gen_node:
        system_prompt = get_system_prompt_by_config_id(pk_gen_node["id"])
    else:
        system_prompt = await get_system_prompt("knowledge_generation")

    if not system_prompt:
        system_prompt = "You are an AI knowledge curator. Synthesize into generalizable Knowledge. Return JSON: {\"name\": \"...\", \"knowledge_type\": \"...\", \"content\": \"...\", \"summary\": \"...\", \"tags\": [...]}"

    try:
        user_msg_parts = []
        if prior_knowledge_text:
            user_msg_parts.append(f"--- Existing Knowledge (do NOT duplicate or repeat these) ---\n{prior_knowledge_text}")
        user_msg_parts.append(f"--- Intelligence Items to Synthesize ---\n{context}")
        user_msg = "\n\n".join(user_msg_parts)

        result_text = await call_llm(
            user_msg[:8000],
            system_prompt=system_prompt,
            max_tokens=600,
            config_id=node_id,
            task_type="knowledge_generation",
        )
        result = json.loads(result_text)
    except Exception as e:
        logger.error(f"Knowledge generation LLM call failed: {e}")
        return

    name = result.get("name", "Unnamed Knowledge")
    knowledge_type = result.get("knowledge_type", "other")
    content = result.get("content", "")
    summary = result.get("summary", "")
    tags = result.get("tags", [])

    if not content:
        return

    # Embed the Knowledge
    embedding = None
    try:
        embedding = await generate_embedding(f"{name}. {summary or content}")
    except Exception as e:
        logger.warning(f"Knowledge embedding failed: {e}")

    knowledge_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
            cursor.execute("""
                INSERT INTO knowledge (
                    id, source_intelligence_ids, knowledge_type, name, content, summary,
                    embedding, visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                knowledge_id, intelligence_ids, knowledge_type, name, content, summary,
                embedding, "shared", tags, now, now,
            ))
        else:
            cursor.execute("""
                INSERT INTO knowledge (
                    id, source_intelligence_ids, knowledge_type, name, content, summary,
                    visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                knowledge_id, intelligence_ids, knowledge_type, name, content, summary,
                "shared", tags, now, now,
            ))

    logger.info(f"Generated Knowledge {knowledge_id} from {len(intelligence_ids)} intelligence")


# ── Knowledge Promotion (Manual 1:1 admin use) ───────────────────────────────────

async def promote_to_knowledge(insight_id: str):
    """
    PII scrub + generalize a single Intelligence and write it as a Knowledge.
    Kept for manual admin promotion — not used by the automatic Knowledge accumulation path.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, primary_entity_type, primary_entity_id, source_memory_ids,
                   knowledge_type, name, content, summary
            FROM intelligence WHERE id = %s
        """, (insight_id,))
        Intelligence = cursor.fetchone()

    if not Intelligence:
        logger.warning(f"promote_to_knowledge: Intelligence {insight_id} not found")
        return

    content = Intelligence["content"]
    summary = Intelligence["summary"] or ""

    # PII scrub
    try:
        content = await scrub_pii(content)
        summary = await scrub_pii(summary) if summary else ""
    except Exception as e:
        logger.warning(f"PII scrub failed for Intelligence {insight_id}: {e}")

    # Generalize entity names
    generalize_prompt = (
        "You are an AI editor. Remove all specific entity names, organization names, and other "
        "identifying information from the following text, replacing with generic terms (e.g., 'the client', "
        "'the institution'). Preserve the Intelligence's meaning. Return only the edited text."
    )
    try:
        content = await call_llm(
            content,
            system_prompt=generalize_prompt,
            max_tokens=600,
            task_type="knowledge_generation"
        )
    except Exception as e:
        logger.warning(f"Knowledge generalization failed: {e}")

    # Embed Knowledge
    embedding = None
    try:
        embedding = await generate_embedding(f"{Intelligence['name']}. {summary or content}")
    except Exception as e:
        logger.warning(f"Knowledge embedding failed: {e}")

    knowledge_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if embedding:
            cursor.execute("""
                INSERT INTO knowledge (
                    id, source_intelligence_ids, knowledge_type, name, content, summary,
                    embedding, visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                knowledge_id, [insight_id], Intelligence["knowledge_type"],
                Intelligence["name"], content, summary, embedding,
                "shared", [], now, now,
            ))
        else:
            cursor.execute("""
                INSERT INTO knowledge (
                    id, source_intelligence_ids, knowledge_type, name, content, summary,
                    visibility, tags, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                knowledge_id, [insight_id], Intelligence["knowledge_type"],
                Intelligence["name"], content, summary,
                "shared", [], now, now,
            ))

    logger.info(f"Promoted Intelligence {insight_id} to Knowledge {knowledge_id}")


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


