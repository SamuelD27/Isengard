"""
Job Endpoints

Unified job management including:
- Log file serving
- Artifact listing and serving
- Debug bundle generation
- Enhanced SSE streaming with structured events
"""

import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import (
    get_logger,
    get_job_log_path,
    get_job_artifacts_dir,
    get_job_samples_dir,
    get_correlation_id,
    redact_sensitive,
)
from packages.shared.src.events import (
    get_event_bus,
    TrainingProgressEvent,
    TrainingStage,
)
from packages.shared.src import redis_client

router = APIRouter()
logger = get_logger("api.routes.jobs")


# Job ID validation pattern - alphanumeric with hyphens and underscores
JOB_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_job_id(job_id: str) -> None:
    """Validate job ID format to prevent path traversal."""
    if not JOB_ID_PATTERN.match(job_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid job ID format. Only alphanumeric characters, hyphens, and underscores are allowed."
        )


# ============================================
# Response Models
# ============================================

class ArtifactInfo(BaseModel):
    """Information about a job artifact."""
    name: str
    path: str
    type: str  # "sample", "checkpoint", "model", "log"
    size_bytes: int
    created_at: str
    step: int | None = None
    url: str


class ArtifactListResponse(BaseModel):
    """Response for artifact listing."""
    job_id: str
    artifacts: list[ArtifactInfo]
    total_count: int


class JobLogEntry(BaseModel):
    """A single log entry."""
    timestamp: str
    level: str
    message: str
    event: str | None = None
    fields: dict | None = None


class JobLogsResponse(BaseModel):
    """Response for log viewing."""
    job_id: str
    entries: list[JobLogEntry]
    total_lines: int
    has_more: bool


class DebugBundleInfo(BaseModel):
    """Information about a debug bundle."""
    job_id: str
    bundle_path: str
    size_bytes: int
    created_at: str
    includes: list[str]


# ============================================
# Log Endpoints
# ============================================

@router.get("/{job_id}/logs")
async def download_job_logs(job_id: str):
    """
    Download the JSONL log file for a specific job.

    Returns the job's log file as a downloadable JSONL file.
    Each line is a JSON object with timestamp, level, message, etc.

    The file can be processed with tools like `jq`:
        cat job.jsonl | jq .

    Or viewed in editors that support JSONL format.
    """
    validate_job_id(job_id)

    # Get log file path
    log_path = get_job_log_path(job_id)

    if log_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Log file for job '{job_id}' not found. The job may not have started yet or logs were not preserved."
        )

    # Additional security: verify path is within expected directory
    config = get_global_config()
    expected_dir = config.volume_root / "logs" / "jobs"

    try:
        log_path.resolve().relative_to(expected_dir.resolve())
    except ValueError:
        logger.warning(
            "Attempted path traversal in job logs request",
            extra={"event": "security.path_traversal", "job_id": job_id}
        )
        raise HTTPException(status_code=400, detail="Invalid job ID")

    logger.info(
        f"Serving job log file",
        extra={"event": "logs.download", "job_id": job_id, "path": str(log_path)}
    )

    return FileResponse(
        path=log_path,
        media_type="application/x-ndjson",
        filename=f"{job_id}.jsonl",
        headers={
            "Content-Disposition": f'attachment; filename="{job_id}.jsonl"'
        }
    )


