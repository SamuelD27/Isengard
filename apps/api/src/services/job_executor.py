"""
Job Executor Service

Executes training and generation jobs in-process using background tasks.
All training (AI-Toolkit) and generation (ComfyUI) logic is inlined here.
Mode selection is via simple if/else on ISENGARD_MODE.

Includes comprehensive observability:
- Structured job logging via TrainingJobLogger
- Event bus integration for real-time SSE streaming
- Sample image tracking
- Error capture with full stack traces
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

import httpx
import yaml

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import (
    get_logger,
    set_correlation_id,
    get_correlation_id,
    TrainingJobLogger,
    get_job_samples_dir,
)
from packages.shared.src.types import (
    JobStatus,
    JobType,
    TrainingJob,
    GenerationJob,
    TrainingConfig,
    GenerationConfig,
    JobProgressEvent,
    TrainingMethod,
)
from packages.shared.src.events import (
    get_event_bus,
    get_gpu_metrics,
    TrainingProgressEvent,
    TrainingStage,
    ProgressBarType,
    ArtifactEvent,
)

logger = get_logger("api.services.job_executor")


# ============================================================================
# DATACLASSES FOR RESULTS
# ============================================================================

@dataclass
class TrainingProgress:
    """Progress update from training."""
    current_step: int
    total_steps: int
    loss: float | None = None
    learning_rate: float | None = None
    message: str | None = None
    sample_path: str | None = None
    preview_path: str | None = None
    eta_seconds: int | None = None

    @property
    def percentage(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100.0


@dataclass
class TrainingResult:
    """Result of a training job."""
    success: bool
    output_path: Path | None = None
    error_message: str | None = None
    total_steps: int = 0
    final_loss: float | None = None
    training_time_seconds: float = 0.0
    samples: list[str] = field(default_factory=list)


@dataclass
class GenerationProgress:
    """Progress update from generation."""
    current_step: int
    total_steps: int
    message: str | None = None

    @property
    def percentage(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100.0


@dataclass
class GenerationResult:
    """Result of an image generation job."""
    success: bool
    output_paths: list[Path] = field(default_factory=list)
    error_message: str | None = None
    generation_time_seconds: float = 0.0
    seed_used: int | None = None


# ============================================================================
# CAPABILITIES (inlined, no plugin abstraction)
# ============================================================================

def get_training_capabilities() -> dict:
    """Return training capabilities (same for mock and production)."""
    return {
        "method": "lora",
        "backend": "ai-toolkit",
        "parameters": {
            "steps": {"type": "int", "min": 100, "max": 10000, "default": 1000, "wired": True},
            "learning_rate": {"type": "float", "min": 1e-6, "max": 0.01, "default": 0.0001, "wired": True},
            "lora_rank": {"type": "enum", "options": [4, 8, 16, 32, 64, 128], "default": 16, "wired": True},
            "resolution": {"type": "enum", "options": [512, 768, 1024], "default": 1024, "wired": True},
            "batch_size": {"type": "enum", "options": [1, 2, 4], "default": 1, "wired": True},
            "optimizer": {"type": "enum", "options": ["adamw8bit", "adamw", "prodigy"], "default": "adamw8bit", "wired": True},
            "scheduler": {"type": "enum", "options": ["constant", "cosine", "cosine_with_restarts", "linear"], "default": "cosine", "wired": True},
            "precision": {"type": "enum", "options": ["bf16", "fp16", "fp32"], "default": "bf16", "wired": True},
            "sample_every_n_steps": {"type": "int", "min": 50, "max": 1000, "default": 100, "wired": True},
            "sample_count": {"type": "int", "min": 1, "max": 5, "default": 3, "wired": True},
            "checkpoint_every_n_steps": {"type": "int", "min": 100, "max": 2000, "default": 250, "wired": True},
            "max_checkpoints": {"type": "int", "min": 1, "max": 4, "default": 2, "wired": True},
        },
    }


def get_generation_capabilities() -> dict:
    """Return generation capabilities (same for mock and production)."""
    return {
        "backend": "comfyui",
        "model_variants": ["flux-dev", "flux-schnell"],
        "toggles": {
            "use_upscale": {"supported": True, "description": "2x upscale"},
            "use_facedetailer": {"supported": False, "description": "Face enhancement"},
            "use_ipadapter": {"supported": False, "description": "Style transfer"},
            "use_controlnet": {"supported": False, "description": "Pose guidance"},
        },
        "parameters": {
            "width": {"type": "int", "min": 512, "max": 2048, "step": 64, "default": 1024, "wired": True},
            "height": {"type": "int", "min": 512, "max": 2048, "step": 64, "default": 1024, "wired": True},
            "steps": {"type": "int", "min": 1, "max": 100, "default": 20, "wired": True},
            "guidance_scale": {"type": "float", "min": 1.0, "max": 20.0, "default": 3.5, "wired": True},
            "seed": {"type": "int", "min": 0, "max": 2147483647, "default": 0, "wired": True},
            "lora_strength": {"type": "float", "min": 0.0, "max": 2.0, "default": 1.0, "wired": True},
            "model_variant": {"type": "enum", "options": ["flux-dev", "flux-schnell"], "default": "flux-dev", "wired": True},
        },
    }


# ============================================================================
# MOCK TRAINING (for fast-test mode)
# ============================================================================

def _generate_placeholder_sample(
    output_path: Path,
    step: int,
    total_steps: int,
    trigger_word: str,
    loss: float,
) -> None:
    """Generate a placeholder sample image for fast-test mode."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        width, height = 512, 512
        img = Image.new("RGB", (width, height))

        progress = step / total_steps if total_steps > 0 else 0
        for y in range(height):
            for x in range(width):
                r = int(30 + (progress * 50) + (x / width * 30))
                g = int(30 + (1 - progress) * 30 + (y / height * 20))
                b = int(50 + (progress * 100))
                img.putpixel((x, y), (r, g, b))

        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font = ImageFont.load_default()

        lines = [
            "ISENGARD SAMPLE",
            f"Step {step}/{total_steps}",
            f"Loss: {loss:.4f}",
            f"Trigger: {trigger_word}",
        ]

        y_offset = 180
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw.text((x, y_offset), line, fill=(255, 255, 255), font=font)
            y_offset += 40

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")

    except ImportError:
        # Minimal PNG without PIL
        import struct
        import zlib

        output_path.parent.mkdir(parents=True, exist_ok=True)
        progress = step / total_steps if total_steps > 0 else 0
        r, g, b = int(50 + progress * 150), int(100 + (1 - progress) * 100), 150

        signature = b'\x89PNG\r\n\x1a\n'
        width, height = 64, 64

        def create_chunk(chunk_type: bytes, data: bytes) -> bytes:
            chunk = chunk_type + data
            crc = zlib.crc32(chunk) & 0xffffffff
            return struct.pack('>I', len(data)) + chunk + struct.pack('>I', crc)

        ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
        ihdr = create_chunk(b'IHDR', ihdr_data)

        raw_data = b''
        for y in range(height):
            raw_data += b'\x00'
            for x in range(width):
                raw_data += bytes([r, g, b])

        compressed = zlib.compress(raw_data)
        idat = create_chunk(b'IDAT', compressed)
        iend = create_chunk(b'IEND', b'')

        with open(output_path, 'wb') as f:
            f.write(signature + ihdr + idat + iend)


