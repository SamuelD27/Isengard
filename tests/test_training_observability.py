"""
Training Observability Tests

Validates the comprehensive observability system:
- JSON log format and redaction
- Event bus publish/subscribe
- TrainingProgressEvent schema
- TrainingJobLogger functionality
- Sample image generation (mock)
"""

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestLogRedaction:
    """Tests for sensitive data redaction in logs."""

    def test_redact_hf_tokens(self):
        from packages.shared.src.logging import redact_sensitive

        text = "Token is hf_abc123DEF456xyz"
        redacted = redact_sensitive(text)
        assert "hf_abc123" not in redacted
        assert "hf_***REDACTED***" in redacted

    def test_redact_api_keys(self):
        from packages.shared.src.logging import redact_sensitive

        text = "API key: sk-proj-abc123def456"
        redacted = redact_sensitive(text)
        assert "sk-proj-abc123" not in redacted
        assert "sk-***REDACTED***" in redacted

    def test_redact_passwords(self):
        from packages.shared.src.logging import redact_sensitive

        text = "password=supersecret123"
        redacted = redact_sensitive(text)
        assert "supersecret123" not in redacted
        assert "password=***" in redacted

    def test_redact_tokens_in_urls(self):
        from packages.shared.src.logging import redact_sensitive

        text = "https://api.example.com?token=abc123def"
        redacted = redact_sensitive(text)
        assert "abc123def" not in redacted
        assert "token=***" in redacted

    def test_preserves_normal_text(self):
        from packages.shared.src.logging import redact_sensitive

        text = "Training step 100/1000, loss: 0.05"
        redacted = redact_sensitive(text)
        assert redacted == text


class TestTrainingProgressEvent:
    """Tests for TrainingProgressEvent schema."""

    def test_create_progress_event(self):
        from packages.shared.src.events import TrainingProgressEvent, TrainingStage

        event = TrainingProgressEvent(
            job_id="train-abc123",
            correlation_id="req-xyz789",
            status="running",
            stage=TrainingStage.TRAINING,
            step=100,
            steps_total=1000,
            progress_pct=10.0,
            loss=0.05,
            lr=0.0001,
            message="Training step 100/1000",
        )

        assert event.job_id == "train-abc123"
        assert event.progress_pct == 10.0
        assert event.loss == 0.05

    def test_to_dict_filters_none(self):
        from packages.shared.src.events import TrainingProgressEvent, TrainingStage

        event = TrainingProgressEvent(
            job_id="train-abc123",
            status="running",
            stage=TrainingStage.TRAINING,
            step=50,
            steps_total=100,
            progress_pct=50.0,
            message="Halfway there",
        )

        event_dict = event.to_dict()
        assert "loss" not in event_dict  # None values filtered
        assert "lr" not in event_dict
        assert event_dict["progress_pct"] == 50.0

    def test_to_sse_format(self):
        from packages.shared.src.events import TrainingProgressEvent, TrainingStage

        event = TrainingProgressEvent(
            job_id="train-abc123",
            status="running",
            stage=TrainingStage.TRAINING,
            step=100,
            steps_total=1000,
            progress_pct=10.0,
            message="Progress",
        )

        sse = event.to_sse()
        assert sse["event"] == "progress"
        assert "data" in sse

    def test_completed_event_uses_complete_sse_type(self):
        from packages.shared.src.events import TrainingProgressEvent, TrainingStage

        event = TrainingProgressEvent(
            job_id="train-abc123",
            status="completed",
            stage=TrainingStage.COMPLETED,
            step=1000,
            steps_total=1000,
            progress_pct=100.0,
            message="Done",
        )

        sse = event.to_sse()
        assert sse["event"] == "complete"


