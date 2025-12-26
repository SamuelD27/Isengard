"""
Isengard API Middleware

Custom middleware for request processing with comprehensive logging.
"""

import time
import uuid

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

        # Set in context for logging
        set_correlation_id(correlation_id)

        # Extract client IP (handle proxy headers)
        client_ip = request.headers.get("X-Forwarded-For")
        if client_ip:
            client_ip = client_ip.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        # Log request start with event type
        log_request_start(
            logger,
            method=request.method,
            path=request.url.path,
            correlation_id=correlation_id,
            client_ip=client_ip,
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

        # Log request end with timing
        log_request_end(
            logger,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response
