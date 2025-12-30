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


class JobLogger:
    """
    Logger that writes to both service log and job-specific JSONL file.

    Each job gets a dedicated log file at:
        VOLUME_ROOT/logs/jobs/{job_id}.jsonl

    This allows:
    - Per-job log isolation for debugging
    - Log file download via API endpoint
    - Complete job trace with correlation ID

    Example:
        job_logger = JobLogger("train-abc123")
        job_logger.info("Starting training", event="job.start", steps=1000)
        job_logger.error("Training failed", event="job.error", reason="OOM")
    """

    def __init__(self, job_id: str, service: str = "worker"):
        """
        Initialize job logger.

        Args:
            job_id: Unique job identifier
            service: Service name for service log (default: worker)
        """
        self.job_id = job_id
        self.service = service
        self._service_logger = get_logger(f"{service}.job.{job_id}", service)

        # Job log path from config (single source of truth)
        config = get_global_config()
        self.job_log_dir = config.volume_root / "logs" / "jobs"
        self.job_log_dir.mkdir(parents=True, exist_ok=True)
        self.job_log_path = self.job_log_dir / f"{job_id}.jsonl"

    def _build_record(
        self,
        level: str,
        msg: str,
        event: str | None,
        fields: dict,
    ) -> dict:
        """Build a log record dictionary."""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": level,
            "service": self.service,
            "job_id": self.job_id,
            "msg": msg,
        }

        # Add correlation ID if present
        correlation_id = get_correlation_id()
        if correlation_id:
            record["correlation_id"] = correlation_id

        # Add event if provided
        if event:
            record["event"] = event

        # Add extra fields if provided
        if fields:
            record["fields"] = fields

        return record

    def _append_to_job_log(self, record: dict) -> None:
        """
        Append record to job log file with file locking.

        Uses simple file-based locking for concurrent writes.
        """
        # Filter out None values for cleaner output
        clean_record = {k: v for k, v in record.items() if v is not None}

        # Apply redaction before writing
        line = redact_sensitive(json.dumps(clean_record, default=str))

        # Simple append with newline
        # Note: For production with high concurrency, consider using portalocker
        try:
            with open(self.job_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            # Don't fail the job if logging fails
            self._service_logger.warning(
                f"Failed to write to job log: {e}",
                extra={"event": "logging.error", "job_id": self.job_id}
            )

    def info(self, msg: str, *, event: str | None = None, **fields) -> None:
        """Log an INFO level message."""
        record = self._build_record("INFO", msg, event, fields)
        self._service_logger.info(msg, extra={"event": event, "job_id": self.job_id, **fields})
        self._append_to_job_log(record)

    def warning(self, msg: str, *, event: str | None = None, **fields) -> None:
        """Log a WARNING level message."""
        record = self._build_record("WARNING", msg, event, fields)
        self._service_logger.warning(msg, extra={"event": event, "job_id": self.job_id, **fields})
        self._append_to_job_log(record)

    def error(self, msg: str, *, event: str | None = None, **fields) -> None:
        """Log an ERROR level message."""
        record = self._build_record("ERROR", msg, event, fields)
        self._service_logger.error(msg, extra={"event": event, "job_id": self.job_id, **fields})
        self._append_to_job_log(record)

    def debug(self, msg: str, *, event: str | None = None, **fields) -> None:
        """Log a DEBUG level message."""
        record = self._build_record("DEBUG", msg, event, fields)
        self._service_logger.debug(msg, extra={"event": event, "job_id": self.job_id, **fields})
        self._append_to_job_log(record)

    def get_log_path(self) -> Path:
        """Get the path to this job's log file."""
        return self.job_log_path


def get_job_log_path(job_id: str) -> Path | None:
    """
    Get the log file path for a job.

    Returns None if the log file doesn't exist.
    """
    config = get_global_config()
    log_path = config.volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
    return log_path if log_path.exists() else None


def get_job_artifacts_dir(job_id: str) -> Path:
    """
    Get the artifacts directory for a job.

    Creates the directory if it doesn't exist.
    """
    config = get_global_config()
    artifacts_dir = config.volume_root / "artifacts" / "jobs" / job_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def get_job_samples_dir(job_id: str) -> Path:
    """
    Get the samples directory for a job.

    Creates the directory if it doesn't exist.
    """
    samples_dir = get_job_artifacts_dir(job_id) / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    return samples_dir


def get_job_checkpoints_dir(job_id: str) -> Path:
    """
    Get the checkpoints directory for a job.

    Creates the directory if it doesn't exist.
    """
    checkpoints_dir = get_job_artifacts_dir(job_id) / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    return checkpoints_dir


class TrainingJobLogger(JobLogger):
    """
    Enhanced job logger specifically for training jobs.

    Adds:
    - Progress event emission to event bus
    - Sample image tracking
    - Subprocess output capture
    - GPU metrics logging
    """

    def __init__(self, job_id: str, correlation_id: str | None = None, service: str = "worker"):
        super().__init__(job_id, service)
        self.correlation_id = correlation_id
        self._samples: list[str] = []
        self._last_step = 0
        self._total_steps = 0
        self._start_time: datetime | None = None

    def set_total_steps(self, total: int) -> None:
        """Set the total number of training steps."""
        self._total_steps = total

    def start(self, total_steps: int, config_summary: dict | None = None) -> None:
        """Log training start."""
        self._total_steps = total_steps
        self._start_time = datetime.now(timezone.utc)

        self.info(
            "Training started",
            event="training.start",
            total_steps=total_steps,
            config=config_summary or {},
        )

    def step(
        self,
        current_step: int,
        loss: float | None = None,
        lr: float | None = None,
        message: str | None = None,
    ) -> None:
        """Log a training step."""
        self._last_step = current_step
        progress = (current_step / self._total_steps * 100) if self._total_steps > 0 else 0

        # Calculate ETA
        eta_seconds = None
        if self._start_time and current_step > 0:
            elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            steps_per_second = current_step / elapsed
            remaining_steps = self._total_steps - current_step
            if steps_per_second > 0:
                eta_seconds = int(remaining_steps / steps_per_second)

        step_msg = message or f"Step {current_step}/{self._total_steps}"

        extra = {
            "step": current_step,
            "total_steps": self._total_steps,
            "progress_pct": round(progress, 2),
        }
        if loss is not None:
            extra["loss"] = round(loss, 6)
        if lr is not None:
            extra["lr"] = lr
        if eta_seconds is not None:
            extra["eta_seconds"] = eta_seconds

        self.debug(step_msg, event="training.step", **extra)

    def sample_generated(self, sample_path: str | Path, step: int) -> None:
        """Log sample image generation."""
        path_str = str(sample_path)
        self._samples.append(path_str)

        self.info(
            f"Sample generated at step {step}",
            event="training.sample",
            sample_path=path_str,
            step=step,
            sample_index=len(self._samples),
        )

    def checkpoint_saved(self, checkpoint_path: str | Path, step: int) -> None:
        """Log checkpoint save."""
        self.info(
            f"Checkpoint saved at step {step}",
            event="training.checkpoint",
            checkpoint_path=str(checkpoint_path),
            step=step,
        )

    def subprocess_output(self, line: str, stream: str = "stdout") -> None:
        """Log subprocess output line."""
        event = f"subprocess.{stream}"
        level = "DEBUG" if stream == "stdout" else "WARNING"

        record = self._build_record(level, line.rstrip(), event, {"stream": stream})
        self._append_to_job_log(record)

        # Also log to service logger at appropriate level
        if stream == "stderr":
            self._service_logger.warning(line.rstrip(), extra={"event": event, "job_id": self.job_id})
        else:
            self._service_logger.debug(line.rstrip(), extra={"event": event, "job_id": self.job_id})

    def complete(self, output_path: str | Path, training_time_seconds: float, final_loss: float | None = None) -> None:
        """Log training completion."""
        self.info(
            "Training completed successfully",
            event="training.complete",
            output_path=str(output_path),
            training_time_seconds=round(training_time_seconds, 2),
            final_loss=round(final_loss, 6) if final_loss else None,
            samples_generated=len(self._samples),
            total_steps=self._total_steps,
        )

    def fail(self, error: str, error_type: str | None = None, stack_trace: str | None = None) -> None:
        """Log training failure with full context."""
        extra = {
            "error": error,
            "step": self._last_step,
            "total_steps": self._total_steps,
        }
        if error_type:
            extra["error_type"] = error_type
        if stack_trace:
            extra["stack_trace"] = stack_trace

        self.error("Training failed", event="training.failed", **extra)

    def get_samples(self) -> list[str]:
        """Get list of generated sample paths."""
        return self._samples.copy()
