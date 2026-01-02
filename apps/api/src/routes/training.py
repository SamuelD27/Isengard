"""
Training Endpoints

Manage LoRA training jobs.
Jobs run in-process via FastAPI BackgroundTasks.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger, get_correlation_id
from ..middleware import get_interaction_id
from packages.shared.src.types import (
    TrainingJob,
    StartTrainingRequest,
    JobStatus,
    JobType,
    JobProgressEvent,
)
from ..services.config_validator import validate_training_config
from ..services.job_executor import get_training_capabilities
from packages.shared.src.rate_limit import rate_limit, RATE_LIMIT_TRAINING

from ..services.job_executor import (
    execute_training_job,
    get_job_progress_events,
)

router = APIRouter()
logger = get_logger("api.routes.training")

# In-memory job storage
_training_jobs: dict[str, TrainingJob] = {}

# In-memory character storage reference (imported from characters route)
from .characters import _characters, _load_all_characters, _save_character, _load_character


async def _get_job_or_404(job_id: str) -> TrainingJob:
    """Get job by ID or raise 404."""
    if job_id not in _training_jobs:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
    return _training_jobs[job_id]


async def _save_job(job: TrainingJob) -> None:
    """Save job to in-memory storage."""
    _training_jobs[job.id] = job


async def _list_jobs(character_id: str | None = None) -> list[TrainingJob]:
    """List jobs from in-memory storage."""
    jobs = list(_training_jobs.values())
    if character_id:
        jobs = [j for j in jobs if j.character_id == character_id]
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs


@router.get("/successful", response_model=list[TrainingJob])
async def list_successful_training_jobs(character_id: str = None):
    """
    List only successful (completed) training jobs.

    Convenience endpoint for the training history view.

    NOTE: Must be defined BEFORE /{job_id} to avoid route collision.
    """
    jobs = await _list_jobs(character_id)

    # Filter for completed jobs - handle both enum and string values
    completed_jobs = []
    for job in jobs:
        status_value = job.status.value if hasattr(job.status, 'value') else str(job.status)
        if status_value == "completed":
            completed_jobs.append(job)

    # Sort by completed_at descending (most recent first)
    completed_jobs.sort(key=lambda j: j.completed_at or "", reverse=True)

    logger.debug(f"Found {len(completed_jobs)} completed jobs out of {len(jobs)} total", extra={
        "event": "jobs.list_successful",
        "total_jobs": len(jobs),
        "completed_jobs": len(completed_jobs),
    })

    return completed_jobs


@router.get("/ongoing", response_model=list[TrainingJob])
async def list_ongoing_training_jobs():
    """
    List only ongoing (running or queued) training jobs.

    Convenience endpoint for the ongoing training view.

    NOTE: Must be defined BEFORE /{job_id} to avoid route collision.
    """
    jobs = await _list_jobs()
    ongoing = [j for j in jobs if j.status in [JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.PENDING]]
    # Sort by created_at descending (most recent first)
    ongoing.sort(key=lambda j: j.created_at, reverse=True)
    return ongoing


@router.post("", response_model=TrainingJob, status_code=201)
@rate_limit(**RATE_LIMIT_TRAINING)
async def start_training(
    http_request: Request,
    request: StartTrainingRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a new training job.

    Creates a job and executes it in the background via BackgroundTasks.
    Rate limited to 5 requests per minute.
    """
    # Ensure characters are loaded
    _load_all_characters()

    # Validate config against capabilities
    capabilities = get_training_capabilities()
    validate_training_config(request.config.model_dump(mode="json"), capabilities)

    # Validate character exists (with fallback to disk if not in cache)
    character = None
    if request.character_id in _characters:
        character = _characters[request.character_id]
    else:
        # Fallback: Try loading directly from disk (handles race condition
        # when character was just created and cache is stale)
        character = _load_character(request.character_id)
        if character:
            _characters[request.character_id] = character
            logger.debug("Character loaded from disk (cache miss)", extra={
                "character_id": request.character_id,
            })

    if character is None:
        raise HTTPException(
            status_code=404,
            detail=f"Character {request.character_id} not found"
        )

    # Check for training images
    config = get_global_config()
    images_dir = config.uploads_dir / request.character_id
    if not images_dir.exists() or not list(images_dir.glob("*")):
        raise HTTPException(
            status_code=400,
            detail="No training images uploaded for this character"
        )

    # Create job with server-generated UUID7-style ID
    job_id = f"train-{uuid.uuid4().hex[:12]}"
    correlation_id = get_correlation_id()
    interaction_id = get_interaction_id()

    job = TrainingJob(
        id=job_id,
        character_id=request.character_id,
        status=JobStatus.QUEUED,
        config=request.config,
        total_steps=request.config.steps,
        created_at=datetime.now(timezone.utc),
        base_model=request.base_model,
        preset_name=request.preset_name,
    )

    # Save job to in-memory storage
    await _save_job(job)

    # Log job creation
    log_extra = {
        "event": "job.created",
        "job_id": job_id,
        "character_id": request.character_id,
        "method": request.config.method.value,
        "steps": request.config.steps,
    }
    if interaction_id:
        log_extra["interaction_id"] = interaction_id
    logger.info("Training job created", extra=log_extra)

    # Execute in-process via BackgroundTasks
    background_tasks.add_task(
        execute_training_job,
        job=job,
        jobs_store=_training_jobs,
        character_trigger_word=character.trigger_word,
        correlation_id=correlation_id,
    )

    return job


