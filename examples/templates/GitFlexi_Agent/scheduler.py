"""Scheduler for GitFlexi Agent."""

import asyncio
import logging
from datetime import datetime

from .agent import default_agent
from .config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("git-flexi-scheduler")


async def run_scheduler():
    """Run the agent periodically based on configuration."""
    interval_seconds = settings.analysis_interval_minutes * 60
    logger.info(f"Starting scheduler. Interval: {settings.analysis_interval_minutes} minutes.")
    
    while True:
        try:
            logger.info("Starting scheduled agent run...")
            start_time = datetime.now()
            
            # Execute agent
            result = await default_agent.run({})
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if result.success:
                logger.info(f"Run completed successfully in {duration:.2f}s.")
            else:
                logger.error(f"Run failed: {result.error}")
                
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            
        # Calculate sleep time (to maintain strict interval if needed, or just sleep fixed amount)
        # Simple sleep for now
        logger.info(f"Sleeping for {settings.analysis_interval_minutes} minutes...")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")
