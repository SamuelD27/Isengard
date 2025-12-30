"""
LoRA Management Endpoints

Upload and manage external LoRA files for image generation.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger
from packages.shared.src.rate_limit import rate_limit, RATE_LIMIT_UPLOAD

router = APIRouter()
logger = get_logger("api.routes.loras")

# Max LoRA file size: 500MB
MAX_LORA_SIZE_MB = 500
MAX_LORA_SIZE_BYTES = MAX_LORA_SIZE_MB * 1024 * 1024


class LoraInfo(BaseModel):
    """Information about an uploaded LoRA."""
    id: str
    name: str
    filename: str
    trigger_word: str | None = None
    size_bytes: int
    uploaded_at: str
    path: str


class LoraListResponse(BaseModel):
    """Response for LoRA listing."""
    loras: list[LoraInfo]
    total_count: int


def _get_loras_dir() -> Path:
    """Get the directory for uploaded LoRAs."""
    config = get_global_config()
    loras_dir = config.volume_root / "uploaded_loras"
    loras_dir.mkdir(parents=True, exist_ok=True)
    return loras_dir


def _get_lora_metadata_path(lora_id: str) -> Path:
    """Get path for LoRA metadata file."""
    return _get_loras_dir() / f"{lora_id}.json"


@router.get("", response_model=LoraListResponse)
async def list_loras():
    """
    List all uploaded LoRA files.

    Returns both uploaded LoRAs and character-trained LoRAs.
    """
    loras = []
    loras_dir = _get_loras_dir()

    # List uploaded LoRAs from metadata files
    import json
    for meta_file in loras_dir.glob("*.json"):
        try:
            metadata = json.loads(meta_file.read_text())
            lora_path = Path(metadata.get("path", ""))
            if lora_path.exists():
                loras.append(LoraInfo(**metadata))
        except Exception as e:
            logger.warning(f"Failed to load LoRA metadata: {e}")

    return LoraListResponse(
        loras=sorted(loras, key=lambda x: x.uploaded_at, reverse=True),
        total_count=len(loras),
    )


@router.post("/upload", response_model=LoraInfo, status_code=201)
@rate_limit(**RATE_LIMIT_UPLOAD)
async def upload_lora(
    file: UploadFile = File(...),
    name: str = Form(...),
    trigger_word: str = Form(None),
):
    """
    Upload an external LoRA file.

    Accepts .safetensors files up to 500MB.
    """
    # Validate file extension
    if not file.filename or not file.filename.endswith(".safetensors"):
        raise HTTPException(
            status_code=400,
            detail="Only .safetensors files are allowed"
        )

    # Read file to check size
    content = await file.read()
    if len(content) > MAX_LORA_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_LORA_SIZE_MB}MB"
        )

    # Generate unique ID
    lora_id = f"lora-{uuid.uuid4().hex[:12]}"

    # Save file
    loras_dir = _get_loras_dir()
    safe_filename = f"{lora_id}.safetensors"
    file_path = loras_dir / safe_filename

    file_path.write_bytes(content)

    # Create metadata
    import json
    metadata = {
        "id": lora_id,
        "name": name,
        "filename": file.filename,
        "trigger_word": trigger_word,
        "size_bytes": len(content),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "path": str(file_path),
    }

    # Save metadata
    meta_path = _get_lora_metadata_path(lora_id)
    meta_path.write_text(json.dumps(metadata, indent=2))

    logger.info("LoRA file uploaded", extra={
        "event": "lora.uploaded",
        "lora_id": lora_id,
        "name": name,
        "size_bytes": len(content),
    })

    return LoraInfo(**metadata)


@router.get("/{lora_id}", response_model=LoraInfo)
async def get_lora(lora_id: str):
    """Get information about a specific LoRA."""
    import json
    meta_path = _get_lora_metadata_path(lora_id)

    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="LoRA not found")

    try:
        metadata = json.loads(meta_path.read_text())
        return LoraInfo(**metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load LoRA: {e}")


@router.delete("/{lora_id}")
async def delete_lora(lora_id: str):
    """Delete an uploaded LoRA."""
    import json
    meta_path = _get_lora_metadata_path(lora_id)

    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="LoRA not found")

    try:
        metadata = json.loads(meta_path.read_text())
        lora_path = Path(metadata.get("path", ""))

        # Delete the LoRA file
        if lora_path.exists():
            lora_path.unlink()

        # Delete metadata
        meta_path.unlink()

        logger.info("LoRA deleted", extra={
            "event": "lora.deleted",
            "lora_id": lora_id,
        })

        return {"status": "deleted", "id": lora_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete LoRA: {e}")
