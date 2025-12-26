"""
Isengard API Middleware

Custom middleware for request processing.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from packages.shared.src.logging import set_correlation_id, get_logger

logger = get_logger("api.middleware")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts or generates correlation ID for each request.

    The correlation ID is:
    1. Extracted from X-Correlation-ID header if present
    2. Generated as UUID if not present
    3. Set in context for logging
    4. Added to response headers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = f"req-{uuid.uuid4().hex[:12]}"

        # Set in context for logging
        set_correlation_id(correlation_id)

        # Log request
        logger.info(
            f"{request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params) if request.query_params else None,
            }
        )

        # Process request
        response = await call_next(request)

        # Add correlation ID to response
        response.headers["X-Correlation-ID"] = correlation_id

        # Log response
        logger.info(
            f"Response {response.status_code}",
            extra={
                "status_code": response.status_code,
                "path": request.url.path,
            }
        )

        return response
