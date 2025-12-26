"""
Training Endpoints

Manage LoRA training jobs.

M2: Uses Redis for job storage and queue.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone

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
from packages.shared.src import redis_client

from ..services.job_executor import (
    execute_training_job,
    get_latest_progress,
    get_job_progress_events,
)

router = APIRouter()
logger = get_logger("api.routes.training")

# Feature flag for Redis mode
USE_REDIS = os.getenv("USE_REDIS", "false").lower() == "true"

# In-memory fallback for M1 compatibility
_training_jobs: dict[str, TrainingJob] = {}

# In-memory character storage reference (imported from characters route)
from .characters import _characters, _load_all_characters, _save_character


async def _get_job_or_404(job_id: str) -> TrainingJob:
    """Get job by ID or raise 404."""
    if USE_REDIS:
        job_data = await redis_client.get_job(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
        return TrainingJob(**job_data)
    else:
        if job_id not in _training_jobs:
            raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
        return _training_jobs[job_id]


async def _save_job(job: TrainingJob) -> None:
    """Save job to storage."""
    if USE_REDIS:
        await redis_client.save_job(job.id, job.model_dump(mode="json"))
    else:
        _training_jobs[job.id] = job


async def _list_jobs(character_id: str | None = None) -> list[TrainingJob]:
    """List jobs from storage."""
    if USE_REDIS:
        jobs_data = await redis_client.list_jobs(job_type="training")
        jobs = [TrainingJob(**j) for j in jobs_data]
        if character_id:
            jobs = [j for j in jobs if j.character_id == character_id]
        return jobs
    else:
        jobs = list(_training_jobs.values())
        if character_id:
            jobs = [j for j in jobs if j.character_id == character_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs


@router.post("", response_model=TrainingJob, status_code=201)
async def start_training(
    request: StartTrainingRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a new training job.

    Creates a job and executes it in the background.
    M1: In-process execution
    M2: Queue to Redis for worker consumption
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
        created_at=datetime.now(timezone.utc),
    )

    # Save job
    await _save_job(job)

    logger.info("Training job created", extra={
        "event": "job.created",
        "job_id": job_id,
        "character_id": request.character_id,
        "method": request.config.method.value,
        "steps": request.config.steps,
        "use_redis": USE_REDIS,
    })

    if USE_REDIS:
        # Queue to Redis for worker consumption
        await redis_client.submit_job(
            stream=redis_client.STREAM_TRAINING,
            job_id=job_id,
            job_type="training",
            payload=request.model_dump(mode="json"),
            correlation_id=correlation_id,
        )
        logger.info("Training job queued to Redis", extra={
            "event": "job.queued",
            "job_id": job_id,
        })
    else:
        # M1 fallback: Execute in-process
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
    correlation_id = get_correlation_id()

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

        if USE_REDIS:
            # Stream from Redis
            async for progress in redis_client.stream_progress(job_id):
                event = JobProgressEvent(
                    job_id=job_id,
                    job_type=JobType.TRAINING,
                    status=JobStatus(progress.get("status", "running")),
                    progress=progress.get("progress", 0),
                    message=progress.get("message", ""),
                    current_step=progress.get("current_step", 0),
                    total_steps=progress.get("total_steps", 0),
                )
                event_name = "complete" if event.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED] else "progress"
                yield {"event": event_name, "data": event.model_dump_json()}
        else:
            # M1 fallback: Poll in-memory store
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

    if USE_REDIS:
        # Publish cancellation event
        await redis_client.publish_progress(
            job_id=job_id,
            status="cancelled",
            progress=job.progress,
            message="Job cancelled by user",
            correlation_id=get_correlation_id(),
        )

    logger.info("Training job cancelled", extra={
        "event": "job.cancelled",
        "job_id": job_id,
    })

    return job


@router.get("", response_model=list[TrainingJob])
async def list_training_jobs(character_id: str = None):
    """
    List training jobs, optionally filtered by character.
    """
    return await _list_jobs(character_id)
