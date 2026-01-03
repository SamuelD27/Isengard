"""
Job Store Service

Persists job metadata to JSON files on disk.
Uses in-memory cache for fast reads with synchronous disk writes for persistence.

Storage Layout:
    $VOLUME_ROOT/jobs/
    ├── training/
    │   ├── train-abc123.json
    │   └── train-def456.json
    └── generation/
        ├── gen-xyz789.json
        └── gen-uvw012.json

Features:
    - Jobs persist across API restarts
    - Backwards compatible with existing log files (migration support)
    - Thread-safe for single-writer scenarios (FastAPI BackgroundTasks)
"""

import json
import threading
from pathlib import Path
from typing import TypeVar, Generic, Type
from datetime import datetime

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_logger
from packages.shared.src.types import TrainingJob, GenerationJob

logger = get_logger("api.services.job_store")

T = TypeVar('T', TrainingJob, GenerationJob)


class JobStore(Generic[T]):
    """
    Persistent job storage backed by JSON files.

    Provides fast in-memory lookups with durable disk persistence.
    Each job is stored as a separate JSON file for atomic operations.
    """

    def __init__(self, job_type: str, model_class: Type[T]):
        """
        Initialize job store.

        Args:
            job_type: "training" or "generation" - determines subdirectory
            model_class: Pydantic model class for deserialization
        """
        self.job_type = job_type
        self.model_class = model_class
        self._cache: dict[str, T] = {}
        self._lock = threading.Lock()

        # Setup storage directory
        config = get_global_config()
        self._store_dir = config.volume_root / "jobs" / job_type
        self._store_dir.mkdir(parents=True, exist_ok=True)

        # Load existing jobs from disk
        self._load_all()

        logger.info(f"JobStore initialized", extra={
            "event": "job_store.init",
            "job_type": job_type,
            "store_dir": str(self._store_dir),
            "loaded_count": len(self._cache),
        })

    def _load_all(self) -> None:
        """Load all jobs from disk into cache."""
        loaded_count = 0
        error_count = 0

        for file_path in self._store_dir.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)

                # Parse using the model class
                job = self.model_class(**data)
                self._cache[job.id] = job
                loaded_count += 1

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse job file", extra={
                    "event": "job_store.load_error",
                    "file": str(file_path),
                    "error": str(e),
                })
                error_count += 1
            except Exception as e:
                logger.warning(f"Failed to load job", extra={
                    "event": "job_store.load_error",
                    "file": str(file_path),
                    "error": str(e),
                    "error_type": type(e).__name__,
                })
                error_count += 1

        if error_count > 0:
            logger.warning(f"Some jobs failed to load", extra={
                "event": "job_store.load_complete",
                "loaded": loaded_count,
                "errors": error_count,
            })

    def get(self, job_id: str) -> T | None:
        """
        Get a job by ID.

        Args:
            job_id: The job identifier

        Returns:
            The job if found, None otherwise
        """
        with self._lock:
            return self._cache.get(job_id)

    def list_all(self) -> list[T]:
        """
        List all jobs.

        Returns:
            List of all jobs (copy of cache values)
        """
        with self._lock:
            return list(self._cache.values())

    def save(self, job: T) -> None:
        """
        Save job to cache and disk.

        This is a synchronous write to ensure durability.
        For high-frequency updates during training/generation,
        the executor should batch updates where appropriate.

        Args:
            job: The job to save
        """
        with self._lock:
            self._cache[job.id] = job
            self._persist(job)

    def _persist(self, job: T) -> None:
        """Write job to disk as JSON."""
        file_path = self._store_dir / f"{job.id}.json"
        temp_path = file_path.with_suffix('.json.tmp')

        try:
            # Serialize with Pydantic, handling datetime
            data = job.model_dump(mode='json')

            # Write to temp file first, then rename (atomic on POSIX)
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            temp_path.rename(file_path)

        except Exception as e:
            logger.error(f"Failed to persist job", extra={
                "event": "job_store.persist_error",
                "job_id": job.id,
                "error": str(e),
                "error_type": type(e).__name__,
            })
            # Clean up temp file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass
            raise

    def delete(self, job_id: str) -> bool:
        """
        Delete a job from cache and disk.

        Args:
            job_id: The job identifier

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if job_id not in self._cache:
                return False

            del self._cache[job_id]

            file_path = self._store_dir / f"{job_id}.json"
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete job file", extra={
                        "event": "job_store.delete_error",
                        "job_id": job_id,
                        "error": str(e),
                    })

            return True

    def exists(self, job_id: str) -> bool:
        """Check if a job exists."""
        with self._lock:
            return job_id in self._cache

    def count(self) -> int:
        """Get total number of jobs."""
        with self._lock:
            return len(self._cache)

    def get_dict(self) -> dict[str, T]:
        """
        Get the internal cache dictionary.

        WARNING: This returns the actual cache dict for compatibility with
        existing code that passes jobs_store to executors. The executor
        updates jobs in-place. Call flush_all() periodically or at shutdown
        to persist changes.

        Returns:
            The internal cache dictionary
        """
        return self._cache

    def flush_all(self) -> int:
        """
        Persist all jobs in cache to disk.

        Useful for shutdown or periodic persistence of executor updates
        that bypass the save() method.

        Returns:
            Number of jobs persisted
        """
        with self._lock:
            count = 0
            for job_id, job in self._cache.items():
                try:
                    self._persist(job)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to flush job", extra={
                        "event": "job_store.flush_error",
                        "job_id": job_id,
                        "error": str(e),
                    })
            return count


# Singleton instances - initialized lazily
_training_store: JobStore[TrainingJob] | None = None
_generation_store: JobStore[GenerationJob] | None = None


def get_training_store() -> JobStore[TrainingJob]:
    """Get the training job store singleton."""
    global _training_store
    if _training_store is None:
        _training_store = JobStore[TrainingJob]("training", TrainingJob)
    return _training_store


def get_generation_store() -> JobStore[GenerationJob]:
    """Get the generation job store singleton."""
    global _generation_store
    if _generation_store is None:
        _generation_store = JobStore[GenerationJob]("generation", GenerationJob)
    return _generation_store


def migrate_jobs_from_logs() -> dict[str, int]:
    """
    Migrate job info from log files to job store.

    Scans existing JSONL log files and attempts to reconstruct job records
    for any jobs that aren't already in the store.

    Returns:
        Dict with migration stats: {"training": N, "generation": M, "errors": E}
    """
    config = get_global_config()
    logs_dir = config.volume_root / "logs" / "jobs"

    stats = {"training": 0, "generation": 0, "errors": 0}

    if not logs_dir.exists():
        logger.info("No job logs directory found, skipping migration", extra={
            "event": "job_store.migrate_skip",
            "logs_dir": str(logs_dir),
        })
        return stats

    training_store = get_training_store()
    generation_store = get_generation_store()

    for log_file in logs_dir.glob("*.jsonl"):
        job_id = log_file.stem

        # Skip if already in store
        if training_store.exists(job_id) or generation_store.exists(job_id):
            continue

        try:
            job_data = _parse_job_from_log(log_file)
            if job_data is None:
                continue

            # Determine job type from ID prefix or log content
            if job_id.startswith("train-"):
                job = TrainingJob(**job_data)
                training_store.save(job)
                stats["training"] += 1
                logger.debug(f"Migrated training job from logs", extra={
                    "event": "job_store.migrate_job",
                    "job_id": job_id,
                })
            elif job_id.startswith("gen-"):
                job = GenerationJob(**job_data)
                generation_store.save(job)
                stats["generation"] += 1
                logger.debug(f"Migrated generation job from logs", extra={
                    "event": "job_store.migrate_job",
                    "job_id": job_id,
                })
            else:
                logger.warning(f"Unknown job type in logs", extra={
                    "event": "job_store.migrate_unknown",
                    "job_id": job_id,
                })

        except Exception as e:
            logger.warning(f"Failed to migrate job from logs", extra={
                "event": "job_store.migrate_error",
                "job_id": job_id,
                "error": str(e),
            })
            stats["errors"] += 1

    logger.info("Job migration complete", extra={
        "event": "job_store.migrate_complete",
        **stats,
    })

    return stats


def _parse_job_from_log(log_file: Path) -> dict | None:
    """
    Parse job metadata from a JSONL log file.

    Looks for job.created events and final status to reconstruct
    the job record.

    Args:
        log_file: Path to the JSONL log file

    Returns:
        Dict with job data if parseable, None otherwise
    """
    job_id = log_file.stem
    job_data = {"id": job_id}

    try:
        with open(log_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event = entry.get("event", "")

                # Extract creation info
                if event == "job.created":
                    if "character_id" in entry:
                        job_data["character_id"] = entry["character_id"]
                    if "method" in entry:
                        job_data.setdefault("config", {})["method"] = entry["method"]
                    if "steps" in entry:
                        job_data.setdefault("config", {})["steps"] = entry["steps"]
                    if "timestamp" in entry:
                        job_data["created_at"] = entry["timestamp"]

                # Extract final status
                if event in ["job.completed", "job.failed", "job.cancelled"]:
                    if event == "job.completed":
                        job_data["status"] = "completed"
                        job_data["progress"] = 100.0
                    elif event == "job.failed":
                        job_data["status"] = "failed"
                        if "error" in entry:
                            job_data["error_message"] = entry["error"]
                    elif event == "job.cancelled":
                        job_data["status"] = "cancelled"

                    if "timestamp" in entry:
                        job_data["completed_at"] = entry["timestamp"]

                # Extract progress info
                if event == "training.progress":
                    if "current_step" in entry:
                        job_data["current_step"] = entry["current_step"]
                    if "total_steps" in entry:
                        job_data["total_steps"] = entry["total_steps"]
                    if "progress" in entry:
                        job_data["progress"] = entry["progress"]

                # Extract output paths
                if event == "generation.output" and "path" in entry:
                    job_data.setdefault("output_paths", []).append(entry["path"])

        # Validate minimum required fields
        if job_id.startswith("train-"):
            if "character_id" not in job_data:
                logger.debug(f"Training job missing character_id", extra={
                    "job_id": job_id,
                })
                return None
            # Provide defaults for required fields
            job_data.setdefault("config", {"method": "lora", "steps": 1000})
            job_data.setdefault("status", "failed")  # Assume failed if no completion event
            job_data.setdefault("progress", 0.0)
            job_data.setdefault("current_step", 0)
            job_data.setdefault("total_steps", job_data.get("config", {}).get("steps", 1000))

        elif job_id.startswith("gen-"):
            # Generation jobs need config with prompt
            if "config" not in job_data or "prompt" not in job_data.get("config", {}):
                job_data.setdefault("config", {"prompt": "[migrated from logs]"})
            job_data.setdefault("status", "failed")
            job_data.setdefault("progress", 0.0)
            job_data.setdefault("output_paths", [])

        return job_data

    except Exception as e:
        logger.debug(f"Failed to parse log file", extra={
            "job_id": job_id,
            "error": str(e),
        })
        return None
