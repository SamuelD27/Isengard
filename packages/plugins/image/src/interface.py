"""
Image Generation Plugin Interface

All image generation backends must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, TypedDict

from packages.shared.src.types import GenerationConfig


# ============================================
# Capability Schema Types
# ============================================

class ParameterSchema(TypedDict, total=False):
    """Schema for a single parameter."""
    type: Literal["int", "float", "enum", "bool", "string"]
    min: float | int | None
    max: float | int | None
    step: float | None  # UI hint for input step size
    options: list[str | int | float] | None  # For enum type
    default: any
    wired: bool  # True if backend actually uses this parameter
    reason: str | None  # Why unavailable (if wired=False)
    description: str | None


class ToggleSchema(TypedDict, total=False):
    """Schema for a toggle feature."""
    supported: bool
    reason: str | None  # Why not supported
    description: str | None


class ImageCapabilities(TypedDict):
    """Capabilities reported by an image generation plugin."""
    backend: str  # e.g., "comfyui"
    model_variants: list[str]  # e.g., ["flux-dev", "flux-schnell"]
    toggles: dict[str, ToggleSchema]  # Feature toggles
    parameters: dict[str, ParameterSchema]


@dataclass
class GenerationProgress:
    """Progress update from generation."""
    current_step: int
    total_steps: int
    message: str = ""
    preview_path: str | None = None

    @property
    def percentage(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100


@dataclass
class GenerationResult:
    """Result of image generation."""
    success: bool
    output_paths: list[Path]
    error_message: str | None = None
    generation_time_seconds: float = 0.0
    seed_used: int | None = None


class ImagePlugin(ABC):
    """
    Abstract base class for image generation plugins.

    Implementations must:
    1. Support the GenerationConfig parameters
    2. Emit progress updates via the callback
    3. Write output images to specified paths
    4. Handle LoRA loading when lora_id is provided
    5. Report capabilities via get_capabilities()
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier (e.g., 'comfyui')."""
        pass

    @abstractmethod
    def get_capabilities(self) -> ImageCapabilities:
        """
        Return the capabilities and supported parameters for this plugin.

        This schema is used by:
        - API /info endpoint to advertise capabilities
        - Frontend to render dynamic controls
        - API validation to reject unsupported parameters

        Returns:
            ImageCapabilities with backend, toggles, and parameter schemas
        """
        pass

    @abstractmethod
    async def check_health(self) -> tuple[bool, str | None]:
        """
        Check if the backend is available and healthy.

        Returns:
            Tuple of (is_healthy, error_message)
        """
        pass

    @abstractmethod
    async def generate(
        self,
        config: GenerationConfig,
        output_dir: Path,
        lora_path: Path | None = None,
        count: int = 1,
        progress_callback: Callable[[GenerationProgress], None] | None = None,
    ) -> GenerationResult:
        """
        Generate images.

        Args:
            config: Generation configuration
            output_dir: Directory to save generated images
            lora_path: Optional path to LoRA model file
            count: Number of images to generate
            progress_callback: Optional callback for progress updates

        Returns:
            GenerationResult with paths to generated images
        """
        pass

    @abstractmethod
    async def cancel(self) -> None:
        """Cancel the current generation if in progress."""
        pass

    @abstractmethod
    async def list_workflows(self) -> list[str]:
        """List available workflow names."""
        pass

    @abstractmethod
    async def get_workflow_info(self, name: str) -> dict | None:
        """Get information about a specific workflow."""
        pass
