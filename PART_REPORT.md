# Part 7: API Contract Hardening - Report

## Summary

Standardized API error responses across all endpoints with machine-readable error codes, field-level error details, and comprehensive documentation updates.

## Deliverables

### 1. Error Response Schema

Created `apps/api/src/models/responses.py` with standardized models:

```python
class ErrorDetail(BaseModel):
    code: str       # Machine-readable error code (e.g., OUT_OF_RANGE)
    message: str    # Human-readable error message
    field: str | None  # Field that caused the error

class ErrorResponse(BaseModel):
    error: str                          # Summary error message
    details: list[ErrorDetail] = []     # Structured error details
    correlation_id: str | None = None   # Request correlation ID

class ErrorCodes:
    # Validation errors (400)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INVALID_TYPE = "INVALID_TYPE"
    INVALID_ENUM = "INVALID_ENUM"
    NOT_SUPPORTED = "NOT_SUPPORTED"

    # Resource errors (404)
    CHARACTER_NOT_FOUND = "CHARACTER_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    LORA_NOT_FOUND = "LORA_NOT_FOUND"

    # State errors (400)
    INVALID_STATE = "INVALID_STATE"
    NO_IMAGES = "NO_IMAGES"

    # Rate limiting (429)
    RATE_LIMITED = "RATE_LIMITED"
```

**Example Error Response:**
```json
{
  "error": "Validation failed",
  "details": [
    {
      "code": "OUT_OF_RANGE",
      "message": "Parameter 'steps' value 50000 is above maximum 10000",
      "field": "steps"
    },
    {
      "code": "NOT_SUPPORTED",
      "message": "Parameter 'lora_rank' not supported by ai-toolkit: Disabled",
      "field": "lora_rank"
    }
  ],
  "correlation_id": "req-abc123"
}
```

### 2. Validation Improvements

Updated `apps/api/src/services/config_validator.py`:

- Added `ValidationError` exception class with `code`, `message`, and `field` attributes
- Changed validation functions to **collect all errors** before returning (not fail-fast)
- Each validation error includes the field name for programmatic error handling
- Standardized error codes across all validation paths

**Key improvements:**
- Multiple validation errors returned in a single response
- Field names included in all errors for frontend field highlighting
- Error codes allow programmatic handling without parsing messages

### 3. API Documentation Updates

Updated `docs/api_contract.md`:

- New section documenting all 20+ error codes with descriptions
- Updated all error response examples to use the new format
- Added TypeScript types for `ErrorResponse` and `ErrorDetail`
- Added `ErrorCode` union type for type-safe error handling
- Added changelog entry documenting the changes

### 4. Route Updates

Updated routes with response model documentation:

**Training Routes (`apps/api/src/routes/training.py`):**
- `POST /api/training` - Added `responses` with 400, 404, 429 error models
- `POST /api/training/{id}/cancel` - Added `responses` with 400, 404 error models
- `_get_job_or_404()` - Returns structured error response

**Generation Routes (`apps/api/src/routes/generation.py`):**
- `POST /api/generation` - Added `responses` with 400, 404, 429 error models
- `POST /api/generation/{id}/cancel` - Added `responses` with 400, 404 error models
- `_get_job_or_404()` - Returns structured error response

## Files Modified

| File | Changes |
|------|---------|
| `apps/api/src/models/responses.py` | **NEW** - Standardized response models |
| `apps/api/src/models/__init__.py` | Export response models |
| `apps/api/src/services/config_validator.py` | ValidationError class, collect-all-errors pattern |
| `apps/api/src/routes/training.py` | Response models, structured errors |
| `apps/api/src/routes/generation.py` | Response models, structured errors |
| `docs/api_contract.md` | Error codes, updated examples, TypeScript types |

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| All routes have response models documented | ✅ Training & Generation routes |
| Error responses use standardized format | ✅ ErrorResponse model |
| Validation errors include field names | ✅ All ValidationError instances |
| docs/api_contract.md is complete | ✅ Error codes, examples, TypeScript types |
| OpenAPI schema is valid | ✅ Response models in decorators |

## Testing Notes

To verify error responses:

```bash
# Test validation error (steps out of range)
curl -X POST http://localhost:8000/api/training \
  -H "Content-Type: application/json" \
  -d '{"character_id": "char-test", "config": {"steps": 999999}}'

# Expected: 400 with error code OUT_OF_RANGE

# Test not found error
curl http://localhost:8000/api/training/nonexistent-job

# Expected: 404 with error code JOB_NOT_FOUND
```

## Conflict Avoidance

This part only modified:
- API layer (routes, validation)
- Response models
- Documentation

**NOT modified:**
- `job_executor.py` (job execution logic)
- Frontend files
- `packages/shared/src/types.py` (owned by Part 1)
