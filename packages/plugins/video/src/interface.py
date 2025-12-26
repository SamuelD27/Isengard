"""
Video Generation Plugin Interface

SCAFFOLD ONLY - This interface is defined for future implementation.
No video generation is currently supported.

This file exists to:
1. Define the expected contract for video plugins
2. Allow the UI to show a proper "In Development" state
3. Enable future implementation without architectural changes
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from pydantic import BaseModel, Field


# ============================================
# Video Types (Scaffold)
# ============================================

class VideoConfig(BaseModel):
    """
    Configuration for video generation.

    SCAFFOLD: These parameters are defined but not implemented.
    """
    prompt: str = Field(..., description="Video generation prompt")
    negative_prompt: str = Field("", description="Negative prompt")
    width: int = Field(512, description="Video width")
    height: int = Field(512, description="Video height")
    frames: int = Field(24, description="Number of frames")
    fps: int = Field(8, description="Frames per second")
    seed: int | None = Field(None, description="Random seed")
    lora_id: str | None = Field(None, description="Character LoRA to use")


@dataclass
class VideoProgress:
    """Progress update from video generation."""
    current_frame: int
    total_frames: int
    message: str = ""

    @property
    def percentage(self) -> float:
        if self.total_frames == 0:
            return 0.0
        return (self.current_frame / self.total_frames) * 100


@dataclass
class VideoResult:
    """Result of video generation."""
    success: bool
    output_path: Path | None
    error_message: str | None = None
    generation_time_seconds: float = 0.0


# ============================================
# Video Plugin Interface (Scaffold)
# ============================================

class VideoPlugin(ABC):
    """
    Abstract base class for video generation plugins.

    SCAFFOLD ONLY - No implementations exist yet.

    Future implementations will:
    1. Support the VideoConfig parameters
    2. Emit progress updates via callback
    3. Write output video to specified path
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier."""
        pass

    @abstractmethod
    async def check_health(self) -> tuple[bool, str | None]:
        """Check if the backend is available."""
        pass

    @abstractmethod
    async def generate(
        self,
        config: VideoConfig,
        output_path: Path,
        lora_path: Path | None = None,
        progress_callback: Callable[[VideoProgress], None] | None = None,
    ) -> VideoResult:
        """Generate video from prompt."""
        pass

    @abstractmethod
    async def cancel(self) -> None:
        """Cancel current generation."""
        pass


# ============================================
# Scaffold Implementation
# ============================================

class ScaffoldVideoPlugin(VideoPlugin):
    """
    Placeholder video plugin that always returns "not implemented".

    This is the only video plugin - video generation is not supported.
    """

    @property
    def name(self) -> str:
        return "scaffold"

    async def check_health(self) -> tuple[bool, str | None]:
        return False, "Video generation is not yet implemented"

    async def generate(
        self,
        config: VideoConfig,
        output_path: Path,
        lora_path: Path | None = None,
        progress_callback: Callable[[VideoProgress], None] | None = None,
    ) -> VideoResult:
        return VideoResult(
            success=False,
            output_path=None,
            error_message="Video generation is in development. Check back in a future release.",
        )

    async def cancel(self) -> None:
        pass  # Nothing to cancel
