"""
ComfyUI Image Plugin

Production image generation backend using ComfyUI API.
This is a stub that will be implemented when integrating with ComfyUI.
"""

from pathlib import Path
from typing import Callable

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger
from packages.shared.src.types import GenerationConfig

from .interface import ImagePlugin, GenerationProgress, GenerationResult

logger = get_logger("plugins.image.comfyui")


class ComfyUIPlugin(ImagePlugin):
    """
    ComfyUI image generation plugin.

    Connects to a ComfyUI server and executes workflows via its API.

    Note: This is a stub. Full implementation requires:
    1. Running ComfyUI server
    2. Workflow JSON files for supported pipelines
    3. Downloaded models (FLUX, SDXL, etc.)
    """

    def __init__(self, server_url: str | None = None):
        config = get_global_config()
        self.server_url = server_url or config.comfyui_url
        self._cancelled = False

    @property
    def name(self) -> str:
        return "comfyui"

    async def check_health(self) -> tuple[bool, str | None]:
        """
        Check if ComfyUI server is available.

        STUB: Will make HTTP request to ComfyUI /system_stats endpoint.
        """
        logger.warning("ComfyUI health check is a stub")

        # TODO: Implement actual health check
        # async with httpx.AsyncClient() as client:
        #     response = await client.get(f"{self.server_url}/system_stats")
        #     return response.status_code == 200, None

        return False, "ComfyUI integration not yet implemented"

    async def generate(
        self,
        config: GenerationConfig,
        output_dir: Path,
        lora_path: Path | None = None,
        count: int = 1,
        progress_callback: Callable[[GenerationProgress], None] | None = None,
    ) -> GenerationResult:
        """
        Execute ComfyUI workflow for image generation.

        STUB: This will be implemented with actual ComfyUI API integration.

        The implementation will:
        1. Load workflow JSON template
        2. Inject parameters (prompt, size, seed, LoRA)
        3. Submit via POST /prompt
        4. Poll /history for completion
        5. Download generated images
        """
        logger.warning("ComfyUI plugin is a stub - use mock plugin for testing")

        # TODO: Implement actual ComfyUI integration
        # Steps:
        # 1. Load workflow template
        # 2. Modify nodes with config parameters
        # 3. POST to /prompt
        # 4. Poll /history/{prompt_id}
        # 5. Download images from output

        return GenerationResult(
            success=False,
            output_paths=[],
            error_message="ComfyUI integration not yet implemented. Use ISENGARD_MODE=fast-test for testing.",
        )

    async def cancel(self) -> None:
        """Cancel ComfyUI generation."""
        self._cancelled = True
        # TODO: POST to /interrupt
        logger.info("Cancel requested for ComfyUI generation (not implemented)")

    async def list_workflows(self) -> list[str]:
        """List available workflow files."""
        # TODO: Scan workflows directory
        return ["flux-dev-lora", "sdxl-lora"]

    async def get_workflow_info(self, name: str) -> dict | None:
        """Get workflow metadata."""
        # TODO: Load from workflow JSON
        return None
