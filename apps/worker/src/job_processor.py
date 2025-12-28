"""
Job Processor

Handles execution of training and generation jobs.

M2: Consumes jobs from Redis Streams via XREADGROUP.
"""

import asyncio
import json
from datetime import datetime, timezone
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
from packages.shared.src import redis_client

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

    M2: Consumes from Redis Streams using consumer groups.
    Initializes plugins based on operating mode and executes jobs.
    """

    def __init__(self, consumer_name: str = "worker-1"):
        self.config = get_global_config()
        self.consumer_name = consumer_name
        self._current_job: dict | None = None
        self._current_message_id: str | None = None
        self._current_stream: str | None = None

    async def initialize(self) -> None:
        """Initialize the processor and register plugins."""
        logger.info("Initializing job processor", extra={
            "mode": self.config.mode,
            "consumer_name": self.consumer_name,
        })

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

        # Ensure consumer groups exist
        await redis_client.ensure_consumer_groups()
        logger.info("Redis consumer groups initialized")

    async def shutdown(self) -> None:
        """Shutdown the processor."""
        await redis_client.close_redis()
        logger.info("Redis connection closed")

    async def get_next_job(self, timeout: float = 5.0) -> dict | None:
        """
        Get the next job from the queue.

        Consumes from both training and generation streams round-robin.
        Uses XREADGROUP for consumer group support.
        """
        # Try training stream first
        jobs = await redis_client.consume_jobs(
            stream=redis_client.STREAM_TRAINING,
            consumer_name=self.consumer_name,
            count=1,
            block_ms=int(timeout * 500),  # Half timeout for each stream
        )
        if jobs:
            message_id, job_data = jobs[0]
            self._current_message_id = message_id
            self._current_stream = redis_client.STREAM_TRAINING
            return job_data

        # Try generation stream
        jobs = await redis_client.consume_jobs(
            stream=redis_client.STREAM_GENERATION,
            consumer_name=self.consumer_name,
            count=1,
            block_ms=int(timeout * 500),
        )
        if jobs:
            message_id, job_data = jobs[0]
            self._current_message_id = message_id
            self._current_stream = redis_client.STREAM_GENERATION
            return job_data

        return None

    async def process_job(self, job: dict) -> None:
        """
        Process a job.

        Routes to appropriate handler based on job type.
        Acknowledges job on completion (success or failure).
        """
        job_type = job.get("type")
        job_id = job.get("id")
        correlation_id = job.get("correlation_id", f"job-{job_id}")
        payload = job.get("payload", {})

        set_correlation_id(correlation_id)
        self._current_job = job

        logger.info("Processing job", extra={
            "event": "job.start",
            "job_id": job_id,
            "job_type": job_type,
            "message_id": self._current_message_id,
        })

        try:
            if job_type == "training":
                await self._process_training_job(job_id, payload, correlation_id)
            elif job_type == "generation":
                await self._process_generation_job(job_id, payload, correlation_id)
            else:
                logger.error(f"Unknown job type: {job_type}")
                await self._mark_job_failed(job_id, f"Unknown job type: {job_type}", correlation_id)

        except Exception as e:
            logger.error(f"Job failed: {e}", extra={
                "event": "job.error",
                "job_id": job_id,
                "error": str(e),
            })
            await self._mark_job_failed(job_id, str(e), correlation_id)

        finally:
            # Acknowledge job completion
            if self._current_stream and self._current_message_id:
                await redis_client.acknowledge_job(self._current_stream, self._current_message_id)
                logger.info("Job acknowledged", extra={
                    "event": "job.acked",
                    "job_id": job_id,
                    "stream": self._current_stream,
                })
            self._current_job = None
            self._current_message_id = None
            self._current_stream = None

    async def _process_training_job(self, job_id: str, payload: dict, correlation_id: str) -> None:
        """Process a training job."""
        character_id = payload.get("character_id")
        config_data = payload.get("config", {})

        config = TrainingConfig(**config_data)
        plugin = get_training_plugin()
        total_steps = config.steps

        logger.info("Starting training", extra={
            "event": "training.start",
            "job_id": job_id,
            "character_id": character_id,
            "plugin": plugin.name,
            "method": config.method.value,
            "steps": total_steps,
        })

        # Mark job as running
        await self._mark_job_running(job_id, correlation_id)

        # Validate config
        valid, error = await plugin.validate_config(config)
        if not valid:
            logger.error(f"Invalid training config: {error}")
            await self._mark_job_failed(job_id, error or "Invalid configuration", correlation_id)
            return

        # Prepare paths
        images_dir = self.config.uploads_dir / character_id
        output_path = self.config.loras_dir / character_id / "v1.safetensors"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get trigger word from character data
        char_data = await redis_client.get_character(character_id)
        trigger_word = char_data.get("trigger_word", "ohwx person") if char_data else "ohwx person"

        # Progress callback with Redis publishing
        async def on_progress(progress):
            percentage = (progress.current_step / total_steps) * 100 if total_steps > 0 else 0
            # Update job record so polling gets latest progress
            await redis_client.update_job_status(
                job_id=job_id,
                status="running",
                progress=percentage,
                current_step=progress.current_step,
                total_steps=total_steps,
            )
            # Also publish to stream for SSE listeners
            await redis_client.publish_progress(
                job_id=job_id,
                status="running",
                progress=percentage,
                message=f"Step {progress.current_step}/{total_steps}",
                correlation_id=correlation_id,
                current_step=progress.current_step,
                total_steps=total_steps,
                loss=progress.loss or 0,
            )
            logger.debug(f"Training progress: {percentage:.1f}%", extra={
                "step": progress.current_step,
                "total": total_steps,
                "loss": progress.loss,
            })

        # Run training
        result = await plugin.train(
            config=config,
            images_dir=images_dir,
            output_path=output_path,
            trigger_word=trigger_word,
            progress_callback=on_progress,
        )

        if result.success:
            logger.info("Training completed", extra={
                "event": "training.complete",
                "job_id": job_id,
                "output_path": str(result.output_path),
                "training_time": result.training_time_seconds,
            })
            await self._mark_job_completed(
                job_id,
                str(result.output_path),
                correlation_id,
                current_step=total_steps,
                total_steps=total_steps,
            )
        else:
            logger.error(f"Training failed: {result.error_message}")
            await self._mark_job_failed(job_id, result.error_message or "Unknown error", correlation_id)

    async def _process_generation_job(self, job_id: str, payload: dict, correlation_id: str) -> None:
        """Process an image generation job."""
        config_data = payload.get("config", {})
        count = payload.get("count", 1)

        config = GenerationConfig(**config_data)
        plugin = get_image_plugin()
        total_steps = 20  # Typical denoising steps

        logger.info("Starting generation", extra={
            "event": "generation.start",
            "job_id": job_id,
            "plugin": plugin.name,
            "size": f"{config.width}x{config.height}",
            "count": count,
        })

        # Mark job as running
        await self._mark_job_running(job_id, correlation_id)

        # Check health
        healthy, error = await plugin.check_health()
        if not healthy:
            await self._mark_job_failed(job_id, error or "Backend unavailable", correlation_id)
            return

        # Prepare paths
        output_dir = self.config.outputs_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        lora_path = None
        if config.lora_id:
            lora_path = self.config.loras_dir / config.lora_id / "v1.safetensors"

        # Progress callback with Redis publishing
        async def on_progress(progress):
            await redis_client.publish_progress(
                job_id=job_id,
                status="running",
                progress=progress.percentage,
                message=f"Step {progress.current_step}/{progress.total_steps}",
                correlation_id=correlation_id,
                current_step=progress.current_step,
                total_steps=progress.total_steps,
            )
            logger.debug(f"Generation progress: {progress.percentage:.1f}%", extra={
                "step": progress.current_step,
                "total": progress.total_steps,
            })

        # Run generation
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
                "event": "generation.complete",
                "job_id": job_id,
                "output_count": len(output_paths),
                "generation_time": result.generation_time_seconds,
            })
            await self._mark_job_completed(job_id, output_paths, correlation_id)
        else:
            logger.error(f"Generation failed: {result.error_message}")
            await self._mark_job_failed(job_id, result.error_message or "Unknown error", correlation_id)

    async def _mark_job_running(self, job_id: str, correlation_id: str) -> None:
        """Mark job as running and publish progress."""
        await redis_client.update_job_status(
            job_id,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        await redis_client.publish_progress(
            job_id=job_id,
            status="running",
            progress=0,
            message="Job started",
            correlation_id=correlation_id,
        )
        logger.info(f"Job {job_id} marked as running")

    async def _mark_job_completed(
        self,
        job_id: str,
        output: Any,
        correlation_id: str,
        **extra,
    ) -> None:
        """Mark job as completed and publish final progress."""
        await redis_client.update_job_status(
            job_id,
            status="completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            output_path=output if isinstance(output, str) else None,
            output_paths=output if isinstance(output, list) else None,
            progress=100,
        )
        await redis_client.publish_progress(
            job_id=job_id,
            status="completed",
            progress=100,
            message="Job completed successfully",
            correlation_id=correlation_id,
            **extra,
        )
        logger.info(f"Job {job_id} marked as completed", extra={"output": output})

    async def _mark_job_failed(self, job_id: str, error: str, correlation_id: str) -> None:
        """Mark job as failed and publish error."""
        await redis_client.update_job_status(
            job_id,
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_message=error,
        )
        await redis_client.publish_progress(
            job_id=job_id,
            status="failed",
            progress=0,
            message=f"Job failed: {error}",
            correlation_id=correlation_id,
            error=error,
        )
        logger.error(f"Job {job_id} marked as failed", extra={"error": error})
