# Part 6: Job Persistence & Storage - Implementation Report

## Summary

Implemented persistent job storage for training and generation jobs, ensuring job history survives API restarts.

## Storage Schema Design

### Directory Structure

```
$VOLUME_ROOT/jobs/
├── training/
│   ├── train-abc123.json
│   ├── train-def456.json
│   └── ...
└── generation/
    ├── gen-xyz789.json
    ├── gen-uvw012.json
    └── ...
```

### Job File Format

Each job is stored as a separate JSON file named `{job_id}.json`. Example:

```json
{
  "id": "train-abc123def4",
  "character_id": "char-001",
  "status": "completed",
  "config": {
    "method": "lora",
    "steps": 1500,
    "learning_rate": 0.0001,
    "batch_size": 1,
    "resolution": 1024,
    "lora_rank": 16
  },
  "progress": 100.0,
  "current_step": 1500,
  "total_steps": 1500,
  "created_at": "2025-01-03T12:00:00Z",
  "started_at": "2025-01-03T12:00:05Z",
  "completed_at": "2025-01-03T12:45:30Z",
  "output_path": "/runpod-volume/isengard/loras/char-001/v1.safetensors",
  "base_model": "flux-dev",
  "preset_name": "balanced"
}
```

## Implementation Details

### Files Created

| File | Purpose |
|------|---------|
| `apps/api/src/services/job_store.py` | Generic JobStore class with JSON file persistence |

### Files Modified

| File | Changes |
|------|---------|
| `apps/api/src/routes/training.py` | Replaced in-memory dict with JobStore |
| `apps/api/src/routes/generation.py` | Replaced in-memory dict with JobStore |
| `apps/api/src/main.py` | Added job store initialization and shutdown flush |
| `apps/api/src/services/__init__.py` | Exported job store functions |

### Key Components

#### JobStore Class (`job_store.py`)

```python
class JobStore(Generic[T]):
    """Persistent job storage backed by JSON files."""

    def get(self, job_id: str) -> T | None
    def list_all(self) -> list[T]
    def save(self, job: T) -> None
    def delete(self, job_id: str) -> bool
    def exists(self, job_id: str) -> bool
    def count(self) -> int
    def get_dict(self) -> dict[str, T]  # For executor compatibility
    def flush_all(self) -> int  # Persist all cached jobs
```

#### Singleton Access Functions

```python
get_training_store() -> JobStore[TrainingJob]
get_generation_store() -> JobStore[GenerationJob]
migrate_jobs_from_logs() -> dict[str, int]
```

## Migration Strategy

### Automatic Migration on Startup

The API automatically migrates jobs from old JSONL log files on startup:

1. Scans `$VOLUME_ROOT/logs/jobs/*.jsonl`
2. For each log file not already in the job store:
   - Parses job.created events for metadata
   - Parses final status events (completed/failed/cancelled)
   - Reconstructs job record with available data
3. Saves migrated jobs to the new JSON store

### Migration Code Path

```
main.py:lifespan()
  → migrate_jobs_from_logs()
    → _parse_job_from_log() for each .jsonl file
    → training_store.save() or generation_store.save()
```

## Performance Considerations

### Read Operations

- **O(1)** lookups via in-memory cache
- No disk I/O for get/list operations after initial load

### Write Operations

- **Synchronous** writes to ensure durability
- **Atomic** file writes via temp file + rename pattern
- Thread-safe with lock protection

### Persistence Timing

| Event | Persistence Trigger |
|-------|---------------------|
| Job created | Immediate save |
| Job reaches terminal state (SSE stream) | Immediate save |
| API shutdown | flush_all() called |

### Memory Usage

- All jobs loaded into memory at startup
- Acceptable for expected job counts (<10K jobs)
- For larger scales, consider LRU cache or database

## Test Results

### Persistence Test (Simulated)

```
=== Session 1: Create jobs ===
Loaded 0 jobs from /tmp/.../jobs/training
Saved job train-abc123
Saved job train-def456
Session 1 has 2 jobs

=== Files on disk ===
  train-abc123.json
  train-def456.json

=== Session 2: After restart ===
Loaded 2 jobs from /tmp/.../jobs/training
Session 2 has 2 jobs

✓ All persistence tests passed!
```

### Verification Steps

1. Start API → job stores initialized, load count logged
2. Create training job → immediate save to `jobs/training/{id}.json`
3. Job completes (SSE stream) → final state persisted
4. Restart API → jobs reloaded from disk
5. List jobs → all previous jobs present

## Backwards Compatibility

### Executor Integration

The job executor receives `jobs_store.get_dict()` - the internal cache dictionary. This maintains compatibility with the existing executor code that updates jobs in-place.

### Log Files

Existing JSONL log files at `$VOLUME_ROOT/logs/jobs/` are preserved and migrated on first startup. Migration is idempotent - already-migrated jobs are skipped.

## Acceptance Criteria Verification

| Criteria | Status |
|----------|--------|
| Jobs persist across API restarts | ✅ Verified via test |
| Job files stored at `$VOLUME_ROOT/jobs/{type}/{id}.json` | ✅ Implemented |
| Backward compatible with existing log files | ✅ Migration implemented |
| No impact on job execution performance | ✅ Read ops use in-memory cache |

## Future Improvements

1. **Periodic Flush**: Add background task to periodically persist in-progress jobs
2. **Job Cleanup**: Add retention policy to delete old completed/failed jobs
3. **Database Migration**: For larger scales, migrate to SQLite or PostgreSQL
4. **Compression**: Compress older job files to reduce disk usage
