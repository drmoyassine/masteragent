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

memory_bulk_queue = Queue("memory_bulk_ops", opts={"connection": REDIS_URL})
memory_bulk_worker = None

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
        
        provider_config = get_llm_config("summarization")
        
        # Calculate optimal sleep time to honor rate limits dynamically natively
        rpm = 60
        if provider_config and "rate_limit_rpm" in provider_config:
            rpm = provider_config.get("rate_limit_rpm", 60)
            
        sleep_interval = 60.0 / (rpm if rpm and rpm > 0 else 60)

        logger.info(f"Worker picked up job {job.id}: {job.name}")

        # Core Orchestrator Switch
        if job.name in ["ingest_interaction", "reprocess"]:
            interaction_id = job.data.get("interaction_id")
            if interaction_id:
                await process_interaction(interaction_id)
        
        elif job.name == "generate_memory":
            e_type = job.data.get("entity_type")
            e_id = job.data.get("entity_id")
            date_str = job.data.get("interaction_date")
            if e_type and e_id and date_str:
                await _generate_memory_for_entity(e_type, e_id, date_str)
                
        elif job.name == "generate_insight":
            e_type = job.data.get("entity_type")
            e_id = job.data.get("entity_id")
            if e_type and e_id:
                await compact_entity(e_type, e_id)
                
        elif job.name == "generate_lesson":
            await run_lesson_check()
            
        elif job.name == "promote_to_lesson":
            i_id = job.data.get("insight_id")
            if i_id:
                await promote_to_lesson(i_id)
                
        elif job.name == "fire_outbound_webhook":
            webhook_id = job.data.get("webhook_id")
            entity_id = job.data.get("entity_id")
            if webhook_id and entity_id:
                from services.outbound_webhooks import execute_outbound_webhook
                await execute_outbound_webhook(webhook_id, entity_id)
                
        else:
            logger.warning(f"Unknown job name: {job.name}")

        logger.info(f"Successfully processed bulk job {job.id} ({job.name})")
        
        # Mathematical rate limiting sequential block
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
    global memory_bulk_worker
    logger.info("Starting BullMQ Workers...")
    memory_bulk_worker = Worker(
        "memory_bulk_ops",
        _process_bulk_job,
        opts={"connection": REDIS_URL, "concurrency": 1},
    )
    memory_bulk_worker.on("completed", _handle_completed)
    memory_bulk_worker.on("failed", _handle_failed)

async def stop_bullmq_workers():
    global memory_bulk_worker
    if memory_bulk_worker:
        logger.info("Stopping BullMQ Workers gracefully...")
        # give it 30s to finish active tasks
        await memory_bulk_worker.close()
        logger.info("BullMQ Workers stopped.")