@router.get("/{job_id}/logs/view", response_model=JobLogsResponse)
async def view_job_logs(
    job_id: str,
    offset: int = Query(0, ge=0, description="Line offset to start from"),
    limit: int = Query(100, ge=1, le=1000, description="Number of lines to return"),
    level: str | None = Query(None, description="Filter by log level (INFO, WARNING, ERROR, DEBUG)"),
    event: str | None = Query(None, description="Filter by event type"),
    search: str | None = Query(None, description="Search in message text"),
):
    """
    View job logs with pagination and filtering.

    Returns structured log entries for display in the UI.
    Supports filtering by level, event type, and text search.
    """
    validate_job_id(job_id)

    log_path = get_job_log_path(job_id)
    if log_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Log file for job '{job_id}' not found."
        )

    entries = []
    total_lines = 0

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            total_lines = len(all_lines)

            for line in all_lines[offset:offset + limit]:
                try:
                    data = json.loads(line.strip())

                    # Apply filters
                    if level and data.get("level", "").upper() != level.upper():
                        continue
                    if event and data.get("event") != event:
                        continue
                    if search and search.lower() not in data.get("msg", "").lower():
                        continue

                    entries.append(JobLogEntry(
                        timestamp=data.get("ts", ""),
                        level=data.get("level", "INFO"),
                        message=data.get("msg", ""),
                        event=data.get("event"),
                        fields=data.get("fields"),
                    ))
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        logger.error(f"Failed to read job logs: {e}", extra={"job_id": job_id})
        raise HTTPException(status_code=500, detail="Failed to read log file")

    return JobLogsResponse(
        job_id=job_id,
        entries=entries,
        total_lines=total_lines,
        has_more=offset + limit < total_lines,
    )


# ============================================
# Artifact Endpoints
# ============================================

