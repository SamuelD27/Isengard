"""
Security Utilities

File validation, path sanitization, and other security helpers.
"""

import hashlib
import os
import re
from pathlib import Path
from typing import BinaryIO

from .logging import get_logger

logger = get_logger("shared.security")

# File upload constraints
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_IMAGE_DIMENSION = 8192  # Max width or height

# Default min dimension (can be overridden for testing)
MIN_IMAGE_DIMENSION = 64


def _get_min_image_dimension() -> int:
    """Get minimum image dimension, allowing 1x1 in fast-test mode."""
    mode = os.getenv("ISENGARD_MODE", "").lower()
    if mode == "fast_test":
        return 1
    return MIN_IMAGE_DIMENSION

# Allowed image types with magic bytes
IMAGE_SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': ('png', 'image/png'),
    b'\xff\xd8\xff': ('jpg', 'image/jpeg'),
    b'GIF87a': ('gif', 'image/gif'),
    b'GIF89a': ('gif', 'image/gif'),
    b'RIFF': ('webp', 'image/webp'),  # WebP starts with RIFF
}

# Dangerous filename patterns
DANGEROUS_PATTERNS = [
    r'\.\.',           # Path traversal
    r'^/',             # Absolute path
    r'^\\',            # Windows absolute
    r'[<>:"|?*]',      # Illegal chars
    r'\x00',           # Null byte
    r'\.exe$',         # Executable extensions
    r'\.sh$',
    r'\.bat$',
    r'\.cmd$',
    r'\.php$',
    r'\.py$',
    r'\.js$',
]


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and injection attacks.

    Args:
        filename: Original filename from upload

    Returns:
        Safe filename with only alphanumeric, dash, underscore, and single dot

    Raises:
        ValueError: If filename is empty or entirely dangerous
    """
    if not filename:
        raise ValueError("Filename cannot be empty")

    # Get base name only (strip any path components)
    filename = Path(filename).name

    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            logger.warning("Dangerous filename pattern detected", extra={
                "event": "security.filename.dangerous",
                "original_filename": filename,
                "pattern": pattern,
            })
            # Don't raise, just sanitize aggressively
            break

    # Extract extension before sanitizing
    parts = filename.rsplit('.', 1)
    name = parts[0]
    ext = parts[1].lower() if len(parts) > 1 else ''

    # Sanitize name: keep only safe chars
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)

    # Sanitize extension
    ext = re.sub(r'[^a-zA-Z0-9]', '', ext)

    # Ensure we have a valid name
    if not name:
        name = 'file'

    # Limit length
    name = name[:100]
    ext = ext[:10]

    result = f"{name}.{ext}" if ext else name

    if result != filename:
        logger.debug("Filename sanitized", extra={
            "original": filename,
            "sanitized": result,
        })

    return result


def validate_image_magic_bytes(content: bytes) -> tuple[str, str] | None:
    """
    Validate image by checking magic bytes (file signature).

    Args:
        content: First bytes of file content (at least 12 bytes recommended)

    Returns:
        Tuple of (extension, mimetype) if valid image, None otherwise
    """
    for signature, (ext, mimetype) in IMAGE_SIGNATURES.items():
        if content.startswith(signature):
            return (ext, mimetype)

        # Special case for WebP (RIFF....WEBP)
        if signature == b'RIFF' and content[:4] == b'RIFF' and content[8:12] == b'WEBP':
            return ('webp', 'image/webp')

    return None


def validate_file_size(content: bytes, max_size: int = MAX_FILE_SIZE_BYTES) -> bool:
    """Check if file content is within size limit."""
    return len(content) <= max_size


def get_content_hash(content: bytes) -> str:
    """Generate SHA-256 hash of content for deduplication/integrity."""
    return hashlib.sha256(content).hexdigest()


def validate_image_dimensions(width: int, height: int) -> tuple[bool, str | None]:
    """
    Validate image dimensions are within acceptable range.

    Returns:
        Tuple of (is_valid, error_message)
    """
    min_dim = _get_min_image_dimension()

    if width < min_dim or height < min_dim:
        return False, f"Image too small. Minimum size is {min_dim}x{min_dim}"

    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        return False, f"Image too large. Maximum size is {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"

    return True, None


def get_image_dimensions_from_header(content: bytes) -> tuple[int, int] | None:
    """
    Extract image dimensions from file header without loading full image.

    Works for PNG and JPEG. Returns None if cannot determine.
    """
    # PNG: dimensions at bytes 16-24
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        if len(content) >= 24:
            width = int.from_bytes(content[16:20], 'big')
            height = int.from_bytes(content[20:24], 'big')
            return (width, height)

    # JPEG: need to parse segments
    if content[:2] == b'\xff\xd8':
        # Simplified JPEG parsing - look for SOF0/SOF2 markers
        i = 2
        while i < len(content) - 9:
            if content[i] != 0xff:
                i += 1
                continue

            marker = content[i + 1]

            # SOF0 (0xC0) or SOF2 (0xC2) contain dimensions
            if marker in (0xC0, 0xC2):
                height = int.from_bytes(content[i + 5:i + 7], 'big')
                width = int.from_bytes(content[i + 7:i + 9], 'big')
                return (width, height)

            # Skip to next marker
            if marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9):
                i += 2
            else:
                if i + 4 > len(content):
                    break
                length = int.from_bytes(content[i + 2:i + 4], 'big')
                i += 2 + length

    return None


class SecurityError(Exception):
    """Raised when security validation fails."""
    pass


class FileSizeError(SecurityError):
    """File exceeds size limit."""
    pass


class FileTypeError(SecurityError):
    """Invalid or unallowed file type."""
    pass


class ImageDimensionError(SecurityError):
    """Image dimensions out of range."""
    pass
