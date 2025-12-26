"""
Isengard Structured Logging Module

Provides JSON-formatted structured logging with:
- Correlation ID propagation
- Secret/path redaction
- Log rotation (latest/archive structure)
- File and stdout output
- Service-based log organization
- Event type support

See packages/shared/observability/LOGGING_SPEC.md for full specification.
"""

import json
import logging
import os
import re
import shutil
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from .config import get_global_config

# Context variable for correlation ID
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Session ID for this process run
_session_id: str | None = None


def get_correlation_id() -> str | None:
    """Get the current correlation ID from context."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in context."""
    _correlation_id.set(correlation_id)


def get_session_id() -> str:
    """Get the session ID for this process run."""
    global _session_id
    if _session_id is None:
        _session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _session_id


def with_correlation_id(func: Callable) -> Callable:
    """
    Decorator that extracts correlation ID from request headers
    and sets it in context for the duration of the function.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Try to get correlation ID from request if available
        request = kwargs.get("request")
        if request and hasattr(request, "headers"):
            correlation_id = request.headers.get("X-Correlation-ID")
            if correlation_id:
                set_correlation_id(correlation_id)
        return await func(*args, **kwargs)
    return wrapper


# Redaction patterns - compile once for performance
REDACTION_PATTERNS = [
    (re.compile(r"hf_[A-Za-z0-9]+"), "hf_***REDACTED***"),
    (re.compile(r"sk-[A-Za-z0-9-]+"), "sk-***REDACTED***"),  # Include hyphens for sk-proj-...
    (re.compile(r"ghp_[A-Za-z0-9]+"), "ghp_***REDACTED***"),
    (re.compile(r"rpa_[A-Za-z0-9]+"), "rpa_***REDACTED***"),
    (re.compile(r"/Users/[^/]+/"), "/[HOME]/"),
    (re.compile(r"/home/[^/]+/"), "/[HOME]/"),
    (re.compile(r"token=[^&\s]+"), "token=***"),
    (re.compile(r"password=[^\s&]+"), "password=***"),
    (re.compile(r"api_key=[^\s&]+"), "api_key=***"),
    (re.compile(r'"password"\s*:\s*"[^"]+"'), '"password": "***"'),
    (re.compile(r'"token"\s*:\s*"[^"]+"'), '"token": "***"'),
    (re.compile(r'"api_key"\s*:\s*"[^"]+"'), '"api_key": "***"'),
]


def redact_sensitive(text: str) -> str:
    """Apply all redaction patterns to text."""
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.000Z",
        "level": "INFO",
        "service": "api",
        "correlation_id": "req-abc123",
        "logger": "api.routes.training",
        "message": "Training job started",
        "event": "job.start",
        "context": {...}
    }
    """

    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        # Build base log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if present
        correlation_id = get_correlation_id()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        # Add event type if provided
        if hasattr(record, "event") and record.event:
            log_entry["event"] = record.event

        # Add extra context if provided
        if hasattr(record, "context") and record.context:
            log_entry["context"] = record.context

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Convert to JSON and apply redaction
        json_str = json.dumps(log_entry, default=str)
        return redact_sensitive(json_str)


class ContextAdapter(logging.LoggerAdapter):
    """Logger adapter that handles context and event fields."""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = kwargs.get("extra", {})
        new_extra = {}

        # Extract event if provided
        if "event" in extra:
            new_extra["event"] = extra.pop("event")

        # Remaining extra fields go into context
        if extra:
            new_extra["context"] = extra

        kwargs["extra"] = new_extra
        return msg, kwargs


def _get_service_log_dirs(service: str) -> tuple[Path, Path, Path]:
    """
    Get log directory paths for a service.

    Returns:
        Tuple of (base_dir, latest_dir, archive_dir)
    """
    config = get_global_config()
    base_dir = config.log_dir / service
    latest_dir = base_dir / "latest"
    archive_dir = base_dir / "archive"
    return base_dir, latest_dir, archive_dir


def rotate_logs(service: str) -> Path | None:
    """
    Archive previous session logs and prepare for new session.

    If latest/ exists and contains files:
    1. Move latest/ to archive/{timestamp}/
    2. Create new empty latest/

    Args:
        service: Service name (api, worker, web)

    Returns:
        Path to archive directory if rotation occurred, None otherwise
    """
    base_dir, latest_dir, archive_dir = _get_service_log_dirs(service)

    # Ensure base directories exist
    base_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Check if latest has content to archive
    if latest_dir.exists() and any(latest_dir.iterdir()):
        # Generate archive timestamp
        archive_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dest = archive_dir / archive_timestamp

        # Move latest to archive
        shutil.move(str(latest_dir), str(archive_dest))

        # Create fresh latest directory
        latest_dir.mkdir(parents=True, exist_ok=True)

        return archive_dest

    # Ensure latest exists even if no rotation
    latest_dir.mkdir(parents=True, exist_ok=True)
    return None


