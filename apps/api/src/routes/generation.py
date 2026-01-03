"""
Image Generation Endpoints

Handle image generation requests.
Jobs run in-process via FastAPI BackgroundTasks.
"""

import asyncio
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger, get_correlation_id
from ..middleware import get_interaction_id
from packages.shared.src.types import (
    GenerationJob,
    GenerateImageRequest,
    JobStatus,
    JobType,
    JobProgressEvent,
)
from packages.shared.src.rate_limit import rate_limit, RATE_LIMIT_GENERATION

from ..models.responses import (
    ErrorResponse,
    ErrorCodes,
)
from ..services.config_validator import validate_generation_config
from ..services.job_executor import get_generation_capabilities

from ..services.job_executor import (
    execute_generation_job,
    get_job_progress_events,
)
from ..services.job_store import get_generation_store

router = APIRouter()
logger = get_logger("api.routes.generation")

# Persistent job storage (backed by JSON files on disk)
# Initialized lazily on first access via get_generation_store()

# Reference to character storage
from .characters import _characters, _load_all_characters, _load_character


async def _get_job_or_404(job_id: str) -> GenerationJob:
    """Get job by ID or raise 404 with structured error."""
    store = get_generation_store()
    job = store.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error="Job not found",
                details=[{
                    "code": ErrorCodes.JOB_NOT_FOUND,
                    "message": f"Generation job {job_id} not found",
                    "field": "job_id",
                }],
            ).model_dump(),
        )
    return job


async def _save_job(job: GenerationJob) -> None:
    """Save job to persistent storage."""
    store = get_generation_store()
    store.save(job)


async def _list_jobs(limit: int = 20) -> list[GenerationJob]:
    """List jobs from persistent storage."""
    store = get_generation_store()
    jobs = store.list_all()
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs[:limit]


