"""
Isengard Capability Matrix

Authoritative source for what features are supported.
Check this before implementing any feature-dependent logic.
"""

from typing import TypedDict, Literal


class CapabilityInfo(TypedDict):
    """Information about a capability."""
    supported: bool
    status: Literal["production", "beta", "scaffold_only", "not_implemented", "out_of_scope"]
    backend: str | None
    notes: str | None


# ============================================
# CAPABILITY MATRIX - Single Source of Truth
# ============================================

CAPABILITIES: dict[str, dict[str, CapabilityInfo]] = {
    "training": {
        "lora": {
            "supported": True,
            "status": "production",
            "backend": "ai-toolkit",
            "notes": "Primary training method. Uses FLUX.1-dev in production mode.",
        },
        "dora": {
            "supported": False,
            "status": "not_implemented",
            "backend": None,
            "notes": "May be added in future versions.",
        },
        "full_finetune": {
            "supported": False,
            "status": "out_of_scope",
            "backend": None,
            "notes": "Not planned for this project.",
        },
    },
    "image_generation": {
        "comfyui": {
            "supported": True,
            "status": "production",
            "backend": "comfyui",
            "notes": "Primary image generation backend. Supports FLUX and SDXL workflows.",
        },
        "direct_diffusers": {
            "supported": False,
            "status": "not_implemented",
            "backend": None,
            "notes": "May be added as alternative backend.",
        },
    },
    "video_generation": {
        "any": {
            "supported": False,
            "status": "scaffold_only",
            "backend": None,
            "notes": "Interface defined, implementation deferred. UI shows 'In Development'.",
        },
    },
}


def is_capability_supported(category: str, capability: str) -> bool:
    """
    Check if a capability is supported.

    Args:
        category: Category name (e.g., 'training', 'image_generation')
        capability: Capability name (e.g., 'lora', 'comfyui')

    Returns:
        True if capability is supported and production-ready
    """
    if category not in CAPABILITIES:
        return False
    if capability not in CAPABILITIES[category]:
        return False
    return CAPABILITIES[category][capability]["supported"]


def get_capability_info(category: str, capability: str) -> CapabilityInfo | None:
    """
    Get detailed information about a capability.

    Args:
        category: Category name
        capability: Capability name

    Returns:
        CapabilityInfo dict or None if not found
    """
    if category not in CAPABILITIES:
        return None
    return CAPABILITIES[category].get(capability)


def get_unsupported_message(category: str, capability: str) -> str:
    """
    Get a user-friendly message for unsupported capabilities.

    Args:
        category: Category name
        capability: Capability name

    Returns:
        Human-readable message explaining why capability is unavailable
    """
    info = get_capability_info(category, capability)
    if info is None:
        return f"Unknown capability: {category}/{capability}"

    if info["supported"]:
        return f"{capability} is supported."

    status = info["status"]
    notes = info.get("notes", "")

    if status == "scaffold_only":
        return f"{capability.title()} is currently in development. {notes}"
    elif status == "not_implemented":
        return f"{capability.title()} is not yet implemented. {notes}"
    elif status == "out_of_scope":
        return f"{capability.title()} is not planned for this project. {notes}"

    return f"{capability.title()} is not available. {notes}"


def list_supported_capabilities() -> dict[str, list[str]]:
    """
    Get all supported capabilities organized by category.

    Returns:
        Dict mapping category to list of supported capability names
    """
    result: dict[str, list[str]] = {}
    for category, capabilities in CAPABILITIES.items():
        supported = [
            name for name, info in capabilities.items()
            if info["supported"]
        ]
        if supported:
            result[category] = supported
    return result
