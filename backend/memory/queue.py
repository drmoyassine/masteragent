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


def _positive_int_env(name: str, default: int) -> int:
    """Read a bounded queue setting without allowing malformed deployment envs."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; using %s", name, default)
        return default
    return max(0, value)


# BullMQ stores completed/failed job payloads unless retention is explicitly
# bounded.  Counts are deliberately configurable because production operators
# may need a larger audit window, but must never be unbounded by default.
BULL_REMOVE_ON_COMPLETE = _positive_int_env("BULL_REMOVE_ON_COMPLETE_COUNT", 1000)
BULL_REMOVE_ON_FAIL = _positive_int_env("BULL_REMOVE_ON_FAIL_COUNT", 1000)
BULL_DEFAULT_JOB_OPTIONS = {
    "removeOnComplete": BULL_REMOVE_ON_COMPLETE,
    "removeOnFail": BULL_REMOVE_ON_FAIL,
}

interactions_queue = Queue("interactions_ops", opts={"connection": REDIS_URL, "defaultJobOptions": BULL_DEFAULT_JOB_OPTIONS})
memory_queue = Queue("memory_ops", opts={"connection": REDIS_URL, "defaultJobOptions": BULL_DEFAULT_JOB_OPTIONS})
knowledge_queue = Queue("knowledge_ops", opts={"connection": REDIS_URL, "defaultJobOptions": BULL_DEFAULT_JOB_OPTIONS})
memory_bulk_queue = interactions_queue

interactions_worker = None
memory_worker = None
knowledge_worker = None

async def _process_bulk_job(job: Job, token: str):
    singleton_lock_name = None
    run_id = None
    operation_result = None
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
            "extract_knowledge_attachment",
        }
        if job.name in ai_jobs:
            from services.job_safety import active_provider_stop
            provider_block = active_provider_stop()
            if provider_block:
                if job.name == "extract_knowledge_attachment" and job.data.get("attachment_id"):
                    from core.storage import get_memory_db_context
                    with get_memory_db_context() as conn:
                        conn.cursor().execute(
                            "UPDATE knowledge_attachments SET status='blocked', extraction=%s::jsonb, updated_at=NOW() WHERE id=%s",
                            (json.dumps({"error": provider_block["message"], "reason": provider_block["code"]}), job.data.get("attachment_id")),
                        )
                from memory_db_writes import log_pipeline_run
                log_pipeline_run(job.name, "blocked", reason_code=provider_block["code"],
                                 detail={"message": provider_block["message"], "queue_job_id": str(job.id)},
                                 trigger="queue")
                logger.warning("Skipping %s (%s): %s", job.name, job.id, provider_block["code"])
                return {"status": "blocked", "reason": provider_block["code"]}

        control_job = {
            "knowledge_embedding_backfill": "knowledge_embedding_backfill",
            "run_all_knowledge_generation": "run_all_knowledge_generation",
            "generate_knowledge": "run_all_knowledge_generation",
            "knowledge_hygiene_run": "knowledge_hygiene_run",
            "run_consolidation": "knowledge_hygiene_run",
            "backfill_facets": "backfill_facets",
            "interaction_retention": "interaction_retention",
        }.get(job.name)
        if control_job:
            from services.job_controls import get_command
            command = get_command(control_job)
            if command in {"pause", "cancel"}:
                logger.info("Skipping %s at operator checkpoint (%s)", job.name, command)
                from memory_db_writes import log_pipeline_run
                log_pipeline_run(job.name, "skipped", reason_code=f"operator_{command}",
                                 detail={"queue_job_id": str(job.id), "control": command}, trigger="queue")
                return {"status": command, "reason": f"operator_{command}"}

        singleton_jobs = {
            "knowledge_embedding_backfill", "backfill_facets", "backfill_telemetry",
            "run_all_knowledge_generation", "run_consolidation", "knowledge_hygiene_run",
            "extract_playbooks", "interaction_retention", "refresh_operation_metrics",
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
            max_records = job.data.get("max_records")
            batch_size = job.data.get("batch_size")
            if max_records:
                if job.name == "knowledge_embedding_backfill":
                    average_tokens, price_per_million = 500, 0.02
                else:
                    # Generation/facet/hygiene input sizes vary by record and
                    # provider. Store a planning token estimate, but do not
                    # pretend we can calculate a reliable bill without model
                    # pricing metadata.
                    average_tokens, price_per_million = 1200, None
                estimated_tokens = int(max_records) * average_tokens
                estimated_cost = (estimated_tokens * price_per_million / 1_000_000) if price_per_million else None
            else:
                estimated_tokens = estimated_cost = None
            run_id = log_pipeline_run(
                job.name, "started",
                detail={"queue_job_id": str(job.id), "progress_total": int(max_records or 0),
                        "estimated_tokens": estimated_tokens, "estimated_cost_usd": estimated_cost,
                        "batch_size": batch_size,
                        "records_per_batch": job.data.get("records_per_batch") or batch_size,
                        "batches_per_run": job.data.get("batches_per_run"),
                        "run_all": bool(job.data.get("run_all", False))}, trigger="queue")

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
            operation_result = await run_knowledge_check(
                drain=bool(job.data.get("drain")), min_count=job.data.get("min_count"),
                max_rounds=int(job.data.get("max_rounds", 50 if job.data.get("drain") else 1)),
                max_records=int(job.data.get("max_records", 100000)),
                progress_run_id=run_id,
            )
            p_conf = get_llm_config("knowledge_generation")
            if p_conf and "rate_limit_rpm" in p_conf:
                rpm = p_conf.get("rate_limit_rpm", 60)

        elif job.name == "run_all_knowledge_generation":
            # One orchestrated run for every enabled producer. Individual legacy
            # job names remain accepted for API/backlog compatibility.
            operation_result = await run_knowledge_check(
                drain=bool(job.data.get("drain")), min_count=job.data.get("min_count"),
                max_rounds=int(job.data.get("max_rounds", 50 if job.data.get("drain") else 1)),
                max_records=int(job.data.get("max_records", 100000)),
                progress_run_id=run_id,
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
            operation_result = await run_consolidation(
                max_records=int(job.data.get("max_records", 1000)),
                max_clusters=int(job.data.get("max_clusters", 100)),
                progress_run_id=run_id,
            )

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
            operation_result = await discover_and_propose(
                run_id=job.data.get("run_id"),
                origin=job.data.get("origin") or "scheduled",
                mode=_mode,
                category_filter=job.data.get("category"),
                actor_id=None,
                auto_apply=bool(_auto),
                max_records=int(job.data.get("max_records", 5000)),
                max_clusters=int(job.data.get("max_clusters", 100)),
                progress_run_id=run_id,
            )

        elif job.name == "knowledge_embedding_backfill":
            # Resumable, idempotent embedding backfill (never mutates content/status).
            from memory_embedding_backfill import run_embedding_backfill
            operation_result = await run_embedding_backfill(
                batch_size=int(job.data.get("batch_size", 25)),
                max_records=int(job.data.get("max_records", 1000)),
                progress_run_id=run_id,
            )

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
            operation_result = await backfill_facets(
                batch_size=int(job.data.get("batch_size", 25)),
                max_records=int(job.data.get("max_records", 250)),
                progress_run_id=run_id,
            )

        elif job.name == "backfill_telemetry":
            from memory_telemetry import backfill_telemetry
            await backfill_telemetry(max_days=int(job.data.get("max_days", 7)))

        elif job.name == "interaction_retention":
            from memory_interaction_retention import run_interaction_retention
            operation_result = run_interaction_retention(
                batch_size=int(job.data.get("batch_size", 500)),
                max_records=int(job.data.get("max_records", 5000)),
                progress_run_id=run_id,
            )

        elif job.name == "refresh_operation_metrics":
            from memory_operation_metrics import refresh_snapshots
            operation_result = refresh_snapshots()

        elif job.name == "run_intelligence_sweep":
            from memory_compaction import run_compaction_check
            await run_compaction_check(min_count=job.data.get("min_count"))

        elif job.name == "reflect_telemetry":
            from memory_telemetry import run_telemetry_reflection
            await run_telemetry_reflection(job.data.get("reflection_date"))

        elif job.name == "extract_knowledge_attachment":
            from memory_knowledge_attachments import extract_attachment
            operation_result = await extract_attachment(
                str(job.data.get("attachment_id")),
                max_pages=int(job.data.get("max_pages", 200)),
            )

        else:
            logger.warning(f"Unknown job name: {job.name}")

        logger.info(f"Successfully processed bulk job {job.id} ({job.name})")
        if singleton_lock_name:
            from memory_db_writes import log_pipeline_run
            from services.job_controls import get_command
            control = control_job and get_command(control_job)
            stopped = control in {"pause", "cancel"}
            detail = {"queue_job_id": str(job.id), "result": operation_result or {},
                      "control": control or "run"}
            if run_id:
                from memory_db_writes import update_pipeline_run
                if isinstance(operation_result, dict):
                    tier_results = operation_result.get("tiers") or {}
                    base_completed = operation_result.get("processed")
                    if base_completed is None:
                        base_completed = operation_result.get("clusters_found", operation_result.get("records_scanned", 0))
                        if operation_result.get("clusters_found") is not None:
                            base_completed = min(int(base_completed or 0), int(job.data.get("max_clusters", 100)))
                    completed = int(base_completed or 0) + sum(int(v.get("processed", 0) or 0) for v in tier_results.values() if isinstance(v, dict))
                    failed_total = int(operation_result.get("failed", 0) or 0) + sum(int(v.get("failed", 0) or 0) for v in tier_results.values() if isinstance(v, dict))
                else:
                    completed, failed_total = int(operation_result or 0), 0
                update_pipeline_run(run_id, status="cancelled" if control == "cancel" else ("paused" if control == "pause" else "completed"),
                                    outcome="stopped" if stopped else "completed", records_created=int(completed or 0),
                                    progress_completed=int(completed or 0), progress_failed=failed_total,
                                    detail=detail)
            else:
                log_pipeline_run(job.name, "completed", detail=detail, trigger="queue")

            # Eligibility changes when any Knowledge operation completes. Keep
            # the persisted UI snapshot current even when no browser is open;
            # the guard collapses simultaneous completion/UI refresh requests.
            if job.name in {
                "knowledge_embedding_backfill", "run_all_knowledge_generation",
                "knowledge_hygiene_run", "backfill_facets",
            }:
                from memory_operation_metrics import mark_refresh_error, request_refresh
                if request_refresh():
                    try:
                        await knowledge_queue.add("refresh_operation_metrics", {}, {"priority": 4})
                    except Exception as refresh_exc:
                        mark_refresh_error(f"Could not queue post-operation eligibility refresh: {refresh_exc}")
                        logger.warning("Could not queue eligibility refresh: %s", refresh_exc)
        
        # Mathematical rate limiting sequential block
        sleep_interval = 60.0 / (rpm if rpm and rpm > 0 else 60)
        await asyncio.sleep(sleep_interval)
            
    except Exception as e:
        logger.error(f"Bulk job {job.id} failed: {e}")

        if run_id:
            from memory_db_writes import update_pipeline_run
            update_pipeline_run(run_id, status="failed", outcome="failed",
                                reason_code="job_failed",
                                detail={"message": str(e), "queue_job_id": str(job.id)})

        from services.job_safety import ProviderStopError
        if isinstance(e, ProviderStopError):
            from memory_db_writes import log_pipeline_run
            if run_id:
                from memory_db_writes import update_pipeline_run
                update_pipeline_run(run_id, status="blocked", outcome="blocked", reason_code=e.code,
                                    detail={"message": str(e), "queue_job_id": str(job.id)})
            else:
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
    
    from services.job_safety import reconcile_stale_maintenance_runs
    reconcile_stale_maintenance_runs()

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