async def _run_mock_training(
    config: TrainingConfig,
    images_dir: Path,
    output_path: Path,
    trigger_word: str,
    progress_callback: Callable[[TrainingProgress], None] | None,
    job_id: str | None,
) -> TrainingResult:
    """Run mock training for fast-test mode."""
    import random

    total_steps = config.steps
    sample_interval = getattr(config, 'sample_every_n_steps', None) or max(1, total_steps // 10)
    simulated_loss = 0.5
    samples_generated = []

    logger.info("Starting mock training", extra={
        "event": "training.start",
        "mode": "mock",
        "steps": total_steps,
        "job_id": job_id,
    })

    try:
        for step in range(1, total_steps + 1):
            await asyncio.sleep(0.05)

            noise = random.uniform(-0.01, 0.01)
            simulated_loss = max(0.01, simulated_loss * 0.998 + noise)

            # Generate sample at intervals
            if job_id and (step % sample_interval == 0 or step == total_steps):
                samples_dir = get_job_samples_dir(job_id)
                sample_path = samples_dir / f"step_{step:05d}.png"
                _generate_placeholder_sample(sample_path, step, total_steps, trigger_word, simulated_loss)
                samples_generated.append(str(sample_path))

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

        # Create placeholder model
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"MOCK_LORA_MODEL_PLACEHOLDER\n")
            f.write(f"trigger_word={trigger_word}\n".encode())
            f.write(f"steps={total_steps}\n".encode())

        logger.info("Mock training completed", extra={
            "event": "training.complete",
            "output_path": str(output_path),
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
        logger.error(f"Mock training failed: {e}")
        return TrainingResult(
            success=False,
            error_message=str(e),
        )


# ============================================================================
# AI-TOOLKIT TRAINING (for production mode)
# ============================================================================

# Regex patterns for parsing AI-Toolkit output
STEP_PATTERN = re.compile(r"step[:\s]+(\d+)[/\s]+(\d+)", re.IGNORECASE)
TQDM_PATTERN = re.compile(r"(\d+)%\|[^|]*\|\s*(\d+)/(\d+)")
FRACTION_PATTERN = re.compile(r"[\s|](\d+)/(\d+)[\s|\[]")
LOSS_PATTERN = re.compile(r"loss[:\s]+([0-9.]+)", re.IGNORECASE)


def _generate_aitoolkit_config(
    config: TrainingConfig,
    images_dir: Path,
    output_dir: Path,
    trigger_word: str,
    job_name: str,
) -> dict:
    """Generate AI-Toolkit config dictionary."""
    default_prompts = [
        f"a photo of {trigger_word}",
        f"a portrait of {trigger_word}, professional photography",
        f"{trigger_word} smiling, natural lighting",
    ]

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
                        "save_every": config.checkpoint_every_n_steps,
                        "max_step_saves_to_keep": config.max_checkpoints,
                    },
                    "datasets": [
                        {
                            "folder_path": str(images_dir),
                            "caption_ext": "txt",
                            "caption_dropout_rate": 0.05,
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
                        "dtype": "bf16",
                    },
                    "model": {
                        "name_or_path": "black-forest-labs/FLUX.1-dev",
                        "is_flux": True,
                        "quantize": True,
                    },
                    "sample": {
                        "sampler": "flowmatch",
                        "sample_every": config.sample_every_n_steps,
                        "width": config.resolution,
                        "height": config.resolution,
                        "prompts": default_prompts[:config.sample_count],
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


async def _run_aitoolkit_training(
    config: TrainingConfig,
    images_dir: Path,
    output_path: Path,
    trigger_word: str,
    progress_callback: Callable[[TrainingProgress], None] | None,
    job_id: str | None,
) -> TrainingResult:
    """Run AI-Toolkit training for production mode."""
    app_config = get_global_config()
    start_time = time.time()
    job_name = f"lora_{trigger_word.replace(' ', '_')}"

    # Create temp directory for training
    with tempfile.TemporaryDirectory(prefix="isengard_training_") as temp_dir:
        temp_path = Path(temp_dir)
        output_dir = temp_path / "output"
        output_dir.mkdir(parents=True)
        config_path = temp_path / "config.yaml"

        # Generate config
        toolkit_config = _generate_aitoolkit_config(
            config=config,
            images_dir=images_dir,
            output_dir=output_dir,
            trigger_word=trigger_word,
            job_name=job_name,
        )

        with open(config_path, "w") as f:
            yaml.dump(toolkit_config, f, default_flow_style=False)

        logger.info("Generated AI-Toolkit config", extra={
            "event": "training.config_generated",
            "config_path": str(config_path),
        })

        # Ensure caption files exist
        image_extensions = {".jpg", ".jpeg", ".png"}
        for img_path in images_dir.iterdir():
            if img_path.suffix.lower() in image_extensions:
                caption_path = img_path.with_suffix(".txt")
                if not caption_path.exists():
                    caption_path.write_text(f"a photo of {trigger_word}")

        # Run training subprocess
        aitoolkit_path = app_config.aitoolkit_path
        aitoolkit_run_py = aitoolkit_path / "run.py"
        cmd = ["python", str(aitoolkit_run_py), str(config_path)]

        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": f"{aitoolkit_path}:{os.environ.get('PYTHONPATH', '')}",
            "HF_HOME": str(app_config.cache_dir / "huggingface"),
        }

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(aitoolkit_path),
            env=env,
        )

        current_step = 0
        current_loss = None
        total_steps = config.steps

        try:
            import select
            import fcntl
            import os as os_module

            fd = process.stdout.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os_module.O_NONBLOCK)

            output_buffer = ""

            while process.poll() is None:
                readable, _, _ = select.select([process.stdout], [], [], 0.5)
                if readable:
                    try:
                        chunk = process.stdout.read(4096)
                        if chunk:
                            output_buffer += chunk

                            # Parse progress
                            step_match = STEP_PATTERN.search(output_buffer)
                            if step_match:
                                new_step = int(step_match.group(1))
                                if new_step >= current_step:
                                    current_step = new_step

                            loss_match = LOSS_PATTERN.search(output_buffer)
                            if loss_match:
                                current_loss = float(loss_match.group(1))

                            # Clear buffer periodically
                            if len(output_buffer) > 10000:
                                output_buffer = output_buffer[-5000:]

                            # Emit progress
                            if progress_callback and current_step > 0:
                                progress = TrainingProgress(
                                    current_step=current_step,
                                    total_steps=total_steps,
                                    loss=current_loss,
                                    message=f"Step {current_step}/{total_steps}",
                                )
                                if asyncio.iscoroutinefunction(progress_callback):
                                    await progress_callback(progress)
                                else:
                                    progress_callback(progress)

                    except BlockingIOError:
                        pass

            return_code = process.wait()

            if return_code != 0:
                return TrainingResult(
                    success=False,
                    error_message=f"AI-Toolkit exited with code {return_code}",
                    training_time_seconds=time.time() - start_time,
                )

            # Find output file
            lora_files = list(output_dir.glob("**/*.safetensors"))
            if not lora_files:
                return TrainingResult(
                    success=False,
                    error_message="No .safetensors file found after training",
                    training_time_seconds=time.time() - start_time,
                )

            latest_lora = max(lora_files, key=lambda p: p.stat().st_mtime)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(latest_lora, output_path)

            return TrainingResult(
                success=True,
                output_path=output_path,
                total_steps=current_step,
                final_loss=current_loss,
                training_time_seconds=time.time() - start_time,
            )

        finally:
            if process.poll() is None:
                process.terminate()


