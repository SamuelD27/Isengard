"""
Image Generation Endpoints

Handle image generation requests.
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
    GenerationJob,
    GenerateImageRequest,
    JobStatus,
    JobType,
    JobProgressEvent,
)
from packages.shared.src.capabilities import is_capability_supported

from ..services.job_executor import (
    execute_generation_job,
    get_latest_progress,
    get_job_progress_events,
)

router = APIRouter()
logger = get_logger("api.routes.generation")

# In-memory job storage (will be replaced with Redis in M2)
_generation_jobs: dict[str, GenerationJob] = {}

# Reference to character storage
from .characters import _characters, _load_all_characters


def _get_job_or_404(job_id: str) -> GenerationJob:
    """Get job by ID or raise 404."""
    if job_id not in _generation_jobs:
        raise HTTPException(status_code=404, detail=f"Generation job {job_id} not found")
    return _generation_jobs[job_id]


@router.post("", response_model=GenerationJob, status_code=201)
async def generate_images(
    request: GenerateImageRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start an image generation job.

    Executes generation in background (M1: in-process, M2: Redis queue).
    """
    _load_all_characters()
    config = get_global_config()

    # Validate capability
    if not is_capability_supported("image_generation", "comfyui"):
        # In fast-test mode, mock plugin is available
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
        # Check if LoRA exists on disk
        lora_dir = config.loras_dir / request.config.lora_id
        if not lora_dir.exists() or not list(lora_dir.glob("v*.safetensors")):
            raise HTTPException(
                status_code=400,
                detail=f"Character {request.config.lora_id} has not been trained yet"
            )

    # Create job with server-generated ID
    job_id = f"gen-{uuid.uuid4().hex[:12]}"
    correlation_id = get_correlation_id()

    job = GenerationJob(
        id=job_id,
        status=JobStatus.QUEUED,
        config=request.config,
        created_at=datetime.utcnow(),
    )

    _generation_jobs[job_id] = job

    logger.info("Generation job created", extra={
        "job_id": job_id,
        "prompt": request.config.prompt[:50] + "..." if len(request.config.prompt) > 50 else request.config.prompt,
        "size": f"{request.config.width}x{request.config.height}",
        "count": request.count,
        "lora_id": request.config.lora_id,
        "toggles": {
            "use_controlnet": request.config.use_controlnet,
            "use_ipadapter": request.config.use_ipadapter,
            "use_facedetailer": request.config.use_facedetailer,
            "use_upscale": request.config.use_upscale,
        },
    })

    # Execute job in background
    background_tasks.add_task(
        execute_generation_job,
        job=job,
        jobs_store=_generation_jobs,
        count=request.count,
        correlation_id=correlation_id,
    )

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
            job_type=JobType.IMAGE_GENERATION,
            status=job.status,
            progress=job.progress,
            message="Connected to progress stream",
        )
        event_data = initial_event.model_dump()
        event_data["correlation_id"] = correlation_id
        yield {"event": "progress", "data": initial_event.model_dump_json()}

        # Poll for updates (M1: in-process, M2: would use Redis Streams)
        while True:
            await asyncio.sleep(0.3)  # Poll frequently for responsive generation updates

            if job_id not in _generation_jobs:
                break

            current_job = _generation_jobs[job_id]

            # Check for new progress events from executor
            progress_events = get_job_progress_events(job_id)
            if len(progress_events) > last_event_count:
                for event in progress_events[last_event_count:]:
                    event_data = event.model_dump()
                    event_data["correlation_id"] = correlation_id
                    yield {"event": "progress", "data": event.model_dump_json()}
                last_event_count = len(progress_events)

            # Stop streaming when job completes or fails
            if current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                final_event = JobProgressEvent(
                    job_id=job_id,
                    job_type=JobType.IMAGE_GENERATION,
                    status=current_job.status,
                    progress=current_job.progress,
                    message="Generation finished" if current_job.status == JobStatus.COMPLETED else f"Job {current_job.status.value}",
                    error=current_job.error_message,
                )
                yield {"event": "complete", "data": final_event.model_dump_json()}
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
