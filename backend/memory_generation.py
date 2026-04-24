"""Daily memory generation pipeline: orchestration, pipeline node executor, job log helpers."""
import json
import logging
import uuid
from datetime import date, timedelta
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
)
from services.config_helpers import get_pipeline_configs, get_system_prompt_by_config_id, get_schema_by_config_id
from services.prompt_renderer import inject_variables
from memory_db_writes import insert_memory
from memory_prior_context import fetch_prior_memories
from memory_helpers import (
    _get_entity_type_config,
    _format_signal_definitions,
    _format_ner_output,
    _build_ner_text_payload,
)

logger = logging.getLogger(__name__)


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


# ── Orphan Sweeper ──────────────────────────────────────────────────────────

async def run_orphan_sweeper():
    """Find interactions stuck in pending state for > 6 hours and re-enqueue them."""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
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


# ── Daily Memory Generation ──────────────────────────────────────────────────

async def run_daily_memory_generation(include_today: bool = False):
    """
    For each entity with pending interactions from yesterday (or older),
    build a NER-enriched, embedded daily memory record.
    One memory per entity per day — written once (not upserted).
    """
    cutoff_date = date.today().isoformat() if include_today else (date.today() - timedelta(days=1)).isoformat()

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT primary_entity_type, primary_entity_id,
                   DATE(timestamp) AS interaction_date
            FROM interactions
            WHERE status IN ('pending', 'failed')
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

        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM memories
                WHERE date = %s AND primary_entity_type = %s AND primary_entity_id = %s
            """, (interaction_date, entity_type, entity_id))
            if cursor.fetchone():
                cursor.execute("""
                    UPDATE interactions SET status = 'done'
                    WHERE primary_entity_type = %s AND primary_entity_id = %s
                      AND DATE(timestamp) = %s AND status IN ('pending', 'failed')
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

    config = _get_entity_type_config(entity_type)

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, metadata, metadata_field_map, interaction_type
            FROM interactions
            WHERE primary_entity_type = %s
              AND primary_entity_id = %s
              AND DATE(timestamp) = %s
              AND status IN ('pending', 'failed')
            ORDER BY timestamp
        """, (entity_type, entity_id, interaction_date))
        interactions = [dict(r) for r in cursor.fetchall()]

    if not interactions:
        return

    interaction_ids = [i["id"] for i in interactions]
    raw_text = "\n\n---\n\n".join(i["content"] for i in interactions if i.get("content"))
    ner_payload = _build_ner_text_payload(interactions)

    prior_context = await fetch_prior_memories(entity_type, entity_id, interaction_date, raw_text)

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

    content_summary = ctx["derived_text"] if ctx["derived_text"] != raw_text else ""
    embedding = ctx["embedding"]
    related_entities = ctx["ner_results"]["entities"]
    intents = ctx["ner_results"]["intents"]
    relationships = ctx["ner_results"]["relationships"]
    processing_errors = ctx["processing_errors"]

    memory_id = str(uuid.uuid4())
    insert_memory(
        memory_id=memory_id,
        interaction_date=interaction_date,
        entity_type=entity_type,
        entity_id=entity_id,
        interaction_ids=interaction_ids,
        content_summary=content_summary,
        related_entities=related_entities,
        intents=intents,
        relationships=relationships,
        embedding=embedding,
        processing_errors=processing_errors,
    )

    for iid in interaction_ids:
        flush_interaction_cache(iid)

    logger.info(
        f"Generated memory {memory_id} for {entity_type}/{entity_id} on {interaction_date} "
        f"({len(interaction_ids)} interactions, {len(pipeline_nodes)} pipeline nodes)"
    )

    # Import here to avoid circular dependency at module level
    from memory_compaction import _check_compaction_trigger
    await _check_compaction_trigger(entity_type, entity_id, config)


# ── Sequential Pipeline Node Executor ─────────────────────────────────────────

async def _execute_pipeline_node(node: dict, ctx: dict):
    """Execute a single pipeline node against the mutable context."""
    task_type = node["task_type"]
    node_id = node["id"]
    provider = node.get("provider", "")

    if task_type == "entity_extraction":
        threshold = ctx["config"].get("ner_confidence_threshold", 0.5)
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
        signal_vars = {"entity": {"type": ctx.get("entity_type", ""), "id": ctx.get("entity_id", "")}}
        entity_config = ctx.get("config") or _get_entity_type_config(ctx.get("entity_type", ""))
        if task_type == "intelligence_generation":
            signals = entity_config.get("intelligence_signals_prompt") or []
            signal_vars["intelligence_signals"] = _format_signal_definitions(signals)
        elif task_type == "knowledge_generation":
            signals = entity_config.get("knowledge_signals_prompt") or []
            signal_vars["knowledge_signals"] = _format_signal_definitions(signals)
        system_prompt = inject_variables(system_prompt, signal_vars)
        ctx["derived_text"] = await call_llm(
            ctx["derived_text"][:8000],
            system_prompt=system_prompt,
            max_tokens=800,
            config_id=node_id,
        )
        logger.info(f"{task_type} node {node_id}: generated knowledge")

    elif task_type == "vision":
        logger.debug(f"Vision node {node_id} skipped (only runs during interaction ingestion)")

    else:
        logger.warning(f"Unknown pipeline task_type '{task_type}' for node {node_id} — skipped")
