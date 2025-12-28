"""
UELR (User End Log Register) API Routes

Provides endpoints for:
- Creating and completing interactions
- Appending steps to interactions
- Listing and querying interactions
- Downloading interaction bundles with related logs
"""

import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Literal
from enum import Enum

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from packages.shared.src.logging import get_logger, get_correlation_id
from packages.shared.src.config import get_global_config

router = APIRouter()
logger = get_logger("api.uelr")

# Configuration
UELR_LOG_DIR = Path(os.getenv("UELR_LOG_DIR", "./logs/uelr"))
MAX_INTERACTIONS = 1000
MAX_STEPS_PER_INTERACTION = 500
RETENTION_DAYS = 30

# Ensure directories exist
UELR_LOG_DIR.mkdir(parents=True, exist_ok=True)
(UELR_LOG_DIR / "interactions").mkdir(exist_ok=True)
(UELR_LOG_DIR / "index").mkdir(exist_ok=True)


# ============ Pydantic Models ============


class StepType(str, Enum):
    UI_ACTION_START = "UI_ACTION_START"
    UI_ACTION_END = "UI_ACTION_END"
    UI_STATE_CHANGE = "UI_STATE_CHANGE"
    NETWORK_REQUEST_START = "NETWORK_REQUEST_START"
    NETWORK_REQUEST_END = "NETWORK_REQUEST_END"
    SSE_CONNECT = "SSE_CONNECT"
    SSE_MESSAGE = "SSE_MESSAGE"
    SSE_CLOSE = "SSE_CLOSE"
    SSE_ERROR = "SSE_ERROR"
    BACKEND_ROUTE_START = "BACKEND_ROUTE_START"
    BACKEND_ROUTE_END = "BACKEND_ROUTE_END"
    BACKEND_ERROR = "BACKEND_ERROR"
    JOB_ENQUEUE = "JOB_ENQUEUE"
    JOB_START = "JOB_START"
    JOB_PROGRESS = "JOB_PROGRESS"
    JOB_END = "JOB_END"
    WORKER_TASK_START = "WORKER_TASK_START"
    WORKER_TASK_END = "WORKER_TASK_END"
    PLUGIN_CALL = "PLUGIN_CALL"
    PLUGIN_RESPONSE = "PLUGIN_RESPONSE"
    COMFYUI_REQUEST = "COMFYUI_REQUEST"
    COMFYUI_RESPONSE = "COMFYUI_RESPONSE"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class StepComponent(str, Enum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    WORKER = "worker"
    PLUGIN = "plugin"
    COMFYUI = "comfyui"
    REDIS = "redis"


class StepStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class UELRStep(BaseModel):
    step_id: str
    interaction_id: str
    correlation_id: str
    type: StepType
    component: StepComponent
    timestamp: str
    duration_ms: Optional[float] = None
    message: str
    status: StepStatus
    details: Optional[dict] = None


class UELRInteraction(BaseModel):
    interaction_id: str
    correlation_id: str
    action_name: str
    action_category: Optional[str] = None
    started_at: str
    ended_at: Optional[str] = None
    duration_ms: Optional[float] = None
    status: StepStatus = StepStatus.PENDING
    error_summary: Optional[str] = None
    page: Optional[str] = None
    user_agent: Optional[str] = None
    step_count: int = 0
    error_count: int = 0
    steps: Optional[list[UELRStep]] = None


class CreateInteractionRequest(BaseModel):
    interaction_id: str
    correlation_id: str
    action_name: str
    action_category: Optional[str] = None
    page: Optional[str] = None
    user_agent: Optional[str] = None


class AppendStepsRequest(BaseModel):
    interaction_id: str
    steps: list[dict] = Field(default_factory=list)


class CompleteInteractionRequest(BaseModel):
    interaction_id: str
    status: StepStatus
    error_summary: Optional[str] = None


class ListInteractionsResponse(BaseModel):
    interactions: list[UELRInteraction]
    total: int
    has_more: bool


# ============ Redaction ============


REDACTION_PATTERNS = [
    (re.compile(r"hf_[A-Za-z0-9]+"), "hf_***REDACTED***"),
    (re.compile(r"sk-[A-Za-z0-9-]+"), "sk-***REDACTED***"),
    (re.compile(r"ghp_[A-Za-z0-9]+"), "ghp_***REDACTED***"),
    (re.compile(r"rpa_[A-Za-z0-9]+"), "rpa_***REDACTED***"),
    (re.compile(r"Bearer [A-Za-z0-9._-]+", re.IGNORECASE), "Bearer ***REDACTED***"),
    (re.compile(r"token=[^&\s]+", re.IGNORECASE), "token=***"),
    (re.compile(r"password=[^\s&]+", re.IGNORECASE), "password=***"),
    (re.compile(r"api[_-]?key=[^&\s]+", re.IGNORECASE), "api_key=***"),
    (re.compile(r"/Users/[^/]+/"), "/[HOME]/"),
    (re.compile(r"/home/[^/]+/"), "/[HOME]/"),
]

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "credential",
    "auth",
    "bearer",
    "hf_token",
    "runpod_api_key",
    "github_token",
    "cloudflare_api_token",
}


