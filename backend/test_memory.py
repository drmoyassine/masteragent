import asyncio
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.info("Starting...")
from memory_tasks import run_daily_memory_generation
logger.info("Imported memory_tasks")
async def main():
    logger.info("Running memory generation")
    try:
        await run_daily_memory_generation(include_today=True)
        logger.info("Done successfully")
    except Exception as e:
        logger.error("Failed with error", exc_info=True)
asyncio.run(main())
