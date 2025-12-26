"""
Isengard Worker - Background Job Processor

M2: Consumes jobs from Redis Streams via XREADGROUP.
Executes training/generation tasks using registered plugins.
"""

import asyncio
import os
import signal
import sys
from pathlib import Path

# Add packages to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import configure_logging, get_logger, set_correlation_id

from .job_processor import JobProcessor

logger = get_logger("worker.main")


class Worker:
    """
    Background job worker.

    M2: Consumes jobs from Redis Streams using consumer groups.
    Processes them using registered plugins.
    """

    def __init__(self, consumer_name: str | None = None):
        self.config = get_global_config()
        # Consumer name for Redis consumer group (allow scaling with unique names)
        self.consumer_name = consumer_name or os.getenv("WORKER_NAME", "worker-1")
        self.processor = JobProcessor(consumer_name=self.consumer_name)
        self._shutdown = asyncio.Event()
        self._running = False

    async def start(self) -> None:
        """Start the worker."""
        configure_logging("worker")
        self.config.ensure_directories()

        logger.info("Starting Isengard Worker", extra={
            "event": "worker.start",
            "mode": self.config.mode,
            "consumer_name": self.consumer_name,
            "concurrency": self.config.worker_concurrency,
            "redis_url": self.config.redis_url.split("@")[-1],  # Redact credentials
        })

        # Register signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        # Initialize processor
        await self.processor.initialize()

        self._running = True
        logger.info("Worker started, waiting for jobs...")

        # Main processing loop
        try:
            await self._run_loop()
        except asyncio.CancelledError:
            logger.info("Worker cancelled")
        finally:
            await self._cleanup()

    async def _run_loop(self) -> None:
        """Main job processing loop."""
        while self._running and not self._shutdown.is_set():
            try:
                # Try to get a job from the queue
                job = await self.processor.get_next_job(timeout=5.0)

                if job:
                    # Process the job
                    await self.processor.process_job(job)
                else:
                    # No job available, continue polling
                    await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"Error in worker loop: {e}", extra={"error": str(e)})
                await asyncio.sleep(5.0)  # Back off on error

    def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._running = False
        self._shutdown.set()

    async def _cleanup(self) -> None:
        """Cleanup on shutdown."""
        logger.info("Cleaning up worker...")
        await self.processor.shutdown()
        logger.info("Worker shutdown complete")


async def main():
    """Main entry point."""
    worker = Worker()
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