# ============================================================================
# MOCK GENERATION (for fast-test mode)
# ============================================================================

PLACEHOLDER_SVG = """<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#1a1a2e"/>
  <text x="50%" y="45%" font-family="Arial" font-size="24" fill="#e94560" text-anchor="middle">
    [Mock Image]
  </text>
  <text x="50%" y="55%" font-family="Arial" font-size="14" fill="#808080" text-anchor="middle">
    {width}x{height} - Seed: {seed}
  </text>
</svg>"""


async def _run_mock_generation(
    config: GenerationConfig,
    output_dir: Path,
    lora_path: Path | None,
    count: int,
    progress_callback: Callable[[GenerationProgress], None] | None,
) -> GenerationResult:
    """Run mock generation for fast-test mode."""
    output_paths: list[Path] = []
    total_steps = config.steps * count

    logger.info("Starting mock generation", extra={
        "event": "generation.start",
        "mode": "mock",
        "count": count,
    })

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        for i in range(count):
            for step in range(config.steps):
                await asyncio.sleep(0.01)

                if progress_callback:
                    current = i * config.steps + step + 1
                    progress_callback(GenerationProgress(
                        current_step=current,
                        total_steps=total_steps,
                        message=f"Generating image {i + 1}/{count}, step {step + 1}/{config.steps}",
                    ))

            seed = config.seed if config.seed else (42 + i)
            svg_content = PLACEHOLDER_SVG.format(width=config.width, height=config.height, seed=seed)

            output_path = output_dir / f"generated_{i + 1}_seed{seed}.svg"
            output_path.write_text(svg_content)
            output_paths.append(output_path)

        return GenerationResult(
            success=True,
            output_paths=output_paths,
            generation_time_seconds=count * config.steps * 0.01,
            seed_used=config.seed or 42,
        )

    except Exception as e:
        logger.error(f"Mock generation failed: {e}")
        return GenerationResult(
            success=False,
            output_paths=output_paths,
            error_message=str(e),
        )


