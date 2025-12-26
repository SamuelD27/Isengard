"""
Character Management Endpoints

CRUD operations for characters/identities.
Persists character metadata to $VOLUME_ROOT/characters/{id}.json
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from typing import List

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger
from packages.shared.src.types import Character, CharacterCreate, CharacterUpdate
from packages.shared.src.security import (
    sanitize_filename,
    validate_image_magic_bytes,
    validate_file_size,
    get_image_dimensions_from_header,
    validate_image_dimensions,
    MAX_FILE_SIZE_MB,
)
from packages.shared.src.rate_limit import rate_limit, RATE_LIMIT_UPLOAD

router = APIRouter()
logger = get_logger("api.routes.characters")

# In-memory cache backed by filesystem
_characters: dict[str, Character] = {}
_characters_loaded: bool = False


def _get_character_path(character_id: str) -> Path:
    """Get the filesystem path for a character's metadata."""
    config = get_global_config()
    return config.characters_dir / f"{character_id}.json"


def _save_character(character: Character) -> None:
    """Save character to filesystem and cache."""
    config = get_global_config()
    config.characters_dir.mkdir(parents=True, exist_ok=True)

    path = _get_character_path(character.id)
    path.write_text(character.model_dump_json(indent=2))
    _characters[character.id] = character

    logger.debug("Character saved to filesystem", extra={
        "character_id": character.id,
        "path": str(path),
    })


def _load_character(character_id: str) -> Character | None:
    """Load a character from filesystem."""
    path = _get_character_path(character_id)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        return Character(**data)
    except Exception as e:
        logger.error(f"Failed to load character {character_id}: {e}")
        return None


def _load_all_characters() -> None:
    """Load all characters from filesystem into cache."""
    global _characters_loaded
    if _characters_loaded:
        return

    config = get_global_config()
    if not config.characters_dir.exists():
        config.characters_dir.mkdir(parents=True, exist_ok=True)
        _characters_loaded = True
        return

    for path in config.characters_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            character = Character(**data)
            _characters[character.id] = character
        except Exception as e:
            logger.error(f"Failed to load character from {path}: {e}")

    _characters_loaded = True
    logger.info(f"Loaded {len(_characters)} characters from filesystem")


def _delete_character_file(character_id: str) -> None:
    """Delete character file from filesystem."""
    path = _get_character_path(character_id)
    if path.exists():
        path.unlink()
        logger.debug(f"Deleted character file: {path}")


def _get_character_or_404(character_id: str) -> Character:
    """Get character by ID or raise 404."""
    _load_all_characters()

    if character_id not in _characters:
        # Try loading from file directly (in case of cache miss)
        character = _load_character(character_id)
        if character:
            _characters[character_id] = character
            return character
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found")
    return _characters[character_id]


@router.get("", response_model=List[Character])
async def list_characters():
    """
    List all characters.
    """
    _load_all_characters()
    logger.info("Listing all characters", extra={"count": len(_characters)})
    return list(_characters.values())


