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
    get_gpu_metrics,
    TrainingProgressEvent,
    TrainingStage,
    ProgressBarType,
    ArtifactEvent,
)

from packages.plugins.training import get_training_plugin, register_training_plugin
from packages.plugins.training.src.mock_plugin import MockTrainingPlugin
from packages.plugins.training.src.interface import TrainingProgress

from packages.plugins.image import get_image_plugin, register_image_plugin
from packages.plugins.image.src.mock_plugin import MockImagePlugin
from packages.plugins.image.src.interface import GenerationProgress

from packages.shared.src.types import Character

logger = get_logger("api.services.job_executor")


def _update_character_lora(character_id: str, lora_path: str) -> bool:
    """
    Update character record with trained LoRA path.

    For M1 mode, characters are stored on filesystem.
    This function updates the character JSON file directly.
    """
    try:
        config = get_global_config()
        char_path = config.characters_dir / f"{character_id}.json"

        if not char_path.exists():
            logger.error(f"Character file not found: {char_path}")
            return False

        # Load existing character data
        char_data = json.loads(char_path.read_text())

        # Update LoRA fields
        char_data["lora_path"] = lora_path
        char_data["lora_trained_at"] = datetime.now(timezone.utc).isoformat()
        char_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Save back to filesystem
        char_path.write_text(json.dumps(char_data, indent=2))

        logger.info("Character updated with LoRA path", extra={
            "event": "character.lora_updated",
            "character_id": character_id,
            "lora_path": lora_path,
        })
        return True

    except Exception as e:
        logger.error(f"Failed to update character LoRA: {e}", extra={
            "event": "character.lora_update_failed",
            "character_id": character_id,
            "error": str(e),
        })
        return False

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

        # Helper to emit stage events with optional progress bar
        async def emit_stage(
            stage: TrainingStage,
            message: str,
            progress_pct: float = 0.0,
            progress_bar_id: str | None = None,
            progress_bar_type: ProgressBarType | None = None,
            progress_bar_label: str | None = None,
            progress_bar_value: float | None = None,
            progress_bar_current: int | None = None,
            progress_bar_total: int | None = None,
        ):
            """Emit a stage event with optional progress bar."""
            event = TrainingProgressEvent(
                job_id=job_id,
                correlation_id=correlation_id,
                status="running",
                stage=stage,
                step=job.current_step,
                steps_total=job.config.steps,
                progress_pct=progress_pct,
                message=message,
                gpu=get_gpu_metrics(),
                progress_bar_id=progress_bar_id,
                progress_bar_type=progress_bar_type,
                progress_bar_label=progress_bar_label,
                progress_bar_value=progress_bar_value,
                progress_bar_current=progress_bar_current,
                progress_bar_total=progress_bar_total,
            )
            await event_bus.publish(job_id, event)
            job_logger.info(message, event=f"stage.{stage.value}")

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

        # STAGE: Queued/Started
        await emit_stage(
            TrainingStage.INITIALIZING,
            "Job started - initializing training pipeline...",
            progress_pct=0.0,
            progress_bar_id="init",
            progress_bar_type=ProgressBarType.STAGE,
            progress_bar_label="Initializing",
            progress_bar_value=10.0,
        )

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

        await emit_stage(
            TrainingStage.INITIALIZING,
            f"Selected training backend: {plugin.name}",
            progress_pct=0.0,
            progress_bar_id="init",
            progress_bar_type=ProgressBarType.STAGE,
            progress_bar_label="Initializing",
            progress_bar_value=30.0,
        )

        # Validate config
        job_logger.info("Validating configuration", event="config.validate")
        await emit_stage(
            TrainingStage.INITIALIZING,
            "Validating training configuration...",
            progress_pct=0.0,
            progress_bar_id="init",
            progress_bar_type=ProgressBarType.STAGE,
            progress_bar_label="Validating config",
            progress_bar_value=50.0,
        )

        valid, error = await plugin.validate_config(job.config)
        if not valid:
            raise ValueError(error or "Invalid configuration")

        await emit_stage(
            TrainingStage.INITIALIZING,
            "Configuration validated successfully",
            progress_pct=0.0,
            progress_bar_id="init",
            progress_bar_type=ProgressBarType.STAGE,
            progress_bar_label="Config validated",
            progress_bar_value=70.0,
        )

        # Prepare paths - use loras_dir with versioning
        images_dir = app_config.uploads_dir / job.character_id
        lora_dir = app_config.loras_dir / job.character_id
        lora_dir.mkdir(parents=True, exist_ok=True)

        # STAGE: Preparing dataset
        await emit_stage(
            TrainingStage.PREPARING_DATASET,
            "Preparing training dataset...",
            progress_pct=0.0,
            progress_bar_id="dataset",
            progress_bar_type=ProgressBarType.STAGE,
            progress_bar_label="Preparing dataset",
            progress_bar_value=0.0,
        )

        # Count training images
        image_count = len(list(images_dir.glob("*.*"))) if images_dir.exists() else 0
        job_logger.info(f"Found {image_count} training images", event="dataset.ready", image_count=image_count)

        await emit_stage(
            TrainingStage.PREPARING_DATASET,
            f"Found {image_count} training images",
            progress_pct=0.0,
            progress_bar_id="dataset",
            progress_bar_type=ProgressBarType.STAGE,
            progress_bar_label="Dataset ready",
            progress_bar_value=100.0,
            progress_bar_current=image_count,
            progress_bar_total=image_count,
        )

        # Determine version number
        existing_versions = list(lora_dir.glob("v*.safetensors"))
        version = len(existing_versions) + 1
        output_path = lora_dir / f"v{version}.safetensors"

        job_logger.info(f"Output path: {output_path}", event="paths.prepared", version=version)

        await emit_stage(
            TrainingStage.INITIALIZING,
            f"Output will be saved as v{version}.safetensors",
            progress_pct=0.0,
            progress_bar_id="init",
            progress_bar_type=ProgressBarType.STAGE,
            progress_bar_label="Ready to train",
            progress_bar_value=100.0,
        )

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

            # Format the message with all details
            speed_str = f"{iteration_speed:.2f} it/s" if iteration_speed else "--"
            eta_str = f"{progress.eta_seconds // 60}m {progress.eta_seconds % 60}s" if progress.eta_seconds else "--"
            loss_str = f"{progress.loss:.4f}" if progress.loss else "--"
            msg = f"Step {progress.current_step}/{progress.total_steps} | Loss: {loss_str} | Speed: {speed_str} | ETA: {eta_str}"

            # Emit progress event with training progress bar
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
                iteration_speed=iteration_speed,
                gpu=get_gpu_metrics(),
                message=msg,
                sample_path=sample_path,
                progress_bar_id="training",
                progress_bar_type=ProgressBarType.TRAINING,
                progress_bar_label=f"Training - Step {progress.current_step}/{progress.total_steps}",
                progress_bar_value=progress.percentage,
                progress_bar_current=progress.current_step,
                progress_bar_total=progress.total_steps,
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

        # STAGE: Loading model (this happens inside plugin.train but we emit before)
        await emit_stage(
            TrainingStage.LOADING_MODEL,
            "Loading FLUX model and preparing for training...",
            progress_pct=0.0,
            progress_bar_id="model",
            progress_bar_type=ProgressBarType.STAGE,
            progress_bar_label="Loading model",
            progress_bar_value=0.0,
        )

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
            # STAGE: Exporting
            await emit_stage(
                TrainingStage.EXPORTING,
                "Exporting trained LoRA model...",
                progress_pct=99.0,
                progress_bar_id="export",
                progress_bar_type=ProgressBarType.STAGE,
                progress_bar_label="Exporting model",
                progress_bar_value=50.0,
            )
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

            # Update character record with LoRA path
            _update_character_lora(job.character_id, str(output_path))

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