# ============================================================================
# COMFYUI GENERATION (for production mode)
# ============================================================================

async def _run_comfyui_generation(
    config: GenerationConfig,
    output_dir: Path,
    lora_path: Path | None,
    count: int,
    progress_callback: Callable[[GenerationProgress], None] | None,
) -> GenerationResult:
    """Run ComfyUI generation for production mode."""
    app_config = get_global_config()
    server_url = app_config.comfyui_url.rstrip("/")
    start_time = time.time()
    output_paths: list[Path] = []

    # Workflow paths
    workflows_dir = Path(__file__).parent.parent / "workflows"

    try:
        async with httpx.AsyncClient(base_url=server_url, timeout=httpx.Timeout(30.0, read=300.0)) as client:
            # Check health
            try:
                response = await client.get("/system_stats")
                if response.status_code != 200:
                    return GenerationResult(
                        success=False,
                        error_message=f"ComfyUI health check failed: {response.status_code}",
                    )
            except httpx.ConnectError:
                return GenerationResult(
                    success=False,
                    error_message=f"Cannot connect to ComfyUI at {server_url}",
                )

            # Select workflow
            workflow_name = "flux-dev-lora" if lora_path else "flux-schnell"
            if config.use_upscale:
                workflow_name += "-upscale"

            workflow_path = workflows_dir / f"{workflow_name}.json"
            if not workflow_path.exists():
                workflow_path = workflows_dir / "flux-dev-lora.json"

            if not workflow_path.exists():
                return GenerationResult(
                    success=False,
                    error_message=f"Workflow file not found: {workflow_name}",
                )

            # Load and parse workflow
            workflow_text = workflow_path.read_text()
            # Replace template markers with defaults for parsing
            workflow_text = re.sub(r'\{\{WIDTH\}\}', '512', workflow_text)
            workflow_text = re.sub(r'\{\{HEIGHT\}\}', '512', workflow_text)
            workflow_text = re.sub(r'\{\{SEED\}\}', '0', workflow_text)
            workflow_text = re.sub(r'\{\{STEPS\}\}', '20', workflow_text)
            workflow_text = re.sub(r'\{\{CFG\}\}', '3.5', workflow_text)
            workflow_text = re.sub(r'\{\{LORA_STRENGTH\}\}', '1.0', workflow_text)
            workflow_text = re.sub(r'\{\{PROMPT\}\}', '__PROMPT__', workflow_text)
            workflow_text = re.sub(r'\{\{NEGATIVE_PROMPT\}\}', '__NEGPROMPT__', workflow_text)
            workflow_text = re.sub(r'\{\{LORA_PATH\}\}', '__LORAPATH__', workflow_text)

            workflow = json.loads(workflow_text)

            output_dir.mkdir(parents=True, exist_ok=True)

            for i in range(count):
                seed = config.seed + i if config.seed else int(time.time() * 1000) + i

                # Inject parameters
                workflow_str = json.dumps(workflow)
                workflow_str = re.sub(r'"width":\s*\d+', f'"width": {config.width}', workflow_str)
                workflow_str = re.sub(r'"height":\s*\d+', f'"height": {config.height}', workflow_str)
                workflow_str = re.sub(r'"seed":\s*\d+', f'"seed": {seed}', workflow_str)
                workflow_str = re.sub(r'"steps":\s*\d+', f'"steps": {config.steps or 20}', workflow_str)
                workflow_str = re.sub(r'"cfg":\s*[\d.]+', f'"cfg": {config.guidance_scale or 3.5}', workflow_str)
                workflow_str = re.sub(r'"guidance":\s*[\d.]+', f'"guidance": {config.guidance_scale or 3.5}', workflow_str)

                escaped_prompt = json.dumps(config.prompt)[1:-1]
                escaped_neg = json.dumps(config.negative_prompt or "")[1:-1]
                workflow_str = workflow_str.replace('__PROMPT__', escaped_prompt)
                workflow_str = workflow_str.replace('__NEGPROMPT__', escaped_neg)

                if lora_path:
                    workflow_str = workflow_str.replace('__LORAPATH__', str(lora_path))
                    workflow_str = re.sub(r'"strength_model":\s*[\d.]+', f'"strength_model": {config.lora_strength or 1.0}', workflow_str)
                else:
                    workflow_str = workflow_str.replace('__LORAPATH__', '')

                prompt = json.loads(workflow_str)

                # Submit to ComfyUI
                payload = {"prompt": prompt, "client_id": str(uuid.uuid4())}
                response = await client.post("/prompt", json=payload)

                if response.status_code != 200:
                    logger.error(f"Failed to submit prompt: {response.text}")
                    continue

                prompt_id = response.json().get("prompt_id")
                if not prompt_id:
                    continue

                logger.info(f"Submitted prompt to ComfyUI", extra={
                    "event": "comfyui.prompt.submitted",
                    "prompt_id": prompt_id,
                })

                # Wait for completion
                timeout = 300.0
                poll_start = time.time()

                while time.time() - poll_start < timeout:
                    response = await client.get(f"/history/{prompt_id}")
                    if response.status_code == 200:
                        history = response.json()
                        if prompt_id in history:
                            prompt_data = history[prompt_id]
                            if prompt_data.get("status", {}).get("completed", False):
                                break
                            # Check for outputs
                            outputs = prompt_data.get("outputs", {})
                            for node_id, node_output in outputs.items():
                                if "images" in node_output:
                                    break
                            else:
                                await asyncio.sleep(0.5)
                                continue
                            break

                    if progress_callback:
                        progress_callback(GenerationProgress(
                            current_step=i * config.steps + int((time.time() - poll_start) / timeout * config.steps),
                            total_steps=count * config.steps,
                            message=f"Generating image {i + 1}/{count}",
                        ))

                    await asyncio.sleep(0.5)

                # Download images
                response = await client.get(f"/history/{prompt_id}")
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                for img_info in node_output["images"]:
                                    filename = img_info.get("filename")
                                    if not filename:
                                        continue

                                    params = {
                                        "filename": filename,
                                        "subfolder": img_info.get("subfolder", ""),
                                        "type": img_info.get("type", "output"),
                                    }
                                    img_response = await client.get("/view", params=params)

                                    if img_response.status_code == 200:
                                        ext = Path(filename).suffix or ".png"
                                        out_path = output_dir / f"image_{i:04d}_{len(output_paths):02d}{ext}"
                                        out_path.write_bytes(img_response.content)
                                        output_paths.append(out_path)

            if not output_paths:
                return GenerationResult(
                    success=False,
                    error_message="No images generated",
                    generation_time_seconds=time.time() - start_time,
                )

            return GenerationResult(
                success=True,
                output_paths=output_paths,
                generation_time_seconds=time.time() - start_time,
                seed_used=config.seed,
            )

    except Exception as e:
        logger.error(f"ComfyUI generation failed: {e}")
        return GenerationResult(
            success=False,
            output_paths=output_paths,
            error_message=str(e),
            generation_time_seconds=time.time() - start_time,
        )


