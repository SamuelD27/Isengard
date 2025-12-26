"""
Training Plugin Registry

Manages registration and retrieval of training plugins.
"""

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger

from .interface import TrainingPlugin

logger = get_logger("plugins.training.registry")

# Plugin registry
_plugins: dict[str, TrainingPlugin] = {}
_default_plugin: str | None = None


def register_training_plugin(plugin: TrainingPlugin, default: bool = False) -> None:
    """
    Register a training plugin.

    Args:
        plugin: Plugin instance to register
        default: Whether this should be the default plugin
    """
    global _default_plugin

    _plugins[plugin.name] = plugin
    logger.info(f"Registered training plugin: {plugin.name}", extra={
        "supported_methods": [m.value for m in plugin.supported_methods]
    })

    if default or _default_plugin is None:
        _default_plugin = plugin.name
        logger.info(f"Default training plugin set to: {plugin.name}")


def get_training_plugin(name: str | None = None) -> TrainingPlugin:
    """
    Get a training plugin by name.

    Args:
        name: Plugin name. If None, returns the default plugin.

    Returns:
        TrainingPlugin instance

    Raises:
        ValueError: If plugin not found or no plugins registered
    """
    if not _plugins:
        raise ValueError("No training plugins registered")

    if name is None:
        if _default_plugin is None:
            raise ValueError("No default training plugin set")
        name = _default_plugin

    if name not in _plugins:
        available = list(_plugins.keys())
        raise ValueError(f"Training plugin '{name}' not found. Available: {available}")

    return _plugins[name]


def list_training_plugins() -> list[str]:
    """Get list of registered plugin names."""
    return list(_plugins.keys())