@router.get("/{job_id}/artifacts", response_model=ArtifactListResponse)
async def list_job_artifacts(job_id: str):
    """
    List all artifacts for a job.

    Includes:
    - Sample images generated during training
    - Checkpoints (if any)
    - Final model output
    - Log files
    """
    validate_job_id(job_id)

    config = get_global_config()
    artifacts = []

    # Check samples directory
    samples_dir = get_job_samples_dir(job_id)
    if samples_dir.exists():
        for sample_file in sorted(samples_dir.glob("*.png")):
            # Extract step number from filename (e.g., step_100.png)
            step = None
            if match := re.match(r"step_(\d+)", sample_file.stem):
                step = int(match.group(1))

            artifacts.append(ArtifactInfo(
                name=sample_file.name,
                path=str(sample_file),
                type="sample",
                size_bytes=sample_file.stat().st_size,
                created_at=datetime.fromtimestamp(
                    sample_file.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                step=step,
                url=f"/api/jobs/{job_id}/artifacts/samples/{sample_file.name}",
            ))

    # Check for log file
    log_path = get_job_log_path(job_id)
    if log_path and log_path.exists():
        artifacts.append(ArtifactInfo(
            name=f"{job_id}.jsonl",
            path=str(log_path),
            type="log",
            size_bytes=log_path.stat().st_size,
            created_at=datetime.fromtimestamp(
                log_path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            url=f"/api/jobs/{job_id}/logs",
        ))

    # Check for trained model (for training jobs)
    if job_id.startswith("train-"):
        # Get job data to find character_id
        job_data = await redis_client.get_job(job_id)
        if job_data and job_data.get("output_path"):
            output_path = Path(job_data["output_path"])
            if output_path.exists():
                artifacts.append(ArtifactInfo(
                    name=output_path.name,
                    path=str(output_path),
                    type="model",
                    size_bytes=output_path.stat().st_size,
                    created_at=datetime.fromtimestamp(
                        output_path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    url=f"/api/jobs/{job_id}/artifacts/model",
                ))

    return ArtifactListResponse(
        job_id=job_id,
        artifacts=artifacts,
        total_count=len(artifacts),
    )


@router.get("/{job_id}/artifacts/samples/{filename}")
async def get_sample_image(job_id: str, filename: str):
    """
    Serve a sample image from a training job.

    Sample images are generated during training at configured intervals.
    """
    validate_job_id(job_id)

    # Validate filename
    if not re.match(r"^[\w\-\.]+$", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    samples_dir = get_job_samples_dir(job_id)
    sample_path = samples_dir / filename

    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found")

    # Security: verify path is within samples directory
    try:
        sample_path.resolve().relative_to(samples_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    return FileResponse(
        path=sample_path,
        media_type="image/png",
        filename=filename,
    )


# ============================================
# SSE Stream Endpoint
# ============================================

@router.get("/{job_id}/stream")
async def stream_job_events(job_id: str):
    """
    Stream job events via Server-Sent Events.

    Provides real-time updates for:
    - Progress updates (step, loss, ETA)
    - Sample image generation
    - Completion/failure events

    Events are structured according to the TrainingProgressEvent schema.

    Reconnection: Clients can reconnect and will receive recent events from history.
    """
    validate_job_id(job_id)

    config = get_global_config()
    use_redis = os.getenv("USE_REDIS", "false").lower() == "true"
    correlation_id = get_correlation_id()

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for job progress."""

        # Get initial job state
        job_data = await redis_client.get_job(job_id)
        if not job_data:
            # Job might be in-memory only, send initial connecting event
            yield {
                "event": "connected",
                "data": json.dumps({
                    "job_id": job_id,
                    "message": "Connected to job stream",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            }
        else:
            # Send initial state
            initial_event = TrainingProgressEvent(
                job_id=job_id,
                correlation_id=correlation_id,
                status=job_data.get("status", "running"),
                stage=TrainingStage.TRAINING,
                step=job_data.get("current_step", 0),
                steps_total=job_data.get("total_steps", 0),
                progress_pct=job_data.get("progress", 0),
                message="Connected to progress stream",
            )
            yield initial_event.to_sse()

        # Check if job already completed
        if job_data and job_data.get("status") in ("completed", "failed", "cancelled"):
            return

        if use_redis:
            # Stream from Redis
            try:
                async for progress in redis_client.stream_progress(job_id):
                    # Convert Redis progress to our event format
                    event = TrainingProgressEvent(
                        job_id=job_id,
                        correlation_id=progress.get("correlation_id"),
                        status=progress.get("status", "running"),
                        stage=TrainingStage.TRAINING,
                        step=int(progress.get("current_step", 0)),
                        steps_total=int(progress.get("total_steps", 0)),
                        progress_pct=float(progress.get("progress", 0)),
                        loss=float(progress.get("loss")) if progress.get("loss") else None,
                        message=progress.get("message", ""),
                        error=progress.get("error"),
                    )
                    yield event.to_sse()

                    # Stop on terminal state
                    if event.status in ("completed", "failed", "cancelled"):
                        return
            except Exception as e:
                logger.error(f"SSE stream error: {e}", extra={"job_id": job_id})
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)}),
                }
        else:
            # Use in-memory event bus
            event_bus = get_event_bus()
            try:
                async for event_dict in event_bus.subscribe(job_id):
                    if event_dict.get("type") == "keepalive":
                        yield {"event": "keepalive", "data": "{}"}
                        continue

                    yield {
                        "event": "complete" if event_dict.get("status") in ("completed", "failed", "cancelled") else "progress",
                        "data": json.dumps(event_dict),
                    }

                    if event_dict.get("status") in ("completed", "failed", "cancelled"):
                        return
            except Exception as e:
                logger.error(f"Event bus stream error: {e}", extra={"job_id": job_id})

    return EventSourceResponse(event_generator())


# ============================================
# Debug Bundle Endpoint
# ============================================

@router.get("/{job_id}/debug-bundle")
async def download_debug_bundle(job_id: str):
    """
    Download a debug bundle for a job.

    The bundle is a ZIP file containing:
    - Job metadata (config, status, timestamps)
    - Complete job log file (events.jsonl)
    - Last 1000 lines of service logs (api, worker)
    - Sample images (if any)
    - Environment snapshot (redacted)
    - Directory tree of artifacts

    Use this for debugging failed jobs or sharing with support.
    """
    validate_job_id(job_id)

    config = get_global_config()

    # Create in-memory ZIP file
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        bundle_contents = []

        # 1. Job metadata
        job_data = await redis_client.get_job(job_id)
        if job_data:
            # Redact sensitive fields
            safe_job_data = {
                k: v for k, v in job_data.items()
                if not any(s in k.lower() for s in ["token", "key", "secret", "password"])
            }
            job_json = json.dumps(safe_job_data, indent=2, default=str)
            zf.writestr(f"{job_id}/metadata.json", job_json)
            bundle_contents.append("metadata.json")

        # 2. Job log file
        log_path = get_job_log_path(job_id)
        if log_path and log_path.exists():
            log_content = log_path.read_text(encoding="utf-8")
            # Redact sensitive data
            log_content = redact_sensitive(log_content)
            zf.writestr(f"{job_id}/events.jsonl", log_content)
            bundle_contents.append("events.jsonl")

        # 3. Service logs (last 1000 lines each)
        for service in ["api", "worker"]:
            service_log = config.log_dir / service / "latest" / f"{service}.log"
            if service_log.exists():
                try:
                    with open(service_log, "r", encoding="utf-8") as f:
                        lines = f.readlines()[-1000:]
                    content = redact_sensitive("".join(lines))
                    zf.writestr(f"{job_id}/service_logs/{service}.log", content)
                    bundle_contents.append(f"service_logs/{service}.log")
                except Exception as e:
                    logger.warning(f"Failed to include {service} logs: {e}")

        # 4. Sample images
        samples_dir = get_job_samples_dir(job_id)
        if samples_dir.exists():
            for sample_file in samples_dir.glob("*.png"):
                zf.write(sample_file, f"{job_id}/samples/{sample_file.name}")
                bundle_contents.append(f"samples/{sample_file.name}")

        # 5. Environment snapshot (heavily redacted)
        env_snapshot = {
            "ISENGARD_MODE": os.getenv("ISENGARD_MODE", "unknown"),
            "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
            "USE_REDIS": os.getenv("USE_REDIS", "false"),
            "volume_root": str(config.volume_root),
            "log_dir": str(config.log_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        zf.writestr(f"{job_id}/environment.json", json.dumps(env_snapshot, indent=2))
        bundle_contents.append("environment.json")

        # 6. Directory tree
        tree_lines = [f"Debug Bundle for {job_id}", "=" * 40, ""]
        tree_lines.append("Contents:")
        for item in bundle_contents:
            tree_lines.append(f"  - {item}")
        tree_lines.append("")
        tree_lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        zf.writestr(f"{job_id}/README.txt", "\n".join(tree_lines))

    # Prepare response
    zip_buffer.seek(0)
    bundle_name = f"{job_id}_debug.zip"

    logger.info(
        "Debug bundle created",
        extra={
            "event": "debug_bundle.created",
            "job_id": job_id,
            "contents": bundle_contents,
        }
    )

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{bundle_name}"'
        }
    )


# ============================================
# Job Summary Endpoint
# ============================================

@router.get("/{job_id}/summary")
async def get_job_summary(job_id: str):
    """
    Get a summary of a job including:
    - Current status and progress
    - Key metrics (loss, step, ETA)
    - Artifact counts
    - First error (if failed)

    Useful for quick status checks without streaming.
    """
    validate_job_id(job_id)

    job_data = await redis_client.get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    # Count artifacts
    samples_dir = get_job_samples_dir(job_id)
    sample_count = len(list(samples_dir.glob("*.png"))) if samples_dir.exists() else 0

    # Find first error in logs
    first_error = None
    log_path = get_job_log_path(job_id)
    if log_path and log_path.exists() and job_data.get("status") == "failed":
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("level") == "ERROR":
                            first_error = {
                                "timestamp": entry.get("ts"),
                                "message": entry.get("msg"),
                                "event": entry.get("event"),
                            }
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

    summary = {
        "job_id": job_id,
        "status": job_data.get("status"),
        "progress": job_data.get("progress", 0),
        "current_step": job_data.get("current_step", 0),
        "total_steps": job_data.get("total_steps", 0),
        "created_at": job_data.get("created_at"),
        "started_at": job_data.get("started_at"),
        "completed_at": job_data.get("completed_at"),
        "artifacts": {
            "samples": sample_count,
            "has_log": log_path is not None and log_path.exists(),
            "has_model": job_data.get("output_path") is not None,
        },
        "first_error": first_error,
        "error_message": job_data.get("error_message"),
    }

    return summary
