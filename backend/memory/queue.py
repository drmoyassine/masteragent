import os
import json
import asyncio
import logging
from typing import Optional, TypedDict, Any
from bullmq import Queue, Worker, Job
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Enterprise Type Safety for BullMQ
class IngestInteractionPayload(TypedDict):
    interaction_id: str

class GenerateMemoryPayload(TypedDict):
    entity_type: str
    entity_id: str
    interaction_date: str

class BasicEntityPayload(TypedDict):
    entity_type: str
    entity_id: str

class PromoteKnowledgePayload(TypedDict):
    insight_id: str

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

interactions_queue = Queue("interactions_ops", opts={"connection": REDIS_URL})
memory_queue = Queue("memory_ops", opts={"connection": REDIS_URL})
knowledge_queue = Queue("knowledge_ops", opts={"connection": REDIS_URL})
memory_bulk_queue = interactions_queue

interactions_worker = None
memory_worker = None
knowledge_worker = None

async def _process_bulk_job(job: Job, token: str):
    singleton_lock_name = None
    try:
        # A credit/quota hard-stop must halt queued AI work cleanly. Completing
        # the skipped job (rather than retrying it) prevents a queue storm; an
        # operator can re-run it after resolving the provider alert.
        ai_jobs = {
            "ingest_interaction", "reprocess", "generate_memory", "generate_insight",
            "generate_knowledge", "run_all_knowledge_generation", "promote_to_knowledge",
            "extract_playbooks", "knowledge_hygiene_run", "knowledge_embedding_backfill",
            "creation_time_consolidation", "backfill_facets", "backfill_telemetry",
            "run_intelligence_sweep", "reflect_telemetry",
        }
        if job.name in ai_jobs:
            from services.job_safety import active_provider_stop
            provider_block = active_provider_stop()
            if provider_block:
                from memory_db_writes import log_pipeline_run
                log_pipeline_run(job.name, "blocked", reason_code=provider_block["code"],
                                 detail={"message": provider_block["message"], "queue_job_id": str(job.id)},
                                 trigger="queue")
                logger.warning("Skipping %s (%s): %s", job.name, job.id, provider_block["code"])
                return {"status": "blocked", "reason": provider_block["code"]}

        singleton_jobs = {
            "knowledge_embedding_backfill", "backfill_facets", "backfill_telemetry",
            "run_all_knowledge_generation", "run_consolidation", "knowledge_hygiene_run",
            "extract_playbooks",
        }
        if job.name in singleton_jobs:
            from services.job_safety import try_acquire_singleton_job
            if not try_acquire_singleton_job(job.name):
                from memory_db_writes import log_pipeline_run
                log_pipeline_run(job.name, "skipped", reason_code="already_running",
                                 detail={"queue_job_id": str(job.id)}, trigger="queue")
                logger.warning("Skipping duplicate maintenance job %s (%s)", job.name, job.id)
                return {"status": "skipped", "reason": "already_running"}
            singleton_lock_name = job.name
            from memory_db_writes import log_pipeline_run
            log_pipeline_run(job.name, "started", detail={"queue_job_id": str(job.id)}, trigger="queue")

        # Import dynamically to avoid circular dependencies at boot
        from memory_tasks import (
            process_interaction, 
            _generate_memory_for_entity,
            compact_entity,
            run_knowledge_check,
            promote_to_knowledge
        )
        from services.config_helpers import get_llm_config
        
        logger.info(f"Worker picked up job {job.id}: {job.name}")

        # Core Orchestrator Switch & specific mathematical sleeping
        rpm = 60
        if job.name in ["ingest_interaction", "reprocess"]:
            interaction_id = job.data.get("interaction_id")
            if interaction_id:
                await process_interaction(interaction_id)
            rpm = 600
        
        elif job.name == "fire_outbound_webhook":
            webhook_id = job.data.get("webhook_id")
            entity_id = job.data.get("entity_id")
            if webhook_id and entity_id:
                from services.outbound_webhooks import execute_outbound_webhook
                await execute_outbound_webhook(webhook_id, entity_id)
            rpm = 600
        
        elif job.name == "generate_memory":
            e_type = job.data.get("entity_type")
            e_id = job.data.get("entity_id")
            date_str = job.data.get("interaction_date")
            if e_type and e_id and date_str:
                await _generate_memory_for_entity(e_type, e_id, date_str)
            p_conf = get_llm_config("summarization")
            if p_conf and "rate_limit_rpm" in p_conf:
                rpm = p_conf.get("rate_limit_rpm", 60)
                
        elif job.name == "generate_insight":
            e_type = job.data.get("entity_type")
            e_id = job.data.get("entity_id")
            if e_type and e_id:
                await compact_entity(e_type, e_id)
            p_conf = get_llm_config("intelligence_generation")
            if p_conf and "rate_limit_rpm" in p_conf:
                rpm = p_conf.get("rate_limit_rpm", 60)

        elif job.name == "generate_knowledge":
            await run_knowledge_check(drain=bool(job.data.get("drain")), min_count=job.data.get("min_count"))
            p_conf = get_llm_config("knowledge_generation")
            if p_conf and "rate_limit_rpm" in p_conf:
                rpm = p_conf.get("rate_limit_rpm", 60)

        elif job.name == "run_all_knowledge_generation":
            # One orchestrated run for every enabled producer. Individual legacy
            # job names remain accepted for API/backlog compatibility.
            await run_knowledge_check(
                drain=bool(job.data.get("drain")), min_count=job.data.get("min_count"),
            )
            from memory_playbooks import run_playbook_check
            from memory_telemetry import run_telemetry_reflection, backfill_telemetry
            await run_playbook_check()
            if job.data.get("drain"):
                await backfill_telemetry(max_days=int(job.data.get("max_days", 7)))
            else:
                await run_telemetry_reflection(job.data.get("reflection_date"))

        elif job.name == "promote_to_knowledge":
            i_id = job.data.get("insight_id")
            if i_id:
                await promote_to_knowledge(i_id)
            p_conf = get_llm_config("knowledge_generation")
            if p_conf and "rate_limit_rpm" in p_conf:
                rpm = p_conf.get("rate_limit_rpm", 60)

        elif job.name == "extract_playbooks":
            from memory_playbooks import run_playbook_check
            await run_playbook_check()

        elif job.name == "run_consolidation":
            # Legacy job name kept as a backward-compatible alias: it now starts
            # a hygiene run using the configured mode (no pairwise retirement).
            from memory_consolidation import run_consolidation
            await run_consolidation()

        elif job.name == "knowledge_hygiene_run":
            # Knowledge hygiene: discover candidate clusters + generate proposals.
            # Auto-apply only in auto_* modes; manual_only/proposal_only never apply.
            from memory_consolidation_service import discover_and_propose
            from services.config_helpers import get_memory_settings
            _hsettings = get_memory_settings() or {}
            _mode = job.data.get("mode") or _hsettings.get("knowledge_hygiene_mode", "manual_only")
            _auto = (
                bool(job.data.get("allow_auto_apply", False))
                and _mode in ("auto_conservative", "auto_synthesis")
                and _hsettings.get("knowledge_hygiene_enabled", True)
            )
            await discover_and_propose(
                run_id=job.data.get("run_id"),
                origin=job.data.get("origin") or "scheduled",
                mode=_mode,
                category_filter=job.data.get("category"),
                actor_id=None,
                auto_apply=bool(_auto),
            )

        elif job.name == "knowledge_embedding_backfill":
            # Resumable, idempotent embedding backfill (never mutates content/status).
            from memory_embedding_backfill import run_embedding_backfill
            await run_embedding_backfill()

        elif job.name == "creation_time_consolidation":
            # Async creation-time consolidation: find candidates for a freshly
            # created record and propose (auto-apply only in auto_* modes).
            from memory_consolidation_service import creation_time_propose
            from services.config_helpers import get_memory_settings
            _cts = get_memory_settings() or {}
            _cmode = _cts.get("knowledge_hygiene_mode", "manual_only")
            await creation_time_propose(
                knowledge_id=job.data.get("knowledge_id"),
                auto_apply=_cmode in ("auto_conservative", "auto_synthesis"),
            )

        elif job.name == "backfill_facets":
            from memory_facets import backfill_facets
            await backfill_facets()

        elif job.name == "backfill_telemetry":
            from memory_telemetry import backfill_telemetry
            await backfill_telemetry(max_days=int(job.data.get("max_days", 7)))

        elif job.name == "run_intelligence_sweep":
            from memory_compaction import run_compaction_check
            await run_compaction_check(min_count=job.data.get("min_count"))

        elif job.name == "reflect_telemetry":
            from memory_telemetry import run_telemetry_reflection
            await run_telemetry_reflection(job.data.get("reflection_date"))

        else:
            logger.warning(f"Unknown job name: {job.name}")

        logger.info(f"Successfully processed bulk job {job.id} ({job.name})")
        if singleton_lock_name:
            from memory_db_writes import log_pipeline_run
            log_pipeline_run(job.name, "completed", detail={"queue_job_id": str(job.id)}, trigger="queue")
        
        # Mathematical rate limiting sequential block
        sleep_interval = 60.0 / (rpm if rpm and rpm > 0 else 60)
        await asyncio.sleep(sleep_interval)
            
    except Exception as e:
        logger.error(f"Bulk job {job.id} failed: {e}")

        from services.job_safety import ProviderStopError
        if isinstance(e, ProviderStopError):
            from memory_db_writes import log_pipeline_run
            log_pipeline_run(job.name, "blocked", reason_code=e.code,
                             detail={"message": str(e), "queue_job_id": str(job.id)}, trigger="queue")
            # Do not re-raise: a provider stop is operational state, not a
            # per-record failure that BullMQ should repeatedly retry.
            return {"status": "blocked", "reason": e.code}
        
        # DLQ logic: If this is the final attempt, update database status
        attempts_made = job.attemptsMade + 1
        max_attempts = job.opts.get("attempts", 1)
        
        if attempts_made >= max_attempts:
            logger.error(f"Job {job.id} exhausted {max_attempts} retries. Moving to DLQ.")
            from core.storage import get_memory_db_context
            try:
                # Basic DLQ effort for interactions
                if job.name in ["ingest_interaction", "reprocess"]:
                    i_id = job.data.get("interaction_id")
                    if i_id:
                        with get_memory_db_context() as conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE interactions SET status = 'failed', processing_errors = %s WHERE id = %s", 
                                           (json.dumps({"fatal_error": str(e)}), i_id))
            except Exception as dlq_e:
                logger.error(f"DLQ update failed for job {job.id}: {dlq_e}")
                
        raise e
    finally:
        if singleton_lock_name:
            from services.job_safety import release_singleton_job
            release_singleton_job(singleton_lock_name)

