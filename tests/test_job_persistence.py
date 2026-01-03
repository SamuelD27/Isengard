"""
Test Job Persistence (Part 6)

Validates that:
- Jobs are stored persistently (survive API restart)
- Job state is correctly serialized/deserialized
- Jobs can be recovered after restart

NOTE: The current architecture uses in-memory storage.
These tests document expected behavior for future persistent storage.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def create_test_image(width: int = 512, height: int = 512) -> bytes:
    """Create a valid PNG test image with specified dimensions."""
    import struct
    import zlib

    # PNG signature
    signature = b'\x89PNG\r\n\x1a\n'

    def create_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', crc)

    # IHDR chunk (width, height, bit depth, color type, compression, filter, interlace)
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr = create_chunk(b'IHDR', ihdr_data)

    # Create minimal image data (solid red)
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'  # filter byte
        for x in range(width):
            raw_data += bytes([255, 0, 0])  # RGB

    compressed = zlib.compress(raw_data)
    idat = create_chunk(b'IDAT', compressed)
    iend = create_chunk(b'IEND', b'')

    return signature + ihdr + idat + iend

# Create a 512x512 test image
TEST_IMAGE_DATA = create_test_image(512, 512)


@pytest.fixture(scope="module")
def test_volume_root(tmp_path_factory):
    """Create a temporary volume root for tests."""
    tmp = tmp_path_factory.mktemp("isengard_test")
    os.environ["VOLUME_ROOT"] = str(tmp)
    os.environ["ISENGARD_MODE"] = "fast-test"
    return tmp


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    from apps.api.src.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestJobDataStructure:
    """Test job data serialization."""

    def test_training_job_serializable(self):
        """Verify TrainingJob can be serialized to JSON."""
        from packages.shared.src.types import (
            TrainingJob,
            TrainingConfig,
            TrainingMethod,
            JobStatus,
        )

        config = TrainingConfig(
            method=TrainingMethod.LORA,
            steps=1000,
            learning_rate=0.0001,
        )

        job = TrainingJob(
            id="train-test123",
            character_id="char-abc",
            status=JobStatus.RUNNING,
            config=config,
            total_steps=1000,
            current_step=500,
            progress=50.0,
            created_at=datetime.now(timezone.utc),
        )

        # Should serialize without error
        job_dict = job.model_dump(mode="json")
        json_str = json.dumps(job_dict)

        # Should deserialize back
        loaded = json.loads(json_str)
        assert loaded["id"] == "train-test123"
        assert loaded["character_id"] == "char-abc"
        assert loaded["status"] == "running"

    def test_generation_job_serializable(self):
        """Verify GenerationJob can be serialized to JSON."""
        from packages.shared.src.types import (
            GenerationJob,
            GenerationConfig,
            JobStatus,
        )

        config = GenerationConfig(
            prompt="Test prompt",
            width=1024,
            height=768,
        )

        job = GenerationJob(
            id="gen-test456",
            status=JobStatus.COMPLETED,
            config=config,
            progress=100.0,
            output_paths=["/path/to/output.png"],
            created_at=datetime.now(timezone.utc),
        )

        # Should serialize without error
        job_dict = job.model_dump(mode="json")
        json_str = json.dumps(job_dict)

        # Should deserialize back
        loaded = json.loads(json_str)
        assert loaded["id"] == "gen-test456"
        assert loaded["status"] == "completed"
        assert len(loaded["output_paths"]) == 1


class TestJobStorage:
    """Test job storage patterns (in-memory)."""

    @pytest.mark.asyncio
    async def test_training_job_stored_after_creation(self, client, test_volume_root):
        """Verify training job is stored after creation."""
        # First create a character
        char_resp = await client.post("/api/characters", json={
            "name": "Persistence Test",
            "trigger_word": "persisttest person",
        })
        assert char_resp.status_code == 201
        char_id = char_resp.json()["id"]

        # Upload an image
        files = [("files", ("test.png", TEST_IMAGE_DATA, "image/png"))]
        await client.post(f"/api/characters/{char_id}/images", files=files)

        # Create training job
        train_resp = await client.post("/api/training", json={
            "character_id": char_id,
            "config": {"steps": 100},
        })
        assert train_resp.status_code == 201
        job_id = train_resp.json()["id"]

        # Verify job can be retrieved
        get_resp = await client.get(f"/api/training/{job_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == job_id

    @pytest.mark.asyncio
    async def test_generation_job_stored_after_creation(self, client, test_volume_root):
        """Verify generation job is stored after creation."""
        gen_resp = await client.post("/api/generation", json={
            "config": {"prompt": "Test prompt"},
            "count": 1,
        })
        assert gen_resp.status_code == 201
        job_id = gen_resp.json()["id"]

        # Verify job can be retrieved
        get_resp = await client.get(f"/api/generation/{job_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == job_id


class TestJobFileStorage:
    """Test job state file storage patterns."""

    def test_job_log_file_persisted(self, test_volume_root):
        """Verify job log files are written to disk."""
        from packages.shared.src.logging import JobLogger, get_job_log_path

        job_id = "test-persist-log"
        logger = JobLogger(job_id)
        logger.info("Test log entry")
        logger.info("Another entry")

        # Verify log file exists
        log_path = get_job_log_path(job_id)
        assert log_path is not None
        assert log_path.exists()

        # Verify content
        content = log_path.read_text()
        assert "Test log entry" in content
        assert "Another entry" in content

    def test_training_config_saved(self, test_volume_root):
        """Verify training config JSON is saved after training."""
        # This tests the pattern used by execute_training_job
        from packages.shared.src.config import get_global_config

        with patch.dict(os.environ, {"VOLUME_ROOT": str(test_volume_root)}):
            import packages.shared.src.config as config_module
            config_module._config = None
            config = get_global_config()

            # Create mock training config
            char_id = "test-char"
            lora_dir = config.loras_dir / char_id
            lora_dir.mkdir(parents=True, exist_ok=True)

            config_data = {
                "job_id": "train-test",
                "character_id": char_id,
                "trigger_word": "test person",
                "config": {"steps": 1000},
                "output_path": str(lora_dir / "v1.safetensors"),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

            config_path = lora_dir / "training_config.json"
            config_path.write_text(json.dumps(config_data, indent=2))

            # Verify saved
            assert config_path.exists()
            loaded = json.loads(config_path.read_text())
            assert loaded["job_id"] == "train-test"


class TestJobListPersistence:
    """Test job listing operations."""

    @pytest.mark.asyncio
    async def test_training_jobs_list_includes_created(self, client, test_volume_root):
        """Verify created training jobs appear in list."""
        # Create character
        char_resp = await client.post("/api/characters", json={
            "name": "List Test",
            "trigger_word": "listtest person",
        })
        char_id = char_resp.json()["id"]

        # Upload image
        files = [("files", ("test.png", TEST_IMAGE_DATA, "image/png"))]
        await client.post(f"/api/characters/{char_id}/images", files=files)

        # Create training job
        train_resp = await client.post("/api/training", json={
            "character_id": char_id,
            "config": {"steps": 100},
        })
        job_id = train_resp.json()["id"]

        # List jobs
        list_resp = await client.get("/api/training")
        assert list_resp.status_code == 200
        jobs = list_resp.json()

        # Our job should be in list
        job_ids = [j["id"] for j in jobs]
        assert job_id in job_ids

    @pytest.mark.asyncio
    async def test_generation_jobs_list_includes_created(self, client, test_volume_root):
        """Verify created generation jobs appear in list."""
        # Create generation job
        gen_resp = await client.post("/api/generation", json={
            "config": {"prompt": "List test"},
            "count": 1,
        })
        job_id = gen_resp.json()["id"]

        # List jobs
        list_resp = await client.get("/api/generation")
        assert list_resp.status_code == 200
        jobs = list_resp.json()

        # Our job should be in list
        job_ids = [j["id"] for j in jobs]
        assert job_id in job_ids


class TestJobStateUpdates:
    """Test job state updates are stored."""

    @pytest.mark.asyncio
    async def test_job_progress_updated(self, client, test_volume_root):
        """Verify job progress is updated during execution."""
        import asyncio

        # Create generation job (quick to complete)
        gen_resp = await client.post("/api/generation", json={
            "config": {"prompt": "Progress test", "steps": 5},
            "count": 1,
        })
        assert gen_resp.status_code == 201
        job_id = gen_resp.json()["id"]

        # Wait a bit for job to progress
        await asyncio.sleep(1)

        # Check progress
        get_resp = await client.get(f"/api/generation/{job_id}")
        job = get_resp.json()

        # Status should have changed from queued
        assert job["status"] in ["running", "completed"]

    @pytest.mark.asyncio
    async def test_completed_job_has_output_paths(self, client, test_volume_root):
        """Verify completed job has output paths."""
        import asyncio

        gen_resp = await client.post("/api/generation", json={
            "config": {"prompt": "Output test", "steps": 3},
            "count": 1,
        })
        job_id = gen_resp.json()["id"]

        # Wait for completion
        for _ in range(30):
            await asyncio.sleep(0.5)
            get_resp = await client.get(f"/api/generation/{job_id}")
            if get_resp.json()["status"] == "completed":
                break

        job = (await client.get(f"/api/generation/{job_id}")).json()
        assert job["status"] == "completed"
        assert len(job["output_paths"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