@router.get("/{job_id}", response_model=TrainingJob)
async def get_training_job(job_id: str):
    """
    Get training job status.
    """
    return await _get_job_or_404(job_id)


@router.get("/{job_id}/stream")
async def stream_training_progress(job_id: str):
    """
    Stream training progress via Server-Sent Events.

    Connect to this endpoint to receive real-time progress updates.
    All events include job_id and correlation_id.
    """
    job = await _get_job_or_404(job_id)

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for job progress."""

        # Send initial state
        initial_event = JobProgressEvent(
            job_id=job_id,
            job_type=JobType.TRAINING,
            status=job.status,
            progress=job.progress,
            message="Connected to progress stream",
            current_step=job.current_step,
            total_steps=job.total_steps,
        )
        yield {"event": "progress", "data": initial_event.model_dump_json()}

        # Poll in-memory store for updates
        last_event_count = 0
        while True:
            await asyncio.sleep(0.5)

            if job_id not in _training_jobs:
                break

            current_job = _training_jobs[job_id]

            # Check for new progress events from executor
            progress_events = get_job_progress_events(job_id)
            if len(progress_events) > last_event_count:
                for event in progress_events[last_event_count:]:
                    yield {"event": "progress", "data": event.model_dump_json()}
                last_event_count = len(progress_events)

            # Stop streaming when job completes
            if current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                final_event = JobProgressEvent(
                    job_id=job_id,
                    job_type=JobType.TRAINING,
                    status=current_job.status,
                    progress=current_job.progress,
                    message="Job finished" if current_job.status == JobStatus.COMPLETED else f"Job {current_job.status.value}",
                    current_step=current_job.current_step,
                    total_steps=current_job.total_steps,
                    error=current_job.error_message,
                )
                yield {"event": "complete", "data": final_event.model_dump_json()}
                break

    return EventSourceResponse(event_generator())


@router.post("/{job_id}/cancel", response_model=TrainingJob)
async def cancel_training(job_id: str):
    """
    Cancel a training job.
    """
    job = await _get_job_or_404(job_id)

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in {job.status} state"
        )

    job.status = JobStatus.CANCELLED
    await _save_job(job)

    logger.info("Training job cancelled", extra={
        "event": "job.cancelled",
        "job_id": job_id,
    })

    return job


@router.get("", response_model=list[TrainingJob])
async def list_training_jobs(
    character_id: str = None,
    status: str = None,
):
    """
    List training jobs, optionally filtered by character and/or status.

    Args:
        character_id: Filter by character ID
        status: Comma-separated list of statuses to filter by
                (e.g., "running,queued" or "completed" or "failed")
    """
    jobs = await _list_jobs(character_id)

    # Filter by status if provided
    if status:
        status_list = [s.strip().lower() for s in status.split(",")]
        jobs = [j for j in jobs if j.status.value.lower() in status_list]

    return jobs
