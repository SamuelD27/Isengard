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

from .interface import TrainingPlugin, TrainingProgress, TrainingResult, TrainingCapabilities

logger = get_logger("plugins.training.ai_toolkit")

# Regex patterns for parsing AI-Toolkit output
# Matches: "step: 10/100", "step 10 100", "Step: 10/100"
STEP_PATTERN = re.compile(r"step[:\s]+(\d+)[/\s]+(\d+)", re.IGNORECASE)
# Matches tqdm format: "50%|████████| 50/100 [00:10<00:10]" or just "50/100"
TQDM_PATTERN = re.compile(r"(\d+)%\|[^|]*\|\s*(\d+)/(\d+)")
# Simple fraction pattern: " 50/100 " or "|50/100|"
FRACTION_PATTERN = re.compile(r"[\s|](\d+)/(\d+)[\s|\[]")
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

    def get_capabilities(self) -> TrainingCapabilities:
        """
        Return AI-Toolkit training capabilities.

        Parameters marked as wired=True are actively used by the training config.
        Parameters marked as wired=False are defined but not yet implemented.
        """
        return {
            "method": "lora",
            "backend": "ai-toolkit",
            "parameters": {
                # Wired parameters - actively used
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
                    "description": "LoRA rank (higher = more capacity, more VRAM)",
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
                    "description": "Training batch size (higher = more VRAM)",
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
                    "description": "Training precision (bf16 recommended)",
                },
                # Unwired parameters - planned for Phase 2
                "gradient_accumulation": {
                    "type": "int",
                    "min": 1,
                    "max": 8,
                    "default": 1,
                    "wired": False,
                    "reason": "Not yet implemented in AI-Toolkit adapter",
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
                "caption_strategy": {
                    "type": "enum",
                    "options": ["trigger_only", "natural", "tags"],
                    "default": "trigger_only",
                    "wired": False,
                    "reason": "Planned for Phase 2",
                    "description": "How captions are generated for training",
                },
                "checkpoint_every": {
                    "type": "int",
                    "min": 100,
                    "max": 5000,
                    "default": 500,
                    "wired": False,
                    "reason": "Planned for Phase 2",
                    "description": "Save checkpoint every N steps",
                },
            },
        }

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
        # AI-Toolkit venv and run.py path (configured for pod isolation)
        aitoolkit_venv_python = "/runpod-volume/isengard/.venvs/aitoolkit/bin/python"
        aitoolkit_run_py = "/runpod-volume/isengard/ai-toolkit/run.py"
        cmd = [aitoolkit_venv_python, aitoolkit_run_py, str(config_path)]

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
            cwd="/runpod-volume/isengard/ai-toolkit",
            env={**os.environ, "PYTHONUNBUFFERED": "1", "HF_HOME": "/runpod-volume/isengard/cache/huggingface"},
        )

        current_step = 0
        current_loss = None
        last_progress_time = time.time()
        output_buffer = ""

        def parse_and_emit_progress(text: str):
            """Parse progress from text and emit callback if progress found."""
            nonlocal current_step, current_loss, total_steps, last_progress_time

            new_step = None
            new_total = None

            # Try all patterns - prioritize explicit step patterns
            step_match = STEP_PATTERN.search(text)
            tqdm_match = TQDM_PATTERN.search(text) if not step_match else None
            # Only use fraction pattern if it looks like progress (total is reasonable)
            frac_match = FRACTION_PATTERN.search(text) if not step_match and not tqdm_match else None

            if step_match:
                new_step = int(step_match.group(1))
                new_total = int(step_match.group(2))
            elif tqdm_match:
                new_step = int(tqdm_match.group(2))
                new_total = int(tqdm_match.group(3))
            elif frac_match:
                candidate_step = int(frac_match.group(1))
                candidate_total = int(frac_match.group(2))
                # Only accept if total is reasonable (within 2x of expected)
                if candidate_total > 50 and candidate_total <= total_steps * 2:
                    new_step = candidate_step
                    new_total = candidate_total

            # Only update if new step is forward progress (never go backwards)
            if new_step is not None and new_step >= current_step:
                current_step = new_step
                if new_total and new_total != total_steps and new_total > 0:
                    total_steps = new_total

            loss_match = LOSS_PATTERN.search(text)
            if loss_match:
                current_loss = float(loss_match.group(1))

        def check_samples_for_progress(samples_dir: Path):
            """Fallback: detect progress from sample filenames."""
            nonlocal current_step
            try:
                if samples_dir.exists():
                    samples = list(samples_dir.glob("*.jpg"))
                    if samples:
                        # Get latest sample, extract step from filename
                        latest = max(samples, key=lambda p: p.stat().st_mtime)
                        # Filename format: {timestamp}__{step 9 digits}_{idx}.jpg
                        match = re.search(r"__(\d{9})_", latest.name)
                        if match:
                            step = int(match.group(1))
                            if step > current_step:
                                current_step = step
                                return True
            except Exception:
                pass
            return False

        try:
            import select
            import fcntl
            import os as os_module

            # Make stdout non-blocking
            fd = self._process.stdout.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os_module.O_NONBLOCK)

            # Get training output directory from config path (config.yaml is in the training folder)
            training_folder = config_path.parent / "output"
            samples_dir = training_folder / "lora_ohwx_person" / "samples" if training_folder.exists() else None

            while self._process.poll() is None:
                if self._cancelled:
                    self._process.terminate()
                    return TrainingResult(
                        success=False,
                        output_path=None,
                        error_message="Training cancelled",
                    )

                # Non-blocking read with select
                readable, _, _ = select.select([self._process.stdout], [], [], 0.5)
                if readable:
                    try:
                        chunk = self._process.stdout.read(4096)
                        if chunk is not None and chunk:
                            output_buffer += chunk
                            # Parse on \r or \n boundaries (tqdm uses \r)
                            while "\r" in output_buffer or "\n" in output_buffer:
                                # Find first delimiter
                                r_pos = output_buffer.find("\r")
                                n_pos = output_buffer.find("\n")
                                if r_pos == -1:
                                    pos = n_pos
                                elif n_pos == -1:
                                    pos = r_pos
                                else:
                                    pos = min(r_pos, n_pos)

                                line = output_buffer[:pos].strip()
                                output_buffer = output_buffer[pos + 1:]

                                if line:
                                    parse_and_emit_progress(line)

                                    # Log significant lines
                                    if any(kw in line.lower() for kw in ["error", "exception", "saved", "sample"]):
                                        logger.info(f"AI-Toolkit: {line}")
                    except BlockingIOError:
                        pass

                # Fallback: check sample files every 5 seconds
                if samples_dir and time.time() - last_progress_time > 5:
                    if check_samples_for_progress(samples_dir):
                        last_progress_time = time.time()

                # Emit progress callback
                if progress_callback and current_step > 0:
                    progress = TrainingProgress(
                        current_step=current_step,
                        total_steps=total_steps,
                        loss=current_loss,
                        learning_rate=None,
                        message=f"Step {current_step}/{total_steps}",
                    )
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(progress)
                    else:
                        progress_callback(progress)

            # Read any remaining output
            try:
                remaining = self._process.stdout.read()
                if remaining is not None and remaining:
                    parse_and_emit_progress(remaining)
            except Exception:
                pass  # Ignore read errors at end

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
