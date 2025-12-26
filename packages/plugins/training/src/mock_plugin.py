"""
Mock Training Plugin

Used for fast-test mode to validate wiring without actual GPU training.
Creates placeholder model files and simulates progress.
"""

import asyncio
from pathlib import Path
from typing import Callable

from packages.shared.src.logging import get_logger
from packages.shared.src.types import TrainingConfig, TrainingMethod

from .interface import TrainingPlugin, TrainingProgress, TrainingResult

logger = get_logger("plugins.training.mock")


class MockTrainingPlugin(TrainingPlugin):
    """
    Mock training plugin for testing.

    Simulates training progress without actual computation.
    Used in fast-test mode.
    """

    def __init__(self):
        self._cancelled = False
        self._running = False

    @property
    def name(self) -> str:
        return "mock"

    @property
    def supported_methods(self) -> list[TrainingMethod]:
        return [TrainingMethod.LORA]

    async def validate_config(self, config: TrainingConfig) -> tuple[bool, str | None]:
        """Always valid in mock mode."""
        if config.method not in self.supported_methods:
            return False, f"Method {config.method} not supported"
        return True, None

    async def train(
        self,
        config: TrainingConfig,
        images_dir: Path,
        output_path: Path,
        trigger_word: str,
        progress_callback: Callable[[TrainingProgress], None] | None = None,
    ) -> TrainingResult:
        """
        Simulate training with progress updates.

        Creates a placeholder .safetensors file.
        """
        self._cancelled = False
        self._running = True

        logger.info("Starting mock training", extra={
            "images_dir": str(images_dir),
            "output_path": str(output_path),
            "trigger_word": trigger_word,
            "steps": config.steps,
        })

        total_steps = config.steps
        simulated_loss = 0.5

        try:
            for step in range(1, total_steps + 1):
                if self._cancelled:
                    logger.info("Training cancelled by user")
                    return TrainingResult(
                        success=False,
                        output_path=None,
                        error_message="Training cancelled by user",
                    )

                # Simulate step time (fast in mock mode)
                await asyncio.sleep(0.05)

                # Decay loss over time
                simulated_loss *= 0.999

                if progress_callback:
                    progress = TrainingProgress(
                        current_step=step,
                        total_steps=total_steps,
                        loss=simulated_loss,
                        learning_rate=config.learning_rate,
                        message=f"Training step {step}/{total_steps}",
                    )
                    progress_callback(progress)

                # Log every 10%
                if step % (total_steps // 10 or 1) == 0:
                    logger.info(f"Training progress: {step}/{total_steps}", extra={
                        "step": step,
                        "total": total_steps,
                        "loss": simulated_loss,
                    })

            # Create placeholder model file
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write a minimal placeholder (not a real safetensors)
            with open(output_path, "wb") as f:
                # Just write some metadata as placeholder
                f.write(b"MOCK_LORA_MODEL_PLACEHOLDER\n")
                f.write(f"trigger_word={trigger_word}\n".encode())
                f.write(f"steps={total_steps}\n".encode())
                f.write(f"final_loss={simulated_loss}\n".encode())

            logger.info("Mock training completed successfully", extra={
                "output_path": str(output_path),
                "final_loss": simulated_loss,
            })

            return TrainingResult(
                success=True,
                output_path=output_path,
                total_steps=total_steps,
                final_loss=simulated_loss,
                training_time_seconds=total_steps * 0.05,
            )

        except Exception as e:
            logger.error(f"Mock training failed: {e}", extra={"error": str(e)})
            return TrainingResult(
                success=False,
                output_path=None,
                error_message=str(e),
            )
        finally:
            self._running = False

    async def cancel(self) -> None:
        """Cancel the mock training."""
        if self._running:
            self._cancelled = True
            logger.info("Cancel requested for mock training")
