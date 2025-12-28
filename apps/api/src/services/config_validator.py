"""
Config Validator

Validates training and generation configs against plugin capabilities.
Rejects unsupported parameters with detailed error messages.
"""

from typing import Any

from fastapi import HTTPException


def validate_training_config(
    config: dict[str, Any],
    capabilities: dict[str, Any],
) -> None:
    """
    Validate training configuration against plugin capabilities.

    Checks:
    - Parameters are wired (supported by backend)
    - Values are within valid ranges
    - Enum values are in allowed options

    Args:
        config: Training configuration dictionary
        capabilities: Plugin capabilities from get_capabilities()

    Raises:
        HTTPException: 400 if validation fails with detailed message
    """
    params = capabilities.get("parameters", {})
    backend = capabilities.get("backend", "unknown")

    for key, value in config.items():
        # Skip non-parameter fields
        if key in ("character_id", "method"):
            continue

        if key not in params:
            # Unknown params ignored for forward compatibility
            continue

        param_schema = params[key]

        # Reject if not wired
        if not param_schema.get("wired", False):
            reason = param_schema.get("reason", "Not supported")
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{key}' not supported by {backend}: {reason}",
            )

        # Validate type and range
        _validate_param_value(key, value, param_schema, backend)


def validate_generation_config(
    config: dict[str, Any],
    capabilities: dict[str, Any],
) -> None:
    """
    Validate generation configuration against plugin capabilities.

    Checks:
    - Parameters are wired (supported by backend)
    - Toggle features are supported
    - Values are within valid ranges

    Args:
        config: Generation configuration dictionary
        capabilities: Plugin capabilities from get_capabilities()

    Raises:
        HTTPException: 400 if validation fails with detailed message
    """
    params = capabilities.get("parameters", {})
    toggles = capabilities.get("toggles", {})
    backend = capabilities.get("backend", "unknown")

    # Validate toggle features
    toggle_keys = ["use_upscale", "use_controlnet", "use_ipadapter", "use_facedetailer"]
    for toggle_key in toggle_keys:
        if config.get(toggle_key, False):
            toggle_schema = toggles.get(toggle_key, {})
            if not toggle_schema.get("supported", False):
                reason = toggle_schema.get("reason", "Not supported")
                raise HTTPException(
                    status_code=400,
                    detail=f"Feature '{toggle_key}' not supported by {backend}: {reason}",
                )

    # Validate parameters
    for key, value in config.items():
        # Skip non-parameter fields and toggles
        if key in ("prompt", "negative_prompt", "lora_id") or key.startswith("use_"):
            continue

        if key not in params:
            # Unknown params ignored for forward compatibility
            continue

        param_schema = params[key]

        # Reject if not wired
        if not param_schema.get("wired", False):
            reason = param_schema.get("reason", "Not supported")
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{key}' not supported by {backend}: {reason}",
            )

        # Validate type and range
        _validate_param_value(key, value, param_schema, backend)


def _validate_param_value(
    key: str,
    value: Any,
    schema: dict[str, Any],
    backend: str,
) -> None:
    """
    Validate a single parameter value against its schema.

    Args:
        key: Parameter name
        value: Parameter value
        schema: Parameter schema from capabilities
        backend: Backend name for error messages

    Raises:
        HTTPException: 400 if validation fails
    """
    param_type = schema.get("type", "string")

    # Validate range for numeric types
    if param_type in ("int", "float"):
        if value is None:
            return  # None is allowed (uses default)

        min_val = schema.get("min")
        max_val = schema.get("max")

        if min_val is not None and value < min_val:
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{key}' value {value} is below minimum {min_val}",
            )

        if max_val is not None and value > max_val:
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{key}' value {value} is above maximum {max_val}",
            )

    # Validate enum values
    elif param_type == "enum":
        options = schema.get("options", [])
        if value is not None and value not in options:
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{key}' value '{value}' not in allowed options: {options}",
            )

    # Validate boolean
    elif param_type == "bool":
        if value is not None and not isinstance(value, bool):
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{key}' must be a boolean, got {type(value).__name__}",
            )
