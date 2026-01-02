"""
Health Check Endpoints

Provides health and readiness checks for the API.
Also includes debug endpoints for GUI→API wiring diagnostics.
"""

import os
from fastapi import APIRouter, Request

from packages.shared.src.config import get_global_config
from ..services.job_executor import (
    get_training_capabilities,
    get_generation_capabilities,
    check_comfyui_health,
)

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Basic health check.

    Returns 200 if the API is running.
    """
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check():
    """
    Readiness check with dependency status.

    Returns the status of required dependencies including internal services.
    ComfyUI is an internal service (127.0.0.1:8188) - not exposed externally.
    """
    import httpx

    config = get_global_config()

    # Check ComfyUI internal service
    comfyui_status = "unknown"
    comfyui_details = None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{config.comfyui_url}/system_stats")
            if response.status_code == 200:
                comfyui_status = "healthy"
                stats = response.json()
                comfyui_details = {
                    "url": config.comfyui_url,
                    "binding": f"{config.comfyui_host}:{config.comfyui_port}",
                    "exposed": False,  # Internal service only
                }
            else:
                comfyui_status = "unhealthy"
    except Exception as e:
        comfyui_status = "unreachable"
        comfyui_details = {"error": str(e)}

    # Determine overall status
    # API is ready even if ComfyUI is down (fast-test mode works without it)
    overall_status = "ready"
    if config.is_production and comfyui_status != "healthy":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "mode": config.mode,
        "dependencies": {
            "storage": "ok" if config.data_dir.exists() else "missing",
            "comfyui": {
                "status": comfyui_status,
                "internal_service": True,
                "details": comfyui_details,
            },
            "aitoolkit": {
                "status": "ok" if config.aitoolkit_path.exists() else "missing",
                "path": str(config.aitoolkit_path),
                "vendored": True,
            },
        }
    }


@router.get("/info")
async def api_info():
    """
    API information and capabilities.

    Returns capability schemas for:
    - Training: parameter ranges, supported options
    - Image Generation: toggles, parameters, model variants

    The frontend uses this schema to:
    - Render dynamic controls from schema (not hardcoded)
    - Show unavailable parameters in collapsed section
    - Validate inputs before submission
    """
    config = get_global_config()

    return {
        "name": "Isengard API",
        "version": "0.1.0",
        "mode": config.mode,
        "training": get_training_capabilities(),
        "image_generation": get_generation_capabilities(),
    }


@router.get("/_debug/echo")
async def debug_echo(request: Request):
    """
    Debug endpoint for GUI→API wiring diagnostics.

    Returns request details to verify:
    - Headers are correctly propagated (correlation ID, interaction ID)
    - Request is hitting the correct backend (not static server)
    - Proxy is forwarding correctly

    Only enabled when ISENGARD_MODE != 'production' or DEBUG_ENDPOINTS=true
    """
    config = get_global_config()

    # Disable in production unless explicitly enabled
    if config.mode == "production" and not os.getenv("DEBUG_ENDPOINTS", "").lower() == "true":
        return {
            "error": "Debug endpoints disabled in production",
            "hint": "Set DEBUG_ENDPOINTS=true to enable",
        }

    # Extract headers for diagnostics
    headers_dict = dict(request.headers)

    # Redact sensitive headers
    sensitive_headers = {"authorization", "cookie", "x-api-key"}
    for key in sensitive_headers:
        if key in headers_dict:
            headers_dict[key] = "[REDACTED]"

    return {
        "status": "echo",
        "backend": "fastapi",
        "mode": config.mode,
        "request": {
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_host": request.client.host if request.client else None,
            "client_port": request.client.port if request.client else None,
        },
        "headers": {
            "correlation_id": headers_dict.get("x-correlation-id"),
            "interaction_id": headers_dict.get("x-interaction-id"),
            "host": headers_dict.get("host"),
            "origin": headers_dict.get("origin"),
            "referer": headers_dict.get("referer"),
            "user_agent": headers_dict.get("user-agent"),
            "content_type": headers_dict.get("content-type"),
            "x_forwarded_for": headers_dict.get("x-forwarded-for"),
            "x_forwarded_proto": headers_dict.get("x-forwarded-proto"),
            "x_real_ip": headers_dict.get("x-real-ip"),
        },
        "environment": {
            "api_base_expected": "/api",
            "volume_root": str(config.data_dir),
            "log_dir": str(config.log_dir),
        },
    }


@router.post("/_debug/echo")
async def debug_echo_post(request: Request):
    """
    POST variant of debug echo to test POST request routing.
    """
    config = get_global_config()

    if config.mode == "production" and not os.getenv("DEBUG_ENDPOINTS", "").lower() == "true":
        return {
            "error": "Debug endpoints disabled in production",
            "hint": "Set DEBUG_ENDPOINTS=true to enable",
        }

    # Try to read body
    try:
        body = await request.body()
        body_preview = body[:500].decode("utf-8", errors="replace") if body else None
    except Exception:
        body_preview = "[unable to read body]"

    headers_dict = dict(request.headers)

    return {
        "status": "echo",
        "backend": "fastapi",
        "mode": config.mode,
        "method": "POST",
        "request": {
            "path": request.url.path,
            "content_type": headers_dict.get("content-type"),
            "content_length": headers_dict.get("content-length"),
            "body_preview": body_preview,
        },
        "headers": {
            "correlation_id": headers_dict.get("x-correlation-id"),
            "interaction_id": headers_dict.get("x-interaction-id"),
        },
    }
