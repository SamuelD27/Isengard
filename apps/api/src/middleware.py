"""
Isengard API Middleware

Custom middleware for request processing with comprehensive logging.
Includes UELR (User End Log Register) support for end-to-end tracing.
"""

import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from packages.shared.src.logging import (
    set_correlation_id,
    get_logger,
    log_request_start,
    log_request_end,
)

logger = get_logger("api.middleware")

# Context variable for interaction ID (UELR)
_interaction_id: ContextVar[str | None] = ContextVar("interaction_id", default=None)


def get_interaction_id() -> str | None:
    """Get the current interaction ID from context."""
    return _interaction_id.get()


def set_interaction_id(interaction_id: str | None) -> None:
    """Set the interaction ID in context."""
    _interaction_id.set(interaction_id)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts or generates correlation ID for each request.

    The correlation ID is:
    1. Extracted from X-Correlation-ID header if present
    2. Generated as UUID if not present
    3. Set in context for logging
    4. Added to response headers

    Also handles:
    - Request/response timing
    - Structured event logging
    - Client IP extraction
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Start timing
        start_time = time.perf_counter()

        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = f"req-{uuid.uuid4().hex[:12]}"

        # Extract interaction ID (UELR) if present
        interaction_id = request.headers.get("X-Interaction-ID")

        # Set in context for logging
        set_correlation_id(correlation_id)
        set_interaction_id(interaction_id)

        # Extract client IP (handle proxy headers)
        client_ip = request.headers.get("X-Forwarded-For")
        if client_ip:
            client_ip = client_ip.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        # Log request start with event type (include interaction_id if present)
        extra_context = {}
        if interaction_id:
            extra_context["interaction_id"] = interaction_id

        log_request_start(
            logger,
            method=request.method,
            path=request.url.path,
            correlation_id=correlation_id,
            client_ip=client_ip,
            **extra_context,
        )

        # Additional request details at DEBUG level
        if request.query_params:
            logger.debug(
                "Request query parameters",
                extra={
                    "query_params": dict(request.query_params),
                }
            )

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Calculate duration even on error
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log error
            logger.error(
                f"Request failed: {str(e)}",
                extra={
                    "event": "request.error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True,
            )
            raise

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Add correlation ID to response
        response.headers["X-Correlation-ID"] = correlation_id

        # Add interaction ID to response if present
        if interaction_id:
            response.headers["X-Interaction-ID"] = interaction_id

        # Log request end with timing
        log_request_end(
            logger,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response
