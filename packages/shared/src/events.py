"""
Isengard Event System

Defines canonical event schemas for training progress, logging, and SSE streaming.
All services must use these schemas for consistency.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Callable, Any
from collections import defaultdict

from .config import get_global_config


class TrainingStage(str, Enum):
    """Training pipeline stages."""
    QUEUED = "queued"
    INITIALIZING = "initializing"
    PREPARING_DATASET = "preparing_dataset"
    CAPTIONING = "captioning"
    TRAINING = "training"
    SAMPLING = "sampling"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """Event types for structured logging."""
    # Job lifecycle
    JOB_CREATED = "job.created"
    JOB_QUEUED = "job.queued"
    JOB_STARTED = "job.started"
    JOB_PROGRESS = "job.progress"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"

    # Training specific
    TRAINING_STEP = "training.step"
    TRAINING_CHECKPOINT = "training.checkpoint"
    TRAINING_SAMPLE = "training.sample"

    # Subprocess
    SUBPROCESS_START = "subprocess.start"
    SUBPROCESS_STDOUT = "subprocess.stdout"
    SUBPROCESS_STDERR = "subprocess.stderr"
    SUBPROCESS_EXIT = "subprocess.exit"

    # System
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"

    # Artifact
    ARTIFACT_CREATED = "artifact.created"


@dataclass
class GPUMetrics:
    """GPU metrics snapshot."""
    utilization: float = 0.0  # 0-100%
    memory_used: float = 0.0  # GB
    memory_total: float = 0.0  # GB
    temperature: float = 0.0  # Celsius
    power_watts: float = 0.0  # Watts

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrainingProgressEvent:
    """
    Canonical training progress event schema.

    Used for:
    - SSE streaming to frontend
    - JSONL logging to job log files
    - Redis pub/sub progress updates
    """
    job_id: str
    correlation_id: str | None = None
    status: str = "running"
    stage: TrainingStage = TrainingStage.TRAINING
    step: int = 0
    steps_total: int = 0
    progress_pct: float = 0.0
    loss: float | None = None
    lr: float | None = None
    eta_seconds: int | None = None
    gpu: GPUMetrics | None = None
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Optional fields for specific events
    sample_path: str | None = None
    checkpoint_path: str | None = None
    error: str | None = None
    error_type: str | None = None
    error_stack: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary, filtering None values."""
        result = {
            "job_id": self.job_id,
            "status": self.status,
            "stage": self.stage.value if isinstance(self.stage, TrainingStage) else self.stage,
            "step": self.step,
            "steps_total": self.steps_total,
            "progress_pct": round(self.progress_pct, 2),
            "message": self.message,
            "timestamp": self.timestamp,
        }

        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        if self.loss is not None:
            result["loss"] = round(self.loss, 6)
        if self.lr is not None:
            result["lr"] = self.lr
        if self.eta_seconds is not None:
            result["eta_seconds"] = self.eta_seconds
        if self.gpu is not None:
            result["gpu"] = self.gpu.to_dict()
        if self.sample_path:
            result["sample_path"] = self.sample_path
        if self.checkpoint_path:
            result["checkpoint_path"] = self.checkpoint_path
        if self.error:
            result["error"] = self.error
        if self.error_type:
            result["error_type"] = self.error_type
        if self.error_stack:
            result["error_stack"] = self.error_stack

        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def to_sse(self) -> dict:
        """Format for SSE EventSourceResponse."""
        event_name = "complete" if self.status in ("completed", "failed", "cancelled") else "progress"
        return {
            "event": event_name,
            "data": self.to_json(),
        }


@dataclass
class ArtifactEvent:
    """Event emitted when a training artifact is created."""
    job_id: str
    artifact_type: str  # "sample", "checkpoint", "model"
    path: str
    step: int | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "step": self.step,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ============================================
# Event Bus Abstraction
# ============================================

class EventBus(ABC):
    """
    Abstract event bus for publishing and subscribing to job events.

    Implementations:
    - InMemoryEventBus: For single-process local dev
    - RedisEventBus: For multi-process production
    """

    @abstractmethod
    async def publish(self, job_id: str, event: TrainingProgressEvent | ArtifactEvent) -> None:
        """Publish an event for a job."""
        pass

    @abstractmethod
    async def subscribe(self, job_id: str) -> AsyncGenerator[TrainingProgressEvent | ArtifactEvent, None]:
        """Subscribe to events for a job."""
        pass

    @abstractmethod
    async def get_history(self, job_id: str, limit: int = 100) -> list[dict]:
        """Get recent event history for a job."""
        pass


class InMemoryEventBus(EventBus):
    """
    In-memory event bus for single-process operation.

    Used in local development and fast-test mode.
    """

    def __init__(self, max_history: int = 100):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: dict[str, list[dict]] = defaultdict(list)
        self._max_history = max_history

    async def publish(self, job_id: str, event: TrainingProgressEvent | ArtifactEvent) -> None:
        """Publish event to all subscribers and store in history."""
        event_dict = event.to_dict()

        # Store in history
        self._history[job_id].append(event_dict)
        if len(self._history[job_id]) > self._max_history:
            self._history[job_id] = self._history[job_id][-self._max_history:]

        # Notify subscribers
        for queue in self._subscribers[job_id]:
            try:
                await queue.put(event_dict)
            except:
                pass  # Subscriber may have disconnected

    async def subscribe(self, job_id: str) -> AsyncGenerator[dict, None]:
        """Subscribe to events for a job."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[job_id].append(queue)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event

                    # Check for terminal event
                    if event.get("status") in ("completed", "failed", "cancelled"):
                        return
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"type": "keepalive", "job_id": job_id}
        finally:
            if queue in self._subscribers[job_id]:
                self._subscribers[job_id].remove(queue)

    async def get_history(self, job_id: str, limit: int = 100) -> list[dict]:
        """Get recent event history."""
        return self._history[job_id][-limit:]

    def clear_job(self, job_id: str) -> None:
        """Clear all data for a completed job."""
        if job_id in self._history:
            del self._history[job_id]
        if job_id in self._subscribers:
            del self._subscribers[job_id]


# Singleton event bus
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = InMemoryEventBus()
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Set a custom event bus (e.g., Redis-based)."""
    global _event_bus
    _event_bus = bus


# ============================================
# GPU Metrics Collection (Optional NVML)
# ============================================

_nvml_available = False
_nvml_handle = None

try:
    import pynvml
    pynvml.nvmlInit()
    _nvml_available = True
    _nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
except:
    pass


def get_gpu_metrics() -> GPUMetrics | None:
    """Get current GPU metrics if NVML is available."""
    if not _nvml_available or _nvml_handle is None:
        return None

    try:
        import pynvml

        utilization = pynvml.nvmlDeviceGetUtilizationRates(_nvml_handle)
        memory = pynvml.nvmlDeviceGetMemoryInfo(_nvml_handle)
        temp = pynvml.nvmlDeviceGetTemperature(_nvml_handle, pynvml.NVML_TEMPERATURE_GPU)
        power = pynvml.nvmlDeviceGetPowerUsage(_nvml_handle) / 1000.0  # mW to W

        return GPUMetrics(
            utilization=utilization.gpu,
            memory_used=memory.used / (1024**3),  # bytes to GB
            memory_total=memory.total / (1024**3),
            temperature=temp,
            power_watts=power,
        )
    except:
        return None
