"""
Training Plugin Interface

All training backends must implement this interface.
This provides a stable contract between the worker and training implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable, Literal, TypedDict

from packages.shared.src.types import TrainingConfig, TrainingMethod


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


class TrainingCapabilities(TypedDict):
    """Capabilities reported by a training plugin."""
    method: str  # e.g., "lora"
    backend: str  # e.g., "ai-toolkit"
    parameters: dict[str, ParameterSchema]


@dataclass
class TrainingProgress:
    """Progress update from training."""
    current_step: int
    total_steps: int
    loss: float | None = None
    learning_rate: float | None = None
    message: str = ""
    preview_path: str | None = None
    sample_path: str | None = None  # Path to newly generated sample image
    eta_seconds: int | None = None  # Estimated time remaining

    @property
    def percentage(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100


@dataclass
class TrainingResult:
    """Result of a completed training run."""
    success: bool
    output_path: Path | None
    error_message: str | None = None
    total_steps: int = 0
    final_loss: float | None = None
    training_time_seconds: float = 0.0
    samples: list[str] | None = None  # Paths to generated sample images


class TrainingPlugin(ABC):
    """
    Abstract base class for training plugins.

    Implementations must:
    1. Support the specified training methods
    2. Emit progress updates via the callback
    3. Write output to the specified path
    4. Handle cancellation gracefully
    5. Clean up resources on completion
    6. Report capabilities via get_capabilities()
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier (e.g., 'ai-toolkit')."""
        pass

    @property
    @abstractmethod
    def supported_methods(self) -> list[TrainingMethod]:
        """List of training methods this plugin supports."""
        pass

    @abstractmethod
    def get_capabilities(self) -> TrainingCapabilities:
        """
        Return the capabilities and supported parameters for this plugin.

        This schema is used by:
        - API /info endpoint to advertise capabilities
        - Frontend to render dynamic controls
        - API validation to reject unsupported parameters

        Returns:
            TrainingCapabilities with method, backend, and parameter schemas
        """
        pass

    @abstractmethod
    async def validate_config(self, config: TrainingConfig) -> tuple[bool, str | None]:
        """
        Validate training configuration before starting.

        Args:
            config: Training configuration to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        pass

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
        Execute training run.

        Args:
            config: Training configuration
            images_dir: Directory containing training images
            output_path: Path where trained model should be saved
            trigger_word: Trigger word for the identity
            progress_callback: Optional callback for progress updates
            job_id: Optional job ID for organizing sample images

        Returns:
            TrainingResult with success status and output path
        """
        pass

    @abstractmethod
    async def cancel(self) -> None:
        """Cancel the current training run if in progress."""
        pass

    def supports_method(self, method: TrainingMethod) -> bool:
        """Check if this plugin supports a given method."""
        return method in self.supported_methods
