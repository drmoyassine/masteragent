import os
import json
import asyncio
import logging
from bullmq import Queue, Worker
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
redis_conn = Redis.from_url(REDIS_URL)

memory_bulk_queue = Queue("memory_bulk_ops", connection=redis_conn)
memory_bulk_worker = None

async def _process_bulk_job(job, token):
    try:
        # Import dynamically to avoid circular dependencies at boot
        from memory.webhooks import process_interaction
        from services.config_helpers import get_llm_config
        
        interaction_id = job.data.get("interaction_id")
        provider_config = get_llm_config("summarization")
        
        # Calculate optimal sleep time to honor rate limits dynamically natively
        # OpenRouter default config usually implies 60 RPM if not specifically set
        # Using 60 as a default fallback logic metric for backoff arrays
        rpm = 60
        if provider_config and "rate_limit_rpm" in provider_config:
            rpm = provider_config.get("rate_limit_rpm", 60)
            
        sleep_interval = 60.0 / (rpm if rpm and rpm > 0 else 60)

        if interaction_id:
            await process_interaction(interaction_id)
            logger.info(f"Successfully processed bulk job {job.id} for interaction {interaction_id}")
            
            # Mathematical rate limiting sequential block
            await asyncio.sleep(sleep_interval)
            
    except Exception as e:
        logger.error(f"Bulk job {job.id} failed: {e}")
        raise e

async def start_bullmq_workers():
    global memory_bulk_worker
    logger.info("Starting BullMQ Workers...")
    memory_bulk_worker = Worker(
        "memory_bulk_ops",
        _process_bulk_job,
        connection=redis_conn,
        concurrency=1,
    )

async def stop_bullmq_workers():
    global memory_bulk_worker
    if memory_bulk_worker:
        logger.info("Stopping BullMQ Workers...")
        await memory_bulk_worker.close()
