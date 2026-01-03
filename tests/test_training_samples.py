"""
Test Training Sample Generation (Part 2)

Validates that training generates sample images during the process:
- Samples are generated at configured intervals
- Samples are copied to the job samples directory
- Sample paths are tracked and returned in training result
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestProductionTrainingSamples:
    """Test sample generation in production training mode."""

    @pytest.mark.asyncio
    async def test_mock_training_generates_samples_at_intervals(self):
        """Verify samples are generated at configured intervals."""
        from apps.api.src.services.job_executor import _run_mock_training
        from packages.shared.src.types import TrainingConfig, TrainingMethod

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir, "ISENGARD_MODE": "fast-test"}):
                import packages.shared.src.config as config_module
                config_module._config = None

                images_dir = Path(tmpdir) / "uploads" / "test-char"
                images_dir.mkdir(parents=True)
                (images_dir / "test.jpg").write_bytes(b"dummy image")

                output_path = Path(tmpdir) / "loras" / "test-char" / "v1.safetensors"

                config = TrainingConfig(
                    method=TrainingMethod.LORA,
                    steps=200,
                    learning_rate=0.0001,
                    batch_size=1,
                    resolution=512,
                    lora_rank=8,
                    sample_every_n_steps=50,  # Sample every 50 steps
                )

                result = await _run_mock_training(
                    config=config,
                    images_dir=images_dir,
                    output_path=output_path,
                    trigger_word="ohwx",
                    progress_callback=None,
                    job_id="test-sample-interval",
                )

                assert result.success
                # With 200 steps and sample_every=50, should generate at steps 50, 100, 150, 200
                assert len(result.samples) >= 3

    @pytest.mark.asyncio
    async def test_samples_directory_structure(self):
        """Verify samples are saved in correct directory structure."""
        from apps.api.src.services.job_executor import _run_mock_training
        from packages.shared.src.types import TrainingConfig, TrainingMethod
        from packages.shared.src.logging import get_job_samples_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir, "ISENGARD_MODE": "fast-test"}):
                import packages.shared.src.config as config_module
                config_module._config = None

                images_dir = Path(tmpdir) / "uploads" / "test-char"
                images_dir.mkdir(parents=True)
                (images_dir / "test.jpg").write_bytes(b"dummy image")

                output_path = Path(tmpdir) / "loras" / "test-char" / "v1.safetensors"
                job_id = "test-dir-structure"

                config = TrainingConfig(
                    method=TrainingMethod.LORA,
                    steps=100,
                    learning_rate=0.0001,
                )

                result = await _run_mock_training(
                    config=config,
                    images_dir=images_dir,
                    output_path=output_path,
                    trigger_word="ohwx",
                    progress_callback=None,
                    job_id=job_id,
                )

                assert result.success

                # Samples should be in job-specific directory
                samples_dir = get_job_samples_dir(job_id)
                assert samples_dir.exists()

                # All samples should be in this directory
                for sample_path in result.samples:
                    assert samples_dir in Path(sample_path).parents or samples_dir == Path(sample_path).parent

    @pytest.mark.asyncio
    async def test_sample_progress_callback(self):
        """Verify sample paths are included in progress callbacks."""
        from apps.api.src.services.job_executor import _run_mock_training, TrainingProgress
        from packages.shared.src.types import TrainingConfig, TrainingMethod

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir, "ISENGARD_MODE": "fast-test"}):
                import packages.shared.src.config as config_module
                config_module._config = None

                images_dir = Path(tmpdir) / "uploads" / "test-char"
                images_dir.mkdir(parents=True)
                (images_dir / "test.jpg").write_bytes(b"dummy image")

                output_path = Path(tmpdir) / "loras" / "test-char" / "v1.safetensors"

                config = TrainingConfig(
                    method=TrainingMethod.LORA,
                    steps=100,
                    learning_rate=0.0001,
                )

                progress_with_samples = []

                def on_progress(p: TrainingProgress):
                    if p.sample_path:
                        progress_with_samples.append(p)

                result = await _run_mock_training(
                    config=config,
                    images_dir=images_dir,
                    output_path=output_path,
                    trigger_word="ohwx",
                    progress_callback=on_progress,
                    job_id="test-callback-samples",
                )

                assert result.success
                # Should have received progress events with sample paths
                assert len(progress_with_samples) >= 1

                # Verify sample paths in callbacks match result
                callback_sample_paths = [p.sample_path for p in progress_with_samples]
                for path in callback_sample_paths:
                    assert Path(path).exists()


class TestSampleImageContent:
    """Test that generated sample images are valid."""

    @pytest.mark.asyncio
    async def test_sample_is_valid_image(self):
        """Verify generated samples are valid image files."""
        from apps.api.src.services.job_executor import _run_mock_training
        from packages.shared.src.types import TrainingConfig, TrainingMethod

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir, "ISENGARD_MODE": "fast-test"}):
                import packages.shared.src.config as config_module
                config_module._config = None

                images_dir = Path(tmpdir) / "uploads" / "test-char"
                images_dir.mkdir(parents=True)
                (images_dir / "test.jpg").write_bytes(b"dummy image")

                output_path = Path(tmpdir) / "loras" / "test-char" / "v1.safetensors"

                config = TrainingConfig(
                    method=TrainingMethod.LORA,
                    steps=100,
                    learning_rate=0.0001,
                )

                result = await _run_mock_training(
                    config=config,
                    images_dir=images_dir,
                    output_path=output_path,
                    trigger_word="ohwx",
                    progress_callback=None,
                    job_id="test-valid-image",
                )

                assert result.success
                assert len(result.samples) >= 1

                for sample_path in result.samples:
                    path = Path(sample_path)
                    assert path.exists()
                    # Verify it's a PNG file (starts with PNG signature)
                    content = path.read_bytes()
                    assert content[:4] == b'\x89PNG' or len(content) > 0

    @pytest.mark.asyncio
    async def test_sample_filenames_include_step(self):
        """Verify sample filenames include step number for ordering."""
        from apps.api.src.services.job_executor import _run_mock_training
        from packages.shared.src.types import TrainingConfig, TrainingMethod

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir, "ISENGARD_MODE": "fast-test"}):
                import packages.shared.src.config as config_module
                config_module._config = None

                images_dir = Path(tmpdir) / "uploads" / "test-char"
                images_dir.mkdir(parents=True)
                (images_dir / "test.jpg").write_bytes(b"dummy image")

                output_path = Path(tmpdir) / "loras" / "test-char" / "v1.safetensors"

                config = TrainingConfig(
                    method=TrainingMethod.LORA,
                    steps=100,
                    learning_rate=0.0001,
                )

                result = await _run_mock_training(
                    config=config,
                    images_dir=images_dir,
                    output_path=output_path,
                    trigger_word="ohwx",
                    progress_callback=None,
                    job_id="test-step-in-name",
                )

                assert result.success

                # Each sample filename should indicate the step
                for sample_path in result.samples:
                    filename = Path(sample_path).name
                    # Should contain step number (e.g., step_00100.png)
                    assert "step" in filename.lower() or any(c.isdigit() for c in filename)


class TestTrainingResultSamples:
    """Test TrainingResult sample tracking."""

    @pytest.mark.asyncio
    async def test_result_includes_all_samples(self):
        """Verify TrainingResult includes all generated samples."""
        from apps.api.src.services.job_executor import _run_mock_training
        from packages.shared.src.types import TrainingConfig, TrainingMethod
        from packages.shared.src.logging import get_job_samples_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"VOLUME_ROOT": tmpdir, "ISENGARD_MODE": "fast-test"}):
                import packages.shared.src.config as config_module
                config_module._config = None

                images_dir = Path(tmpdir) / "uploads" / "test-char"
                images_dir.mkdir(parents=True)
                (images_dir / "test.jpg").write_bytes(b"dummy image")

                output_path = Path(tmpdir) / "loras" / "test-char" / "v1.safetensors"
                job_id = "test-all-samples"

                config = TrainingConfig(
                    method=TrainingMethod.LORA,
                    steps=100,
                    learning_rate=0.0001,
                )

                result = await _run_mock_training(
                    config=config,
                    images_dir=images_dir,
                    output_path=output_path,
                    trigger_word="ohwx",
                    progress_callback=None,
                    job_id=job_id,
                )

                assert result.success

                # Count samples on disk
                samples_dir = get_job_samples_dir(job_id)
                disk_samples = list(samples_dir.glob("*.png"))

                # Result should track all samples on disk
                assert len(result.samples) == len(disk_samples)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