def redact_string(value: str) -> str:
    """Apply redaction patterns to a string."""
    result = value
    for pattern, replacement in REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: dict, depth: int = 0) -> dict:
    """Recursively redact sensitive data from a dictionary."""
    if depth > 10:
        return {"_truncated": True}

    result = {}
    for key, value in data.items():
        lower_key = key.lower()
        if any(sensitive in lower_key for sensitive in SENSITIVE_KEYS):
            result[key] = "***REDACTED***"
        elif isinstance(value, str):
            result[key] = redact_string(value)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, depth + 1)
        elif isinstance(value, list):
            result[key] = [
                redact_dict(item, depth + 1) if isinstance(item, dict)
                else redact_string(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


# ============ Persistence Layer ============


def _get_interaction_path(interaction_id: str) -> Path:
    """Get the file path for an interaction."""
    # Use date-based subdirectories for better organization
    return UELR_LOG_DIR / "interactions" / f"{interaction_id}.jsonl"


def _get_index_path() -> Path:
    """Get the index file path."""
    return UELR_LOG_DIR / "index" / "interactions.jsonl"


def _load_interaction(interaction_id: str) -> Optional[UELRInteraction]:
    """Load an interaction from disk."""
    path = _get_interaction_path(interaction_id)
    if not path.exists():
        return None

    interaction_data = None
    steps = []

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if data.get("_type") == "interaction":
                interaction_data = data
            elif data.get("_type") == "step":
                steps.append(data)

    if not interaction_data:
        return None

    # Remove internal fields
    interaction_data.pop("_type", None)

    return UELRInteraction(
        **interaction_data,
        steps=[UELRStep(**{k: v for k, v in s.items() if k != "_type"}) for s in steps],
    )


def _save_interaction(interaction: UELRInteraction) -> None:
    """Save an interaction header to disk."""
    path = _get_interaction_path(interaction.interaction_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write interaction header (will be first line)
    data = interaction.model_dump(exclude={"steps"})
    data["_type"] = "interaction"

    # If file exists, read existing steps and rewrite
    existing_steps = []
    if path.exists():
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("_type") == "step":
                    existing_steps.append(entry)

    # Rewrite file with updated header + existing steps
    with open(path, "w") as f:
        f.write(json.dumps(data) + "\n")
        for step in existing_steps:
            f.write(json.dumps(step) + "\n")

    # Update index
    _update_index(interaction)


def _append_steps(interaction_id: str, steps: list[UELRStep]) -> None:
    """Append steps to an interaction file."""
    path = _get_interaction_path(interaction_id)

    if not path.exists():
        logger.warning(f"Interaction file not found for {interaction_id}")
        return

    with open(path, "a") as f:
        for step in steps:
            data = step.model_dump()
            data["_type"] = "step"
            # Ensure details are redacted
            if data.get("details"):
                data["details"] = redact_dict(data["details"])
            f.write(json.dumps(data) + "\n")


def _update_index(interaction: UELRInteraction) -> None:
    """Update the index with interaction metadata."""
    index_path = _get_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing index
    index: dict[str, dict] = {}
    if index_path.exists():
        with open(index_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                index[entry["interaction_id"]] = entry

    # Update entry
    index[interaction.interaction_id] = {
        "interaction_id": interaction.interaction_id,
        "correlation_id": interaction.correlation_id,
        "action_name": interaction.action_name,
        "action_category": interaction.action_category,
        "started_at": interaction.started_at,
        "ended_at": interaction.ended_at,
        "duration_ms": interaction.duration_ms,
        "status": interaction.status.value if isinstance(interaction.status, StepStatus) else interaction.status,
        "error_summary": interaction.error_summary,
        "page": interaction.page,
        "step_count": interaction.step_count,
        "error_count": interaction.error_count,
    }

    # Enforce max interactions (remove oldest)
    if len(index) > MAX_INTERACTIONS:
        sorted_entries = sorted(index.values(), key=lambda x: x["started_at"], reverse=True)
        index = {e["interaction_id"]: e for e in sorted_entries[:MAX_INTERACTIONS]}

        # Delete removed interaction files
        removed = set(index.keys()) - {e["interaction_id"] for e in sorted_entries[:MAX_INTERACTIONS]}
        for iid in removed:
            path = _get_interaction_path(iid)
            if path.exists():
                path.unlink()

    # Rewrite index
    with open(index_path, "w") as f:
        for entry in sorted(index.values(), key=lambda x: x["started_at"], reverse=True):
            f.write(json.dumps(entry) + "\n")


def _list_interactions(
    limit: int = 50,
    offset: int = 0,
    action_name: Optional[str] = None,
    status: Optional[str] = None,
    correlation_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> tuple[list[dict], int]:
    """List interactions from the index."""
    index_path = _get_index_path()

    if not index_path.exists():
        return [], 0

    entries = []
    with open(index_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)

            # Apply filters
            if action_name and action_name.lower() not in entry.get("action_name", "").lower():
                continue
            if status and entry.get("status") != status:
                continue
            if correlation_id and entry.get("correlation_id") != correlation_id:
                continue
            if from_date and entry.get("started_at", "") < from_date:
                continue
            if to_date and entry.get("started_at", "") > to_date:
                continue

            entries.append(entry)

    total = len(entries)
    return entries[offset:offset + limit], total


# ============ API Endpoints ============


@router.post("/interactions", status_code=201)
async def create_interaction(request: CreateInteractionRequest) -> UELRInteraction:
    """Create a new interaction."""
    # Check if already exists
    existing = _load_interaction(request.interaction_id)
    if existing:
        # Return existing (idempotent)
        return existing

    interaction = UELRInteraction(
        interaction_id=request.interaction_id,
        correlation_id=request.correlation_id,
        action_name=request.action_name,
        action_category=request.action_category,
        started_at=datetime.utcnow().isoformat() + "Z",
        page=request.page,
        user_agent=request.user_agent,
        step_count=0,
        error_count=0,
    )

    _save_interaction(interaction)

    logger.info(
        f"Created UELR interaction: {request.action_name}",
        extra={
            "event": "uelr.interaction.created",
            "interaction_id": request.interaction_id,
            "action_name": request.action_name,
        },
    )

    return interaction


@router.post("/interactions/{interaction_id}/steps")
async def append_steps(interaction_id: str, request: AppendStepsRequest) -> dict:
    """Append steps to an interaction."""
    interaction = _load_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail=f"Interaction {interaction_id} not found")

    # Convert dict steps to UELRStep objects
    steps = []
    error_count = 0
    for step_data in request.steps:
        # Add interaction_id to step if missing
        step_data["interaction_id"] = interaction_id
        if "correlation_id" not in step_data:
            step_data["correlation_id"] = interaction.correlation_id

        # Redact details
        if step_data.get("details"):
            step_data["details"] = redact_dict(step_data["details"])

        try:
            step = UELRStep(**step_data)
            steps.append(step)
            if step.status == StepStatus.ERROR:
                error_count += 1
        except Exception as e:
            logger.warning(f"Invalid step data: {e}", extra={"step_data": step_data})

    if steps:
        _append_steps(interaction_id, steps)

        # Update interaction counts
        interaction.step_count += len(steps)
        interaction.error_count += error_count
        _save_interaction(interaction)

    logger.debug(
        f"Appended {len(steps)} steps to interaction {interaction_id}",
        extra={
            "event": "uelr.steps.appended",
            "interaction_id": interaction_id,
            "step_count": len(steps),
        },
    )

    return {"appended": len(steps)}


@router.put("/interactions/{interaction_id}/complete")
async def complete_interaction(interaction_id: str, request: CompleteInteractionRequest) -> UELRInteraction:
    """Mark an interaction as complete."""
    interaction = _load_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail=f"Interaction {interaction_id} not found")

    # Update fields
    interaction.status = request.status
    interaction.ended_at = datetime.utcnow().isoformat() + "Z"
    if interaction.started_at:
        try:
            started = datetime.fromisoformat(interaction.started_at.replace("Z", "+00:00"))
            ended = datetime.fromisoformat(interaction.ended_at.replace("Z", "+00:00"))
            interaction.duration_ms = (ended - started).total_seconds() * 1000
        except Exception:
            pass

    if request.error_summary:
        interaction.error_summary = redact_string(request.error_summary)

    _save_interaction(interaction)

    logger.info(
        f"Completed UELR interaction: {interaction.action_name} ({request.status})",
        extra={
            "event": "uelr.interaction.completed",
            "interaction_id": interaction_id,
            "status": request.status.value,
            "duration_ms": interaction.duration_ms,
        },
    )

    # Return without steps for efficiency
    interaction.steps = None
    return interaction


@router.get("/interactions", response_model=ListInteractionsResponse)
async def list_interactions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    action_name: Optional[str] = None,
    status: Optional[str] = None,
    correlation_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> ListInteractionsResponse:
    """List interactions with optional filters."""
    entries, total = _list_interactions(
        limit=limit,
        offset=offset,
        action_name=action_name,
        status=status,
        correlation_id=correlation_id,
        from_date=from_date,
        to_date=to_date,
    )

    interactions = [UELRInteraction(**entry) for entry in entries]

    return ListInteractionsResponse(
        interactions=interactions,
        total=total,
        has_more=offset + len(interactions) < total,
    )


@router.get("/interactions/{interaction_id}")
async def get_interaction(interaction_id: str) -> UELRInteraction:
    """Get a single interaction with all its steps."""
    interaction = _load_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail=f"Interaction {interaction_id} not found")
    return interaction


@router.get("/interactions/{interaction_id}/bundle")
async def download_bundle(
    interaction_id: str,
    include_backend_logs: bool = True,
    include_worker_logs: bool = True,
) -> FileResponse:
    """Download a bundle containing the interaction and related logs."""
    interaction = _load_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail=f"Interaction {interaction_id} not found")

    config = get_global_config()

    # Create temp directory for bundle
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_dir = Path(tmpdir) / f"uelr-bundle-{interaction_id}"
        bundle_dir.mkdir()

        # 1. Save interaction JSON
        interaction_file = bundle_dir / "interaction.json"
        with open(interaction_file, "w") as f:
            json.dump(interaction.model_dump(), f, indent=2, default=str)

        # 2. Collect related backend logs
        if include_backend_logs:
            backend_logs = []
            api_log_dir = Path("logs/api/latest")
            if api_log_dir.exists():
                for log_file in api_log_dir.glob("*.log"):
                    try:
                        with open(log_file, "r") as f:
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    entry = json.loads(line)
                                    # Match by correlation_id or interaction_id
                                    if (
                                        entry.get("correlation_id") == interaction.correlation_id
                                        or entry.get("context", {}).get("interaction_id") == interaction_id
                                    ):
                                        backend_logs.append(entry)
                                except json.JSONDecodeError:
                                    pass
                    except Exception as e:
                        logger.warning(f"Failed to read log file {log_file}: {e}")

            if backend_logs:
                backend_file = bundle_dir / "backend_logs.jsonl"
                with open(backend_file, "w") as f:
                    for entry in sorted(backend_logs, key=lambda x: x.get("timestamp", "")):
                        f.write(json.dumps(redact_dict(entry)) + "\n")

        # 3. Collect related worker logs
        if include_worker_logs:
            worker_logs = []
            worker_log_dir = Path("logs/worker/latest")
            if worker_log_dir.exists():
                for log_file in worker_log_dir.glob("*.log"):
                    try:
                        with open(log_file, "r") as f:
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    entry = json.loads(line)
                                    if entry.get("correlation_id") == interaction.correlation_id:
                                        worker_logs.append(entry)
                                except json.JSONDecodeError:
                                    pass
                    except Exception as e:
                        logger.warning(f"Failed to read log file {log_file}: {e}")

            if worker_logs:
                worker_file = bundle_dir / "worker_logs.jsonl"
                with open(worker_file, "w") as f:
                    for entry in sorted(worker_logs, key=lambda x: x.get("timestamp", "")):
                        f.write(json.dumps(redact_dict(entry)) + "\n")

        # 4. Create zip file
        zip_path = Path(tmpdir) / f"uelr-bundle-{interaction_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in bundle_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(bundle_dir))

        # 5. Return the zip file
        # Copy to a location that persists after the temp dir is deleted
        final_path = Path(tmpdir).parent / f"uelr-bundle-{interaction_id}.zip"
        shutil.copy(zip_path, final_path)

        return FileResponse(
            path=final_path,
            filename=f"uelr-bundle-{interaction_id}.zip",
            media_type="application/zip",
        )


@router.delete("/interactions/{interaction_id}")
async def delete_interaction(interaction_id: str) -> dict:
    """Delete an interaction and its steps."""
    path = _get_interaction_path(interaction_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Interaction {interaction_id} not found")

    path.unlink()

    # Update index
    index_path = _get_index_path()
    if index_path.exists():
        entries = []
        with open(index_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry["interaction_id"] != interaction_id:
                    entries.append(entry)

        with open(index_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    logger.info(
        f"Deleted UELR interaction: {interaction_id}",
        extra={
            "event": "uelr.interaction.deleted",
            "interaction_id": interaction_id,
        },
    )

    return {"deleted": True}


@router.post("/cleanup")
async def cleanup_old_interactions(retention_days: int = RETENTION_DAYS) -> dict:
    """Clean up interactions older than retention period."""
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    cutoff_str = cutoff.isoformat() + "Z"

    deleted_count = 0
    index_path = _get_index_path()

    if index_path.exists():
        keep_entries = []
        with open(index_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("started_at", "") >= cutoff_str:
                    keep_entries.append(entry)
                else:
                    # Delete the interaction file
                    iid = entry["interaction_id"]
                    path = _get_interaction_path(iid)
                    if path.exists():
                        path.unlink()
                        deleted_count += 1

        # Rewrite index
        with open(index_path, "w") as f:
            for entry in keep_entries:
                f.write(json.dumps(entry) + "\n")

    logger.info(
        f"Cleaned up {deleted_count} old UELR interactions",
        extra={
            "event": "uelr.cleanup",
            "deleted_count": deleted_count,
            "retention_days": retention_days,
        },
    )

    return {"deleted": deleted_count}
