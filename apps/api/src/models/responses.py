"""
Standardized API Response Models

Provides consistent error and success response formats across all endpoints.
Includes structured error details with error codes and field information.
"""

from pydantic import BaseModel, Field
from typing import Any


class ErrorDetail(BaseModel):
    """Individual error detail for validation or processing errors."""

    code: str = Field(
        ...,
        description="Machine-readable error code (e.g., OUT_OF_RANGE, NOT_FOUND)",
        examples=["OUT_OF_RANGE", "INVALID_TYPE", "NOT_SUPPORTED"]
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Value 50000 exceeds maximum of 10000"]
    )
    field: str | None = Field(
        default=None,
        description="Field name that caused the error, if applicable",
        examples=["steps", "learning_rate"]
    )


class ErrorResponse(BaseModel):
    """
    Standardized error response format.

    All API errors should use this format for consistency.
    The 'error' field provides a summary, while 'details' provides
    structured information for programmatic error handling.
    """

    error: str = Field(
        ...,
        description="Summary error message",
        examples=["Validation failed", "Resource not found"]
    )
    details: list[ErrorDetail] = Field(
        default_factory=list,
        description="List of specific error details"
    )
    correlation_id: str | None = Field(
        default=None,
        description="Request correlation ID for tracing"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": "Validation failed",
                    "details": [
                        {
                            "code": "OUT_OF_RANGE",
                            "message": "steps must be between 100 and 10000",
                            "field": "steps"
                        }
                    ],
                    "correlation_id": "req-abc123"
                }
            ]
        }
    }


class SuccessResponse(BaseModel):
    """
    Generic success response for operations that don't return specific data.

    Use for delete confirmations, status updates, etc.
    """

    success: bool = Field(
        default=True,
        description="Whether the operation succeeded"
    )
    data: Any = Field(
        default=None,
        description="Optional response data"
    )
    message: str | None = Field(
        default=None,
        description="Optional success message",
        examples=["Resource deleted successfully"]
    )


class PaginatedResponse(BaseModel):
    """
    Paginated list response for endpoints that return collections.
    """

    items: list[Any] = Field(
        ...,
        description="List of items in current page"
    )
    total: int = Field(
        ...,
        description="Total number of items across all pages"
    )
    page: int = Field(
        default=1,
        description="Current page number (1-indexed)"
    )
    page_size: int = Field(
        default=20,
        description="Number of items per page"
    )
    has_more: bool = Field(
        ...,
        description="Whether more pages are available"
    )


# Standard error codes for consistency across the API
class ErrorCodes:
    """
    Standard error codes used throughout the API.

    Use these codes in ErrorDetail.code for machine-readable errors.
    """

    # Validation errors (400)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INVALID_TYPE = "INVALID_TYPE"
    INVALID_VALUE = "INVALID_VALUE"
    INVALID_ENUM = "INVALID_ENUM"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_PATH = "INVALID_PATH"

    # Resource errors (404)
    NOT_FOUND = "NOT_FOUND"
    CHARACTER_NOT_FOUND = "CHARACTER_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    IMAGE_NOT_FOUND = "IMAGE_NOT_FOUND"
    LORA_NOT_FOUND = "LORA_NOT_FOUND"

    # State errors (400/409)
    INVALID_STATE = "INVALID_STATE"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    NO_IMAGES = "NO_IMAGES"

    # Rate limiting (429)
    RATE_LIMITED = "RATE_LIMITED"

    # Server errors (500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    BACKEND_ERROR = "BACKEND_ERROR"


# HTTP status code constants for documentation
HTTP_400_VALIDATION = {"model": ErrorResponse, "description": "Validation error"}
HTTP_404_NOT_FOUND = {"model": ErrorResponse, "description": "Resource not found"}
HTTP_429_RATE_LIMITED = {"model": ErrorResponse, "description": "Rate limit exceeded"}
HTTP_500_INTERNAL = {"model": ErrorResponse, "description": "Internal server error"}
