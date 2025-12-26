"""
Isengard Configuration Module

Centralized configuration management with environment-based resolution.
Supports both local development and RunPod deployment.

Storage Contract (authoritative):
  $VOLUME_ROOT/
  ├── characters/     # Character metadata JSON files
  ├── uploads/        # Raw training images (user-provided)
  ├── datasets/       # Curated training datasets (processed)
  ├── synthetic/      # Generated synthetic images for augmentation
  ├── loras/          # Trained LoRA models
  ├── outputs/        # Generated images (final outputs)
  ├── comfyui/        # ComfyUI workspace (production only)
  └── cache/          # Ephemeral cache (can be cleared)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Operating modes
Mode = Literal["fast-test", "production"]


def _resolve_volume_root() -> Path:
    """
    Resolve VOLUME_ROOT based on environment.

    Resolution Order:
    1. Explicit VOLUME_ROOT env var
    2. /runpod-volume/isengard if /runpod-volume exists
    3. /workspace/isengard if /workspace exists
    4. ./data (local fallback)
    """
    explicit = os.getenv("VOLUME_ROOT")
    if explicit:
        return Path(explicit)

    if os.path.exists("/runpod-volume"):
        return Path("/runpod-volume/isengard")

    if os.path.exists("/workspace"):
        return Path("/workspace/isengard")

    return Path("./data")


@dataclass
class Config:
    """Application configuration with sensible defaults."""

    # Core settings
    mode: Mode = "fast-test"
    debug: bool = False

    # Paths - resolved based on environment
    volume_root: Path = field(default_factory=_resolve_volume_root)
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

    # Backwards compatibility alias
    @property
    def data_dir(self) -> Path:
        """Alias for volume_root (backwards compatibility)."""
        return self.volume_root

    # Storage contract directories
    @property
    def characters_dir(self) -> Path:
        """Character metadata JSON files."""
        return self.volume_root / "characters"

    @property
    def uploads_dir(self) -> Path:
        """Raw training images (user-provided)."""
        return self.volume_root / "uploads"

    @property
    def datasets_dir(self) -> Path:
        """Curated training datasets (processed)."""
        return self.volume_root / "datasets"

    @property
    def synthetic_dir(self) -> Path:
        """Generated synthetic images for augmentation."""
        return self.volume_root / "synthetic"

    @property
    def loras_dir(self) -> Path:
        """Trained LoRA models."""
        return self.volume_root / "loras"

    @property
    def outputs_dir(self) -> Path:
        """Generated images (final outputs)."""
        return self.volume_root / "outputs"

    @property
    def comfyui_dir(self) -> Path:
        """ComfyUI workspace (production only)."""
        return self.volume_root / "comfyui"

    @property
    def cache_dir(self) -> Path:
        """Ephemeral cache (can be cleared)."""
        return self.volume_root / "cache"

    # Legacy alias (backwards compatibility)
    @property
    def models_dir(self) -> Path:
        """Alias for loras_dir (backwards compatibility)."""
        return self.loras_dir

    @property
    def is_production(self) -> bool:
        return self.mode == "production"

    @property
    def is_fast_test(self) -> bool:
        return self.mode == "fast-test"

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        for dir_path in [
            self.volume_root,
            self.characters_dir,
            self.uploads_dir,
            self.datasets_dir,
            self.synthetic_dir,
            self.loras_dir,
            self.outputs_dir,
            self.cache_dir,
            self.log_dir,
            self.tmp_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)
        # Note: comfyui_dir created only when needed in production


def get_config() -> Config:
    """
    Load configuration from environment variables.

    Environment variables (all optional with sensible defaults):
        ISENGARD_MODE: 'fast-test' or 'production'
        DEBUG: 'true' or 'false'
        VOLUME_ROOT: Root for all data (default: ./data or RunPod volume)
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

    # Resolve volume root
    volume_root = _resolve_volume_root()

    # Log directory can be overridden
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    tmp_dir = Path(os.getenv("TMP_DIR", "./tmp"))

    config = Config(
        mode=mode,
        debug=os.getenv("DEBUG", "false").lower() == "true",
        volume_root=volume_root,
        log_dir=log_dir,
        tmp_dir=tmp_dir,
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
