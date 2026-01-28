"""
Captioning Endpoints

Generate structured captions for character training images using Florence-2.
Jobs run in-process via FastAPI BackgroundTasks.
"""

import asyncio
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger, get_correlation_id
from packages.shared.src.types import (
    CaptioningJob,
    CaptioningConfig,
    StartCaptioningRequest,
    CaptioningResult,
    JobStatus,
    JobType,
    JobProgressEvent,
)
from ..models.responses import (
    ErrorResponse,
    ErrorCodes,
)

router = APIRouter()
logger = get_logger("api.routes.captioning")

# In-memory job storage (captioning jobs are short-lived, no need for persistence)
_captioning_jobs: dict[str, CaptioningJob] = {}

# Character storage reference
from .characters import _get_character_or_404, _save_character


def _get_job_or_404(job_id: str) -> CaptioningJob:
    """Get captioning job by ID or raise 404."""
    if job_id not in _captioning_jobs:
        raise HTTPException(
            status_code=404,
            detail=f"Captioning job {job_id} not found",
        )
    return _captioning_jobs[job_id]


def _get_caption_script_path() -> Path:
    """Get path to the captioning script."""
    # In container: /app/scripts/engines/caption_images.py
    # Locally: relative to project root
    candidates = [
        Path("/app/scripts/engines/caption_images.py"),
        Path(__file__).parent.parent.parent.parent.parent.parent / "scripts" / "engines" / "caption_images.py",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Caption script not found")


async def _run_captioning_job(job_id: str, character_id: str, trigger_word: str, config: CaptioningConfig):
    """
    Execute captioning job in background.

    Calls the Florence-2 captioning script and parses its output.
    """
    job = _captioning_jobs.get(job_id)
    if not job:
        logger.error(f"Job {job_id} not found in store")
        return

    cfg = get_global_config()

    try:
        # Update job status
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()

        # Get character images directory
        images_dir = cfg.uploads_dir / character_id
        if not images_dir.exists():
            raise FileNotFoundError(f"No images directory for character {character_id}")

        # Count images
        image_files = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.jpeg")) + list(images_dir.glob("*.webp"))
        job.total_images = len(image_files)

        if job.total_images == 0:
            raise ValueError(f"No images found for character {character_id}")

        logger.info(f"Starting captioning job {job_id}", extra={
            "event": "captioning.started",
            "job_id": job_id,
            "character_id": character_id,
            "total_images": job.total_images,
            "trigger_word": trigger_word,
        })

        # Build command
        script_path = _get_caption_script_path()

        cmd = [
            "python", str(script_path),
            "--input", str(images_dir),
            "--trigger", trigger_word,
            "--model", config.model,
            "--style", config.style_hint.value if hasattr(config.style_hint, 'value') else str(config.style_hint),
        ]

        if config.overwrite_existing:
            cmd.append("--overwrite")

        # Check for local model path
        model_path = os.environ.get("FLORENCE2_MODEL_PATH")
        if model_path and Path(model_path).exists():
            cmd.extend(["--model-path", model_path])

        logger.debug(f"Running caption command: {' '.join(cmd)}")

        # Run the captioning script
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        captions = {}
        generated = 0
        skipped = 0
        failed = 0

        # Parse output in real-time
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line = line.decode().strip()

            if line.startswith("PROGRESS:"):
                # PROGRESS:1/10:image.jpg:message
                parts = line[9:].split(":", 3)
                if len(parts) >= 3:
                    progress_str, filename, message = parts[0], parts[1], parts[2] if len(parts) > 2 else ""
                    current, total = progress_str.split("/")
                    job.current_image = int(current)
                    job.total_images = int(total)
                    job.progress = (int(current) / int(total)) * 100

                    logger.debug(f"Captioning progress: {current}/{total} - {filename}")

            elif line.startswith("CAPTION:"):
                # CAPTION:image.jpg:caption text
                parts = line[8:].split(":", 1)
                if len(parts) == 2:
                    filename, caption = parts
                    captions[filename] = caption
                    generated += 1

            elif line.startswith("COMPLETE:"):
                # COMPLETE:total:generated:skipped:failed:time
                parts = line[9:].split(":")
                if len(parts) >= 5:
                    job.total_images = int(parts[0])
                    generated = int(parts[1])
                    skipped = int(parts[2])
                    failed = int(parts[3])

        # Wait for process to complete
        await process.wait()

        # Read stderr for any errors
        stderr = await process.stderr.read()
        if stderr:
            stderr_text = stderr.decode()
            # Log but don't fail - some stderr is debug info
            for line in stderr_text.strip().split("\n"):
                if line.startswith("ERROR:"):
                    logger.error(f"Caption script error: {line}")
                elif line.startswith("INFO:"):
                    logger.info(f"Caption script: {line[5:]}")

        if process.returncode != 0:
            raise RuntimeError(f"Captioning script failed with exit code {process.returncode}")

        # Update job with results
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        job.captions_generated = generated
        job.progress = 100.0

        logger.info(f"Captioning job completed: {job_id}", extra={
            "event": "captioning.completed",
            "job_id": job_id,
            "character_id": character_id,
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
        })

    except Exception as e:
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()

        logger.error(f"Captioning job failed: {job_id}", extra={
            "event": "captioning.failed",
            "job_id": job_id,
            "error": str(e),
        }, exc_info=True)


@router.post("", response_model=CaptioningJob, status_code=201)
async def start_captioning(
    request: StartCaptioningRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a captioning job for a character's images.

    This will generate structured captions for all images in the character's
    upload directory using Florence-2. Captions are saved as .txt files
    alongside each image.

    The job runs asynchronously. Poll the job status endpoint or use SSE
    to track progress.
    """
    # Validate character exists
    character = _get_character_or_404(request.character_id)

    # Create job
    job_id = f"cap-{uuid.uuid4().hex[:8]}"

    job = CaptioningJob(
        id=job_id,
        character_id=request.character_id,
        status=JobStatus.PENDING,
        config=request.config,
        created_at=datetime.utcnow(),
    )

    _captioning_jobs[job_id] = job

    logger.info(f"Created captioning job: {job_id}", extra={
        "event": "captioning.created",
        "job_id": job_id,
        "character_id": request.character_id,
        "character_name": character.name,
        "trigger_word": character.trigger_word,
    })

    # Start background task
    background_tasks.add_task(
        _run_captioning_job,
        job_id,
        request.character_id,
        character.trigger_word,
        request.config,
    )

    return job


@router.get("/{job_id}", response_model=CaptioningJob)
async def get_captioning_job(job_id: str):
    """
    Get the status of a captioning job.
    """
    return _get_job_or_404(job_id)


@router.get("", response_model=list[CaptioningJob])
async def list_captioning_jobs(character_id: str = None):
    """
    List captioning jobs, optionally filtered by character.
    """
    jobs = list(_captioning_jobs.values())

    if character_id:
        jobs = [j for j in jobs if j.character_id == character_id]

    # Sort by created_at descending
    jobs.sort(key=lambda j: j.created_at, reverse=True)

    return jobs


@router.get("/{job_id}/stream")
async def stream_captioning_progress(job_id: str):
    """
    Stream captioning progress via Server-Sent Events.
    """
    _get_job_or_404(job_id)

    async def event_generator() -> AsyncGenerator[dict, None]:
        last_progress = -1

        while True:
            job = _captioning_jobs.get(job_id)
            if not job:
                break

            # Emit progress updates
            if job.progress != last_progress:
                last_progress = job.progress
                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "job_id": job_id,
                        "status": job.status.value if hasattr(job.status, 'value') else str(job.status),
                        "progress": job.progress,
                        "current_image": job.current_image,
                        "total_images": job.total_images,
                        "captions_generated": job.captions_generated,
                    }),
                }

            # Check for completion
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "job_id": job_id,
                        "status": job.status.value if hasattr(job.status, 'value') else str(job.status),
                        "captions_generated": job.captions_generated,
                        "error_message": job.error_message,
                    }),
                }
                break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@router.post("/{job_id}/cancel", status_code=200)
async def cancel_captioning_job(job_id: str):
    """
    Cancel a running captioning job.

    Note: This marks the job as cancelled but the underlying process
    may still complete. The results will be discarded.
    """
    job = _get_job_or_404(job_id)

    if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in status {job.status}",
        )

    job.status = JobStatus.CANCELLED
    job.completed_at = datetime.utcnow()

    logger.info(f"Captioning job cancelled: {job_id}", extra={
        "event": "captioning.cancelled",
        "job_id": job_id,
    })

    return {"status": "cancelled", "job_id": job_id}


@router.get("/character/{character_id}/captions")
async def get_character_captions(character_id: str):
    """
    Get all captions for a character's images.

    Returns a dict mapping image filenames to their captions.
    Images without captions are included with empty strings.
    """
    character = _get_character_or_404(character_id)
    cfg = get_global_config()

    images_dir = cfg.uploads_dir / character_id
    if not images_dir.exists():
        return {"captions": {}, "captioned": 0, "uncaptioned": 0}

    captions = {}
    captioned = 0
    uncaptioned = 0

    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        for image_path in images_dir.glob(ext):
            caption_path = image_path.with_suffix(".txt")

            if caption_path.exists():
                captions[image_path.name] = caption_path.read_text().strip()
                captioned += 1
            else:
                captions[image_path.name] = ""
                uncaptioned += 1

    return {
        "captions": captions,
        "captioned": captioned,
        "uncaptioned": uncaptioned,
        "total": captioned + uncaptioned,
    }


@router.delete("/character/{character_id}/captions", status_code=200)
async def delete_character_captions(character_id: str):
    """
    Delete all captions for a character's images.

    Removes all .txt caption files from the character's image directory.
    """
    character = _get_character_or_404(character_id)
    cfg = get_global_config()

    images_dir = cfg.uploads_dir / character_id
    if not images_dir.exists():
        return {"deleted": 0}

    deleted = 0
    for caption_path in images_dir.glob("*.txt"):
        caption_path.unlink()
        deleted += 1

    logger.info(f"Deleted {deleted} captions for character {character_id}", extra={
        "event": "captions.deleted",
        "character_id": character_id,
        "deleted": deleted,
    })

    return {"deleted": deleted}
