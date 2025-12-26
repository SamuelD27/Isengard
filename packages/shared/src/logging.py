"""
Isengard Structured Logging Module

Provides JSON-formatted structured logging with:
- Correlation ID propagation
- Secret/path redaction
- File and stdout output
- Service-based log organization
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from .config import get_global_config

# Context variable for correlation ID
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Get the current correlation ID from context."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in context."""
    _correlation_id.set(correlation_id)


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
    (re.compile(r"sk-[A-Za-z0-9]+"), "sk-***REDACTED***"),
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
        "context": {...}
    }
    """

    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        # Build base log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if present
        correlation_id = get_correlation_id()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

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
    """Logger adapter that handles context field."""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        # Extract context from extra if provided
        extra = kwargs.get("extra", {})
        if extra:
            # Create a new record attribute for context
            kwargs["extra"] = {"context": extra}
        return msg, kwargs


def _ensure_log_dir(service: str) -> Path:
    """Ensure log directory exists for service."""
    config = get_global_config()
    log_dir = config.log_dir / service
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _get_log_file_path(service: str) -> Path:
    """Get today's log file path for service."""
    log_dir = _ensure_log_dir(service)
    date_str = datetime.now().strftime("%Y-%m-%d")
    return log_dir / f"{date_str}.log"


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
        logger.info("Job started", extra={"job_id": "123"})
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


def configure_logging(service: str) -> None:
    """
    Configure logging for a service.

    Should be called once at service startup.
    """
    config = get_global_config()

    # Ensure log directory exists
    _ensure_log_dir(service)

    # Configure root logger to prevent noise
    root = logging.getLogger()
    root.setLevel(logging.WARNING)

    # Log startup message
    logger = get_logger(f"{service}.startup", service)
    logger.info(
        f"Logging configured for {service}",
        extra={
            "mode": config.mode,
            "log_level": config.log_level,
            "log_dir": str(config.log_dir),
        }
    )
