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
    CAPTIONING = "captioning"


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

    # Sample image configuration
    sample_every_n_steps: int = Field(100, ge=50, le=1000, description="Generate sample images every N steps")
    sample_count: int = Field(3, ge=1, le=5, description="Number of sample images to generate each time")
    sample_prompts: list[str] | None = Field(None, description="Custom prompts for sample generation (uses defaults if not provided)")

    # Checkpoint configuration
    checkpoint_every_n_steps: int = Field(250, ge=100, le=2000, description="Save checkpoint every N steps")
    max_checkpoints: int = Field(2, ge=1, le=4, description="Maximum number of intermediate checkpoints to keep (final model always saved)")

    class Config:
        json_schema_extra = {
            "example": {
                "method": "lora",
                "steps": 1500,
                "learning_rate": 1e-4,
                "batch_size": 1,
                "resolution": 1024,
                "lora_rank": 16,
                "sample_every_n_steps": 100,
                "sample_count": 3,
                "sample_prompts": ["a photo of {trigger_word}", "portrait of {trigger_word}"],
                "checkpoint_every_n_steps": 250,
                "max_checkpoints": 2
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
# Plugin Interface Result Types
# ============================================

class TrainingProgress(BaseModel):
    """
    Progress update from training backend.

    Used as the callback parameter type in TrainingBackend.train().
    Simpler than TrainingProgressEvent for plugin implementations.
    """
    step: int = Field(..., description="Current training step")
    total_steps: int = Field(..., description="Total training steps")
    loss: float | None = Field(None, description="Current loss value")
    learning_rate: float | None = Field(None, description="Current learning rate")
    eta_seconds: int | None = Field(None, description="Estimated time remaining")
    iteration_speed: float | None = Field(None, description="Training speed in iterations/second")
    message: str = Field("", description="Human-readable status message")
    sample_path: str | None = Field(None, description="Path to sample image if just generated")
    checkpoint_path: str | None = Field(None, description="Path to checkpoint if just saved")

    @property
    def progress_pct(self) -> float:
        """Calculate progress percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.step / self.total_steps) * 100.0


class TrainingResult(BaseModel):
    """
    Result from training backend.

    Returned by TrainingBackend.train() upon completion.
    """
    success: bool = Field(..., description="Whether training completed successfully")
    model_path: str | None = Field(None, description="Path to trained model file")
    final_loss: float | None = Field(None, description="Final training loss")
    total_steps: int = Field(0, description="Total steps completed")
    training_time_seconds: float = Field(0.0, description="Total training time")
    error_message: str | None = Field(None, description="Error message if failed")
    checkpoints: list[str] = Field(default_factory=list, description="Paths to saved checkpoints")
    samples: list[str] = Field(default_factory=list, description="Paths to generated samples")


class GenerationProgress(BaseModel):
    """
    Progress update from generation backend.

    Used as the callback parameter type in GenerationBackend.generate().
    """
    step: int = Field(..., description="Current inference step")
    total_steps: int = Field(..., description="Total inference steps")
    message: str = Field("", description="Human-readable status message")
    preview_path: str | None = Field(None, description="Path to preview image if available")

    @property
    def progress_pct(self) -> float:
        """Calculate progress percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.step / self.total_steps) * 100.0


class GenerationResult(BaseModel):
    """
    Result from generation backend.

    Returned by GenerationBackend.generate() upon completion.
    """
    success: bool = Field(..., description="Whether generation completed successfully")
    output_paths: list[str] = Field(default_factory=list, description="Paths to generated images")
    generation_time_seconds: float = Field(0.0, description="Total generation time")
    seed_used: int | None = Field(None, description="Actual seed used for generation")
    error_message: str | None = Field(None, description="Error message if failed")


# ============================================
# Captioning Types
# ============================================

class CaptioningStyle(str, Enum):
    """Style hint for caption generation."""
    PHOTOREALISTIC = "photorealistic"
    ANIME = "anime"
    THREED_RENDERED = "3d-rendered"
    DIGITAL_ART = "digital-art"
    AUTO = "auto"  # Let model detect style


class CaptioningConfig(BaseModel):
    """Configuration for image captioning."""
    model: str = Field("florence-2-large", description="Captioning model to use")
    style_hint: CaptioningStyle = Field(CaptioningStyle.AUTO, description="Style hint for captions")
    include_lighting: bool = Field(True, description="Include lighting description")
    include_camera_angle: bool = Field(True, description="Include camera angle")
    include_background: bool = Field(True, description="Include background description")
    include_clothing: bool = Field(True, description="Include clothing description")
    reference_image: str | None = Field(None, description="Reference image path for outfit consistency")
    overwrite_existing: bool = Field(False, description="Overwrite existing caption files")

    class Config:
        json_schema_extra = {
            "example": {
                "model": "florence-2-large",
                "style_hint": "auto",
                "include_lighting": True,
                "include_camera_angle": True,
                "overwrite_existing": False
            }
        }


class CaptioningJob(BaseModel):
    """A captioning job."""
    id: str = Field(..., description="Unique job identifier")
    character_id: str = Field(..., description="Character being captioned")
    status: JobStatus = Field(JobStatus.PENDING)
    config: CaptioningConfig = Field(default_factory=CaptioningConfig)
    progress: float = Field(0.0, ge=0, le=100, description="Progress percentage")
    current_image: int = Field(0, description="Current image being processed")
    total_images: int = Field(0, description="Total images to caption")
    error_message: str | None = Field(None, description="Error if failed")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(None)
    completed_at: datetime | None = Field(None)
    captions_generated: int = Field(0, description="Number of captions successfully generated")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "cap-xyz789",
                "character_id": "char-abc123",
                "status": "running",
                "progress": 45.5,
                "current_image": 7,
                "total_images": 15,
                "captions_generated": 6
            }
        }


class StartCaptioningRequest(BaseModel):
    """Request to start captioning."""
    character_id: str = Field(..., description="Character to caption images for")
    config: CaptioningConfig = Field(default_factory=CaptioningConfig)


class CaptioningProgress(BaseModel):
    """
    Progress update from captioning backend.

    Used as the callback parameter type in CaptioningBackend.caption().
    """
    current_image: int = Field(..., description="Current image index (0-based)")
    total_images: int = Field(..., description="Total images to process")
    current_filename: str = Field("", description="Current image filename")
    message: str = Field("", description="Human-readable status message")

    @property
    def progress_pct(self) -> float:
        """Calculate progress percentage."""
        if self.total_images == 0:
            return 0.0
        return (self.current_image / self.total_images) * 100.0


class CaptioningResult(BaseModel):
    """
    Result from captioning backend.

    Returned by CaptioningBackend.caption() upon completion.
    """
    success: bool = Field(..., description="Whether captioning completed successfully")
    captions: dict[str, str] = Field(default_factory=dict, description="Map of filename -> caption")
    total_images: int = Field(0, description="Total images processed")
    captions_generated: int = Field(0, description="Number of captions successfully generated")
    captions_skipped: int = Field(0, description="Number of images skipped (existing captions)")
    captions_failed: int = Field(0, description="Number of images that failed to caption")
    processing_time_seconds: float = Field(0.0, description="Total processing time")
    error_message: str | None = Field(None, description="Error message if failed")


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
