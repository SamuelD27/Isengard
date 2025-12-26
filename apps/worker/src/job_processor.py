"""
Job Processor

Handles execution of training and generation jobs.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger, set_correlation_id
from packages.shared.src.types import (
    JobStatus,
    JobType,
    TrainingJob,
    GenerationJob,
    TrainingConfig,
    GenerationConfig,
)

from packages.plugins.training import get_training_plugin, register_training_plugin
from packages.plugins.training.src.mock_plugin import MockTrainingPlugin
from packages.plugins.training.src.ai_toolkit import AIToolkitPlugin

from packages.plugins.image import get_image_plugin, register_image_plugin
from packages.plugins.image.src.mock_plugin import MockImagePlugin
from packages.plugins.image.src.comfyui import ComfyUIPlugin

logger = get_logger("worker.processor")


class JobProcessor:
    """
    Processes jobs from the queue.

    Initializes plugins based on operating mode and executes jobs.
    """

    def __init__(self):
        self.config = get_global_config()
        self._redis = None
        self._current_job: dict | None = None

    async def initialize(self) -> None:
        """Initialize the processor and register plugins."""
        logger.info("Initializing job processor", extra={"mode": self.config.mode})

        # Register plugins based on mode
        if self.config.is_fast_test:
            # Use mock plugins for fast-test mode
            register_training_plugin(MockTrainingPlugin(), default=True)
            register_image_plugin(MockImagePlugin(), default=True)
            logger.info("Registered mock plugins for fast-test mode")
        else:
            # Use production plugins
            register_training_plugin(AIToolkitPlugin(), default=True)
            register_image_plugin(ComfyUIPlugin(), default=True)
            logger.info("Registered production plugins")

        # TODO: Connect to Redis
        # self._redis = await redis.from_url(self.config.redis_url)

    async def shutdown(self) -> None:
        """Shutdown the processor."""
        if self._redis:
            await self._redis.close()

    async def get_next_job(self, timeout: float = 5.0) -> dict | None:
        """
        Get the next job from the queue.

        TODO: Implement actual Redis queue consumption.
        For now, returns None (no jobs).
        """
        # TODO: BLPOP from Redis queue
        # job_data = await self._redis.blpop("isengard:jobs", timeout=timeout)
        # if job_data:
        #     return json.loads(job_data[1])
        return None

    async def process_job(self, job: dict) -> None:
        """
        Process a job.

        Routes to appropriate handler based on job type.
        """
        job_type = job.get("type")
        job_id = job.get("id")
        correlation_id = job.get("correlation_id", f"job-{job_id}")

        set_correlation_id(correlation_id)
        self._current_job = job

        logger.info(f"Processing job", extra={
            "job_id": job_id,
            "job_type": job_type,
        })

        try:
            if job_type == JobType.TRAINING.value:
                await self._process_training_job(job)
            elif job_type == JobType.IMAGE_GENERATION.value:
                await self._process_generation_job(job)
            else:
                logger.error(f"Unknown job type: {job_type}")

        except Exception as e:
            logger.error(f"Job failed: {e}", extra={
                "job_id": job_id,
                "error": str(e),
            })
            await self._mark_job_failed(job_id, str(e))

        finally:
            self._current_job = None

    async def _process_training_job(self, job: dict) -> None:
        """Process a training job."""
        job_id = job["id"]
        character_id = job["character_id"]
        config_data = job.get("config", {})

        config = TrainingConfig(**config_data)
        plugin = get_training_plugin()

        logger.info("Starting training", extra={
            "job_id": job_id,
            "character_id": character_id,
            "plugin": plugin.name,
            "method": config.method.value,
        })

        # Validate config
        valid, error = await plugin.validate_config(config)
        if not valid:
            logger.error(f"Invalid training config: {error}")
            await self._mark_job_failed(job_id, error or "Invalid configuration")
            return

        # Prepare paths
        images_dir = self.config.uploads_dir / character_id
        output_path = self.config.models_dir / f"{character_id}.safetensors"

        # Get trigger word (would come from character data)
        trigger_word = job.get("trigger_word", "ohwx person")

        # Progress callback
        def on_progress(progress):
            logger.info(f"Training progress: {progress.percentage:.1f}%", extra={
                "step": progress.current_step,
                "total": progress.total_steps,
                "loss": progress.loss,
            })
            # TODO: Publish progress to Redis pub/sub

        # Run training
        await self._mark_job_running(job_id)
        result = await plugin.train(
            config=config,
            images_dir=images_dir,
            output_path=output_path,
            trigger_word=trigger_word,
            progress_callback=on_progress,
        )

        if result.success:
            logger.info("Training completed", extra={
                "job_id": job_id,
                "output_path": str(result.output_path),
                "training_time": result.training_time_seconds,
            })
            await self._mark_job_completed(job_id, str(result.output_path))
        else:
            logger.error(f"Training failed: {result.error_message}")
            await self._mark_job_failed(job_id, result.error_message or "Unknown error")

    async def _process_generation_job(self, job: dict) -> None:
        """Process an image generation job."""
        job_id = job["id"]
        config_data = job.get("config", {})
        count = job.get("count", 1)

        config = GenerationConfig(**config_data)
        plugin = get_image_plugin()

        logger.info("Starting generation", extra={
            "job_id": job_id,
            "plugin": plugin.name,
            "size": f"{config.width}x{config.height}",
            "count": count,
        })

        # Check health
        healthy, error = await plugin.check_health()
        if not healthy:
            await self._mark_job_failed(job_id, error or "Backend unavailable")
            return

        # Prepare paths
        output_dir = self.config.outputs_dir / job_id
        lora_path = None
        if config.lora_id:
            lora_path = self.config.models_dir / f"{config.lora_id}.safetensors"

        # Progress callback
        def on_progress(progress):
            logger.info(f"Generation progress: {progress.percentage:.1f}%", extra={
                "step": progress.current_step,
                "total": progress.total_steps,
            })
            # TODO: Publish progress to Redis pub/sub

        # Run generation
        await self._mark_job_running(job_id)
        result = await plugin.generate(
            config=config,
            output_dir=output_dir,
            lora_path=lora_path,
            count=count,
            progress_callback=on_progress,
        )

        if result.success:
            output_paths = [str(p) for p in result.output_paths]
            logger.info("Generation completed", extra={
                "job_id": job_id,
                "output_count": len(output_paths),
                "generation_time": result.generation_time_seconds,
            })
            await self._mark_job_completed(job_id, output_paths)
        else:
            logger.error(f"Generation failed: {result.error_message}")
            await self._mark_job_failed(job_id, result.error_message or "Unknown error")

    async def _mark_job_running(self, job_id: str) -> None:
        """Mark job as running."""
        # TODO: Update job status in Redis/database
        logger.info(f"Job {job_id} marked as running")

    async def _mark_job_completed(self, job_id: str, output: Any) -> None:
        """Mark job as completed."""
        # TODO: Update job status in Redis/database
        logger.info(f"Job {job_id} marked as completed", extra={"output": output})

    async def _mark_job_failed(self, job_id: str, error: str) -> None:
        """Mark job as failed."""
        # TODO: Update job status in Redis/database
        logger.error(f"Job {job_id} marked as failed", extra={"error": error})
