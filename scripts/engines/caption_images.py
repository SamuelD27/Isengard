#!/usr/bin/env python3
"""
Florence-2 Image Captioning Engine for Isengard

Generates structured captions for LoRA training datasets using Florence-2.
Captions follow the format optimized for Stable Diffusion / FLUX training:

{trigger_word} [Style], [Notable Features], [Clothing], [Pose],
[Expression], [Background], [Lighting], [Camera Angle]

Usage:
    python caption_images.py --input /path/to/images --trigger "ohwx woman"
    python caption_images.py --input /path/to/images --trigger "ohwx woman" --model florence-2-base

Output format (stdout, for worker parsing):
    PROGRESS:1/10:image1.jpg:Captioning image
    CAPTION:image1.jpg:ohwx woman photorealistic, long brown hair, ...
    PROGRESS:2/10:image2.jpg:Captioning image
    ...
    COMPLETE:10:8:2:0:45.2
    (total, generated, skipped, failed, time_seconds)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Debug logging helper
def log_debug(stage: str, message: str, data: dict = None):
    """Print debug log in structured format."""
    log_entry = {
        "level": "DEBUG",
        "stage": stage,
        "message": message,
    }
    if data:
        log_entry["data"] = data
    print(f"DEBUG:{json.dumps(log_entry)}", file=sys.stderr)


def log_info(message: str):
    """Print info log."""
    print(f"INFO:{message}", file=sys.stderr)


def log_error(message: str):
    """Print error log."""
    print(f"ERROR:{message}", file=sys.stderr)


# Lazy imports for faster startup when just checking --help
def load_dependencies():
    """Load heavy dependencies only when needed."""
    log_debug("INIT", "Loading dependencies")

    global torch, Image, AutoProcessor, AutoModelForCausalLM

    import torch
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForCausalLM

    log_debug("INIT", "Dependencies loaded", {
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
    })


# Caption format template based on LoRACaptioner analysis
CAPTION_SYSTEM_PROMPT = """You are generating a structured caption for LoRA training.

Format: {trigger_word} [Style], [Notable Visual Features], [Clothing], [Pose], [Expression/Mood], [Background/Setting], [Lighting], [Camera Angle]

Guidelines:
1. Start with the trigger word exactly as provided
2. Style: photorealistic, anime-style, 3D-rendered, digital-art, etc.
3. Notable Features: only describe variable features (not fixed traits like eye/hair color unless unusual)
4. Clothing: describe visible clothing and accessories
5. Pose: standing, sitting, walking, profile view, etc.
6. Expression: neutral, smiling, focused, etc.
7. Background: describe the setting briefly
8. Lighting: soft lighting, dramatic shadows, natural light, etc.
9. Camera Angle: front view, side profile, three-quarter view, low-angle, high-angle

