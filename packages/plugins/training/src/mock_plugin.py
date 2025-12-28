"""
Mock Training Plugin

Used for fast-test mode to validate wiring without actual GPU training.
Creates placeholder model files and simulates progress.
Generates sample images at configurable intervals for UI testing.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from packages.shared.src.logging import get_logger, get_job_samples_dir
from packages.shared.src.types import TrainingConfig, TrainingMethod

from .interface import TrainingPlugin, TrainingProgress, TrainingResult, TrainingCapabilities

logger = get_logger("plugins.training.mock")


def _generate_placeholder_sample(
    output_path: Path,
    step: int,
    total_steps: int,
    trigger_word: str,
    loss: float,
) -> None:
    """
    Generate a placeholder sample image for fast-test mode.

    Creates a simple PNG with text overlay showing training progress.
    Does not require PIL - uses raw PNG generation for minimal dependencies.
    """
    try:
        # Try to use PIL if available for nicer images
        from PIL import Image, ImageDraw, ImageFont

        # Create 512x512 gradient image
        width, height = 512, 512
        img = Image.new("RGB", (width, height))

        # Create gradient based on step progress
        progress = step / total_steps if total_steps > 0 else 0
        for y in range(height):
            for x in range(width):
                # Create a gradient that shifts color based on progress
                r = int(30 + (progress * 50) + (x / width * 30))
                g = int(30 + (1 - progress) * 30 + (y / height * 20))
                b = int(50 + (progress * 100))
                img.putpixel((x, y), (r, g, b))

        # Add text overlay
        draw = ImageDraw.Draw(img)

        # Use default font
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except:
            font = ImageFont.load_default()
            small_font = font

        # Draw sample info
        lines = [
            "ISENGARD SAMPLE",
            f"Step {step}/{total_steps}",
            f"Loss: {loss:.4f}",
            f"Trigger: {trigger_word}",
            datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        ]

        y_offset = 180
        for line in lines:
            # Get text bounding box
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw.text((x, y_offset), line, fill=(255, 255, 255), font=font)
            y_offset += 40

        # Add progress bar
        bar_width = 400
        bar_height = 20
        bar_x = (width - bar_width) // 2
        bar_y = height - 80

        # Background
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=(50, 50, 50))
        # Progress
        fill_width = int(bar_width * progress)
        draw.rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], fill=(100, 200, 100))

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")

        logger.debug(f"Generated PIL sample image at {output_path}")

    except ImportError:
        # Fallback: create minimal valid PNG without PIL
        _generate_minimal_png(output_path, step, total_steps)


def _generate_minimal_png(output_path: Path, step: int, total_steps: int) -> None:
    """
    Generate a minimal valid PNG without external dependencies.

    Creates a 1x1 pixel colored based on progress.
    """
    import struct
    import zlib

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Calculate color based on progress
    progress = step / total_steps if total_steps > 0 else 0
    r = int(50 + progress * 150)
    g = int(100 + (1 - progress) * 100)
    b = int(150)

    # PNG signature
    signature = b'\x89PNG\r\n\x1a\n'

    # IHDR chunk (image header)
    width = 64
    height = 64

    def create_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', crc)

    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr = create_chunk(b'IHDR', ihdr_data)

    # IDAT chunk (image data)
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'  # Filter byte
        for x in range(width):
            raw_data += bytes([r, g, b])

    compressed = zlib.compress(raw_data)
    idat = create_chunk(b'IDAT', compressed)

    # IEND chunk
    iend = create_chunk(b'IEND', b'')

    # Write PNG
    with open(output_path, 'wb') as f:
        f.write(signature + ihdr + idat + iend)

    logger.debug(f"Generated minimal sample PNG at {output_path}")


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

    def get_capabilities(self) -> TrainingCapabilities:
        """
        Return mock training capabilities.

        Mirrors AI-Toolkit capabilities for consistent fast-test behavior.
        All parameters marked as wired to allow full UI testing.
        """
        return {
            "method": "lora",
            "backend": "mock",
            "parameters": {
                "steps": {
                    "type": "int",
                    "min": 100,
                    "max": 10000,
                    "default": 1000,
                    "wired": True,
                    "description": "Total training steps",
                },
                "learning_rate": {
                    "type": "float",
                    "min": 1e-6,
                    "max": 0.01,
                    "step": 1e-6,
                    "default": 0.0001,
                    "wired": True,
                    "description": "Learning rate for optimizer",
                },
                "lora_rank": {
                    "type": "enum",
                    "options": [4, 8, 16, 32, 64, 128],
                    "default": 16,
                    "wired": True,
                    "description": "LoRA rank (higher = more capacity)",
                },
                "resolution": {
                    "type": "enum",
                    "options": [512, 768, 1024],
                    "default": 1024,
                    "wired": True,
                    "description": "Training image resolution",
                },
                "batch_size": {
                    "type": "enum",
                    "options": [1, 2, 4],
                    "default": 1,
                    "wired": True,
                    "description": "Training batch size",
                },
                "optimizer": {
                    "type": "enum",
                    "options": ["adamw8bit", "adamw", "prodigy"],
                    "default": "adamw8bit",
                    "wired": True,
                    "description": "Optimizer algorithm",
                },
                "scheduler": {
                    "type": "enum",
                    "options": ["constant", "cosine", "cosine_with_restarts", "linear"],
                    "default": "cosine",
                    "wired": True,
                    "description": "Learning rate scheduler",
                },
                "precision": {
                    "type": "enum",
                    "options": ["bf16", "fp16", "fp32"],
                    "default": "bf16",
                    "wired": True,
                    "description": "Training precision",
                },
                # Unwired parameters (for testing UI behavior)
                "gradient_accumulation": {
                    "type": "int",
                    "min": 1,
                    "max": 8,
                    "default": 1,
                    "wired": False,
                    "reason": "Not implemented in mock plugin",
                    "description": "Gradient accumulation steps",
                },
                "network_alpha": {
                    "type": "int",
                    "min": 1,
                    "max": 128,
                    "default": 16,
                    "wired": False,
                    "reason": "Planned for Phase 2",
                    "description": "LoRA alpha scaling factor",
                },
            },
        }

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
        job_id: str | None = None,
        sample_interval: int | None = None,
    ) -> TrainingResult:
        """
        Simulate training with progress updates.

        Creates a placeholder .safetensors file.
        Generates sample images at configured intervals.

        Args:
            config: Training configuration
            images_dir: Directory containing training images
            output_path: Where to save the trained model
            trigger_word: Trigger word for the LoRA
            progress_callback: Callback for progress updates
            job_id: Optional job ID for sample image organization
            sample_interval: Generate sample every N steps (default: 10% intervals)
        """
        self._cancelled = False
        self._running = True

        total_steps = config.steps

        # Calculate sample interval (default: generate at 10%, 20%, ... 90%, 100%)
        if sample_interval is None:
            sample_interval = max(1, total_steps // 10)

        # Ensure at least 2 samples for Fast-Test mode (early and late)
        if total_steps < 20:
            sample_interval = max(1, total_steps // 3)

        logger.info("Starting mock training", extra={
            "event": "training.start",
            "images_dir": str(images_dir),
            "output_path": str(output_path),
            "trigger_word": trigger_word,
            "steps": config.steps,
            "sample_interval": sample_interval,
            "job_id": job_id,
        })

        simulated_loss = 0.5
        samples_generated = []

        try:
            for step in range(1, total_steps + 1):
                if self._cancelled:
                    logger.info("Training cancelled by user", extra={
                        "event": "training.cancelled",
                        "step": step,
                    })
                    return TrainingResult(
                        success=False,
                        output_path=None,
                        error_message="Training cancelled by user",
                    )

                # Simulate step time (fast in mock mode)
                await asyncio.sleep(0.05)

                # Decay loss over time with some noise
                import random
                noise = random.uniform(-0.01, 0.01)
                simulated_loss = simulated_loss * 0.998 + noise
                simulated_loss = max(0.01, simulated_loss)  # Floor at 0.01

                # Generate sample image at intervals
                if step % sample_interval == 0 or step == total_steps:
                    sample_path = self._generate_sample(
                        job_id=job_id,
                        step=step,
                        total_steps=total_steps,
                        trigger_word=trigger_word,
                        loss=simulated_loss,
                    )
                    if sample_path:
                        samples_generated.append(str(sample_path))
                        logger.info(f"Sample generated at step {step}", extra={
                            "event": "training.sample",
                            "step": step,
                            "sample_path": str(sample_path),
                        })

                if progress_callback:
                    progress = TrainingProgress(
                        current_step=step,
                        total_steps=total_steps,
                        loss=simulated_loss,
                        learning_rate=config.learning_rate,
                        message=f"Training step {step}/{total_steps}",
                        sample_path=samples_generated[-1] if step % sample_interval == 0 and samples_generated else None,
                    )
                    progress_callback(progress)

                # Log every 10%
                if step % (total_steps // 10 or 1) == 0:
                    logger.info(f"Training progress: {step}/{total_steps}", extra={
                        "event": "training.progress",
                        "step": step,
                        "total": total_steps,
                        "loss": simulated_loss,
                        "progress_pct": round(step / total_steps * 100, 1),
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
                f.write(f"samples_generated={len(samples_generated)}\n".encode())

            logger.info("Mock training completed successfully", extra={
                "event": "training.complete",
                "output_path": str(output_path),
                "final_loss": simulated_loss,
                "samples_generated": len(samples_generated),
            })

            return TrainingResult(
                success=True,
                output_path=output_path,
                total_steps=total_steps,
                final_loss=simulated_loss,
                training_time_seconds=total_steps * 0.05,
                samples=samples_generated,
            )

        except Exception as e:
            import traceback
            stack_trace = traceback.format_exc()
            logger.error(f"Mock training failed: {e}", extra={
                "event": "training.error",
                "error": str(e),
                "error_type": type(e).__name__,
                "stack_trace": stack_trace,
            })
            return TrainingResult(
                success=False,
                output_path=None,
                error_message=str(e),
            )
        finally:
            self._running = False

    def _generate_sample(
        self,
        job_id: str | None,
        step: int,
        total_steps: int,
        trigger_word: str,
        loss: float,
    ) -> Path | None:
        """Generate a sample image for the current training step."""
        if job_id is None:
            # No job ID, can't determine output path
            return None

        try:
            samples_dir = get_job_samples_dir(job_id)
            sample_path = samples_dir / f"step_{step:05d}.png"

            _generate_placeholder_sample(
                output_path=sample_path,
                step=step,
                total_steps=total_steps,
                trigger_word=trigger_word,
                loss=loss,
            )

            return sample_path
        except Exception as e:
            logger.warning(f"Failed to generate sample at step {step}: {e}")
            return None

    async def cancel(self) -> None:
        """Cancel the mock training."""
        if self._running:
            self._cancelled = True
            logger.info("Cancel requested for mock training")