# ============================================================================
# HEALTH CHECK HELPERS
# ============================================================================

async def check_comfyui_health() -> tuple[bool, str | None]:
    """Check if ComfyUI server is available."""
    config = get_global_config()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{config.comfyui_url}/system_stats")
            if response.status_code == 200:
                return True, None
            return False, f"ComfyUI returned status {response.status_code}"
    except httpx.ConnectError:
        return False, f"Cannot connect to ComfyUI at {config.comfyui_url}"
    except Exception as e:
        return False, str(e)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _update_character_lora(character_id: str, lora_path: str) -> bool:
    """Update character record with trained LoRA path."""
    try:
        config = get_global_config()
        char_path = config.characters_dir / f"{character_id}.json"

        if not char_path.exists():
            logger.error(f"Character file not found: {char_path}")
            return False

        char_data = json.loads(char_path.read_text())
        char_data["lora_path"] = lora_path
        char_data["lora_trained_at"] = datetime.now(timezone.utc).isoformat()
        char_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        char_path.write_text(json.dumps(char_data, indent=2))

        logger.info("Character updated with LoRA path", extra={
            "event": "character.lora_updated",
            "character_id": character_id,
            "lora_path": lora_path,
        })
        return True

    except Exception as e:
        logger.error(f"Failed to update character LoRA: {e}")
        return False


