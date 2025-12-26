#!/usr/bin/env python3
"""
Model Download Script

Downloads required models for Isengard training and generation.

Usage:
    python scripts/download_models.py [--models flux,sd] [--cache-dir /path/to/cache]

Required Environment Variables:
    HF_TOKEN: HuggingFace access token (for gated models like FLUX.1-dev)

Models Downloaded:
    - FLUX.1-dev: black-forest-labs/FLUX.1-dev (requires HF access)
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def download_flux_model(cache_dir: Path | None = None) -> bool:
    """
    Download FLUX.1-dev model from HuggingFace.

    Requires:
    - HF_TOKEN environment variable
    - Access granted at https://huggingface.co/black-forest-labs/FLUX.1-dev

    Returns:
        True if successful, False otherwise
    """
    try:
        from huggingface_hub import snapshot_download, HfApi
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub")
        return False

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        print("ERROR: HF_TOKEN environment variable not set")
        print("Get your token from: https://huggingface.co/settings/tokens")
        return False

    model_id = "black-forest-labs/FLUX.1-dev"

    print(f"Downloading {model_id}...")
    print("This may take a while (model is ~25GB)")

    try:
        # Check access first
        api = HfApi()
        try:
            api.model_info(model_id, token=hf_token)
        except Exception as e:
            if "403" in str(e) or "gated" in str(e).lower():
                print(f"ERROR: Access denied to {model_id}")
                print(f"Request access at: https://huggingface.co/{model_id}")
                return False
            raise

        # Download model
        local_dir = snapshot_download(
            repo_id=model_id,
            token=hf_token,
            cache_dir=str(cache_dir) if cache_dir else None,
            local_dir_use_symlinks=False,
            resume_download=True,
        )

        print(f"SUCCESS: Model downloaded to {local_dir}")
        return True

    except Exception as e:
        print(f"ERROR: Failed to download model: {e}")
        return False


def download_schnell_adapter(cache_dir: Path | None = None) -> bool:
    """
    Download FLUX.1-schnell training adapter (for faster training).

    This is an optional adapter that enables training with FLUX.1-schnell.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface_hub not installed")
        return False

    model_id = "ostris/FLUX.1-schnell-training-adapter"

    print(f"Downloading {model_id}...")

    try:
        local_dir = snapshot_download(
            repo_id=model_id,
            cache_dir=str(cache_dir) if cache_dir else None,
            local_dir_use_symlinks=False,
            resume_download=True,
        )

        print(f"SUCCESS: Adapter downloaded to {local_dir}")
        return True

    except Exception as e:
        print(f"ERROR: Failed to download adapter: {e}")
        return False


def check_gpu() -> dict:
    """Check GPU availability and VRAM."""
    info = {
        "cuda_available": False,
        "gpu_count": 0,
        "gpus": [],
    }

    try:
        import torch
        info["cuda_available"] = torch.cuda.is_available()

        if info["cuda_available"]:
            info["gpu_count"] = torch.cuda.device_count()
            for i in range(info["gpu_count"]):
                props = torch.cuda.get_device_properties(i)
                info["gpus"].append({
                    "name": props.name,
                    "vram_gb": props.total_memory / (1024**3),
                    "compute_capability": f"{props.major}.{props.minor}",
                })
    except ImportError:
        pass

    return info


def main():
    parser = argparse.ArgumentParser(description="Download models for Isengard")
    parser.add_argument(
        "--models",
        type=str,
        default="flux",
        help="Comma-separated list of models to download (flux, schnell-adapter)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Custom cache directory for models",
    )
    parser.add_argument(
        "--check-gpu",
        action="store_true",
        help="Check GPU availability before downloading",
    )

    args = parser.parse_args()

    # Check GPU if requested
    if args.check_gpu:
        print("Checking GPU availability...")
        gpu_info = check_gpu()

        if not gpu_info["cuda_available"]:
            print("WARNING: No CUDA GPU detected")
            print("Training will not work without a GPU")
        else:
            print(f"Found {gpu_info['gpu_count']} GPU(s):")
            for i, gpu in enumerate(gpu_info["gpus"]):
                print(f"  [{i}] {gpu['name']} - {gpu['vram_gb']:.1f}GB VRAM")
                if gpu["vram_gb"] < 24:
                    print(f"      WARNING: FLUX training requires 24GB+ VRAM")

        print()

    # Parse models to download
    models = [m.strip().lower() for m in args.models.split(",")]
    success = True

    for model in models:
        if model == "flux":
            if not download_flux_model(args.cache_dir):
                success = False
        elif model == "schnell-adapter":
            if not download_schnell_adapter(args.cache_dir):
                success = False
        else:
            print(f"WARNING: Unknown model '{model}'")

    if success:
        print("\nAll models downloaded successfully!")
        print("\nNext steps:")
        print("1. Ensure ISENGARD_MODE=production is set")
        print("2. Start the worker: docker-compose up worker")
    else:
        print("\nSome downloads failed. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
