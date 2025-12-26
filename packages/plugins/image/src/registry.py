"""
Image Plugin Registry

Manages registration and retrieval of image generation plugins.
"""

from packages.shared.src.logging import get_logger

from .interface import ImagePlugin

logger = get_logger("plugins.image.registry")

# Plugin registry
_plugins: dict[str, ImagePlugin] = {}
_default_plugin: str | None = None


def register_image_plugin(plugin: ImagePlugin, default: bool = False) -> None:
    """
    Register an image generation plugin.

    Args:
        plugin: Plugin instance to register
        default: Whether this should be the default plugin
    """
    global _default_plugin

    _plugins[plugin.name] = plugin
    logger.info(f"Registered image plugin: {plugin.name}")

    if default or _default_plugin is None:
        _default_plugin = plugin.name
        logger.info(f"Default image plugin set to: {plugin.name}")


def get_image_plugin(name: str | None = None) -> ImagePlugin:
    """
    Get an image plugin by name.

    Args:
        name: Plugin name. If None, returns the default plugin.

    Returns:
        ImagePlugin instance

    Raises:
        ValueError: If plugin not found or no plugins registered
    """
    if not _plugins:
        raise ValueError("No image plugins registered")

    if name is None:
        if _default_plugin is None:
            raise ValueError("No default image plugin set")
        name = _default_plugin

    if name not in _plugins:
        available = list(_plugins.keys())
        raise ValueError(f"Image plugin '{name}' not found. Available: {available}")

    return _plugins[name]


def list_image_plugins() -> list[str]:
    """Get list of registered plugin names."""
    return list(_plugins.keys())