# Progress tracking for SSE
_job_progress: dict[str, list[JobProgressEvent]] = {}


def get_job_progress_events(job_id: str) -> list[JobProgressEvent]:
    """Get all progress events for a job."""
    return _job_progress.get(job_id, [])


def get_latest_progress(job_id: str) -> JobProgressEvent | None:
    """Get the latest progress event for a job."""
    events = _job_progress.get(job_id, [])
    return events[-1] if events else None


def _record_progress(job_id: str, event: JobProgressEvent) -> None:
    """Record a progress event for a job."""
    if job_id not in _job_progress:
        _job_progress[job_id] = []
    _job_progress[job_id].append(event)


def clear_job_progress(job_id: str) -> None:
    """Clear progress events for a job (after completion)."""
    if job_id in _job_progress:
        del _job_progress[job_id]


# ============================================================================
# MAIN EXECUTION FUNCTIONS
# ============================================================================

async def execute_training_job(
    job: TrainingJob,
    jobs_store: dict[str, TrainingJob],
    character_trigger_word: str,
    correlation_id: str | None = None,
) -> None:
    """
    Execute a training job.

    Uses mock training in fast-test mode, AI-Toolkit in production mode.
    """
    if correlation_id:
        set_correlation_id(correlation_id)

    job_id = job.id
    app_config = get_global_config()
    event_bus = get_event_bus()
    job_logger = TrainingJobLogger(job_id, correlation_id=correlation_id, service="api")

    logger.info("Starting training job execution", extra={
        "event": "job.start",
        "job_id": job_id,
        "mode": "mock" if app_config.is_fast_test else "production",
    })

    start_time = datetime.now(timezone.utc)

    try:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.total_steps = job.config.steps
        jobs_store[job_id] = job

        # Helper to emit stage events
        async def emit_stage(stage: TrainingStage, message: str, progress_pct: float = 0.0):
            event = TrainingProgressEvent(
                job_id=job_id,
                correlation_id=correlation_id,
                status="running",
                stage=stage,
                step=job.current_step,
                steps_total=job.config.steps,
                progress_pct=progress_pct,
                message=message,
                gpu=get_gpu_metrics(),
            )
            await event_bus.publish(job_id, event)
            job_logger.info(message, event=f"stage.{stage.value}")

        job_logger.start(
            total_steps=job.config.steps,
            config_summary={
                "method": str(job.config.method),
                "steps": job.config.steps,
                "learning_rate": job.config.learning_rate,
            }
        )

        await emit_stage(TrainingStage.INITIALIZING, "Initializing training...")

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.TRAINING,
            status=JobStatus.RUNNING,
            progress=0.0,
            message="Training started",
            current_step=0,
            total_steps=job.config.steps,
        ))

        # Prepare paths
        images_dir = app_config.uploads_dir / job.character_id
        lora_dir = app_config.loras_dir / job.character_id
        lora_dir.mkdir(parents=True, exist_ok=True)

        existing_versions = list(lora_dir.glob("v*.safetensors"))
        version = len(existing_versions) + 1
        output_path = lora_dir / f"v{version}.safetensors"

        await emit_stage(TrainingStage.PREPARING_DATASET, "Preparing dataset...")

        # Progress callback
        last_sample_path = None
        last_step_time = start_time
        last_step = 0

        async def emit_progress(progress: TrainingProgress) -> None:
            nonlocal last_sample_path, last_step_time, last_step

            now = datetime.now(timezone.utc)
            elapsed_seconds = int((now - start_time).total_seconds())

            iteration_speed = None
            if progress.current_step > last_step:
                step_delta = progress.current_step - last_step
                time_delta = (now - last_step_time).total_seconds()
                if time_delta > 0:
                    iteration_speed = step_delta / time_delta
                last_step = progress.current_step
                last_step_time = now

            job.current_step = progress.current_step
            job.progress = progress.percentage
            job.elapsed_seconds = elapsed_seconds
            job.current_loss = progress.loss
            if iteration_speed is not None:
                job.iteration_speed = round(iteration_speed, 2)
            jobs_store[job_id] = job

            job_logger.step(
                current_step=progress.current_step,
                loss=progress.loss,
                lr=progress.learning_rate,
                message=progress.message,
            )

            sample_path = progress.sample_path or progress.preview_path
            if sample_path and sample_path != last_sample_path:
                last_sample_path = sample_path
                job_logger.sample_generated(sample_path, progress.current_step)
                artifact_event = ArtifactEvent(
                    job_id=job_id,
                    artifact_type="sample",
                    path=sample_path,
                    step=progress.current_step,
                )
                await event_bus.publish(job_id, artifact_event)

            progress_event = TrainingProgressEvent(
                job_id=job_id,
                correlation_id=correlation_id,
                status="running",
                stage=TrainingStage.TRAINING,
                step=progress.current_step,
                steps_total=progress.total_steps,
                progress_pct=progress.percentage,
                loss=progress.loss,
                lr=progress.learning_rate,
                iteration_speed=iteration_speed,
                gpu=get_gpu_metrics(),
                message=f"Step {progress.current_step}/{progress.total_steps}",
                sample_path=sample_path,
            )
            await event_bus.publish(job_id, progress_event)

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.TRAINING,
                status=JobStatus.RUNNING,
                progress=progress.percentage,
                message=progress.message or f"Step {progress.current_step}/{progress.total_steps}",
                current_step=progress.current_step,
                total_steps=progress.total_steps,
            ))

        def on_progress(progress: TrainingProgress) -> None:
            asyncio.create_task(emit_progress(progress))

        await emit_stage(TrainingStage.LOADING_MODEL, "Loading model...")

        # Run training based on mode
        if app_config.is_fast_test:
            result = await _run_mock_training(
                config=job.config,
                images_dir=images_dir,
                output_path=output_path,
                trigger_word=character_trigger_word,
                progress_callback=on_progress,
                job_id=job_id,
            )
        else:
            result = await _run_aitoolkit_training(
                config=job.config,
                images_dir=images_dir,
                output_path=output_path,
                trigger_word=character_trigger_word,
                progress_callback=on_progress,
                job_id=job_id,
            )

        training_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        if result.success:
            await emit_stage(TrainingStage.EXPORTING, "Exporting model...")

            config_path = lora_dir / "training_config.json"
            config_data = {
                "job_id": job_id,
                "character_id": job.character_id,
                "trigger_word": character_trigger_word,
                "config": job.config.model_dump(),
                "output_path": str(output_path),
                "final_loss": result.final_loss,
                "training_time_seconds": training_time,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            config_path.write_text(json.dumps(config_data, indent=2))

            _update_character_lora(job.character_id, str(output_path))

            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.current_step = job.total_steps
            job.completed_at = datetime.now(timezone.utc)
            job.output_path = str(output_path)
            jobs_store[job_id] = job

            job_logger.complete(
                output_path=output_path,
                training_time_seconds=training_time,
                final_loss=result.final_loss,
            )

            complete_event = TrainingProgressEvent(
                job_id=job_id,
                correlation_id=correlation_id,
                status="completed",
                stage=TrainingStage.COMPLETED,
                step=job.total_steps,
                steps_total=job.total_steps,
                progress_pct=100.0,
                loss=result.final_loss,
                message="Training completed successfully",
            )
            await event_bus.publish(job_id, complete_event)

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.TRAINING,
                status=JobStatus.COMPLETED,
                progress=100.0,
                message="Training completed successfully",
            ))

            logger.info("Training job completed", extra={
                "event": "job.complete",
                "job_id": job_id,
            })

        else:
            raise Exception(result.error_message or "Training failed")

    except Exception as e:
        error_message = str(e)
        error_type = type(e).__name__
        stack_trace = traceback.format_exc()

        job_logger.fail(error=error_message, error_type=error_type, stack_trace=stack_trace)

        logger.error(f"Training job failed: {e}", exc_info=True)

        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(timezone.utc)
        jobs_store[job_id] = job

        fail_event = TrainingProgressEvent(
            job_id=job_id,
            correlation_id=correlation_id,
            status="failed",
            stage=TrainingStage.FAILED,
            step=job.current_step,
            steps_total=job.total_steps,
            progress_pct=job.progress,
            message=f"Training failed: {error_message}",
            error=error_message,
            error_type=error_type,
        )
        await event_bus.publish(job_id, fail_event)

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.TRAINING,
            status=JobStatus.FAILED,
            progress=job.progress,
            message=f"Training failed: {error_message}",
            error=error_message,
        ))


