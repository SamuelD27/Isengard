"""
Isengard Configuration Module

Centralized configuration management with environment-based resolution.
Supports both local development and RunPod deployment.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Operating modes
Mode = Literal["fast-test", "production"]


@dataclass
class Config:
    """Application configuration with sensible defaults."""

    # Core settings
    mode: Mode = "fast-test"
    debug: bool = False

    # Paths - resolved based on environment
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    log_dir: Path = field(default_factory=lambda: Path("./logs"))
    tmp_dir: Path = field(default_factory=lambda: Path("./tmp"))

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Redis settings
    redis_url: str = "redis://localhost:6379"

    # Worker settings
    worker_concurrency: int = 1

    # ComfyUI settings
    comfyui_url: str = "http://localhost:8188"

    # Logging
    log_level: str = "INFO"
    log_to_file: bool = True
    log_to_stdout: bool = True

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def is_production(self) -> bool:
        return self.mode == "production"

    @property
    def is_fast_test(self) -> bool:
        return self.mode == "fast-test"

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        for dir_path in [
            self.data_dir,
            self.uploads_dir,
            self.models_dir,
            self.outputs_dir,
            self.log_dir,
            self.tmp_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)


def _get_path(env_var: str, default: str) -> Path:
    """Get path from environment or default, handling RunPod volume mounts."""
    value = os.getenv(env_var)
    if value:
        return Path(value)

    # Check for RunPod volume mounts
    runpod_volume = os.getenv("RUNPOD_VOLUME_PATH", "/runpod-volume")
    if os.path.exists(runpod_volume):
        return Path(runpod_volume) / default.lstrip("./")

    workspace = os.getenv("WORKSPACE_PATH", "/workspace")
    if os.path.exists(workspace):
        return Path(workspace) / default.lstrip("./")

    return Path(default)


def get_config() -> Config:
    """
    Load configuration from environment variables.

    Environment variables (all optional with sensible defaults):
        ISENGARD_MODE: 'fast-test' or 'production'
        DEBUG: 'true' or 'false'
        DATA_DIR: Path to data directory
        LOG_DIR: Path to log directory
        TMP_DIR: Path to temp directory
        API_HOST: API bind host
        API_PORT: API bind port
        REDIS_URL: Redis connection URL
        WORKER_CONCURRENCY: Max parallel jobs
        COMFYUI_URL: ComfyUI server URL
        LOG_LEVEL: Minimum log level
        LOG_TO_FILE: 'true' or 'false'
        LOG_TO_STDOUT: 'true' or 'false'
    """
    mode_raw = os.getenv("ISENGARD_MODE", "fast-test")
    mode: Mode = "production" if mode_raw == "production" else "fast-test"

    config = Config(
        mode=mode,
        debug=os.getenv("DEBUG", "false").lower() == "true",
        data_dir=_get_path("DATA_DIR", "./data"),
        log_dir=_get_path("LOG_DIR", "./logs"),
        tmp_dir=_get_path("TMP_DIR", "./tmp"),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        worker_concurrency=int(os.getenv("WORKER_CONCURRENCY", "1")),
        comfyui_url=os.getenv("COMFYUI_URL", "http://localhost:8188"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_to_file=os.getenv("LOG_TO_FILE", "true").lower() == "true",
        log_to_stdout=os.getenv("LOG_TO_STDOUT", "true").lower() == "true",
    )

    return config


# Singleton instance
_config: Config | None = None


def get_global_config() -> Config:
    """Get or create the global configuration singleton."""
    global _config
    if _config is None:
        _config = get_config()
    return _config
