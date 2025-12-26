"""
Training Plugin Interface

All training backends must implement this interface.
This provides a stable contract between the worker and training implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable

from packages.shared.src.types import TrainingConfig, TrainingMethod


@dataclass
class TrainingProgress:
    """Progress update from training."""
    current_step: int
    total_steps: int
    loss: float | None = None
    learning_rate: float | None = None
    message: str = ""
    preview_path: str | None = None

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


class TrainingPlugin(ABC):
    """
    Abstract base class for training plugins.

    Implementations must:
    1. Support the specified training methods
    2. Emit progress updates via the callback
    3. Write output to the specified path
    4. Handle cancellation gracefully
    5. Clean up resources on completion
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
    ) -> TrainingResult:
        """
        Execute training run.

        Args:
            config: Training configuration
            images_dir: Directory containing training images
            output_path: Path where trained model should be saved
            trigger_word: Trigger word for the identity
            progress_callback: Optional callback for progress updates

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
