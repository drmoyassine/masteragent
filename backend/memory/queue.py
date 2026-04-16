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

class PromoteLessonPayload(TypedDict):
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
    try:
        # Import dynamically to avoid circular dependencies at boot
        from memory_tasks import (
            process_interaction, 
            _generate_memory_for_entity,
            compact_entity,
            run_lesson_check,
            promote_to_lesson
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
            p_conf = get_llm_config("insight_generation")
            if p_conf and "rate_limit_rpm" in p_conf:
                rpm = p_conf.get("rate_limit_rpm", 60)
                
        elif job.name == "generate_lesson":
            await run_lesson_check()
            p_conf = get_llm_config("insight_generation")
            if p_conf and "rate_limit_rpm" in p_conf:
                rpm = p_conf.get("rate_limit_rpm", 60)
            
        elif job.name == "promote_to_lesson":
            i_id = job.data.get("insight_id")
            if i_id:
                await promote_to_lesson(i_id)
            p_conf = get_llm_config("insight_generation")
            if p_conf and "rate_limit_rpm" in p_conf:
                rpm = p_conf.get("rate_limit_rpm", 60)
                
        else:
            logger.warning(f"Unknown job name: {job.name}")

        logger.info(f"Successfully processed bulk job {job.id} ({job.name})")
        
        # Mathematical rate limiting sequential block
        sleep_interval = 60.0 / (rpm if rpm and rpm > 0 else 60)
        await asyncio.sleep(sleep_interval)
            
    except Exception as e:
        logger.error(f"Bulk job {job.id} failed: {e}")
        
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
            cursor.execute("SELECT settings FROM memory_settings LIMIT 1")
            row = cursor.fetchone()
            if row and row["settings"]:
                settings = row["settings"]
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
