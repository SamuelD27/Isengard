"""
Plugin Interface Contracts for Isengard

These interfaces define the contract between core code and plugin implementations.
Implementations go in packages/plugins/{training,image,video}/.

Core code (API, Worker) imports these interfaces but NEVER imports plugin internals.
Plugins implement these interfaces and are loaded dynamically by the Worker.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Any

from .types import (
    TrainingConfig,
    TrainingProgress,
    TrainingResult,
    GenerationConfig,
    GenerationProgress,
    GenerationResult,
)


class TrainingBackend(ABC):
    """
    Interface for training backends (e.g., AI-Toolkit, Kohya).

    Implementations should be stateless where possible. Configuration
    and model paths are passed per-call rather than stored on the instance.

    Example implementation location: packages/plugins/training/ai_toolkit.py
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name (e.g., 'AI-Toolkit', 'Kohya')."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Backend version string."""
        ...

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        """
        Return training capabilities schema.

        Returns:
            Dictionary describing supported features, e.g.:
            {
                "methods": ["lora", "dora"],
                "base_models": ["flux-dev", "sdxl"],
                "max_resolution": 2048,
                "supports_sample_generation": True,
                "supports_checkpointing": True,
            }
        """
        ...

    @abstractmethod
    async def validate_config(self, config: TrainingConfig) -> list[str]:
        """
        Validate training configuration before starting.

        Args:
            config: The training configuration to validate.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        ...

    @abstractmethod
    async def train(
        self,
        config: TrainingConfig,
        images_dir: Path,
        output_path: Path,
        trigger_word: str,
        progress_callback: Callable[[TrainingProgress], None] | None = None,
        job_id: str | None = None,
    ) -> TrainingResult:
        """
        Execute training and return result.

        Args:
            config: Training configuration (steps, learning rate, etc.)
            images_dir: Directory containing training images
            output_path: Where to save the trained model
            trigger_word: Trigger word for LoRA activation
            progress_callback: Optional callback for progress updates
            job_id: Optional job ID for logging/correlation

        Returns:
            TrainingResult with success status, model path, metrics, etc.

        Raises:
            Should NOT raise exceptions - return TrainingResult with success=False
            and error_message set instead.
        """
        ...

    @abstractmethod
    async def cancel(self, job_id: str) -> bool:
        """
        Request cancellation of a running training job.

        Args:
            job_id: The job ID to cancel.

        Returns:
            True if cancellation was requested successfully.
            Note: Training may not stop immediately.
        """
        ...


class GenerationBackend(ABC):
    """
    Interface for generation backends (e.g., ComfyUI, A1111).

    Implementations should be stateless where possible. All configuration
    is passed per-call.

    Example implementation location: packages/plugins/image/comfyui.py
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name (e.g., 'ComfyUI', 'A1111')."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Backend version string."""
        ...

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        """
        Return generation capabilities schema.

        Returns:
            Dictionary describing supported features, e.g.:
            {
                "base_models": ["flux-dev", "sdxl"],
                "max_resolution": 2048,
                "supports_controlnet": True,
                "supports_ipadapter": True,
                "supports_facedetailer": True,
                "supports_upscale": True,
                "supported_formats": ["png", "jpg", "webp"],
            }
        """
        ...

    @abstractmethod
    async def validate_config(self, config: GenerationConfig) -> list[str]:
        """
        Validate generation configuration before starting.

        Args:
            config: The generation configuration to validate.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        ...

    @abstractmethod
    async def generate(
        self,
        config: GenerationConfig,
        lora_path: Path | None,
        output_dir: Path,
        progress_callback: Callable[[GenerationProgress], None] | None = None,
        job_id: str | None = None,
    ) -> GenerationResult:
        """
        Execute generation and return result.

        Args:
            config: Generation configuration (prompt, dimensions, etc.)
            lora_path: Optional path to LoRA file to use
            output_dir: Directory to save generated images
            progress_callback: Optional callback for progress updates
            job_id: Optional job ID for logging/correlation

        Returns:
            GenerationResult with success status, output paths, etc.

        Raises:
            Should NOT raise exceptions - return GenerationResult with success=False
            and error_message set instead.
        """
        ...

    @abstractmethod
    async def cancel(self, job_id: str) -> bool:
        """
        Request cancellation of a running generation job.

        Args:
            job_id: The job ID to cancel.

        Returns:
            True if cancellation was requested successfully.
        """
        ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """
        Check if the backend is healthy and ready for requests.

        Returns:
            Dictionary with health status, e.g.:
            {
                "healthy": True,
                "ready": True,
                "queue_size": 0,
                "gpu_available": True,
            }
        """
        ...


class VideoBackend(ABC):
    """
    Interface for video generation backends.

    SCAFFOLD ONLY - Not yet implemented.
    This interface is defined for future video generation support.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Backend version string."""
        ...

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        """Return video generation capabilities schema."""
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        output_dir: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate video from prompt.

        Scaffold - signature will be refined when implemented.
        """
        ...
