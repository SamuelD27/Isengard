"""
Health Check Endpoints

Provides health and readiness checks for the API.
"""

from fastapi import APIRouter

from packages.shared.src.config import get_global_config
from packages.shared.src.capabilities import list_supported_capabilities

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

    Returns the status of required dependencies.
    """
    config = get_global_config()

    # TODO: Add actual dependency checks (Redis, etc.)
    return {
        "status": "ready",
        "mode": config.mode,
        "dependencies": {
            "redis": "unchecked",  # TODO: Implement
            "storage": "ok" if config.data_dir.exists() else "missing",
        }
    }


@router.get("/info")
async def api_info():
    """
    API information and capabilities.
    """
    config = get_global_config()

    return {
        "name": "Isengard API",
        "version": "0.1.0",
        "mode": config.mode,
        "capabilities": list_supported_capabilities(),
    }