@router.post(
    "",
    response_model=GenerationJob,
    status_code=201,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error (invalid config or LoRA not trained)"},
        404: {"model": ErrorResponse, "description": "Character/LoRA not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@rate_limit(**RATE_LIMIT_GENERATION)
async def generate_images(
    http_request: Request,
    request: GenerateImageRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start an image generation job.

    Executes generation in background via BackgroundTasks.
    Rate limited to 20 requests per minute.

    Error Codes:
    - VALIDATION_ERROR: Invalid generation configuration
    - OUT_OF_RANGE: Parameter value outside allowed range
    - NOT_SUPPORTED: Feature not supported by backend
    - LORA_NOT_FOUND: Character/LoRA does not exist
    - INVALID_STATE: Character has not been trained yet
    """
    _load_all_characters()
    config = get_global_config()

    # Validate config against capabilities
    capabilities = get_generation_capabilities()
    validate_generation_config(request.config.model_dump(mode="json"), capabilities)

    # Validate LoRA if specified
    if request.config.lora_id:
        # Check if character exists (with fallback to disk if not in cache)
        character = None
        if request.config.lora_id in _characters:
            character = _characters[request.config.lora_id]
        else:
            # Fallback: Try loading directly from disk (handles race condition
            # when character was just created and cache is stale)
            character = _load_character(request.config.lora_id)
            if character:
                _characters[request.config.lora_id] = character
                logger.debug("Character loaded from disk (cache miss)", extra={
                    "character_id": request.config.lora_id,
                })

        if character is None:
            raise HTTPException(
                status_code=404,
                detail=ErrorResponse(
                    error="LoRA not found",
                    details=[{
                        "code": ErrorCodes.LORA_NOT_FOUND,
                        "message": f"Character LoRA {request.config.lora_id} not found",
                        "field": "lora_id",
                    }],
                ).model_dump(),
            )
        # Check if LoRA exists on disk
        lora_dir = config.loras_dir / request.config.lora_id
        if not lora_dir.exists() or not list(lora_dir.glob("v*.safetensors")):
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="LoRA not trained",
                    details=[{
                        "code": ErrorCodes.INVALID_STATE,
                        "message": f"Character {request.config.lora_id} has not been trained yet",
                        "field": "lora_id",
                    }],
                ).model_dump(),
            )

    # Create job with server-generated ID
    job_id = f"gen-{uuid.uuid4().hex[:12]}"
    correlation_id = get_correlation_id()
    interaction_id = get_interaction_id()

    job = GenerationJob(
        id=job_id,
        status=JobStatus.QUEUED,
        config=request.config,
        created_at=datetime.now(timezone.utc),
    )

    # Save job to persistent storage
    store = get_generation_store()
    store.save(job)

    # Log job creation
    log_extra = {
        "event": "job.created",
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
    }
    if interaction_id:
        log_extra["interaction_id"] = interaction_id
    logger.info("Generation job created", extra=log_extra)

    # Execute in-process via BackgroundTasks
    # Pass the store's internal dict for backwards compatibility with executor
    background_tasks.add_task(
        execute_generation_job,
        job=job,
        jobs_store=store.get_dict(),
        count=request.count,
        correlation_id=correlation_id,
    )

    return job


@router.get("/{job_id}", response_model=GenerationJob)
async def get_generation_job(job_id: str):
    """
    Get generation job status.
    """
    return await _get_job_or_404(job_id)


@router.get("/{job_id}/stream")
async def stream_generation_progress(job_id: str):
    """
    Stream generation progress via Server-Sent Events.

    All events include job_id and correlation_id.
    """
    job = await _get_job_or_404(job_id)

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for job progress."""

        # Send initial state
        initial_event = JobProgressEvent(
            job_id=job_id,
            job_type=JobType.IMAGE_GENERATION,
            status=job.status,
            progress=job.progress,
            message="Connected to progress stream",
        )
        yield {"event": "progress", "data": initial_event.model_dump_json()}

        # Poll persistent store for updates
        store = get_generation_store()
        last_event_count = 0
        while True:
            await asyncio.sleep(0.3)

            current_job = store.get(job_id)
            if current_job is None:
                break

            # Check for new progress events from executor
            progress_events = get_job_progress_events(job_id)
            if len(progress_events) > last_event_count:
                for event in progress_events[last_event_count:]:
                    yield {"event": "progress", "data": event.model_dump_json()}
                last_event_count = len(progress_events)

            # Stop streaming when job completes
            if current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                # Persist final job state to disk
                store.save(current_job)

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


@router.post(
    "/{job_id}/cancel",
    response_model=GenerationJob,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid job state for cancellation"},
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def cancel_generation(job_id: str):
    """
    Cancel a generation job.

    Error Codes:
    - JOB_NOT_FOUND: Generation job does not exist
    - INVALID_STATE: Job cannot be cancelled (already completed/failed/cancelled)
    """
    job = await _get_job_or_404(job_id)

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="Invalid job state",
                details=[{
                    "code": ErrorCodes.INVALID_STATE,
                    "message": f"Cannot cancel job in {job.status.value} state",
                    "field": "status",
                }],
            ).model_dump(),
        )

    job.status = JobStatus.CANCELLED
    await _save_job(job)

    logger.info("Generation job cancelled", extra={
        "event": "job.cancelled",
        "job_id": job_id,
    })

    return job


@router.get("", response_model=list[GenerationJob])
async def list_generation_jobs(limit: int = 20):
    """
    List recent generation jobs.
    """
    return await _list_jobs(limit)


@router.get("/output/{job_id}/{filename}")
async def get_generation_output(job_id: str, filename: str):
    """
    Serve a generated image output.

    Files are stored in outputs/{job_id}/{filename}.
    Both job_id and filename are validated to prevent path traversal.
    """
    # Sanitize job_id - allow alphanumeric, hyphens, underscores only
    safe_job_id = re.sub(r"[^\w\-]", "", job_id)
    if not safe_job_id or safe_job_id != job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id")

    # Sanitize filename - allow alphanumeric, hyphens, underscores, dots only
    safe_filename = re.sub(r"[^\w\-\.]", "", filename)
    if not safe_filename or safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    config = get_global_config()
    output_path = config.outputs_dir / safe_job_id / safe_filename

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    # Verify the file is inside outputs_dir (prevent path traversal)
    try:
        output_path.resolve().relative_to(config.outputs_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    # Determine media type based on file extension
    suffix = output_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=output_path,
        media_type=media_type,
        filename=safe_filename
    )
