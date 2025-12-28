"""
ComfyUI Image Plugin

Production image generation backend using ComfyUI API.
https://github.com/comfyanonymous/ComfyUI

Requires:
- Running ComfyUI server (default: http://localhost:8188)
- Workflow JSON templates in data/comfyui/workflows/
- FLUX/SDXL models downloaded
"""

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import httpx

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger
from packages.shared.src.types import GenerationConfig

from .interface import ImagePlugin, GenerationProgress, GenerationResult, ImageCapabilities

logger = get_logger("plugins.image.comfyui")

# Default workflow injection markers
PROMPT_MARKER = "{{PROMPT}}"
NEGATIVE_PROMPT_MARKER = "{{NEGATIVE_PROMPT}}"
SEED_MARKER = "{{SEED}}"
WIDTH_MARKER = "{{WIDTH}}"
HEIGHT_MARKER = "{{HEIGHT}}"
STEPS_MARKER = "{{STEPS}}"
CFG_MARKER = "{{CFG}}"
LORA_PATH_MARKER = "{{LORA_PATH}}"
LORA_STRENGTH_MARKER = "{{LORA_STRENGTH}}"


class ComfyUIPlugin(ImagePlugin):
    """
    ComfyUI image generation plugin.

    Connects to a ComfyUI server and executes workflows via its REST API.
    Supports:
    - FLUX.1-dev with LoRA
    - SDXL with LoRA
    - ControlNet/IP-Adapter toggles
    - Face detailer
    - Upscaling
    """

    def __init__(self, server_url: str | None = None):
        config = get_global_config()
        self.server_url = (server_url or config.comfyui_url).rstrip("/")
        # Bundled workflows (in source)
        self._bundled_workflows_dir = Path(__file__).parent.parent / "workflows"
        # Custom workflows (in volume_root, can override bundled)
        self._custom_workflows_dir = config.volume_root / "comfyui" / "workflows"
        self._cancelled = False
        self._current_prompt_id: str | None = None
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "comfyui"

    def get_capabilities(self) -> ImageCapabilities:
        """
        Return ComfyUI image generation capabilities.

        Toggles reflect which workflow variants are currently implemented.
        Parameters describe supported generation options.
        """
        return {
            "backend": "comfyui",
            "model_variants": ["flux-dev", "flux-schnell"],
            "toggles": {
                "use_upscale": {
                    "supported": True,
                    "description": "2x upscale with RealESRGAN",
                },
                "use_facedetailer": {
                    "supported": False,
                    "reason": "Workflow not implemented",
                    "description": "Face enhancement with FaceDetailer",
                },
                "use_ipadapter": {
                    "supported": False,
                    "reason": "Workflow not implemented",
                    "description": "Style transfer with IP-Adapter",
                },
                "use_controlnet": {
                    "supported": False,
                    "reason": "Workflow not implemented",
                    "description": "Pose/structure guidance with ControlNet",
                },
            },
            "parameters": {
                "width": {
                    "type": "int",
                    "min": 512,
                    "max": 2048,
                    "step": 64,
                    "default": 1024,
                    "wired": True,
                    "description": "Output image width",
                },
                "height": {
                    "type": "int",
                    "min": 512,
                    "max": 2048,
                    "step": 64,
                    "default": 1024,
                    "wired": True,
                    "description": "Output image height",
                },
                "steps": {
                    "type": "int",
                    "min": 1,
                    "max": 100,
                    "default": 20,
                    "wired": True,
                    "description": "Number of sampling steps",
                },
                "guidance_scale": {
                    "type": "float",
                    "min": 1.0,
                    "max": 20.0,
                    "step": 0.5,
                    "default": 3.5,
                    "wired": True,
                    "description": "Classifier-free guidance scale",
                },
                "seed": {
                    "type": "int",
                    "min": 0,
                    "max": 2147483647,
                    "default": 0,
                    "wired": True,
                    "description": "Random seed (0 for random)",
                },
                "lora_strength": {
                    "type": "float",
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.1,
                    "default": 1.0,
                    "wired": True,
                    "description": "LoRA model strength",
                },
                "model_variant": {
                    "type": "enum",
                    "options": ["flux-dev", "flux-schnell"],
                    "default": "flux-dev",
                    "wired": True,
                    "description": "Base model to use",
                },
            },
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=httpx.Timeout(30.0, read=300.0),
            )
        return self._client

    async def _close_client(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def check_health(self) -> tuple[bool, str | None]:
        """
        Check if ComfyUI server is available.

        Makes request to /system_stats endpoint.
        """
        try:
            client = await self._get_client()
            response = await client.get("/system_stats")

            if response.status_code == 200:
                stats = response.json()
                logger.info("ComfyUI health check passed", extra={
                    "event": "comfyui.health.ok",
                    "gpu_name": stats.get("devices", [{}])[0].get("name", "unknown"),
                })
                return True, None
            else:
                return False, f"ComfyUI returned status {response.status_code}"

        except httpx.ConnectError:
            return False, f"Cannot connect to ComfyUI at {self.server_url}"
        except Exception as e:
            logger.error(f"ComfyUI health check failed: {e}")
            return False, str(e)

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

        Steps:
        1. Load appropriate workflow template
        2. Inject parameters (prompt, size, seed, LoRA)
        3. Submit via POST /prompt
        4. Poll /history for completion
        5. Download generated images
        """
        self._cancelled = False
        start_time = time.time()
        output_paths: list[Path] = []

        try:
            # Select workflow based on config
            workflow_name = self._select_workflow(config, lora_path)
            workflow = await self._load_workflow(workflow_name)

            if workflow is None:
                return GenerationResult(
                    success=False,
                    output_paths=[],
                    error_message=f"Workflow '{workflow_name}' not found",
                )

            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)

            # Generate images
            for i in range(count):
                if self._cancelled:
                    break

                # Use different seed for each image
                seed = config.seed + i if config.seed else int(time.time() * 1000) + i

                # Inject parameters into workflow
                prompt = self._inject_parameters(
                    workflow=workflow,
                    config=config,
                    seed=seed,
                    lora_path=lora_path,
                )

                # Submit to ComfyUI
                prompt_id = await self._submit_prompt(prompt)
                if not prompt_id:
                    continue

                self._current_prompt_id = prompt_id

                logger.info(f"Submitted prompt to ComfyUI", extra={
                    "event": "comfyui.prompt.submitted",
                    "prompt_id": prompt_id,
                    "image_index": i + 1,
                    "total": count,
                })

                # Wait for completion with progress updates
                result = await self._wait_for_completion(
                    prompt_id=prompt_id,
                    total_images=count,
                    current_image=i + 1,
                    progress_callback=progress_callback,
                )

                if result is None:
                    continue

                # Download generated images
                images = await self._download_images(prompt_id, output_dir, i)
                output_paths.extend(images)

            generation_time = time.time() - start_time

            if not output_paths:
                return GenerationResult(
                    success=False,
                    output_paths=[],
                    error_message="No images generated",
                    generation_time_seconds=generation_time,
                )

            logger.info("Generation completed", extra={
                "event": "comfyui.generation.complete",
                "output_count": len(output_paths),
                "generation_time_seconds": generation_time,
            })

            return GenerationResult(
                success=True,
                output_paths=output_paths,
                generation_time_seconds=generation_time,
                seed_used=config.seed,
            )

        except asyncio.CancelledError:
            return GenerationResult(
                success=False,
                output_paths=output_paths,
                error_message="Generation cancelled",
                generation_time_seconds=time.time() - start_time,
            )
        except Exception as e:
            logger.error(f"Generation failed: {e}", extra={
                "event": "comfyui.generation.error",
                "error": str(e),
            })
            return GenerationResult(
                success=False,
                output_paths=output_paths,
                error_message=str(e),
                generation_time_seconds=time.time() - start_time,
            )

    def _select_workflow(self, config: GenerationConfig, lora_path: Path | None) -> str:
        """Select appropriate workflow based on config."""
        # Determine base workflow
        if lora_path:
            base = "flux-dev-lora"
        else:
            base = "flux-schnell"

        # Add modifiers for features
        modifiers = []
        if config.use_controlnet:
            modifiers.append("controlnet")
        if config.use_ipadapter:
            modifiers.append("ipadapter")
        if config.use_facedetailer:
            modifiers.append("facedetailer")
        if config.use_upscale:
            modifiers.append("upscale")

        if modifiers:
            return f"{base}-{'-'.join(modifiers)}"
        return base

    async def _load_workflow(self, name: str) -> dict | None:
        """Load workflow JSON from file.

        Checks custom workflows directory first (allows user overrides),
        then falls back to bundled workflows.
        """
        workflow_path = None

        # Search order: custom exact -> custom base -> bundled exact -> bundled base -> bundled default
        search_dirs = [self._custom_workflows_dir, self._bundled_workflows_dir]

        for workflows_dir in search_dirs:
            if not workflows_dir.exists():
                continue

            # Try exact match
            candidate = workflows_dir / f"{name}.json"
            if candidate.exists():
                workflow_path = candidate
                break

            # Try base workflow (e.g., flux-dev-lora from flux-dev-lora-controlnet)
            if "-" in name:
                parts = name.split("-")
                if len(parts) >= 2:
                    base_name = f"{parts[0]}-{parts[1]}"
                    if len(parts) > 2:
                        base_name += f"-{parts[2]}"  # Include lora part
                    candidate = workflows_dir / f"{base_name}.json"
                    if candidate.exists():
                        workflow_path = candidate
                        break

        # Final fallback: bundled default
        if workflow_path is None:
            workflow_path = self._bundled_workflows_dir / "flux-dev-lora.json"
            if not workflow_path.exists():
                logger.error(f"Workflow not found: {name}", extra={
                    "event": "comfyui.workflow.not_found",
                    "workflow_name": name,
                    "search_paths": [str(d) for d in search_dirs],
                })
                return None

        try:
            with open(workflow_path) as f:
                workflow_text = f.read()
            
            # Pre-process template markers to valid JSON placeholders before parsing
            # Replace numeric placeholders with valid JSON numbers
            workflow_text = re.sub(r'\{\{WIDTH\}\}', '512', workflow_text)
            workflow_text = re.sub(r'\{\{HEIGHT\}\}', '512', workflow_text)
            workflow_text = re.sub(r'\{\{SEED\}\}', '0', workflow_text)
            workflow_text = re.sub(r'\{\{STEPS\}\}', '20', workflow_text)
            workflow_text = re.sub(r'\{\{CFG\}\}', '3.5', workflow_text)
            workflow_text = re.sub(r'\{\{LORA_STRENGTH\}\}', '1.0', workflow_text)
            # String placeholders are already in quotes, just use placeholder text
            workflow_text = re.sub(r'\{\{PROMPT\}\}', '__PROMPT_PLACEHOLDER__', workflow_text)
            workflow_text = re.sub(r'\{\{NEGATIVE_PROMPT\}\}', '__NEGATIVE_PROMPT_PLACEHOLDER__', workflow_text)
            workflow_text = re.sub(r'\{\{LORA_PATH\}\}', '__LORA_PATH_PLACEHOLDER__', workflow_text)
            
            workflow = json.loads(workflow_text)
            logger.debug(f"Loaded workflow: {workflow_path.name} from {workflow_path.parent}")
            return workflow
        except json.JSONDecodeError as e:
            logger.error(f"Invalid workflow JSON: {e}")
            return None

    def _inject_parameters(
        self,
        workflow: dict,
        config: GenerationConfig,
        seed: int,
        lora_path: Path | None,
    ) -> dict:
        """
        Inject generation parameters into workflow.

        Replaces marker strings with actual values.
        """
        # Convert to string for simple replacement
        workflow_str = json.dumps(workflow)

        # Handle numeric fields - replace default values with actual config values
        workflow_str = workflow_str.replace('"width": 512', f'"width": {config.width}')
        workflow_str = workflow_str.replace('"height": 512', f'"height": {config.height}')
        workflow_str = workflow_str.replace('"seed": 0', f'"seed": {seed}')
        workflow_str = workflow_str.replace('"steps": 20', f'"steps": {config.steps or 20}')
        workflow_str = workflow_str.replace('"steps": 4', f'"steps": {config.steps or 4}')  # flux-schnell uses 4 steps
        workflow_str = workflow_str.replace('"cfg": 3.5', f'"cfg": {config.guidance_scale or 3.5}')
        workflow_str = workflow_str.replace('"cfg": 1.0', f'"cfg": {config.guidance_scale or 1.0}')  # flux-schnell uses 1.0
        workflow_str = workflow_str.replace('"guidance": 3.5', f'"guidance": {config.guidance_scale or 3.5}')
        
        # Replace string placeholders for prompts
        escaped_prompt = json.dumps(config.prompt)[1:-1]  # Remove quotes and escape
        escaped_neg_prompt = json.dumps(config.negative_prompt or "")[1:-1]
        
        workflow_str = workflow_str.replace('__PROMPT_PLACEHOLDER__', escaped_prompt)
        workflow_str = workflow_str.replace('__NEGATIVE_PROMPT_PLACEHOLDER__', escaped_neg_prompt)
        
        # Handle LoRA path placeholder
        if lora_path:
            workflow_str = workflow_str.replace('__LORA_PATH_PLACEHOLDER__', str(lora_path))
            workflow_str = workflow_str.replace('"strength_model": 1.0', f'"strength_model": {config.lora_strength or 1.0}')
            workflow_str = workflow_str.replace('"strength_clip": 1.0', f'"strength_clip": {config.lora_strength or 1.0}')
        else:
            workflow_str = workflow_str.replace('__LORA_PATH_PLACEHOLDER__', '')

        return json.loads(workflow_str)

    async def _submit_prompt(self, prompt: dict) -> str | None:
        """Submit prompt to ComfyUI and return prompt_id."""
        try:
            client = await self._get_client()

            # ComfyUI expects prompt wrapped in a specific format
            payload = {
                "prompt": prompt,
                "client_id": str(uuid.uuid4()),
            }

            response = await client.post("/prompt", json=payload)

            if response.status_code == 200:
                data = response.json()
                return data.get("prompt_id")
            else:
                logger.error(f"Failed to submit prompt: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error submitting prompt: {e}")
            return None

    async def _wait_for_completion(
        self,
        prompt_id: str,
        total_images: int,
        current_image: int,
        progress_callback: Callable[[GenerationProgress], None] | None,
        timeout: float = 300.0,
    ) -> dict | None:
        """
        Wait for prompt execution to complete.

        Polls /history endpoint for status updates.
        """
        client = await self._get_client()
        start_time = time.time()
        last_step = 0

        while time.time() - start_time < timeout:
            if self._cancelled:
                return None

            try:
                response = await client.get(f"/history/{prompt_id}")

                if response.status_code == 200:
                    history = response.json()

                    if prompt_id in history:
                        prompt_data = history[prompt_id]

                        # Check for completion
                        if prompt_data.get("status", {}).get("completed", False):
                            return prompt_data

                        # Check for error
                        if prompt_data.get("status", {}).get("status_str") == "error":
                            logger.error("ComfyUI execution error")
                            return None

                        # Extract progress from executing node
                        outputs = prompt_data.get("outputs", {})
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                # Has output, likely complete
                                return prompt_data

                # Poll queue for progress info
                queue_response = await client.get("/queue")
                if queue_response.status_code == 200:
                    queue_data = queue_response.json()
                    running = queue_data.get("queue_running", [])

                    for item in running:
                        if len(item) > 2 and item[1] == prompt_id:
                            # Extract current node progress if available
                            current_node = item[2] if len(item) > 2 else {}
                            step = current_node.get("value", last_step)

                            if step != last_step and progress_callback:
                                last_step = step
                                total_steps = current_node.get("max", 20)
                                progress = GenerationProgress(
                                    current_step=step,
                                    total_steps=total_steps,
                                    message=f"Image {current_image}/{total_images} - Step {step}/{total_steps}",
                                )
                                if asyncio.iscoroutinefunction(progress_callback):
                                    await progress_callback(progress)
                                else:
                                    progress_callback(progress)

            except Exception as e:
                logger.warning(f"Error polling status: {e}")

            await asyncio.sleep(0.5)

        logger.error(f"Timeout waiting for prompt {prompt_id}")
        return None

    async def _download_images(
        self,
        prompt_id: str,
        output_dir: Path,
        batch_index: int,
    ) -> list[Path]:
        """Download generated images from ComfyUI."""
        downloaded: list[Path] = []
        client = await self._get_client()

        try:
            response = await client.get(f"/history/{prompt_id}")
            if response.status_code != 200:
                return downloaded

            history = response.json()
            if prompt_id not in history:
                return downloaded

            outputs = history[prompt_id].get("outputs", {})

            for node_id, node_output in outputs.items():
                if "images" not in node_output:
                    continue

                for img_info in node_output["images"]:
                    filename = img_info.get("filename")
                    subfolder = img_info.get("subfolder", "")
                    img_type = img_info.get("type", "output")

                    if not filename:
                        continue

                    # Build view URL
                    params = {
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": img_type,
                    }

                    img_response = await client.get("/view", params=params)

                    if img_response.status_code == 200:
                        # Save image
                        ext = Path(filename).suffix or ".png"
                        output_path = output_dir / f"image_{batch_index:04d}_{len(downloaded):02d}{ext}"

                        output_path.write_bytes(img_response.content)
                        downloaded.append(output_path)

                        logger.debug(f"Downloaded image: {output_path.name}")

        except Exception as e:
            logger.error(f"Error downloading images: {e}")

        return downloaded

    async def cancel(self) -> None:
        """Cancel ComfyUI generation."""
        self._cancelled = True

        if self._current_prompt_id:
            try:
                client = await self._get_client()
                await client.post("/interrupt")
                logger.info("Sent interrupt to ComfyUI")
            except Exception as e:
                logger.warning(f"Error sending interrupt: {e}")

    async def list_workflows(self) -> list[str]:
        """List available workflow files from both bundled and custom directories."""
        workflows = set()

        for workflows_dir in [self._bundled_workflows_dir, self._custom_workflows_dir]:
            if workflows_dir.exists():
                for f in workflows_dir.glob("*.json"):
                    workflows.add(f.stem)

        return sorted(workflows)

    async def get_workflow_info(self, name: str) -> dict | None:
        """Get workflow metadata."""
        workflow = await self._load_workflow(name)
        if not workflow:
            return None

        # Extract basic info
        return {
            "name": name,
            "node_count": len(workflow),
            "has_lora": LORA_PATH_MARKER in json.dumps(workflow),
            "has_controlnet": "ControlNet" in json.dumps(workflow),
        }

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_client()
