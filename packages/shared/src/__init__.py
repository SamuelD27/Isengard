# Isengard Shared Source

# Logging utilities
from .logging import get_logger, with_correlation_id, set_correlation_id

# Configuration
from .config import get_config, Config

# Core types
from .types import (
    JobStatus,
    JobType,
    TrainingMethod,
    Character,
    CharacterCreate,
    CharacterUpdate,
    TrainingConfig,
    TrainingJob,
    StartTrainingRequest,
    GenerationConfig,
    GenerationJob,
    GenerateImageRequest,
    # Plugin interface result types
    TrainingProgress,
    TrainingResult,
    GenerationProgress,
    GenerationResult,
    JobProgressEvent,
    # Captioning types
    CaptioningStyle,
    CaptioningConfig,
    CaptioningJob,
    StartCaptioningRequest,
    CaptioningProgress,
    CaptioningResult,
)

# Plugin interfaces
from .interfaces import (
    TrainingBackend,
    GenerationBackend,
    VideoBackend,
    CaptioningBackend,
)

# Event system types
from .events import (
    TrainingStage,
    ProgressBarType,
    EventType,
    GPUMetrics,
    TrainingProgressEvent,
    ArtifactEvent,
    EventBus,
    InMemoryEventBus,
    get_event_bus,
    set_event_bus,
    get_gpu_metrics,
)

__all__ = [
    # Logging
    "get_logger",
    "with_correlation_id",
    "set_correlation_id",
    # Config
    "get_config",
    "Config",
    # Enums
    "JobStatus",
    "JobType",
    "TrainingMethod",
    # Character types
    "Character",
    "CharacterCreate",
    "CharacterUpdate",
    # Training types
    "TrainingConfig",
    "TrainingJob",
    "StartTrainingRequest",
    "TrainingProgress",
    "TrainingResult",
    # Generation types
    "GenerationConfig",
    "GenerationJob",
    "GenerateImageRequest",
    "GenerationProgress",
    "GenerationResult",
    # Captioning types
    "CaptioningStyle",
    "CaptioningConfig",
    "CaptioningJob",
    "StartCaptioningRequest",
    "CaptioningProgress",
    "CaptioningResult",
    # SSE events
    "JobProgressEvent",
    # Plugin interfaces
    "TrainingBackend",
    "GenerationBackend",
    "VideoBackend",
    "CaptioningBackend",
    # Event system
    "TrainingStage",
    "ProgressBarType",
    "EventType",
    "GPUMetrics",
    "TrainingProgressEvent",
    "ArtifactEvent",
    "EventBus",
    "InMemoryEventBus",
    "get_event_bus",
    "set_event_bus",
    "get_gpu_metrics",
]
