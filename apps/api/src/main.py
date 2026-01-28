"""
Isengard API - Main Application

FastAPI backend for character management, training, and image generation.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add packages to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import configure_logging, get_logger

from .routes import health, characters, training, generation, logs, jobs, uelr, loras, captioning
from .middleware import CorrelationIDMiddleware
from .services.job_store import (
    get_training_store,
    get_generation_store,
    migrate_jobs_from_logs,
)

logger = get_logger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    config = get_global_config()

    # Configure logging (with rotation of previous session)
    configure_logging("api", rotate=True)

    logger.info("Isengard API starting", extra={
        "event": "system.startup",
        "mode": config.mode,
        "volume_root": str(config.volume_root),
        "api_host": config.api_host,
        "api_port": config.api_port,
    })

    # Ensure directories exist
    config.ensure_directories()

    # Initialize job stores (loads persisted jobs from disk)
    training_store = get_training_store()
    generation_store = get_generation_store()
    logger.info("Job stores initialized", extra={
        "event": "job_store.loaded",
        "training_jobs": training_store.count(),
        "generation_jobs": generation_store.count(),
    })

    # Migrate any jobs from old log files
    migration_stats = migrate_jobs_from_logs()
    if migration_stats["training"] > 0 or migration_stats["generation"] > 0:
        logger.info("Jobs migrated from logs", extra={
            "event": "job_store.migration_complete",
            **migration_stats,
        })

    logger.info("Isengard API ready", extra={
        "event": "system.ready",
    })

    yield

    # Persist all job states before shutdown
    training_flushed = training_store.flush_all()
    generation_flushed = generation_store.flush_all()
    logger.info("Job stores flushed on shutdown", extra={
        "event": "job_store.shutdown_flush",
        "training_jobs": training_flushed,
        "generation_jobs": generation_flushed,
    })

    logger.info("Isengard API shutting down", extra={
        "event": "system.shutdown",
    })


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_global_config()

    app = FastAPI(
        title="Isengard API",
        description="Identity LoRA Training + Image Generation Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware - configure based on environment
    # In development: allow localhost origins
    # In production: restrict to configured origins only
    if config.is_fast_test or config.mode == "development":
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    else:
        # Production: only allow same-origin and explicitly configured origins
        # Add additional origins via CORS_ORIGINS env var (comma-separated)
        import os
        cors_origins = os.getenv("CORS_ORIGINS", "")
        allowed_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
        if not allowed_origins:
            # Default: same-origin only (no explicit origins needed)
            allowed_origins = []

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=None if allowed_origins else r"https?://localhost:\d+",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Correlation ID middleware
    app.add_middleware(CorrelationIDMiddleware)

    # Include routers
    # Health endpoints under /api for frontend compatibility
    app.include_router(health.router, prefix="/api", tags=["Health"])

    # Also expose root /health for backwards compatibility (Docker health checks, etc.)
    @app.get("/health", include_in_schema=False)
    async def root_health():
        return {"status": "healthy"}
    app.include_router(characters.router, prefix="/api/characters", tags=["Characters"])
    app.include_router(training.router, prefix="/api/training", tags=["Training"])
    app.include_router(generation.router, prefix="/api/generation", tags=["Generation"])
    app.include_router(captioning.router, prefix="/api/captioning", tags=["Captioning"])
    app.include_router(loras.router, prefix="/api/loras", tags=["LoRAs"])
    app.include_router(logs.router, prefix="/api/client-logs", tags=["Client Logs"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
    app.include_router(uelr.router, prefix="/api/uelr", tags=["UELR"])

    return app


# Application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = get_global_config()
    uvicorn.run(
        "src.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
    )
