"""
Simple Rate Limiting

In-memory rate limiter for API endpoints.
For production with multiple instances, use Redis-backed rate limiting.
"""

import time
from collections import defaultdict
from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .logging import get_logger

logger = get_logger("shared.rate_limit")


class RateLimiter:
    """
    Token bucket rate limiter.

    Thread-safe for single instance. For multi-instance deployments,
    use Redis-backed implementation.
    """

    def __init__(self):
        # {key: [(timestamp, count), ...]}
        self._requests: dict[str, list[tuple[float, int]]] = defaultdict(list)

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Identifier for rate limit bucket (e.g., IP address)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (is_allowed, remaining_requests, retry_after_seconds)
        """
        now = time.time()
        window_start = now - window_seconds

        # Clean old entries
        self._requests[key] = [
            (ts, count) for ts, count in self._requests[key]
            if ts > window_start
        ]

        # Count requests in window
        total_requests = sum(count for _, count in self._requests[key])

        if total_requests >= max_requests:
            # Calculate retry-after
            if self._requests[key]:
                oldest = min(ts for ts, _ in self._requests[key])
                retry_after = int(oldest + window_seconds - now) + 1
            else:
                retry_after = window_seconds

            return False, 0, retry_after

        # Record this request
        self._requests[key].append((now, 1))

        remaining = max_requests - total_requests - 1
        return True, remaining, 0

    def clear(self, key: str | None = None) -> None:
        """Clear rate limit data for key or all keys."""
        if key:
            self._requests.pop(key, None)
        else:
            self._requests.clear()


# Global rate limiter instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return _rate_limiter


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For header (set by reverse proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP in the list is the client
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct connection IP
    if request.client:
        return request.client.host

    return "unknown"


def rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60,
    key_func: Callable[[Request], str] | None = None,
):
    """
    Rate limiting decorator for FastAPI endpoints.

    Args:
        max_requests: Maximum requests per window (default: 100)
        window_seconds: Window size in seconds (default: 60)
        key_func: Optional function to extract rate limit key from request.
                  Default uses client IP.

    Usage:
        @router.post("/upload")
        @rate_limit(max_requests=10, window_seconds=60)
        async def upload(request: Request):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find Request in args or kwargs
            # Check all arguments for a Request object (FastAPI injects it)
            request = None

            # Check positional args
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            # Check kwargs for any Request object
            if not request:
                for key, value in kwargs.items():
                    if isinstance(value, Request):
                        request = value
                        break

            if not request:
                # No request object, skip rate limiting
                logger.warning("Rate limit decorator used without Request parameter")
                return await func(*args, **kwargs)

            # Get rate limit key
            if key_func:
                key = key_func(request)
            else:
                key = get_client_ip(request)

            # Check rate limit
            limiter = get_rate_limiter()
            allowed, remaining, retry_after = limiter.is_allowed(
                key=f"{func.__name__}:{key}",
                max_requests=max_requests,
                window_seconds=window_seconds,
            )

            if not allowed:
                logger.warning("Rate limit exceeded", extra={
                    "event": "rate_limit.exceeded",
                    "endpoint": func.__name__,
                    "client_ip": key,
                    "retry_after": retry_after,
                })
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "retry_after": retry_after,
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                    }
                )

            # Execute the endpoint
            response = await func(*args, **kwargs)

            # Note: Headers won't be added to response here since
            # FastAPI handles response differently. For full header support,
            # use middleware instead.

            return response

        return wrapper
    return decorator


# Preset rate limits for common use cases
RATE_LIMIT_UPLOAD = {"max_requests": 30, "window_seconds": 60}  # 30/min
RATE_LIMIT_TRAINING = {"max_requests": 5, "window_seconds": 60}  # 5/min
RATE_LIMIT_GENERATION = {"max_requests": 20, "window_seconds": 60}  # 20/min
RATE_LIMIT_DEFAULT = {"max_requests": 100, "window_seconds": 60}  # 100/min
