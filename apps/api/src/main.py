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

from .routes import health, characters, training, generation
from .middleware import CorrelationIDMiddleware

logger = get_logger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    config = get_global_config()

    # Configure logging
    configure_logging("api")
    logger.info("Starting Isengard API", extra={
        "mode": config.mode,
        "data_dir": str(config.data_dir),
    })

    # Ensure directories exist
    config.ensure_directories()

    yield

    logger.info("Shutting down Isengard API")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_global_config()

    app = FastAPI(
        title="Isengard API",
        description="Identity LoRA Training + Image Generation Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Correlation ID middleware
    app.add_middleware(CorrelationIDMiddleware)

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(characters.router, prefix="/api/characters", tags=["Characters"])
    app.include_router(training.router, prefix="/api/training", tags=["Training"])
    app.include_router(generation.router, prefix="/api/generation", tags=["Generation"])

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
