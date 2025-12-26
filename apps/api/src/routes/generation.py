"""
Image Generation Endpoints

Handle image generation requests.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger
from packages.shared.src.types import (
    GenerationJob,
    GenerateImageRequest,
    JobStatus,
    JobType,
    JobProgressEvent,
)
from packages.shared.src.capabilities import is_capability_supported

router = APIRouter()
logger = get_logger("api.routes.generation")

# In-memory job storage (will be replaced with Redis)
_generation_jobs: dict[str, GenerationJob] = {}

# Reference to character storage
from .characters import _characters


def _get_job_or_404(job_id: str) -> GenerationJob:
    """Get job by ID or raise 404."""
    if job_id not in _generation_jobs:
        raise HTTPException(status_code=404, detail=f"Generation job {job_id} not found")
    return _generation_jobs[job_id]


@router.post("", response_model=GenerationJob, status_code=201)
async def generate_images(request: GenerateImageRequest):
    """
    Start an image generation job.
    """
    # Validate capability
    if not is_capability_supported("image_generation", "comfyui"):
        # In fast-test mode, mock plugin is available
        config = get_global_config()
        if not config.is_fast_test:
            raise HTTPException(
                status_code=503,
                detail="Image generation is not available in production mode yet"
            )

    # Validate LoRA if specified
    if request.config.lora_id:
        if request.config.lora_id not in _characters:
            raise HTTPException(
                status_code=404,
                detail=f"Character LoRA {request.config.lora_id} not found"
            )
        character = _characters[request.config.lora_id]
        if not character.lora_path:
            raise HTTPException(
                status_code=400,
                detail=f"Character {request.config.lora_id} has not been trained yet"
            )

    # Create job
    job_id = f"gen-{uuid.uuid4().hex[:8]}"
    job = GenerationJob(
        id=job_id,
        status=JobStatus.QUEUED,
        config=request.config,
        created_at=datetime.utcnow(),
    )

    _generation_jobs[job_id] = job

    # TODO: Push to Redis queue for worker

    logger.info("Generation job created", extra={
        "job_id": job_id,
        "prompt": request.config.prompt[:50] + "..." if len(request.config.prompt) > 50 else request.config.prompt,
        "size": f"{request.config.width}x{request.config.height}",
        "count": request.count,
        "lora_id": request.config.lora_id,
    })

    return job


@router.get("/{job_id}", response_model=GenerationJob)
async def get_generation_job(job_id: str):
    """
    Get generation job status.
    """
    return _get_job_or_404(job_id)


@router.get("/{job_id}/stream")
async def stream_generation_progress(job_id: str):
    """
    Stream generation progress via Server-Sent Events.
    """
    job = _get_job_or_404(job_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for job progress."""
        # Send initial state
        event = JobProgressEvent(
            job_id=job_id,
            job_type=JobType.IMAGE_GENERATION,
            status=job.status,
            progress=job.progress,
            message="Connected to progress stream",
        )
        yield {"event": "progress", "data": event.model_dump_json()}

        # TODO: Subscribe to Redis pub/sub for real updates

        import asyncio
        while True:
            await asyncio.sleep(2)

            if job_id in _generation_jobs:
                current_job = _generation_jobs[job_id]
                event = JobProgressEvent(
                    job_id=job_id,
                    job_type=JobType.IMAGE_GENERATION,
                    status=current_job.status,
                    progress=current_job.progress,
                    message=f"Generation progress: {current_job.progress:.1f}%",
                )
                yield {"event": "progress", "data": event.model_dump_json()}

                if current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    yield {"event": "complete", "data": event.model_dump_json()}
                    break
            else:
                break

    return EventSourceResponse(event_generator())


@router.post("/{job_id}/cancel", response_model=GenerationJob)
async def cancel_generation(job_id: str):
    """
    Cancel a generation job.
    """
    job = _get_job_or_404(job_id)

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in {job.status} state"
        )

    job.status = JobStatus.CANCELLED
    _generation_jobs[job_id] = job

    logger.info("Generation job cancelled", extra={"job_id": job_id})

    return job


@router.get("", response_model=list[GenerationJob])
async def list_generation_jobs(limit: int = 20):
    """
    List recent generation jobs.
    """
    jobs = list(_generation_jobs.values())
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs[:limit]
