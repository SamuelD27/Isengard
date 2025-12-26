"""
AI-Toolkit Training Plugin

Production training backend using AI-Toolkit for FLUX LoRA training.
This is a stub that will be implemented when integrating the actual library.
"""

from pathlib import Path
from typing import Callable

from packages.shared.src.logging import get_logger
from packages.shared.src.types import TrainingConfig, TrainingMethod

from .interface import TrainingPlugin, TrainingProgress, TrainingResult

logger = get_logger("plugins.training.ai_toolkit")


class AIToolkitPlugin(TrainingPlugin):
    """
    AI-Toolkit training plugin for production LoRA training.

    Uses: https://github.com/ostris/ai-toolkit

    Note: This is a stub. Full implementation requires:
    1. Installing ai-toolkit
    2. Downloading FLUX.1-dev model
    3. GPU with sufficient VRAM (24GB+ recommended)
    """

    def __init__(self):
        self._cancelled = False
        self._process = None

    @property
    def name(self) -> str:
        return "ai-toolkit"

    @property
    def supported_methods(self) -> list[TrainingMethod]:
        return [TrainingMethod.LORA]

    async def validate_config(self, config: TrainingConfig) -> tuple[bool, str | None]:
        """
        Validate configuration for AI-Toolkit training.

        Checks:
        - Method is supported
        - Resolution is valid for FLUX
        - LoRA rank is within acceptable range
        """
        if config.method not in self.supported_methods:
            return False, f"Method {config.method} not supported by AI-Toolkit"

        if config.resolution not in [512, 768, 1024]:
            return False, f"Resolution {config.resolution} not recommended. Use 512, 768, or 1024."

        if config.lora_rank > 64:
            logger.warning(f"High LoRA rank {config.lora_rank} may cause instability")

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
        Execute AI-Toolkit LoRA training.

        STUB: This will be implemented with actual AI-Toolkit integration.

        The implementation will:
        1. Generate AI-Toolkit config YAML
        2. Launch training subprocess
        3. Parse progress from logs
        4. Handle cancellation via process signals
        """
        logger.warning("AI-Toolkit plugin is a stub - use mock plugin for testing")

        # TODO: Implement actual AI-Toolkit integration
        # Steps:
        # 1. Create config YAML from TrainingConfig
        # 2. subprocess.Popen(['python', 'run.py', config_path])
        # 3. Parse stdout for progress updates
        # 4. Return result when complete

        return TrainingResult(
            success=False,
            output_path=None,
            error_message="AI-Toolkit integration not yet implemented. Use ISENGARD_MODE=fast-test for testing.",
        )

    async def cancel(self) -> None:
        """Cancel AI-Toolkit training."""
        if self._process:
            self._process.terminate()
            self._cancelled = True
            logger.info("Sent termination signal to AI-Toolkit process")
