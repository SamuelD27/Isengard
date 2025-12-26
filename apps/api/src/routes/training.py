"""
Training Endpoints

Manage LoRA training jobs.
"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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

router = APIRouter()
logger = get_logger("api.routes.training")

# In-memory job storage (will be replaced with Redis)
_training_jobs: dict[str, TrainingJob] = {}

# In-memory character storage reference (imported from characters route)
from .characters import _characters


def _get_job_or_404(job_id: str) -> TrainingJob:
    """Get job by ID or raise 404."""
    if job_id not in _training_jobs:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
    return _training_jobs[job_id]


@router.post("", response_model=TrainingJob, status_code=201)
async def start_training(request: StartTrainingRequest):
    """
    Start a new training job.

    Creates a job and queues it for the worker to process.
    """
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

    # Create job
    job_id = f"train-{uuid.uuid4().hex[:8]}"
    job = TrainingJob(
        id=job_id,
        character_id=request.character_id,
        status=JobStatus.QUEUED,
        config=request.config,
        total_steps=request.config.steps,
        created_at=datetime.utcnow(),
    )

    _training_jobs[job_id] = job

    # TODO: Push to Redis queue for worker
    # For now, just mark as queued

    logger.info("Training job created", extra={
        "job_id": job_id,
        "character_id": request.character_id,
        "method": request.config.method.value,
        "steps": request.config.steps,
    })

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
    """
    job = _get_job_or_404(job_id)
    correlation_id = get_correlation_id()

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for job progress."""
        # Send initial state
        event = JobProgressEvent(
            job_id=job_id,
            job_type=JobType.TRAINING,
            status=job.status,
            progress=job.progress,
            message="Connected to progress stream",
            current_step=job.current_step,
            total_steps=job.total_steps,
        )
        yield {"event": "progress", "data": event.model_dump_json()}

        # TODO: Subscribe to Redis pub/sub for real updates
        # For now, this is a placeholder that would be connected to the worker

        # Keep connection alive with heartbeats
        import asyncio
        while True:
            await asyncio.sleep(5)

            # Refresh job state
            if job_id in _training_jobs:
                current_job = _training_jobs[job_id]
                event = JobProgressEvent(
                    job_id=job_id,
                    job_type=JobType.TRAINING,
                    status=current_job.status,
                    progress=current_job.progress,
                    message=f"Training progress: {current_job.progress:.1f}%",
                    current_step=current_job.current_step,
                    total_steps=current_job.total_steps,
                )
                yield {"event": "progress", "data": event.model_dump_json()}

                # Stop streaming when job completes or fails
                if current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    yield {"event": "complete", "data": event.model_dump_json()}
                    break
            else:
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
