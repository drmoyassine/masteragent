"""Daily memory generation pipeline: orchestration, pipeline node executor, job log helpers."""
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from core.storage import get_memory_db_context, flush_interaction_cache
from memory_services import (
    call_llm,
    call_llm_with_thinking,
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


def _llm_call(node: dict):
    """Return (llm_fn, extra_kwargs) based on the node's thinking config."""
    extra = node.get("extra_config") or {}
    if extra.get("thinking_enabled"):
        return call_llm_with_thinking, {"max_think_steps": int(extra.get("max_think_steps", 5))}
    return call_llm, {}


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


def claim_job_date(job_name: str, run_date: date) -> bool:
    """Atomically claim a scheduled job/date across all app replicas."""
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_job_log (job_name, last_run, last_date, status, last_error)
            VALUES (%s, NOW(), %s, 'running', NULL)
            ON CONFLICT (job_name) DO UPDATE
              SET last_run = NOW(), last_date = EXCLUDED.last_date,
                  status = 'running', last_error = NULL
            WHERE memory_job_log.last_date IS DISTINCT FROM EXCLUDED.last_date
               OR memory_job_log.status = 'failed'
               -- Reclaim: a 'running' claim older than 15 min means the claimant
               -- died between claim and complete (the claim only spans the
               -- enqueue/scan, so 15 min is generous). Without this, the UTC day
               -- silently skips until tomorrow.
               OR (
                    memory_job_log.status = 'running'
                    AND memory_job_log.last_run < NOW() - INTERVAL '15 minutes'
                  )
            RETURNING job_name
        """, (job_name, run_date))
        return cursor.fetchone() is not None


def complete_job_date(job_name: str, run_date: date) -> None:
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE memory_job_log SET status='completed', completed_at=NOW(), last_error=NULL "
            "WHERE job_name=%s AND last_date=%s",
            (job_name, run_date),
        )


def fail_job_date(job_name: str, run_date: date, error: Exception) -> None:
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE memory_job_log SET status='failed', last_error=%s, last_date=NULL "
            "WHERE job_name=%s AND last_date=%s",
            (str(error)[:2000], job_name, run_date),
        )


# ── Orphan Sweeper ──────────────────────────────────────────────────────────

async def run_orphan_sweeper():
    """Re-enqueue interactions whose enrichment never completed.

    A 'pending' row older than 6h means stuck enrichment; enriched rows resting
    in 'pending' await distillation and must NOT be replayed (a replay
    duplicates attachment text and re-bills vision OCR). Stale 'queued' rows are
    included: a worker that died between claim and save leaves them behind.
    Capped per night to bound a pathological replay storm."""
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM interactions
                WHERE status IN ('pending', 'queued')
                  AND COALESCE(is_enriched, FALSE) = FALSE
                  AND CAST(created_at AS timestamp) < NOW() - INTERVAL '6 hours'
                LIMIT 500
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

# Poison-pill ceiling for deterministically-failing entity-days. Each anti-husk
# raise bumps a generation_cycle stamp on the day's interactions; with the
# queue's 3 attempts per nightly job this is ~3 nights of retries before the
# day is quarantined (see run_daily_memory_generation).
MAX_GENERATION_CYCLES = 9


async def run_daily_memory_generation(include_today: bool = False):
    """
    For each entity with pending interactions from yesterday (or older),
    build a NER-enriched, embedded daily memory record.
    One memory per entity per day — written once (not upserted).
    """
    today_utc = datetime.now(timezone.utc).date()
    cutoff_date = today_utc.isoformat() if include_today else (today_utc - timedelta(days=1)).isoformat()

    # Husk self-heal: a memory row with an empty summary AND recorded node
    # errors is a failed distillation (a "poisoned husk"). The existence check
    # in the loop below would otherwise treat it as final forever — delete the
    # husk and re-arm its interactions so the day flows through the normal
    # enqueue. Truthfully-empty days (no recorded errors) and quarantined days
    # stay closed.
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, primary_entity_type, primary_entity_id FROM memories
            WHERE COALESCE(processing_errors, '{}'::jsonb) <> '{}'::jsonb
              AND (content_summary IS NULL OR btrim(content_summary) = '')
              AND compacted = FALSE
              AND NOT (processing_errors ? 'quarantine')
              AND date <= %s
        """, (cutoff_date,))
        poisoned_days = cursor.fetchall()

    for row in poisoned_days:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM memories
                WHERE date = %s AND primary_entity_type = %s AND primary_entity_id = %s
            """, (row["date"], row["primary_entity_type"], row["primary_entity_id"]))
            # Status only — generation_cycle stamps survive so the poison-pill
            # cap still counts attempts across nights.
            cursor.execute("""
                UPDATE interactions SET status = 'pending'
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND DATE(timestamp) = %s AND status IN ('done', 'failed')
            """, (row["primary_entity_type"], row["primary_entity_id"], row["date"]))
    if poisoned_days:
        logger.warning(
            f"Husk self-heal: re-armed {len(poisoned_days)} poisoned memory days "
            f"(empty summary + node errors); their interactions are pending again"
        )

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
                SELECT interaction_ids, compacted,
                       COALESCE(processing_errors, '{}'::jsonb) AS processing_errors
                FROM memories
                WHERE date = %s AND primary_entity_type = %s AND primary_entity_id = %s
            """, (interaction_date, entity_type, entity_id))
            existing = cursor.fetchone()

        if existing:
            covered = list(existing["interaction_ids"] or [])
            with get_memory_db_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM interactions
                    WHERE primary_entity_type = %s AND primary_entity_id = %s
                      AND DATE(timestamp) = %s AND status IN ('pending', 'failed')
                      AND NOT (id = ANY(%s))
                """, (entity_type, entity_id, interaction_date, covered))
                uncovered = [r["id"] for r in cursor.fetchall()]

            if not uncovered:
                # The memory covers every interaction still pending/failed for
                # the day — close it (previous behavior, now coverage-checked).
                with get_memory_db_context() as conn:
                    conn.cursor().execute("""
                        UPDATE interactions SET status = 'done'
                        WHERE primary_entity_type = %s AND primary_entity_id = %s
                          AND DATE(timestamp) = %s AND status IN ('pending', 'failed')
                    """, (entity_type, entity_id, interaction_date))
                continue

            if existing["compacted"] or existing["processing_errors"].get("quarantine"):
                # Regenerating would dangle intelligence/knowledge lineage (or
                # undo a deliberate quarantine). Discard the late rows with an
                # audit note instead of silently closing them.
                with get_memory_db_context() as conn:
                    conn.cursor().execute("""
                        UPDATE interactions SET status = 'done',
                          processing_errors = COALESCE(processing_errors, '{}'::jsonb)
                            || '{"discarded_late": "day memory compacted/quarantined before this interaction arrived; not re-distilled"}'::jsonb
                        WHERE primary_entity_type = %s AND primary_entity_id = %s
                          AND DATE(timestamp) = %s AND status IN ('pending', 'failed')
                          AND NOT (id = ANY(%s))
                    """, (entity_type, entity_id, interaction_date, covered))
                logger.warning(
                    f"Existence check: {len(uncovered)} late interaction(s) for "
                    f"{entity_type}/{entity_id} on {interaction_date} arrived after the day "
                    f"was compacted/quarantined; marked done with a discarded_late note"
                )
                continue

            # Late arrivals after the day distilled: regenerate the day so
            # nothing silently drops (same pattern as the husk self-heal).
            # generation_cycle stamps survive, so the poison-pill cap below
            # still bounds a pathology loop. Deleting the memory can leave a
            # dangling source_memory_ids in intelligence that already cited it —
            # acceptable at nightly cadence (lineage columns are advisory).
            with get_memory_db_context() as conn:
                conn.cursor().execute("""
                    DELETE FROM memories
                    WHERE date = %s AND primary_entity_type = %s AND primary_entity_id = %s
                """, (interaction_date, entity_type, entity_id))
            logger.warning(
                f"Existence check: memory for {entity_type}/{entity_id} on {interaction_date} "
                f"does not cover {len(uncovered)} pending interaction(s); regenerating the day"
            )

        # Poison-pill cap: a day whose generation keeps failing (cycle stamp on
        # its interactions, bumped by every anti-husk raise) is quarantined
        # once the cap is hit instead of retrying forever. The quarantine husk
        # carries the reason in processing_errors and stays repairable (empty
        # summary + not compacted → any later successful re-run heals it; bulk
        # reprocess deletes the row and re-arms the interactions).
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(MAX((processing_errors->>'generation_cycle')::int), 0) AS cycles
                FROM interactions
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND DATE(timestamp) = %s
            """, (entity_type, entity_id, interaction_date))
            cycles = (cursor.fetchone()["cycles"] or 0)

        if cycles >= MAX_GENERATION_CYCLES:
            logger.error(
                f"Memory generation quarantined for {entity_type}/{entity_id} on "
                f"{interaction_date} after {cycles} failed generation cycles"
            )
            insert_memory(
                memory_id=str(uuid.uuid4()),
                interaction_date=interaction_date,
                entity_type=entity_type,
                entity_id=entity_id,
                interaction_ids=[],
                content_summary="",
                related_entities=[],
                intents=[],
                relationships=[],
                embedding=None,
                processing_errors={
                    "quarantine": (
                        f"generation failed {cycles} cycles; interactions marked done "
                        f"to stop nightly retry churn. Repair via bulk reprocess."
                    )
                },
            )
            with get_memory_db_context() as conn:
                cursor = conn.cursor()
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
    Uses the sequential pipeline executor to process nodes in DB-defined order.

    Acquires the per-entity+date memory lock so the same entity-day cannot be
    generated twice concurrently (outbound webhooks gate on the entity across
    all dates via memory_lock.is_locked). Released in a finally block."""
    from services import memory_lock

    # Best-effort: if another job is already generating this entity-day, skip —
    # that job will produce the memory. The daily scheduler will also retry on
    # the next run.
    lock_token = memory_lock.acquire(entity_type, entity_id, interaction_date)
    if not lock_token:
        logger.info(
            f"Memory lock held for {entity_type}/{entity_id} on {interaction_date}; "
            f"another job in flight. Skipping."
        )
        return

    try:
        await _generate_memory_for_entity_impl(entity_type, entity_id, interaction_date)
    finally:
        memory_lock.release(entity_type, entity_id, lock_token, interaction_date)


async def _generate_memory_for_entity_impl(entity_type: str, entity_id: str, interaction_date: str):
    """Implementation body. Wrapped by _generate_memory_for_entity which holds
    the per-entity memory lock for the duration."""

    config = _get_entity_type_config(entity_type)

    # Read interaction types filter for memory generation (e.g. AI thoughts/tool calls)
    settings = get_memory_settings()
    excluded_types = settings.get("memory_generation_interaction_types")
    if isinstance(excluded_types, str):
        import json as _json
        excluded_types = _json.loads(excluded_types)
    mode = settings.get("memory_generation_interaction_types_mode", "exclude")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        if excluded_types:
            op = "= ANY(%s)" if mode == "include" else "!= ALL(%s)"
            cursor.execute(f"""
                SELECT id, content, metadata, metadata_field_map, interaction_type
                FROM interactions
                WHERE primary_entity_type = %s
                  AND primary_entity_id = %s
                  AND DATE(timestamp) = %s
                  AND status IN ('pending', 'failed')
                  AND interaction_type {op}
                ORDER BY timestamp
            """, (entity_type, entity_id, interaction_date, excluded_types))
        else:
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
        "settings": settings,
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

    if not content_summary and processing_errors:
        # Do NOT write an empty "husk": a row with an empty summary marks its
        # interactions done and (via the daily sweep's existence check) blocks
        # regeneration of this entity-day forever, silently. Raise so BullMQ
        # retries with backoff and the interactions stay pending instead. Each
        # raise bumps a generation-cycle stamp on the day's interactions; the
        # nightly sweep quarantines the day once MAX_GENERATION_CYCLES is hit.
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE interactions
                SET processing_errors = jsonb_set(
                        COALESCE(processing_errors, '{}'::jsonb),
                        '{generation_cycle}',
                        to_jsonb(COALESCE((processing_errors->>'generation_cycle')::int, 0) + 1))
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND DATE(timestamp) = %s
                  AND status IN ('pending', 'failed')
            """, (entity_type, entity_id, interaction_date))
        raise RuntimeError(
            f"Memory generation produced no summary for {entity_type}/{entity_id} on "
            f"{interaction_date} ({len(processing_errors)} pipeline node errors: "
            f"{sorted(processing_errors.keys())})"
        )

    memory_id = str(uuid.uuid4())
    stored_id = insert_memory(
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
        f"Generated memory {stored_id} for {entity_type}/{entity_id} on {interaction_date} "
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
        # entity_type/entity_id passed top-level so inject_variables' profile
        # resolver fires and exposes {{ entity.name }}/{{ entity.subtype }} etc.
        system_prompt = inject_variables(system_prompt, {
            "entity_type": ctx["entity_type"],
            "entity_id": ctx["entity_id"],
            "date": ctx["interaction_date"],
        })
        llm_fn, llm_kwargs = _llm_call(node)
        result = await llm_fn(
            llm_context[:10000],
            system_prompt=system_prompt,
            max_tokens=(ctx.get("settings") or {}).get("memory_generation_max_tokens") or 1200,
            config_id=node_id,
            **llm_kwargs,
        )
        if result is None or not str(result).strip():
            # A 200-with-empty-content LLM response (e.g. a reasoning model that
            # spent its whole completion budget on invisible reasoning tokens)
            # must not fall through as a "successful" node — that writes an
            # empty husk with no recorded errors and blocks this entity-day
            # forever. Raise so the node error is recorded and the job retries.
            raise RuntimeError(f"Memory-generation LLM returned empty output (node {node_id})")
        ctx["derived_text"] = result
        logger.info(f"Memory generation node {node_id}: produced summary")

    elif task_type == "summarization":
        system_prompt = get_system_prompt_by_config_id(node_id) or "Summarize this in 1-2 sentences:\n\n{{text}}"
        prompt = system_prompt.replace("{{text}}", ctx["derived_text"][:4000])
        llm_fn, llm_kwargs = _llm_call(node)
        result = await llm_fn(
            prompt, max_tokens=200, config_id=node_id, **llm_kwargs,
        )
        if result is None or not str(result).strip():
            raise RuntimeError(f"Summarization LLM returned empty output (node {node_id})")
        ctx["derived_text"] = result
        logger.info(f"Summarization node {node_id}: summarized text")

    elif task_type == "pii_scrubbing":
        if provider == "zendata":
            ctx["derived_text"] = await scrub_pii(ctx["derived_text"])
        else:
            system_prompt = get_system_prompt_by_config_id(node_id) or "Remove all PII from the following text. Return only the scrubbed text."
            llm_fn, llm_kwargs = _llm_call(node)
            ctx["derived_text"] = await llm_fn(
                ctx["derived_text"][:8000],
                system_prompt=system_prompt,
                max_tokens=2000,
                config_id=node_id,
                **llm_kwargs,
            )
        logger.info(f"PII scrubbing node {node_id}: scrubbed text")

    elif task_type in ("intelligence_generation", "knowledge_generation"):
        system_prompt = get_system_prompt_by_config_id(node_id)
        if not system_prompt:
            system_prompt = "You are an AI analyst. Identify a meaningful pattern or insight. Return JSON."
        # top-level keys so inject_variables' profile resolver fires (entity.name etc.)
        signal_vars = {"entity_type": ctx.get("entity_type", ""), "entity_id": ctx.get("entity_id", "")}
        entity_config = ctx.get("config") or _get_entity_type_config(ctx.get("entity_type", ""))
        if task_type == "intelligence_generation":
            signals = entity_config.get("intelligence_signals_prompt") or []
            signal_vars["intelligence_signals"] = _format_signal_definitions(signals)
        elif task_type == "knowledge_generation":
            signals = entity_config.get("knowledge_signals_prompt") or []
            signal_vars["knowledge_signals"] = _format_signal_definitions(signals)
        system_prompt = inject_variables(system_prompt, signal_vars)
        llm_fn, llm_kwargs = _llm_call(node)
        ctx["derived_text"] = await llm_fn(
            ctx["derived_text"][:8000],
            system_prompt=system_prompt,
            max_tokens=800,
            config_id=node_id,
            **llm_kwargs,
        )
        logger.info(f"{task_type} node {node_id}: generated knowledge")

    elif task_type == "vision":
        logger.debug(f"Vision node {node_id} skipped (only runs during interaction ingestion)")

    else:
        logger.warning(f"Unknown pipeline task_type '{task_type}' for node {node_id} — skipped")