async def execute_generation_job(
    job: GenerationJob,
    jobs_store: dict[str, GenerationJob],
    count: int = 1,
    correlation_id: str | None = None,
) -> None:
    """
    Execute an image generation job.

    Uses mock generation in fast-test mode, ComfyUI in production mode.
    """
    if correlation_id:
        set_correlation_id(correlation_id)

    job_id = job.id
    config = get_global_config()

    logger.info("Starting generation job execution", extra={
        "job_id": job_id,
        "mode": "mock" if config.is_fast_test else "production",
        "count": count,
    })

    try:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        jobs_store[job_id] = job

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.IMAGE_GENERATION,
            status=JobStatus.RUNNING,
            progress=0.0,
            message="Generation started",
        ))

        # Check health in production mode
        if not config.is_fast_test:
            healthy, error = await check_comfyui_health()
            if not healthy:
                raise Exception(error or "ComfyUI unavailable")

        # Prepare paths
        output_dir = config.outputs_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        lora_path = None
        if job.config.lora_id:
            lora_dir = config.loras_dir / job.config.lora_id
            versions = sorted(lora_dir.glob("v*.safetensors"))
            if versions:
                lora_path = versions[-1]

        # Progress callback
        def on_progress(progress: GenerationProgress) -> None:
            job.progress = progress.percentage
            jobs_store[job_id] = job

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.IMAGE_GENERATION,
                status=JobStatus.RUNNING,
                progress=progress.percentage,
                message=progress.message or "Generating...",
            ))

        # Run generation based on mode
        if config.is_fast_test:
            result = await _run_mock_generation(
                config=job.config,
                output_dir=output_dir,
                lora_path=lora_path,
                count=count,
                progress_callback=on_progress,
            )
        else:
            result = await _run_comfyui_generation(
                config=job.config,
                output_dir=output_dir,
                lora_path=lora_path,
                count=count,
                progress_callback=on_progress,
            )

        if result.success:
            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.completed_at = datetime.utcnow()
            job.output_paths = [str(p) for p in result.output_paths]
            jobs_store[job_id] = job

            _record_progress(job_id, JobProgressEvent(
                job_id=job_id,
                job_type=JobType.IMAGE_GENERATION,
                status=JobStatus.COMPLETED,
                progress=100.0,
                message=f"Generated {len(result.output_paths)} image(s)",
            ))

            logger.info("Generation job completed", extra={
                "job_id": job_id,
                "output_count": len(result.output_paths),
            })

        else:
            raise Exception(result.error_message or "Generation failed")

    except Exception as e:
        logger.error(f"Generation job failed: {e}")

        job.status = JobStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        jobs_store[job_id] = job

        _record_progress(job_id, JobProgressEvent(
            job_id=job_id,
            job_type=JobType.IMAGE_GENERATION,
            status=JobStatus.FAILED,
            progress=job.progress,
            message=f"Generation failed: {e}",
            error=str(e),
        ))
