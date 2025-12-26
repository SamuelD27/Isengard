"""
Training Endpoints

Manage LoRA training jobs.
"""

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger, get_correlation_id
from packages.shared.src.types import (
    TrainingJob,
    StartTrainingRequest,
    JobStatus,
    JobType,
    JobProgressEvent,
)
from packages.shared.src.capabilities import is_capability_supported

from ..services.job_executor import (
    execute_training_job,
    get_latest_progress,
    get_job_progress_events,
)

router = APIRouter()
logger = get_logger("api.routes.training")

# In-memory job storage (will be replaced with Redis in M2)
_training_jobs: dict[str, TrainingJob] = {}

# In-memory character storage reference (imported from characters route)
from .characters import _characters, _load_all_characters, _save_character


def _get_job_or_404(job_id: str) -> TrainingJob:
    """Get job by ID or raise 404."""
    if job_id not in _training_jobs:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
    return _training_jobs[job_id]


@router.post("", response_model=TrainingJob, status_code=201)
async def start_training(
    request: StartTrainingRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a new training job.

    Creates a job and executes it in the background (M1: in-process, M2: Redis queue).
    """
    # Ensure characters are loaded
    _load_all_characters()

    # Validate capability
    if not is_capability_supported("training", request.config.method.value):
        raise HTTPException(
            status_code=400,
            detail=f"Training method '{request.config.method.value}' is not supported"
        )

    # Validate character exists
    if request.character_id not in _characters:
        raise HTTPException(
            status_code=404,
            detail=f"Character {request.character_id} not found"
        )

    character = _characters[request.character_id]

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

    job = TrainingJob(
        id=job_id,
        character_id=request.character_id,
        status=JobStatus.QUEUED,
        config=request.config,
        total_steps=request.config.steps,
        created_at=datetime.utcnow(),
    )

    _training_jobs[job_id] = job

    logger.info("Training job created", extra={
        "job_id": job_id,
        "character_id": request.character_id,
        "method": request.config.method.value,
        "steps": request.config.steps,
    })

    # Execute job in background (M1: in-process, M2: would queue to Redis)
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
    return _get_job_or_404(job_id)


@router.get("/{job_id}/stream")
async def stream_training_progress(job_id: str):
    """
    Stream training progress via Server-Sent Events.

    Connect to this endpoint to receive real-time progress updates.
    All events include job_id and correlation_id.
    """
    job = _get_job_or_404(job_id)
    correlation_id = get_correlation_id()

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for job progress."""
        last_event_count = 0

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
        # Include correlation_id in the event data
        event_data = initial_event.model_dump()
        event_data["correlation_id"] = correlation_id
        yield {"event": "progress", "data": initial_event.model_dump_json()}

        # Poll for updates (M1: in-process, M2: would use Redis Streams)
        while True:
            await asyncio.sleep(0.5)  # Poll every 500ms for responsive updates

            if job_id not in _training_jobs:
                break

            current_job = _training_jobs[job_id]

            # Check for new progress events from executor
            progress_events = get_job_progress_events(job_id)
            if len(progress_events) > last_event_count:
                # Send new events
                for event in progress_events[last_event_count:]:
                    event_data = event.model_dump()
                    event_data["correlation_id"] = correlation_id
                    yield {"event": "progress", "data": event.model_dump_json()}
                last_event_count = len(progress_events)

            # Stop streaming when job completes or fails
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
    job = _get_job_or_404(job_id)

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in {job.status} state"
        )

    job.status = JobStatus.CANCELLED
    _training_jobs[job_id] = job

    # TODO: Send cancel signal to worker via Redis

    logger.info("Training job cancelled", extra={"job_id": job_id})

    return job


@router.get("", response_model=list[TrainingJob])
async def list_training_jobs(character_id: str = None):
    """
    List training jobs, optionally filtered by character.
    """
    jobs = list(_training_jobs.values())

    if character_id:
        jobs = [j for j in jobs if j.character_id == character_id]

    # Sort by created_at descending
    jobs.sort(key=lambda j: j.created_at, reverse=True)

    return jobs
