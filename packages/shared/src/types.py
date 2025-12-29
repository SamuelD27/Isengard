"""
Isengard Type Definitions

Shared type definitions used across all services.
These are the canonical types - do not duplicate in service code.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a background job."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Type of background job."""
    TRAINING = "training"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"  # Scaffold only


class TrainingMethod(str, Enum):
    """Supported training methods."""
    LORA = "lora"
    # DORA = "dora"  # Not supported yet
    # FULL_FINETUNE = "full_finetune"  # Not supported


# ============================================
# Character Types
# ============================================

class Character(BaseModel):
    """A character/identity for training and generation."""
    id: str = Field(..., description="Unique character identifier")
    name: str = Field(..., description="Display name")
    description: str | None = Field(None, description="Optional description")
    trigger_word: str = Field(..., description="Trigger word for LoRA activation")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    image_count: int = Field(0, description="Number of training images")
    lora_path: str | None = Field(None, description="Path to trained LoRA if exists")
    lora_trained_at: datetime | None = Field(None, description="When LoRA was trained")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "char-abc123",
                "name": "Sarah",
                "description": "Professional headshots",
                "trigger_word": "ohwx woman",
                "image_count": 15,
                "lora_path": "/data/models/sarah-v1.safetensors"
            }
        }


class CharacterCreate(BaseModel):
    """Request to create a new character."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    trigger_word: str = Field(..., min_length=2, max_length=50)


class CharacterUpdate(BaseModel):
    """Request to update a character."""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    trigger_word: str | None = Field(None, min_length=2, max_length=50)


# ============================================
# Training Types
# ============================================

class TrainingConfig(BaseModel):
    """Configuration for LoRA training."""
    method: TrainingMethod = Field(TrainingMethod.LORA, description="Training method")
    steps: int = Field(1000, ge=100, le=10000, description="Training steps")
    learning_rate: float = Field(1e-4, ge=1e-6, le=1e-2, description="Learning rate")
    batch_size: int = Field(1, ge=1, le=8, description="Batch size")
    resolution: int = Field(1024, description="Training resolution")
    lora_rank: int = Field(16, ge=4, le=128, description="LoRA rank")

    class Config:
        json_schema_extra = {
            "example": {
                "method": "lora",
                "steps": 1500,
                "learning_rate": 1e-4,
                "batch_size": 1,
                "resolution": 1024,
                "lora_rank": 16
            }
        }


class TrainingJob(BaseModel):
    """A training job."""
    id: str = Field(..., description="Unique job identifier")
    character_id: str = Field(..., description="Character being trained")
    status: JobStatus = Field(JobStatus.PENDING)
    config: TrainingConfig = Field(default_factory=TrainingConfig)
    progress: float = Field(0.0, ge=0, le=100, description="Progress percentage")
    current_step: int = Field(0, description="Current training step")
    total_steps: int = Field(0, description="Total training steps")
    error_message: str | None = Field(None, description="Error if failed")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(None)
    completed_at: datetime | None = Field(None)
    output_path: str | None = Field(None, description="Path to trained model")

    # Extended fields for UI display
    base_model: str = Field("flux-dev", description="Base model used for training")
    preset_name: str | None = Field(None, description="Preset name if used (quick/balanced/quality/custom)")
    iteration_speed: float | None = Field(None, description="Current training speed in it/s")
    eta_seconds: int | None = Field(None, description="Estimated time remaining in seconds")
    elapsed_seconds: int | None = Field(None, description="Elapsed training time in seconds")
    current_loss: float | None = Field(None, description="Current training loss value")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "job-xyz789",
                "character_id": "char-abc123",
                "status": "running",
                "progress": 45.5,
                "current_step": 682,
                "total_steps": 1500,
                "base_model": "flux-dev",
                "preset_name": "balanced"
            }
        }


class StartTrainingRequest(BaseModel):
    """Request to start training."""
    character_id: str = Field(..., description="Character to train")
    config: TrainingConfig = Field(default_factory=TrainingConfig)
    preset_name: str | None = Field(None, description="Preset name if used (quick/balanced/quality/custom)")
    base_model: str = Field("flux-dev", description="Base model to use for training")


# ============================================
# Image Generation Types
# ============================================

class GenerationConfig(BaseModel):
    """Configuration for image generation."""
    prompt: str = Field(..., min_length=1, max_length=2000, description="Generation prompt")
    negative_prompt: str = Field("", max_length=1000, description="Negative prompt")
    width: int = Field(1024, ge=512, le=2048, description="Image width")
    height: int = Field(1024, ge=512, le=2048, description="Image height")
    steps: int = Field(30, ge=1, le=100, description="Inference steps")
    guidance_scale: float = Field(7.5, ge=1.0, le=20.0, description="CFG scale")
    seed: int | None = Field(None, description="Random seed for reproducibility")
    lora_id: str | None = Field(None, description="Character LoRA to use")
    lora_strength: float = Field(0.8, ge=0.0, le=1.5, description="LoRA strength")

    # Toggle options for advanced features
    use_controlnet: bool = Field(False, description="Enable ControlNet for pose/composition control")
    use_ipadapter: bool = Field(False, description="Enable IP-Adapter for reference image guidance")
    use_facedetailer: bool = Field(False, description="Enable FaceDetailer for face enhancement")
    use_upscale: bool = Field(False, description="Enable upscaling for higher resolution output")

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "ohwx woman as a professional photographer, studio lighting",
                "negative_prompt": "blurry, low quality",
                "width": 1024,
                "height": 1024,
                "steps": 30,
                "guidance_scale": 7.5,
                "lora_id": "char-abc123",
                "lora_strength": 0.8,
                "use_controlnet": False,
                "use_ipadapter": False,
                "use_facedetailer": True,
                "use_upscale": False
            }
        }


class GenerationJob(BaseModel):
    """An image generation job."""
    id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(JobStatus.PENDING)
    config: GenerationConfig
    progress: float = Field(0.0, ge=0, le=100)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_paths: list[str] = Field(default_factory=list)


class GenerateImageRequest(BaseModel):
    """Request to generate images."""
    config: GenerationConfig
    count: int = Field(1, ge=1, le=4, description="Number of images to generate")


# ============================================
# Job Progress Events (for SSE)
# ============================================

class JobProgressEvent(BaseModel):
    """Progress event for SSE streaming."""
    job_id: str
    job_type: JobType
    status: JobStatus
    progress: float
    message: str
    current_step: int | None = None
    total_steps: int | None = None
    preview_url: str | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_sse(self) -> str:
        """Format as SSE data line."""
        return f"data: {self.model_dump_json()}\n\n"