class TestEventBus:
    """Tests for EventBus abstraction."""

    @pytest.mark.asyncio
    async def test_in_memory_publish_subscribe(self):
        from packages.shared.src.events import InMemoryEventBus, TrainingProgressEvent, TrainingStage

        bus = InMemoryEventBus()

        # Start subscriber
        received = []
        async def subscriber():
            async for event in bus.subscribe("job-123"):
                received.append(event)
                if event.get("status") == "completed":
                    break

        # Run subscriber in background
        sub_task = asyncio.create_task(subscriber())

        # Give subscriber time to start
        await asyncio.sleep(0.1)

        # Publish events
        event1 = TrainingProgressEvent(
            job_id="job-123",
            status="running",
            stage=TrainingStage.TRAINING,
            step=50,
            steps_total=100,
            progress_pct=50.0,
            message="Halfway",
        )
        await bus.publish("job-123", event1)

        event2 = TrainingProgressEvent(
            job_id="job-123",
            status="completed",
            stage=TrainingStage.COMPLETED,
            step=100,
            steps_total=100,
            progress_pct=100.0,
            message="Done",
        )
        await bus.publish("job-123", event2)

        # Wait for subscriber
        await asyncio.wait_for(sub_task, timeout=5.0)

        assert len(received) == 2
        assert received[0]["status"] == "running"
        assert received[1]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_event_history(self):
        from packages.shared.src.events import InMemoryEventBus, TrainingProgressEvent, TrainingStage

        bus = InMemoryEventBus()

        # Publish some events
        for i in range(5):
            event = TrainingProgressEvent(
                job_id="job-456",
                status="running",
                stage=TrainingStage.TRAINING,
                step=i * 10,
                steps_total=50,
                progress_pct=i * 20,
                message=f"Step {i}",
            )
            await bus.publish("job-456", event)

        # Get history
        history = await bus.get_history("job-456")
        assert len(history) == 5


class TestTrainingJobLogger:
    """Tests for TrainingJobLogger."""

    def test_logger_creates_job_log_file(self):
        from packages.shared.src.logging import TrainingJobLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the volume root
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir}):
                from packages.shared.src.config import get_config
                config = get_config()
                config.volume_root = Path(tmpdir)

                # Create logger
                job_id = "test-job-123"
                logger = TrainingJobLogger(job_id, correlation_id="req-abc", service="test")

                # Log some events
                logger.info("Test message", event="test.event")
                logger.step(current_step=10, loss=0.05)

                # Verify log file exists
                log_path = logger.get_log_path()
                assert log_path.exists()

                # Verify content
                content = log_path.read_text()
                lines = content.strip().split("\n")
                assert len(lines) >= 2

                # Parse first line
                entry = json.loads(lines[0])
                assert entry["msg"] == "Test message"

    def test_logger_tracks_samples(self):
        from packages.shared.src.logging import TrainingJobLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir}):
                from packages.shared.src.config import get_config
                config = get_config()
                config.volume_root = Path(tmpdir)

                logger = TrainingJobLogger("job-789", service="test")
                logger.sample_generated("/path/to/sample1.png", step=10)
                logger.sample_generated("/path/to/sample2.png", step=20)

                samples = logger.get_samples()
                assert len(samples) == 2
                assert "/path/to/sample1.png" in samples
                assert "/path/to/sample2.png" in samples


class TestMockPluginSampleGeneration:
    """Tests for mock plugin sample image generation."""

    @pytest.mark.asyncio
    async def test_mock_plugin_generates_samples(self):
        from packages.plugins.training.src.mock_plugin import MockTrainingPlugin
        from packages.shared.src.types import TrainingConfig, TrainingMethod

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir}):
                # Create necessary directories
                images_dir = Path(tmpdir) / "uploads" / "test-char"
                images_dir.mkdir(parents=True)

                # Create a dummy image file
                (images_dir / "test.jpg").write_bytes(b"dummy image")

                output_path = Path(tmpdir) / "loras" / "test-char" / "v1.safetensors"

                plugin = MockTrainingPlugin()

                config = TrainingConfig(
                    method=TrainingMethod.LORA,
                    steps=100,  # Minimum allowed
                    learning_rate=0.0001,
                    batch_size=1,
                    resolution=512,
                    lora_rank=8,
                )

                progress_events = []
                def on_progress(p):
                    progress_events.append(p)

                result = await plugin.train(
                    config=config,
                    images_dir=images_dir,
                    output_path=output_path,
                    trigger_word="ohwx",
                    progress_callback=on_progress,
                    job_id="test-sample-job",
                    sample_interval=50,  # Generate sample every 50 steps
                )

                # Check result
                assert result.success
                assert result.samples is not None
                assert len(result.samples) >= 2  # At least 2 samples for 100 steps with interval 50

                # Verify samples exist
                for sample_path in result.samples:
                    assert Path(sample_path).exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
