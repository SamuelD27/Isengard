"""
AI-Toolkit Training Plugin

Production training backend using AI-Toolkit for FLUX LoRA training.
https://github.com/ostris/ai-toolkit

Requires:
- ai-toolkit installed (pip install ostris-ai-toolkit)
- FLUX.1-dev model downloaded
- GPU with 24GB+ VRAM
"""

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import time
import yaml
from pathlib import Path
from typing import Callable

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger
from packages.shared.src.types import TrainingConfig, TrainingMethod

from .interface import TrainingPlugin, TrainingProgress, TrainingResult

logger = get_logger("plugins.training.ai_toolkit")

# Regex patterns for parsing AI-Toolkit output
STEP_PATTERN = re.compile(r"step[:\s]+(\d+)[/\s]+(\d+)", re.IGNORECASE)
LOSS_PATTERN = re.compile(r"loss[:\s]+([0-9.]+)", re.IGNORECASE)
LR_PATTERN = re.compile(r"lr[:\s]+([0-9.e\-]+)", re.IGNORECASE)


class AIToolkitPlugin(TrainingPlugin):
    """
    AI-Toolkit training plugin for production LoRA training.

    Uses: https://github.com/ostris/ai-toolkit

    Requirements:
    1. ai-toolkit installed in environment
    2. FLUX.1-dev model downloaded to models cache
    3. GPU with 24GB+ VRAM (RTX 3090, A5000, etc.)
    """

    def __init__(self):
        self._cancelled = False
        self._process: subprocess.Popen | None = None
        self._config = get_global_config()

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
        - Steps are reasonable
        """
        if config.method not in self.supported_methods:
            return False, f"Method {config.method} not supported by AI-Toolkit"

        if config.resolution not in [512, 768, 1024]:
            return False, f"Resolution {config.resolution} not recommended. Use 512, 768, or 1024."

        if config.lora_rank > 64:
            logger.warning(f"High LoRA rank {config.lora_rank} may cause instability")

        if config.steps < 100:
            return False, f"Steps {config.steps} too low. Minimum 100 for meaningful training."

        if config.steps > 10000:
            logger.warning(f"High step count {config.steps} may take very long")

        return True, None

    def _generate_config(
        self,
        config: TrainingConfig,
        images_dir: Path,
        output_dir: Path,
        trigger_word: str,
        job_name: str,
    ) -> dict:
        """
        Generate AI-Toolkit config dictionary from TrainingConfig.

        Based on: https://github.com/ostris/ai-toolkit/blob/main/config/examples/train_lora_flux_24gb.yaml
        """
        return {
            "job": "extension",
            "config": {
                "name": job_name,
                "process": [
                    {
                        "type": "sd_trainer",
                        "training_folder": str(output_dir),
                        "device": "cuda:0",
                        "trigger_word": trigger_word,
                        "network": {
                            "type": "lora",
                            "linear": config.lora_rank,
                            "linear_alpha": config.lora_rank,
                        },
                        "save": {
                            "dtype": "float16",
                            "save_every": max(config.steps // 4, 100),
                            "max_step_saves_to_keep": 2,
                        },
                        "datasets": [
                            {
                                "folder_path": str(images_dir),
                                "caption_ext": "txt",
                                "caption_dropout_rate": 0.05,
                                "shuffle_tokens": False,
                                "cache_latents_to_disk": True,
                                "resolution": [config.resolution, config.resolution],
                            }
                        ],
                        "train": {
                            "batch_size": config.batch_size,
                            "steps": config.steps,
                            "gradient_accumulation_steps": 1,
                            "train_unet": True,
                            "train_text_encoder": False,
                            "gradient_checkpointing": True,
                            "noise_scheduler": "flowmatch",
                            "optimizer": "adamw8bit",
                            "lr": config.learning_rate,
                            "ema_config": {
                                "use_ema": True,
                                "ema_decay": 0.99,
                            },
                            "dtype": "bf16",
                        },
                        "model": {
                            "name_or_path": "black-forest-labs/FLUX.1-dev",
                            "is_flux": True,
                            "quantize": True,
                        },
                        "sample": {
                            "sampler": "flowmatch",
                            "sample_every": max(config.steps // 10, 50),
                            "width": config.resolution,
                            "height": config.resolution,
                            "prompts": [
                                f"a photo of {trigger_word}",
                                f"a portrait of {trigger_word}, professional photography",
                                f"{trigger_word} smiling, natural lighting",
                            ],
                            "neg": "",
                            "seed": 42,
                            "walk_seed": True,
                            "guidance_scale": 3.5,
                            "sample_steps": 20,
                        },
                    }
                ],
            },
        }

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

        Steps:
        1. Generate AI-Toolkit config YAML
        2. Prepare caption files if missing
        3. Launch training subprocess
        4. Parse progress from stdout
        5. Handle cancellation via SIGTERM
        6. Move output to expected path
        """
        self._cancelled = False
        start_time = time.time()
        job_name = f"lora_{trigger_word.replace(' ', '_')}"

        # Create temp directory for training
        with tempfile.TemporaryDirectory(prefix="isengard_training_") as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "output"
            output_dir.mkdir(parents=True)
            config_path = temp_path / "config.yaml"

            # Generate config
            toolkit_config = self._generate_config(
                config=config,
                images_dir=images_dir,
                output_dir=output_dir,
                trigger_word=trigger_word,
                job_name=job_name,
            )

            # Write config YAML
            with open(config_path, "w") as f:
                yaml.dump(toolkit_config, f, default_flow_style=False)

            logger.info("Generated AI-Toolkit config", extra={
                "event": "training.config_generated",
                "config_path": str(config_path),
                "steps": config.steps,
                "lora_rank": config.lora_rank,
            })

            # Ensure caption files exist
            await self._prepare_captions(images_dir, trigger_word)

            # Run training
            try:
                result = await self._run_training(
                    config_path=config_path,
                    total_steps=config.steps,
                    progress_callback=progress_callback,
                )

                if not result.success:
                    return result

                # Find and move output file
                lora_files = list(output_dir.glob("**/*.safetensors"))
                if not lora_files:
                    return TrainingResult(
                        success=False,
                        output_path=None,
                        error_message="Training completed but no .safetensors file found",
                    )

                # Get the latest (final) checkpoint
                latest_lora = max(lora_files, key=lambda p: p.stat().st_mtime)

                # Move to expected output path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(latest_lora, output_path)

                training_time = time.time() - start_time

                logger.info("Training completed", extra={
                    "event": "training.complete",
                    "output_path": str(output_path),
                    "training_time_seconds": training_time,
                    "final_loss": result.final_loss,
                })

                return TrainingResult(
                    success=True,
                    output_path=output_path,
                    total_steps=config.steps,
                    final_loss=result.final_loss,
                    training_time_seconds=training_time,
                )

            except asyncio.CancelledError:
                logger.info("Training cancelled")
                return TrainingResult(
                    success=False,
                    output_path=None,
                    error_message="Training cancelled",
                    training_time_seconds=time.time() - start_time,
                )
            except Exception as e:
                logger.error(f"Training failed: {e}", extra={
                    "event": "training.error",
                    "error": str(e),
                })
                return TrainingResult(
                    success=False,
                    output_path=None,
                    error_message=str(e),
                    training_time_seconds=time.time() - start_time,
                )

    async def _prepare_captions(self, images_dir: Path, trigger_word: str) -> None:
        """
        Ensure all images have caption files.
        Creates simple captions with trigger word if missing.
        """
        image_extensions = {".jpg", ".jpeg", ".png"}

        for img_path in images_dir.iterdir():
            if img_path.suffix.lower() in image_extensions:
                caption_path = img_path.with_suffix(".txt")
                if not caption_path.exists():
                    # Create simple caption with trigger word
                    caption = f"a photo of {trigger_word}"
                    caption_path.write_text(caption)
                    logger.debug(f"Created caption for {img_path.name}")

    async def _run_training(
        self,
        config_path: Path,
        total_steps: int,
        progress_callback: Callable[[TrainingProgress], None] | None = None,
    ) -> TrainingResult:
        """
        Run AI-Toolkit training subprocess and parse output.
        """
        # Find AI-Toolkit run script
        # It could be installed as a package or as a local clone
        cmd = ["python", "-m", "toolkit.job", str(config_path)]

        logger.info("Starting AI-Toolkit training", extra={
            "event": "training.subprocess_start",
            "command": " ".join(cmd),
        })

        # Start subprocess
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        current_step = 0
        current_loss = None

        try:
            # Read output line by line
            for line in iter(self._process.stdout.readline, ""):
                if self._cancelled:
                    self._process.terminate()
                    return TrainingResult(
                        success=False,
                        output_path=None,
                        error_message="Training cancelled",
                    )

                line = line.strip()
                if not line:
                    continue

                # Parse progress from output
                step_match = STEP_PATTERN.search(line)
                if step_match:
                    current_step = int(step_match.group(1))
                    total = int(step_match.group(2))
                    if total != total_steps:
                        total_steps = total  # Update if AI-Toolkit reports different

                loss_match = LOSS_PATTERN.search(line)
                if loss_match:
                    current_loss = float(loss_match.group(1))

                lr_match = LR_PATTERN.search(line)
                current_lr = float(lr_match.group(1)) if lr_match else None

                # Emit progress
                if progress_callback and current_step > 0:
                    progress = TrainingProgress(
                        current_step=current_step,
                        total_steps=total_steps,
                        loss=current_loss,
                        learning_rate=current_lr,
                        message=f"Step {current_step}/{total_steps}",
                    )
                    # Handle both sync and async callbacks
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(progress)
                    else:
                        progress_callback(progress)

                # Log significant lines
                if any(keyword in line.lower() for keyword in ["error", "exception", "saved", "sample"]):
                    logger.info(f"AI-Toolkit: {line}")

            # Wait for process to complete
            return_code = self._process.wait()

            if return_code != 0:
                return TrainingResult(
                    success=False,
                    output_path=None,
                    error_message=f"AI-Toolkit exited with code {return_code}",
                    total_steps=current_step,
                    final_loss=current_loss,
                )

            return TrainingResult(
                success=True,
                output_path=None,  # Will be filled by caller
                total_steps=current_step,
                final_loss=current_loss,
            )

        finally:
            if self._process and self._process.poll() is None:
                self._process.terminate()
            self._process = None

    async def cancel(self) -> None:
        """Cancel AI-Toolkit training."""
        self._cancelled = True
        if self._process and self._process.poll() is None:
            self._process.terminate()
            logger.info("Sent termination signal to AI-Toolkit process")

            # Give it a moment to clean up
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                logger.warning("Force killed AI-Toolkit process")
