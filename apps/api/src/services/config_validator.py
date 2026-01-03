"""
Config Validator

Validates training and generation configs against plugin capabilities.
Rejects unsupported parameters with detailed error messages.

Returns structured ValidationError instances with error codes and field names
for consistent API error responses.
"""

from typing import Any

from fastapi import HTTPException

from ..models.responses import ErrorDetail, ErrorResponse, ErrorCodes


class ValidationError(Exception):
    """
    Structured validation error with code, message, and optional field.

    Attributes:
        code: Machine-readable error code (e.g., OUT_OF_RANGE)
        message: Human-readable error message
        field: Optional field name that caused the error
    """

    def __init__(self, code: str, message: str, field: str | None = None):
        self.code = code
        self.message = message
        self.field = field
        super().__init__(message)

    def to_error_detail(self) -> ErrorDetail:
        """Convert to ErrorDetail for API response."""
        return ErrorDetail(code=self.code, message=self.message, field=self.field)


def _raise_validation_errors(errors: list[ValidationError]) -> None:
    """
    Raise HTTPException with structured error response if errors exist.

    Args:
        errors: List of validation errors

    Raises:
        HTTPException: 400 with ErrorResponse body
    """
    if not errors:
        return

    response = ErrorResponse(
        error="Validation failed",
        details=[e.to_error_detail() for e in errors],
    )

    raise HTTPException(
        status_code=400,
        detail=response.model_dump(),
    )


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
        HTTPException: 400 if validation fails with structured ErrorResponse
    """
    params = capabilities.get("parameters", {})
    backend = capabilities.get("backend", "unknown")
    errors: list[ValidationError] = []

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
            errors.append(ValidationError(
                code=ErrorCodes.NOT_SUPPORTED,
                message=f"Parameter '{key}' not supported by {backend}: {reason}",
                field=key,
            ))
            continue

        # Validate type and range (collects errors)
        param_errors = _validate_param_value(key, value, param_schema, backend)
        errors.extend(param_errors)

    _raise_validation_errors(errors)


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
        HTTPException: 400 if validation fails with structured ErrorResponse
    """
    params = capabilities.get("parameters", {})
    toggles = capabilities.get("toggles", {})
    backend = capabilities.get("backend", "unknown")
    errors: list[ValidationError] = []

    # Validate toggle features
    toggle_keys = ["use_upscale", "use_controlnet", "use_ipadapter", "use_facedetailer"]
    for toggle_key in toggle_keys:
        if config.get(toggle_key, False):
            toggle_schema = toggles.get(toggle_key, {})
            if not toggle_schema.get("supported", False):
                reason = toggle_schema.get("reason", "Not supported")
                errors.append(ValidationError(
                    code=ErrorCodes.NOT_SUPPORTED,
                    message=f"Feature '{toggle_key}' not supported by {backend}: {reason}",
                    field=toggle_key,
                ))

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
            errors.append(ValidationError(
                code=ErrorCodes.NOT_SUPPORTED,
                message=f"Parameter '{key}' not supported by {backend}: {reason}",
                field=key,
            ))
            continue

        # Validate type and range (collects errors)
        param_errors = _validate_param_value(key, value, param_schema, backend)
        errors.extend(param_errors)

    _raise_validation_errors(errors)


def _validate_param_value(
    key: str,
    value: Any,
    schema: dict[str, Any],
    backend: str,
) -> list[ValidationError]:
    """
    Validate a single parameter value against its schema.

    Args:
        key: Parameter name
        value: Parameter value
        schema: Parameter schema from capabilities
        backend: Backend name for error messages

    Returns:
        List of ValidationError instances (empty if valid)
    """
    errors: list[ValidationError] = []
    param_type = schema.get("type", "string")

    # Validate range for numeric types
    if param_type in ("int", "float"):
        if value is None:
            return errors  # None is allowed (uses default)

        min_val = schema.get("min")
        max_val = schema.get("max")

        if min_val is not None and value < min_val:
            errors.append(ValidationError(
                code=ErrorCodes.OUT_OF_RANGE,
                message=f"Parameter '{key}' value {value} is below minimum {min_val}",
                field=key,
            ))

        if max_val is not None and value > max_val:
            errors.append(ValidationError(
                code=ErrorCodes.OUT_OF_RANGE,
                message=f"Parameter '{key}' value {value} is above maximum {max_val}",
                field=key,
            ))

    # Validate enum values
    elif param_type == "enum":
        options = schema.get("options", [])
        if value is not None and value not in options:
            errors.append(ValidationError(
                code=ErrorCodes.INVALID_ENUM,
                message=f"Parameter '{key}' value '{value}' not in allowed options: {options}",
                field=key,
            ))

    # Validate boolean
    elif param_type == "bool":
        if value is not None and not isinstance(value, bool):
            errors.append(ValidationError(
                code=ErrorCodes.INVALID_TYPE,
                message=f"Parameter '{key}' must be a boolean, got {type(value).__name__}",
                field=key,
            ))

    # Validate string_list (list of strings)
    elif param_type == "string_list":
        if value is None:
            return errors  # None is allowed (uses default)
        if not isinstance(value, list):
            errors.append(ValidationError(
                code=ErrorCodes.INVALID_TYPE,
                message=f"Parameter '{key}' must be a list of strings, got {type(value).__name__}",
                field=key,
            ))
        else:
            for i, item in enumerate(value):
                if not isinstance(item, str):
                    errors.append(ValidationError(
                        code=ErrorCodes.INVALID_TYPE,
                        message=f"Parameter '{key}' item {i} must be a string, got {type(item).__name__}",
                        field=f"{key}[{i}]",
                    ))

    return errors
