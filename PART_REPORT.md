# Part 1: Contracts & Shared Interfaces - Report

**Worktree:** `wt-contracts`
**Completed:** 2026-01-03

---

## Files Created/Modified

### Created

| File | Purpose |
|------|---------|
| `packages/shared/src/interfaces.py` | Plugin interface ABCs (TrainingBackend, GenerationBackend, VideoBackend) |

### Modified

| File | Changes |
|------|---------|
| `packages/shared/src/types.py` | Added 4 new result types (TrainingProgress, TrainingResult, GenerationProgress, GenerationResult) |
| `packages/shared/src/__init__.py` | Expanded exports to include all types, interfaces, and events |

---

## Interface Signatures Defined

### TrainingBackend (ABC)

```python
class TrainingBackend(ABC):
    @property
    def name(self) -> str: ...
    @property
    def version(self) -> str: ...

    def get_capabilities(self) -> dict[str, Any]: ...
    async def validate_config(self, config: TrainingConfig) -> list[str]: ...
    async def train(
        self,
        config: TrainingConfig,
        images_dir: Path,
        output_path: Path,
        trigger_word: str,
        progress_callback: Callable[[TrainingProgress], None] | None = None,
        job_id: str | None = None,
    ) -> TrainingResult: ...
    async def cancel(self, job_id: str) -> bool: ...
```

### GenerationBackend (ABC)

```python
class GenerationBackend(ABC):
    @property
    def name(self) -> str: ...
    @property
    def version(self) -> str: ...

    def get_capabilities(self) -> dict[str, Any]: ...
    async def validate_config(self, config: GenerationConfig) -> list[str]: ...
    async def generate(
        self,
        config: GenerationConfig,
        lora_path: Path | None,
        output_dir: Path,
        progress_callback: Callable[[GenerationProgress], None] | None = None,
        job_id: str | None = None,
    ) -> GenerationResult: ...
    async def cancel(self, job_id: str) -> bool: ...
    async def health_check(self) -> dict[str, Any]: ...
```

### VideoBackend (ABC) - Scaffold

```python
class VideoBackend(ABC):
    @property
    def name(self) -> str: ...
    @property
    def version(self) -> str: ...

    def get_capabilities(self) -> dict[str, Any]: ...
    async def generate(self, prompt: str, output_dir: Path, **kwargs: Any) -> dict[str, Any]: ...
```

---

## New Types Added to types.py

### TrainingProgress (lines 231-253)

Progress callback type for `TrainingBackend.train()`:
- `step`, `total_steps` (required)
- `loss`, `learning_rate`, `eta_seconds`, `iteration_speed` (optional metrics)
- `message`, `sample_path`, `checkpoint_path` (optional status)
- `progress_pct` property (computed)

### TrainingResult (lines 256-269)

Return type for `TrainingBackend.train()`:
- `success: bool` (required)
- `model_path`, `final_loss`, `total_steps`, `training_time_seconds`
- `error_message` (if failed)
- `checkpoints`, `samples` (artifact paths)

### GenerationProgress (lines 272-288)

Progress callback type for `GenerationBackend.generate()`:
- `step`, `total_steps` (required)
- `message`, `preview_path` (optional)
- `progress_pct` property (computed)

### GenerationResult (lines 291-301)

Return type for `GenerationBackend.generate()`:
- `success: bool` (required)
- `output_paths: list[str]`
- `generation_time_seconds`, `seed_used`
- `error_message` (if failed)

---

## Design Decisions

### 1. ABCs Over Protocols

Used `ABC` from `abc` module instead of `Protocol` for stricter interface enforcement. Implementations must explicitly inherit from the backend class, which provides:
- Clear error messages when methods are missing
- Self-documenting code structure
- IDE support for "implement abstract methods"

### 2. Stateless Design

Interfaces are designed to be stateless where possible:
- All configuration passed per-call (not stored on instance)
- `job_id` passed to methods rather than stored
- Enables easier testing and scaling

### 3. No Exceptions Policy

Backend methods should NOT raise exceptions. Instead:
- Return `TrainingResult(success=False, error_message="...")`
- Return `GenerationResult(success=False, error_message="...")`

This simplifies error handling in the Worker and ensures consistent error propagation.

### 4. Separate Progress vs Result Types

Created distinct types:
- `TrainingProgress` / `GenerationProgress` - for streaming updates during execution
- `TrainingResult` / `GenerationResult` - for final completion status

This is cleaner than overloading a single type for both purposes.

### 5. VideoBackend Scaffold

Included `VideoBackend` as a scaffold to maintain architectural symmetry, even though video generation is not yet implemented. This prevents breaking changes when video support is added.

### 6. Pydantic BaseModel for Types

Result types use Pydantic `BaseModel` for consistency with existing codebase types. This provides:
- JSON serialization for API responses
- Field validation
- Schema generation

---

## Commands Run and Output

```bash
# Verification of imports (in temporary venv with pydantic installed)
$ python -c "from packages.shared.src.interfaces import TrainingBackend, GenerationBackend, VideoBackend; ..."

✓ interfaces.py imports work
✓ result types import work
✓ all imports from __init__.py work
✓ TrainingBackend methods: ['cancel', 'get_capabilities', 'name', 'train', 'validate_config', 'version']
✓ GenerationBackend methods: ['cancel', 'generate', 'get_capabilities', 'health_check', 'name', 'validate_config', 'version']
```

---

## Files NOT Modified (Per Scope)

The following files were explicitly NOT touched per Part 1 scope:
- `apps/*` (no API or Worker changes)
- `vendor/*` (vendored code)
- Any test files
- `packages/plugins/*` (will be implemented in Part 2)

---

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| `packages/shared/src/interfaces.py` exists with TrainingBackend and GenerationBackend ABCs | ✅ |
| All dataclass types (TrainingProgress, TrainingResult, etc.) are in types.py | ✅ |
| `python -c "from packages.shared.src import ..."` works without errors | ✅ |
| No changes to any files outside `packages/shared/src/` | ✅ |

---

## How Other Parts Should Import

```python
# From packages.shared.src (or packages.shared.src.interfaces)
from packages.shared.src import (
    # Interfaces
    TrainingBackend,
    GenerationBackend,

    # Config types (input)
    TrainingConfig,
    GenerationConfig,

    # Progress types (callbacks)
    TrainingProgress,
    GenerationProgress,

    # Result types (output)
    TrainingResult,
    GenerationResult,
)
```