@router.post("", response_model=Character, status_code=201)
async def create_character(request: CharacterCreate):
    """
    Create a new character.
    """
    character_id = f"char-{uuid.uuid4().hex[:8]}"

    character = Character(
        id=character_id,
        name=request.name,
        description=request.description,
        trigger_word=request.trigger_word,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Save to filesystem and cache
    _save_character(character)

    logger.info("Created character", extra={
        "character_id": character_id,
        "name": request.name,
        "trigger_word": request.trigger_word,
    })

    return character


@router.get("/{character_id}", response_model=Character)
async def get_character(character_id: str):
    """
    Get a character by ID.
    """
    return _get_character_or_404(character_id)


@router.patch("/{character_id}", response_model=Character)
async def update_character(character_id: str, request: CharacterUpdate):
    """
    Update a character.
    """
    character = _get_character_or_404(character_id)

    if request.name is not None:
        character.name = request.name
    if request.description is not None:
        character.description = request.description
    if request.trigger_word is not None:
        character.trigger_word = request.trigger_word

    character.updated_at = datetime.utcnow()

    # Save to filesystem and cache
    _save_character(character)

    logger.info("Updated character", extra={"character_id": character_id})

    return character


@router.delete("/{character_id}", status_code=204)
async def delete_character(character_id: str):
    """
    Delete a character.
    """
    _get_character_or_404(character_id)

    # Remove from cache and filesystem
    del _characters[character_id]
    _delete_character_file(character_id)

    logger.info("Deleted character", extra={"character_id": character_id})


@router.post("/{character_id}/images", status_code=201)
@rate_limit(**RATE_LIMIT_UPLOAD)
async def upload_training_images(
    request: Request,
    character_id: str,
    files: List[UploadFile] = File(...),
):
    """
    Upload training images for a character.

    Security:
    - Rate limited: 30 requests per minute
    - Validates file size (max 20MB per file)
    - Validates image magic bytes (PNG, JPEG, GIF, WebP)
    - Sanitizes filenames to prevent path traversal
    - Validates image dimensions (64-8192px)
    """
    character = _get_character_or_404(character_id)
    config = get_global_config()

    # Create character's upload directory
    upload_dir = config.uploads_dir / character_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    rejected = []

    for file in files:
        original_filename = file.filename or "unknown"

        # Read content
        content = await file.read()

        # Validate file size
        if not validate_file_size(content):
            logger.warning("File too large", extra={
                "event": "upload.rejected.size",
                "filename": original_filename,
                "size_mb": len(content) / (1024 * 1024),
                "max_mb": MAX_FILE_SIZE_MB,
            })
            rejected.append({"filename": original_filename, "reason": f"File too large (max {MAX_FILE_SIZE_MB}MB)"})
            continue

        # Validate image magic bytes (not just content-type which can be spoofed)
        image_type = validate_image_magic_bytes(content[:12])
        if not image_type:
            logger.warning("Invalid image type", extra={
                "event": "upload.rejected.type",
                "filename": original_filename,
                "claimed_type": file.content_type,
            })
            rejected.append({"filename": original_filename, "reason": "Invalid image type"})
            continue

        ext, mimetype = image_type

        # Validate image dimensions
        dimensions = get_image_dimensions_from_header(content)
        if dimensions:
            width, height = dimensions
            valid, error = validate_image_dimensions(width, height)
            if not valid:
                logger.warning("Invalid image dimensions", extra={
                    "event": "upload.rejected.dimensions",
                    "filename": original_filename,
                    "width": width,
                    "height": height,
                })
                rejected.append({"filename": original_filename, "reason": error})
                continue

        # Sanitize filename and use validated extension
        try:
            safe_name = sanitize_filename(original_filename)
            # Ensure correct extension based on magic bytes
            base_name = safe_name.rsplit('.', 1)[0] if '.' in safe_name else safe_name
            safe_filename = f"{base_name}.{ext}"
        except ValueError as e:
            rejected.append({"filename": original_filename, "reason": str(e)})
            continue

        # Save file
        file_path = upload_dir / safe_filename
        file_path.write_bytes(content)
        uploaded.append(safe_filename)

        logger.debug("Image uploaded", extra={
            "event": "upload.success",
            "original_filename": original_filename,
            "saved_as": safe_filename,
            "size_bytes": len(content),
            "dimensions": dimensions,
        })

    # Update image count and save
    character.image_count = len(list(upload_dir.glob("*")))
    character.updated_at = datetime.utcnow()
    _save_character(character)

    logger.info("Upload batch completed", extra={
        "character_id": character_id,
        "uploaded_count": len(uploaded),
        "rejected_count": len(rejected),
        "total_images": character.image_count,
    })

    return {
        "uploaded": uploaded,
        "rejected": rejected,
        "total_images": character.image_count,
    }


@router.get("/{character_id}/images")
async def list_training_images(character_id: str):
    """
    List training images for a character.
    """
    character = _get_character_or_404(character_id)
    config = get_global_config()

    upload_dir = config.uploads_dir / character_id
    if not upload_dir.exists():
        return {"images": [], "count": 0}

    images = [f.name for f in upload_dir.glob("*") if f.is_file()]

    return {
        "images": images,
        "count": len(images),
    }
