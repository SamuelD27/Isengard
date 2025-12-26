"""
Job Executor Service

Executes training and generation jobs in-process using background tasks.
For M1, this runs synchronously in the API process. M2 will move to Redis-based workers.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger, set_correlation_id, get_correlation_id
from packages.shared.src.types import (
    JobStatus,
    JobType,
    TrainingJob,
    GenerationJob,
    TrainingConfig,
    GenerationConfig,
    JobProgressEvent,
)

from packages.plugins.training import get_training_plugin, register_training_plugin
from packages.plugins.training.src.mock_plugin import MockTrainingPlugin
from packages.plugins.training.src.interface import TrainingProgress

from packages.plugins.image import get_image_plugin, register_image_plugin
from packages.plugins.image.src.mock_plugin import MockImagePlugin
from packages.plugins.image.src.interface import GenerationProgress

logger = get_logger("api.services.job_executor")

# Track registered plugins
_plugins_initialized = False


def _ensure_plugins_initialized() -> None:
    """Initialize plugins based on operating mode."""
    global _plugins_initialized
    if _plugins_initialized:
        return

    config = get_global_config()

    if config.is_fast_test:
        register_training_plugin(MockTrainingPlugin(), default=True)
        register_image_plugin(MockImagePlugin(), default=True)
        logger.info("Registered mock plugins for fast-test mode")
    else:
        # Production plugins would be registered here
        # For M1, we only support fast-test mode
        register_training_plugin(MockTrainingPlugin(), default=True)
        register_image_plugin(MockImagePlugin(), default=True)
        logger.warning("Production plugins not yet available, using mock")

    _plugins_initialized = True


# Progress tracking for SSE
_job_progress: dict[str, list[JobProgressEvent]] = {}


def get_job_progress_events(job_id: str) -> list[JobProgressEvent]:
    """Get all progress events for a job."""
    return _job_progress.get(job_id, [])


def get_latest_progress(job_id: str) -> JobProgressEvent | None:
    """Get the latest progress event for a job."""
    events = _job_progress.get(job_id, [])
    return events[-1] if events else None


def _record_progress(job_id: str, event: JobProgressEvent) -> None:
    """Record a progress event for a job."""
    if job_id not in _job_progress:
        _job_progress[job_id] = []
    _job_progress[job_id].append(event)


def clear_job_progress(job_id: str) -> None:
    """Clear progress events for a job (after completion)."""
    if job_id in _job_progress:
        del _job_progress[job_id]


async def execute_training_job(
    job: TrainingJob,
    jobs_store: dict[str, TrainingJob],
    character_trigger_word: str,
    correlation_id: str | None = None,
) -> None:
    """
    Execute a training job using the appropriate plugin.

    Args:
        job: The training job to execute
        jobs_store: Reference to the jobs dictionary (for updating status)
        character_trigger_word: Trigger word for the LoRA
        correlation_id: Correlation ID for logging
    """
    _ensure_plugins_initialized()

    if correlation_id:
        set_correlation_id(correlation_id)

    job_id = job.id
    config = get_global_config()

    logger.info("Starting training job execution", extra={
        "job_id": job_id,
        "character_id": job.character_id,
        "steps": job.config.steps,
    })

    try:
        # Mark as running
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        jobs_store[job_id] = job

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.TRAINING,
            status=JobStatus.RUNNING,
            progress=0.0,
            message="Training started",
            current_step=0,
            total_steps=job.config.steps,
        ))

        # Get plugin
        plugin = get_training_plugin()

        # Validate config
        valid, error = await plugin.validate_config(job.config)
        if not valid:
            raise ValueError(error or "Invalid configuration")

        # Prepare paths - use loras_dir with versioning
        images_dir = config.uploads_dir / job.character_id
        lora_dir = config.loras_dir / job.character_id
        lora_dir.mkdir(parents=True, exist_ok=True)

        # Determine version number
        existing_versions = list(lora_dir.glob("v*.safetensors"))
        version = len(existing_versions) + 1
        output_path = lora_dir / f"v{version}.safetensors"

        # Progress callback
        def on_progress(progress: TrainingProgress) -> None:
            job.current_step = progress.current_step
            job.progress = progress.percentage
            jobs_store[job_id] = job

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.TRAINING,
                status=JobStatus.RUNNING,
                progress=progress.percentage,
                message=progress.message or f"Step {progress.current_step}/{progress.total_steps}",
                current_step=progress.current_step,
                total_steps=progress.total_steps,
            ))

        # Run training
        result = await plugin.train(
            config=job.config,
            images_dir=images_dir,
            output_path=output_path,
            trigger_word=character_trigger_word,
            progress_callback=on_progress,
        )

        if result.success:
            # Save training config alongside model
            config_path = lora_dir / "training_config.json"
            config_data = {
                "job_id": job_id,
                "character_id": job.character_id,
                "trigger_word": character_trigger_word,
                "config": job.config.model_dump(),
                "output_path": str(output_path),
                "final_loss": result.final_loss,
                "total_steps": result.total_steps,
                "training_time_seconds": result.training_time_seconds,
                "completed_at": datetime.utcnow().isoformat(),
            }
            config_path.write_text(json.dumps(config_data, indent=2))

            # Mark completed
            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.current_step = job.total_steps
            job.completed_at = datetime.utcnow()
            job.output_path = str(output_path)
            jobs_store[job_id] = job

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.TRAINING,
                status=JobStatus.COMPLETED,
                progress=100.0,
                message="Training completed successfully",
                current_step=job.total_steps,
                total_steps=job.total_steps,
            ))

            logger.info("Training job completed", extra={
                "job_id": job_id,
                "output_path": str(output_path),
                "training_time": result.training_time_seconds,
            })

        else:
            raise Exception(result.error_message or "Training failed")

    except Exception as e:
        logger.error(f"Training job failed: {e}", extra={
            "job_id": job_id,
            "error": str(e),
        })

        job.status = JobStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        jobs_store[job_id] = job

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.TRAINING,
            status=JobStatus.FAILED,
            progress=job.progress,
            message=f"Training failed: {e}",
            error=str(e),
        ))


async def execute_generation_job(
    job: GenerationJob,
    jobs_store: dict[str, GenerationJob],
    count: int = 1,
    correlation_id: str | None = None,
) -> None:
    """
    Execute an image generation job using the appropriate plugin.

    Args:
        job: The generation job to execute
        jobs_store: Reference to the jobs dictionary
        count: Number of images to generate
        correlation_id: Correlation ID for logging
    """
    _ensure_plugins_initialized()

    if correlation_id:
        set_correlation_id(correlation_id)

    job_id = job.id
    config = get_global_config()

    logger.info("Starting generation job execution", extra={
        "job_id": job_id,
        "prompt": job.config.prompt[:50] + "..." if len(job.config.prompt) > 50 else job.config.prompt,
        "count": count,
    })

    try:
        # Mark as running
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        jobs_store[job_id] = job

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.IMAGE_GENERATION,
            status=JobStatus.RUNNING,
            progress=0.0,
            message="Generation started",
        ))

        # Get plugin
        plugin = get_image_plugin()

        # Check health
        healthy, error = await plugin.check_health()
        if not healthy:
            raise Exception(error or "Image generation backend unavailable")

        # Prepare paths
        output_dir = config.outputs_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        lora_path = None
        if job.config.lora_id:
            lora_dir = config.loras_dir / job.config.lora_id
            # Find latest version
            versions = sorted(lora_dir.glob("v*.safetensors"))
            if versions:
                lora_path = versions[-1]

        # Progress callback
        def on_progress(progress: GenerationProgress) -> None:
            job.progress = progress.percentage
            jobs_store[job_id] = job

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.IMAGE_GENERATION,
                status=JobStatus.RUNNING,
                progress=progress.percentage,
                message=progress.message or f"Generating...",
            ))

        # Run generation
        result = await plugin.generate(
            config=job.config,
            output_dir=output_dir,
            lora_path=lora_path,
            count=count,
            progress_callback=on_progress,
        )

        if result.success:
            # Mark completed
            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.completed_at = datetime.utcnow()
            job.output_paths = [str(p) for p in result.output_paths]
            jobs_store[job_id] = job

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.IMAGE_GENERATION,
                status=JobStatus.COMPLETED,
                progress=100.0,
                message=f"Generated {len(result.output_paths)} image(s)",
            ))

            logger.info("Generation job completed", extra={
                "job_id": job_id,
                "output_count": len(result.output_paths),
                "generation_time": result.generation_time_seconds,
            })

        else:
            raise Exception(result.error_message or "Generation failed")

    except Exception as e:
        logger.error(f"Generation job failed: {e}", extra={
            "job_id": job_id,
            "error": str(e),
        })

        job.status = JobStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        jobs_store[job_id] = job

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.IMAGE_GENERATION,
            status=JobStatus.FAILED,
            progress=job.progress,
            message=f"Generation failed: {e}",
            error=str(e),
        ))
