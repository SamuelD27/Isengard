"""
Character Management Endpoints

CRUD operations for characters/identities.
"""

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger
from packages.shared.src.types import Character, CharacterCreate, CharacterUpdate

router = APIRouter()
logger = get_logger("api.routes.characters")

# In-memory storage for now (will be replaced with database)
_characters: dict[str, Character] = {}


def _get_character_or_404(character_id: str) -> Character:
    """Get character by ID or raise 404."""
    if character_id not in _characters:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found")
    return _characters[character_id]


@router.get("", response_model=List[Character])
async def list_characters():
    """
    List all characters.
    """
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

    _characters[character_id] = character

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
    _characters[character_id] = character

    logger.info("Updated character", extra={"character_id": character_id})

    return character


@router.delete("/{character_id}", status_code=204)
async def delete_character(character_id: str):
    """
    Delete a character.
    """
    _get_character_or_404(character_id)
    del _characters[character_id]

    logger.info("Deleted character", extra={"character_id": character_id})


@router.post("/{character_id}/images", status_code=201)
async def upload_training_images(
    character_id: str,
    files: List[UploadFile] = File(...),
):
    """
    Upload training images for a character.
    """
    character = _get_character_or_404(character_id)
    config = get_global_config()

    # Create character's upload directory
    upload_dir = config.uploads_dir / character_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            logger.warning(f"Skipping non-image file: {file.filename}")
            continue

        # Save file
        file_path = upload_dir / file.filename
        content = await file.read()
        file_path.write_bytes(content)
        uploaded.append(file.filename)

    # Update image count
    character.image_count = len(list(upload_dir.glob("*")))
    character.updated_at = datetime.utcnow()
    _characters[character_id] = character

    logger.info("Uploaded training images", extra={
        "character_id": character_id,
        "count": len(uploaded),
        "total_images": character.image_count,
    })

    return {
        "uploaded": uploaded,
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
