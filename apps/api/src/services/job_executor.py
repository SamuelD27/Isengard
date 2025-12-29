"""
Job Executor Service

Executes training and generation jobs in-process using background tasks.
For M1, this runs synchronously in the API process. M2 will move to Redis-based workers.

Includes comprehensive observability:
- Structured job logging via TrainingJobLogger
- Event bus integration for real-time SSE streaming
- Sample image tracking
- Error capture with full stack traces
"""

import asyncio
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import (
    get_logger,
    set_correlation_id,
    get_correlation_id,
    TrainingJobLogger,
)
from packages.shared.src.types import (
    JobStatus,
    JobType,
    TrainingJob,
    GenerationJob,
    TrainingConfig,
    GenerationConfig,
    JobProgressEvent,
)
from packages.shared.src.events import (
    get_event_bus,
    TrainingProgressEvent,
    TrainingStage,
    ArtifactEvent,
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

    Observability:
        - Creates per-job JSONL log file
        - Emits progress events to EventBus for SSE streaming
        - Tracks sample images generated during training
        - Captures full stack traces on errors
    """
    _ensure_plugins_initialized()

    if correlation_id:
        set_correlation_id(correlation_id)

    job_id = job.id
    app_config = get_global_config()
    event_bus = get_event_bus()

    # Create job-specific logger
    job_logger = TrainingJobLogger(job_id, correlation_id=correlation_id, service="api")

    logger.info("Starting training job execution", extra={
        "event": "job.start",
        "job_id": job_id,
        "character_id": job.character_id,
        "steps": job.config.steps,
        "correlation_id": correlation_id,
    })

    start_time = datetime.now(timezone.utc)

    try:
        # Mark as running
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.total_steps = job.config.steps
        jobs_store[job_id] = job

        # Log and emit start event
        job_logger.start(
            total_steps=job.config.steps,
            config_summary={
                "method": str(job.config.method),
                "steps": job.config.steps,
                "learning_rate": job.config.learning_rate,
                "batch_size": job.config.batch_size,
                "resolution": job.config.resolution,
                "lora_rank": job.config.lora_rank,
            }
        )

        start_event = TrainingProgressEvent(
            job_id=job_id,
            correlation_id=correlation_id,
            status="running",
            stage=TrainingStage.INITIALIZING,
            step=0,
            steps_total=job.config.steps,
            progress_pct=0.0,
            message="Training started",
        )
        await event_bus.publish(job_id, start_event)

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
        job_logger.info(f"Using training plugin: {plugin.name}", event="plugin.selected")

        # Validate config
        job_logger.info("Validating configuration", event="config.validate")
        valid, error = await plugin.validate_config(job.config)
        if not valid:
            raise ValueError(error or "Invalid configuration")

        # Prepare paths - use loras_dir with versioning
        images_dir = app_config.uploads_dir / job.character_id
        lora_dir = app_config.loras_dir / job.character_id
        lora_dir.mkdir(parents=True, exist_ok=True)

        # Count training images
        image_count = len(list(images_dir.glob("*.*"))) if images_dir.exists() else 0
        job_logger.info(f"Found {image_count} training images", event="dataset.ready", image_count=image_count)

        # Determine version number
        existing_versions = list(lora_dir.glob("v*.safetensors"))
        version = len(existing_versions) + 1
        output_path = lora_dir / f"v{version}.safetensors"

        job_logger.info(f"Output path: {output_path}", event="paths.prepared", version=version)

        # Progress callback with event bus integration
        last_sample_path = None
        last_step_time = start_time
        last_step = 0

        async def emit_progress(progress: TrainingProgress) -> None:
            nonlocal last_sample_path, last_step_time, last_step

            # Calculate elapsed time
            now = datetime.now(timezone.utc)
            elapsed_seconds = int((now - start_time).total_seconds())

            # Calculate iteration speed (steps per second)
            iteration_speed = None
            if progress.current_step > last_step:
                step_delta = progress.current_step - last_step
                time_delta = (now - last_step_time).total_seconds()
                if time_delta > 0:
                    iteration_speed = step_delta / time_delta
                last_step = progress.current_step
                last_step_time = now

            job.current_step = progress.current_step
            job.progress = progress.percentage
            job.elapsed_seconds = elapsed_seconds
            job.current_loss = progress.loss
            job.eta_seconds = progress.eta_seconds
            if iteration_speed is not None:
                job.iteration_speed = round(iteration_speed, 2)
            jobs_store[job_id] = job

            # Log step to job log
            job_logger.step(
                current_step=progress.current_step,
                loss=progress.loss,
                lr=progress.learning_rate,
                message=progress.message,
            )

            # Check for sample image
            sample_path = progress.sample_path or progress.preview_path
            if sample_path and sample_path != last_sample_path:
                last_sample_path = sample_path
                job_logger.sample_generated(sample_path, progress.current_step)

                # Emit artifact event
                artifact_event = ArtifactEvent(
                    job_id=job_id,
                    artifact_type="sample",
                    path=sample_path,
                    step=progress.current_step,
                )
                await event_bus.publish(job_id, artifact_event)

            # Emit progress event
            progress_event = TrainingProgressEvent(
                job_id=job_id,
                correlation_id=correlation_id,
                status="running",
                stage=TrainingStage.TRAINING,
                step=progress.current_step,
                steps_total=progress.total_steps,
                progress_pct=progress.percentage,
                loss=progress.loss,
                lr=progress.learning_rate,
                eta_seconds=progress.eta_seconds,
                message=progress.message or f"Step {progress.current_step}/{progress.total_steps}",
                sample_path=sample_path,
            )
            await event_bus.publish(job_id, progress_event)

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.TRAINING,
                status=JobStatus.RUNNING,
                progress=progress.percentage,
                message=progress.message or f"Step {progress.current_step}/{progress.total_steps}",
                current_step=progress.current_step,
                total_steps=progress.total_steps,
                preview_url=f"/api/jobs/{job_id}/artifacts/samples/{Path(sample_path).name}" if sample_path else None,
            ))

        def on_progress(progress: TrainingProgress) -> None:
            """Sync wrapper for async progress callback."""
            asyncio.create_task(emit_progress(progress))

        # Run training with job_id for sample generation
        job_logger.info("Starting training execution", event="training.execute")

        result = await plugin.train(
            config=job.config,
            images_dir=images_dir,
            output_path=output_path,
            trigger_word=character_trigger_word,
            progress_callback=on_progress,
            job_id=job_id,  # Pass job_id for sample image organization
        )

        training_time = (datetime.now(timezone.utc) - start_time).total_seconds()

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
                "training_time_seconds": training_time,
                "samples_generated": len(result.samples) if result.samples else 0,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            config_path.write_text(json.dumps(config_data, indent=2))

            # Mark completed
            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.current_step = job.total_steps
            job.completed_at = datetime.now(timezone.utc)
            job.output_path = str(output_path)
            jobs_store[job_id] = job

            # Log completion
            job_logger.complete(
                output_path=output_path,
                training_time_seconds=training_time,
                final_loss=result.final_loss,
            )

            # Emit completion event
            complete_event = TrainingProgressEvent(
                job_id=job_id,
                correlation_id=correlation_id,
                status="completed",
                stage=TrainingStage.COMPLETED,
                step=job.total_steps,
                steps_total=job.total_steps,
                progress_pct=100.0,
                loss=result.final_loss,
                message="Training completed successfully",
            )
            await event_bus.publish(job_id, complete_event)

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
                "event": "job.complete",
                "job_id": job_id,
                "output_path": str(output_path),
                "training_time": training_time,
                "samples_generated": len(result.samples) if result.samples else 0,
            })

        else:
            raise Exception(result.error_message or "Training failed")

    except Exception as e:
        error_message = str(e)
        error_type = type(e).__name__
        stack_trace = traceback.format_exc()

        # Log error with full context
        job_logger.fail(
            error=error_message,
            error_type=error_type,
            stack_trace=stack_trace,
        )

        logger.error(f"Training job failed: {e}", extra={
            "event": "job.failed",
            "job_id": job_id,
            "error": error_message,
            "error_type": error_type,
        }, exc_info=True)

        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(timezone.utc)
        jobs_store[job_id] = job

        # Emit failure event
        fail_event = TrainingProgressEvent(
            job_id=job_id,
            correlation_id=correlation_id,
            status="failed",
            stage=TrainingStage.FAILED,
            step=job.current_step,
            steps_total=job.total_steps,
            progress_pct=job.progress,
            message=f"Training failed: {error_message}",
            error=error_message,
            error_type=error_type,
            error_stack=stack_trace,
        )
        await event_bus.publish(job_id, fail_event)

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.TRAINING,
            status=JobStatus.FAILED,
            progress=job.progress,
            message=f"Training failed: {error_message}",
            error=error_message,
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
