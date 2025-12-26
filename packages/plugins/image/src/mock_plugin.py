"""
Mock Image Plugin

Used for fast-test mode to validate wiring without actual generation.
Returns placeholder images.
"""

import asyncio
from pathlib import Path
from typing import Callable

from packages.shared.src.logging import get_logger
from packages.shared.src.types import GenerationConfig

from .interface import ImagePlugin, GenerationProgress, GenerationResult

logger = get_logger("plugins.image.mock")


# Simple SVG placeholder template
PLACEHOLDER_SVG = """<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#1a1a2e"/>
  <text x="50%" y="45%" font-family="Arial" font-size="24" fill="#e94560" text-anchor="middle">
    [Mock Image]
  </text>
  <text x="50%" y="55%" font-family="Arial" font-size="14" fill="#808080" text-anchor="middle">
    {width}x{height} - Seed: {seed}
  </text>
  <text x="50%" y="65%" font-family="Arial" font-size="10" fill="#606060" text-anchor="middle">
    Fast-test mode
  </text>
</svg>"""


class MockImagePlugin(ImagePlugin):
    """
    Mock image plugin for testing.

    Generates placeholder SVG images without actual computation.
    Used in fast-test mode.
    """

    def __init__(self):
        self._cancelled = False
        self._running = False

    @property
    def name(self) -> str:
        return "mock"

    async def check_health(self) -> tuple[bool, str | None]:
        """Always healthy in mock mode."""
        return True, None

    async def generate(
        self,
        config: GenerationConfig,
        output_dir: Path,
        lora_path: Path | None = None,
        count: int = 1,
        progress_callback: Callable[[GenerationProgress], None] | None = None,
    ) -> GenerationResult:
        """
        Generate mock placeholder images.
        """
        self._cancelled = False
        self._running = True

        logger.info("Starting mock image generation", extra={
            "prompt": config.prompt[:50] + "..." if len(config.prompt) > 50 else config.prompt,
            "size": f"{config.width}x{config.height}",
            "count": count,
            "lora_path": str(lora_path) if lora_path else None,
        })

        output_paths: list[Path] = []
        total_steps = config.steps * count

        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            for i in range(count):
                if self._cancelled:
                    logger.info("Generation cancelled by user")
                    return GenerationResult(
                        success=False,
                        output_paths=output_paths,
                        error_message="Generation cancelled by user",
                    )

                # Simulate generation steps
                for step in range(config.steps):
                    if self._cancelled:
                        break

                    await asyncio.sleep(0.01)  # Fast in mock mode

                    if progress_callback:
                        current = i * config.steps + step + 1
                        progress_callback(GenerationProgress(
                            current_step=current,
                            total_steps=total_steps,
                            message=f"Generating image {i + 1}/{count}, step {step + 1}/{config.steps}",
                        ))

                # Determine seed
                seed = config.seed if config.seed is not None else (42 + i)

                # Create placeholder image
                svg_content = PLACEHOLDER_SVG.format(
                    width=config.width,
                    height=config.height,
                    seed=seed,
                )

                output_path = output_dir / f"generated_{i + 1}_seed{seed}.svg"
                output_path.write_text(svg_content)
                output_paths.append(output_path)

                logger.info(f"Generated mock image {i + 1}/{count}", extra={
                    "output_path": str(output_path),
                    "seed": seed,
                })

            return GenerationResult(
                success=True,
                output_paths=output_paths,
                generation_time_seconds=count * config.steps * 0.01,
                seed_used=config.seed or 42,
            )

        except Exception as e:
            logger.error(f"Mock generation failed: {e}", extra={"error": str(e)})
            return GenerationResult(
                success=False,
                output_paths=output_paths,
                error_message=str(e),
            )
        finally:
            self._running = False

    async def cancel(self) -> None:
        """Cancel mock generation."""
        if self._running:
            self._cancelled = True
            logger.info("Cancel requested for mock generation")

    async def list_workflows(self) -> list[str]:
        """Return mock workflow list."""
        return ["flux-dev-lora", "sdxl-lora", "flux-schnell"]

    async def get_workflow_info(self, name: str) -> dict | None:
        """Return mock workflow info."""
        workflows = {
            "flux-dev-lora": {
                "name": "flux-dev-lora",
                "description": "FLUX.1-dev with LoRA support",
                "model": "FLUX.1-dev",
                "supports_lora": True,
            },
            "sdxl-lora": {
                "name": "sdxl-lora",
                "description": "SDXL with LoRA support",
                "model": "SDXL 1.0",
                "supports_lora": True,
            },
            "flux-schnell": {
                "name": "flux-schnell",
                "description": "FLUX.1-schnell for fast generation",
                "model": "FLUX.1-schnell",
                "supports_lora": False,
            },
        }
        return workflows.get(name)