Keep it concise - one line, comma-separated. No bullet points or explanations.
"""


class Florence2Captioner:
    """Florence-2 based image captioner for LoRA training datasets."""

    SUPPORTED_MODELS = {
        "florence-2-base": "microsoft/Florence-2-base",
        "florence-2-large": "microsoft/Florence-2-large",
    }

    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

    def __init__(
        self,
        model_name: str = "florence-2-large",
        model_path: str | None = None,
        device: str | None = None,
    ):
        """
        Initialize the captioner.

        Args:
            model_name: Name of the model (florence-2-base or florence-2-large)
            model_path: Optional local path to model files (for R2-downloaded models)
            device: Device to use (cuda, cpu, or auto-detect)
        """
        self.model_name = model_name
        self.model_path = model_path
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        self._loaded = False

        log_debug("INIT", "Captioner initialized", {
            "model_name": model_name,
            "model_path": model_path,
            "device": self.device,
        })

    def load_model(self):
        """Load the Florence-2 model and processor."""
        if self._loaded:
            return

        log_info(f"Loading Florence-2 model: {self.model_name}")
        start_time = time.time()

        # Determine model source
        if self.model_path and os.path.exists(self.model_path):
            model_source = self.model_path
            log_debug("LOAD", f"Loading from local path: {model_source}")
        elif self.model_name in self.SUPPORTED_MODELS:
            model_source = self.SUPPORTED_MODELS[self.model_name]
            log_debug("LOAD", f"Loading from HuggingFace: {model_source}")
        else:
            raise ValueError(f"Unknown model: {self.model_name}. Supported: {list(self.SUPPORTED_MODELS.keys())}")

        # Load processor and model
        self.processor = AutoProcessor.from_pretrained(
            model_source,
            trust_remote_code=True,
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            model_source,
            trust_remote_code=True,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        ).to(self.device)

        self.model.eval()
        self._loaded = True

        load_time = time.time() - start_time
        log_info(f"Model loaded in {load_time:.2f}s on {self.device}")
        log_debug("LOAD", "Model loaded successfully", {
            "load_time_seconds": load_time,
            "device": self.device,
            "dtype": str(self.model.dtype),
        })

    def _get_raw_caption(self, image: "Image.Image") -> str:
        """Get raw detailed caption from Florence-2."""
        # Use MORE_DETAILED_CAPTION for comprehensive descriptions
        task_prompt = "<MORE_DETAILED_CAPTION>"

        inputs = self.processor(
            text=task_prompt,
            images=image,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            generated_ids = self.model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=256,
                num_beams=3,
                do_sample=False,
            )

        generated_text = self.processor.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]

        # Extract the caption part (after the task prompt marker)
        caption = generated_text.replace(task_prompt, "").strip()
        return caption

    def _format_caption(
        self,
        raw_caption: str,
        trigger_word: str,
        style_hint: str = "auto",
    ) -> str:
        """
        Format raw caption into structured LoRA training format.

        Takes the detailed description from Florence-2 and restructures it
        into the format: trigger [Style], [Features], [Clothing], [Pose], etc.
        """
        # Detect style from raw caption
        style = style_hint
        if style == "auto":
            raw_lower = raw_caption.lower()
            if any(word in raw_lower for word in ["anime", "cartoon", "animated", "manga"]):
                style = "anime-style"
            elif any(word in raw_lower for word in ["3d", "rendered", "cgi"]):
                style = "3D-rendered"
            elif any(word in raw_lower for word in ["digital", "illustration", "artwork"]):
                style = "digital-art"
            else:
                style = "photorealistic"

        # Clean up the raw caption - remove leading articles and common phrases
        cleaned = raw_caption.strip()
        for prefix in ["The image shows ", "This is ", "A ", "An ", "The "]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]

        # Ensure proper ending
        cleaned = cleaned.rstrip(".")

        # Build structured caption
        # Start with trigger word and style, then append the description
        structured = f"{trigger_word} {style}, {cleaned}"

        return structured

    def caption_image(
        self,
        image_path: Path,
        trigger_word: str,
        style_hint: str = "auto",
    ) -> str:
        """
        Generate caption for a single image.

        Args:
            image_path: Path to the image file
            trigger_word: Trigger word to prefix the caption
            style_hint: Style hint (auto, photorealistic, anime, etc.)

        Returns:
            Formatted caption string
        """
        self.load_model()

        log_debug("CAPTION", f"Processing: {image_path.name}")

        # Load and prepare image
        image = Image.open(image_path).convert("RGB")

        # Get raw caption
        raw_caption = self._get_raw_caption(image)
        log_debug("CAPTION", f"Raw caption: {raw_caption[:100]}...")

        # Format into structured caption
        formatted = self._format_caption(raw_caption, trigger_word, style_hint)
        log_debug("CAPTION", f"Formatted: {formatted[:100]}...")

        return formatted

    def caption_directory(
        self,
        input_dir: Path,
        trigger_word: str,
        style_hint: str = "auto",
        overwrite: bool = False,
        save_captions: bool = True,
    ) -> dict:
        """
        Generate captions for all images in a directory.

        Args:
            input_dir: Directory containing images
            trigger_word: Trigger word to prefix all captions
            style_hint: Style hint for captions
            overwrite: Whether to overwrite existing caption files
            save_captions: Whether to save .txt files alongside images

        Returns:
            Dictionary with results and statistics
        """
        self.load_model()

        input_path = Path(input_dir)
        if not input_path.exists():
            raise ValueError(f"Input directory does not exist: {input_dir}")

        # Find all image files
        image_files = [
            f for f in input_path.iterdir()
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]

        total = len(image_files)
        if total == 0:
            log_info("No image files found in directory")
            return {
                "success": True,
                "captions": {},
                "total": 0,
                "generated": 0,
                "skipped": 0,
                "failed": 0,
            }

        log_info(f"Found {total} images to process")

        start_time = time.time()
        captions = {}
        generated = 0
        skipped = 0
        failed = 0

        for idx, image_path in enumerate(sorted(image_files)):
            # Check for existing caption
            caption_path = image_path.with_suffix(".txt")

            if caption_path.exists() and not overwrite:
                # Output progress (skipped)
                print(f"PROGRESS:{idx + 1}/{total}:{image_path.name}:Skipped (caption exists)")
                skipped += 1
                # Read existing caption
                captions[image_path.name] = caption_path.read_text().strip()
                continue

            # Output progress
            print(f"PROGRESS:{idx + 1}/{total}:{image_path.name}:Captioning image")

            try:
                caption = self.caption_image(image_path, trigger_word, style_hint)
                captions[image_path.name] = caption
                generated += 1

                # Save caption file
                if save_captions:
                    caption_path.write_text(caption)

                # Output the caption
                print(f"CAPTION:{image_path.name}:{caption}")

            except Exception as e:
                log_error(f"Failed to caption {image_path.name}: {e}")
                failed += 1
                captions[image_path.name] = ""

        elapsed = time.time() - start_time

        # Output completion summary
        print(f"COMPLETE:{total}:{generated}:{skipped}:{failed}:{elapsed:.2f}")

        return {
            "success": failed == 0,
            "captions": captions,
            "total": total,
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "time_seconds": elapsed,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Generate structured captions for LoRA training using Florence-2"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="Directory containing images to caption"
    )
    parser.add_argument(
        "--trigger", "-t",
        type=str,
        required=True,
        help="Trigger word to prefix all captions (e.g., 'ohwx woman')"
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="florence-2-large",
        choices=["florence-2-base", "florence-2-large"],
        help="Florence-2 model variant to use (default: florence-2-large)"
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="Local path to model files (for R2-downloaded models)"
    )
    parser.add_argument(
        "--style",
        type=str,
        default="auto",
        choices=["auto", "photorealistic", "anime", "3d-rendered", "digital-art"],
        help="Style hint for captions (default: auto-detect)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing caption files"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save caption .txt files (just output to stdout)"
    )
    parser.add_argument(
        "--single",
        type=str,
        default=None,
        help="Caption a single image instead of a directory"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for programmatic use)"
    )

    args = parser.parse_args()

    # Load dependencies
    load_dependencies()

    # Initialize captioner
    captioner = Florence2Captioner(
        model_name=args.model,
        model_path=args.model_path,
    )

    if args.single:
        # Single image mode
        caption = captioner.caption_image(
            Path(args.single),
            args.trigger,
            args.style,
        )
        if args.json:
            print(json.dumps({"caption": caption}))
        else:
            print(caption)
    else:
        # Directory mode
        result = captioner.caption_directory(
            Path(args.input),
            args.trigger,
            args.style,
            overwrite=args.overwrite,
            save_captions=not args.no_save,
        )

        if args.json:
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