def _get_log_file_path(service: str, filename: str | None = None) -> Path:
    """
    Get log file path within latest/ directory.

    Args:
        service: Service name
        filename: Optional filename (defaults to {service}.log)

    Returns:
        Path to log file
    """
    _, latest_dir, _ = _get_service_log_dirs(service)
    latest_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = f"{service}.log"

    return latest_dir / filename


def get_subprocess_log_dir(service: str = "worker") -> Path:
    """
    Get directory for subprocess stdout/stderr logs.

    Returns:
        Path to subprocess log directory (created if needed)
    """
    _, latest_dir, _ = _get_service_log_dirs(service)
    subprocess_dir = latest_dir / "subprocess"
    subprocess_dir.mkdir(parents=True, exist_ok=True)
    return subprocess_dir


def get_subprocess_log_paths(job_id: str, service: str = "worker") -> tuple[Path, Path]:
    """
    Get stdout and stderr log file paths for a subprocess job.

    Args:
        job_id: The job identifier
        service: Service name (default: worker)

    Returns:
        Tuple of (stdout_path, stderr_path)
    """
    subprocess_dir = get_subprocess_log_dir(service)
    stdout_path = subprocess_dir / f"{job_id}.stdout.log"
    stderr_path = subprocess_dir / f"{job_id}.stderr.log"
    return stdout_path, stderr_path


# Cache for loggers
_loggers: dict[str, ContextAdapter] = {}


def get_logger(name: str, service: str | None = None) -> ContextAdapter:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (e.g., 'api.routes.training')
        service: Service name for log organization. If not provided,
                 derived from logger name (first component).

    Returns:
        ContextAdapter wrapping configured logger

    Example:
        logger = get_logger("api.routes.training")
        logger.info("Job started", extra={"event": "job.start", "job_id": "123"})
    """
    if name in _loggers:
        return _loggers[name]

    # Derive service from name if not provided
    if service is None:
        service = name.split(".")[0]

    config = get_global_config()

    # Create base logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.log_level.upper()))
    logger.handlers.clear()  # Remove any existing handlers

    # Create structured formatter
    formatter = StructuredFormatter(service)

    # Add stdout handler if configured
    if config.log_to_stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        logger.addHandler(stdout_handler)

    # Add file handler if configured
    if config.log_to_file:
        log_file = _get_log_file_path(service)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    # Wrap with adapter and cache
    adapter = ContextAdapter(logger, {})
    _loggers[name] = adapter

    return adapter


def configure_logging(service: str, rotate: bool = True) -> None:
    """
    Configure logging for a service.

    Should be called once at service startup. Optionally rotates
    previous session logs to archive.

    Args:
        service: Service name (api, worker, web)
        rotate: Whether to archive previous logs (default: True)
    """
    config = get_global_config()

    # Rotate logs if requested
    archive_path = None
    if rotate:
        archive_path = rotate_logs(service)

    # Configure root logger to prevent noise
    root = logging.getLogger()
    root.setLevel(logging.WARNING)

    # Log startup message
    logger = get_logger(f"{service}.startup", service)

    startup_context = {
        "mode": config.mode,
        "log_level": config.log_level,
        "session_id": get_session_id(),
    }

    if archive_path:
        startup_context["previous_logs_archived_to"] = str(archive_path)

    logger.info(
        f"Logging configured for {service}",
        extra={
            "event": "system.startup",
            **startup_context,
        }
    )


def log_request_start(
    logger: ContextAdapter,
    method: str,
    path: str,
    correlation_id: str,
    client_ip: str | None = None,
) -> None:
    """Helper to log request start consistently."""
    set_correlation_id(correlation_id)
    logger.info(
        f"{method} {path}",
        extra={
            "event": "request.start",
            "method": method,
            "path": path,
            "client_ip": client_ip or "unknown",
        }
    )


def log_request_end(
    logger: ContextAdapter,
    status_code: int,
    duration_ms: float,
) -> None:
    """Helper to log request end consistently."""
    logger.info(
        "Request completed",
        extra={
            "event": "request.end",
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
        }
    )


def log_job_event(
    logger: ContextAdapter,
    event: str,
    job_id: str,
    message: str,
    **extra_context,
) -> None:
    """Helper to log job events consistently."""
    logger.info(
        message,
        extra={
            "event": event,
            "job_id": job_id,
            **extra_context,
        }
    )