def _handle_completed(job, result):
    logger.info(f"Job {job.id} completed successfully")

def _handle_failed(job, error):
    logger.error(f"Job {job.id} failed with error: {error}")

async def start_bullmq_workers():
    global interactions_worker, memory_worker, knowledge_worker
    from core.storage import get_memory_db_context
    
    settings = {}
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_settings LIMIT 1")
            row = cursor.fetchone()
            if row:
                settings = dict(row)
    except Exception as e:
        logger.warning(f"Failed to fetch queue settings: {e}")
        
    int_conc = int(settings.get("interactions_queue_concurrency", 5))
    mem_conc = int(settings.get("memory_queue_concurrency", 1))
    know_conc = int(settings.get("knowledge_queue_concurrency", 1))
    
    logger.info(f"Starting BullMQ Workers (Int: {int_conc}, Mem: {mem_conc}, Know: {know_conc})...")
    
    interactions_worker = Worker("interactions_ops", _process_bulk_job, opts={"connection": REDIS_URL, "concurrency": int_conc})
    interactions_worker.on("completed", _handle_completed)
    interactions_worker.on("failed", _handle_failed)

    memory_worker = Worker("memory_ops", _process_bulk_job, opts={"connection": REDIS_URL, "concurrency": mem_conc})
    memory_worker.on("completed", _handle_completed)
    memory_worker.on("failed", _handle_failed)
    
    knowledge_worker = Worker("knowledge_ops", _process_bulk_job, opts={"connection": REDIS_URL, "concurrency": know_conc})
    knowledge_worker.on("completed", _handle_completed)
    knowledge_worker.on("failed", _handle_failed)

async def stop_bullmq_workers():
    global interactions_worker, memory_worker, knowledge_worker
    logger.info("Stopping BullMQ Workers gracefully...")
    tasks = []
    if interactions_worker: tasks.append(interactions_worker.close())
    if memory_worker: tasks.append(memory_worker.close())
    if knowledge_worker: tasks.append(knowledge_worker.close())
    
    if tasks:
        await asyncio.gather(*tasks)
    logger.info("BullMQ Workers stopped.")



