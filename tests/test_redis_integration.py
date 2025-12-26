"""
Redis Integration Tests

Tests for M2 Redis functionality.
Requires Redis to be running at localhost:6379.
"""

import asyncio
import os
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test mode
os.environ["ISENGARD_MODE"] = "fast-test"


def check_redis_available() -> bool:
    """Check if Redis is available (sync wrapper)."""
    async def _check():
        try:
            from packages.shared.src import redis_client
            r = await redis_client.get_redis()
            await r.ping()
            await redis_client.close_redis()
            return True
        except Exception:
            return False

    try:
        return asyncio.run(_check())
    except Exception:
        return False


# Skip all tests if Redis not available
pytestmark = pytest.mark.skipif(
    not check_redis_available(),
    reason="Redis not available"
)


class TestRedisClient:
    """Test Redis client operations."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Setup and cleanup for each test."""
        from packages.shared.src import redis_client

        # Ensure consumer groups exist
        await redis_client.ensure_consumer_groups()

        yield

        # Cleanup
        await redis_client.close_redis()

    async def test_job_persistence(self):
        """Test saving and retrieving job data."""
        from packages.shared.src import redis_client

        job_id = "test-job-001"
        job_data = {
            "id": job_id,
            "type": "training",
            "status": "queued",
            "character_id": "test-char",
        }

        # Save job
        await redis_client.save_job(job_id, job_data)

        # Retrieve job
        retrieved = await redis_client.get_job(job_id)

        assert retrieved is not None
        assert retrieved["id"] == job_id
        assert retrieved["status"] == "queued"

    async def test_job_status_update(self):
        """Test updating job status."""
        from packages.shared.src import redis_client

        job_id = "test-job-002"
        job_data = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
        }

        await redis_client.save_job(job_id, job_data)

        # Update status
        await redis_client.update_job_status(
            job_id,
            status="running",
            progress=50,
        )

        # Verify update
        retrieved = await redis_client.get_job(job_id)
        assert retrieved["status"] == "running"
        assert retrieved["progress"] == 50

    async def test_submit_and_consume_job(self):
        """Test job queue submit and consume."""
        from packages.shared.src import redis_client

        job_id = "test-job-003"
        payload = {"character_id": "test-char", "steps": 100}

        # Submit job
        message_id = await redis_client.submit_job(
            stream=redis_client.STREAM_TRAINING,
            job_id=job_id,
            job_type="training",
            payload=payload,
            correlation_id="test-corr-001",
        )

        assert message_id is not None

        # Consume job
        jobs = await redis_client.consume_jobs(
            stream=redis_client.STREAM_TRAINING,
            consumer_name="test-consumer",
            count=1,
            block_ms=1000,
        )

        assert len(jobs) >= 1

        # Find our job
        our_job = None
        for msg_id, data in jobs:
            if data.get("id") == job_id:
                our_job = (msg_id, data)
                break

        assert our_job is not None
        _, job_data = our_job
        assert job_data["id"] == job_id
        assert job_data["payload"]["character_id"] == "test-char"

    async def test_progress_publishing(self):
        """Test publishing and retrieving progress."""
        from packages.shared.src import redis_client

        job_id = "test-job-004"

        # Publish progress events
        await redis_client.publish_progress(
            job_id=job_id,
            status="running",
            progress=25.0,
            message="Processing step 1",
            correlation_id="test-corr-002",
            current_step=25,
            total_steps=100,
        )

        await redis_client.publish_progress(
            job_id=job_id,
            status="running",
            progress=50.0,
            message="Processing step 2",
            correlation_id="test-corr-002",
            current_step=50,
            total_steps=100,
        )

        # Get latest progress
        latest = await redis_client.get_latest_progress(job_id)

        assert latest is not None
        assert latest["progress"] == 50.0
        assert latest["current_step"] == 50

    async def test_character_persistence(self):
        """Test character save and retrieve."""
        from packages.shared.src import redis_client

        char_id = "test-char-001"
        char_data = {
            "id": char_id,
            "name": "Test Character",
            "trigger_word": "testperson",
            "created_at": "2025-01-01T00:00:00Z",
        }

        # Save character
        await redis_client.save_character(char_id, char_data)

        # Retrieve character
        retrieved = await redis_client.get_character(char_id)

        assert retrieved is not None
        assert retrieved["name"] == "Test Character"
        assert retrieved["trigger_word"] == "testperson"

        # Delete character
        await redis_client.delete_character(char_id)

        # Verify deleted
        deleted = await redis_client.get_character(char_id)
        assert deleted is None

    async def test_health_check(self):
        """Test Redis health check."""
        from packages.shared.src import redis_client

        healthy = await redis_client.check_redis_health()
        assert healthy is True


class TestRedisWithAPI:
    """Test API with Redis mode enabled."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Setup for API tests."""
        # Reset Redis singleton to avoid event loop issues
        from packages.shared.src import redis_client
        redis_client._redis_client = None

        os.environ["USE_REDIS"] = "true"

        yield

        os.environ["USE_REDIS"] = "false"

    @pytest.mark.skip(reason="Event loop conflict with TestClient - test manually with docker-compose")
    async def test_training_job_queued_to_redis(self):
        """Test that training job is queued to Redis."""
        from fastapi.testclient import TestClient
        from apps.api.src.main import app

        client = TestClient(app)

        # Create a character first
        char_response = client.post("/api/characters", json={
            "name": "Redis Test Character",
            "trigger_word": "redistest",
        })
        assert char_response.status_code == 201
        char_id = char_response.json()["id"]

        # Upload a test image
        from io import BytesIO
        fake_image = BytesIO(b"fake image content")
        files = [("files", ("test.jpg", fake_image, "image/jpeg"))]
        upload_response = client.post(f"/api/characters/{char_id}/images", files=files)
        assert upload_response.status_code == 201  # 201 Created

        # Start training (with USE_REDIS=true, this queues to Redis)
        train_response = client.post("/api/training", json={
            "character_id": char_id,
            "config": {
                "method": "lora",
                "steps": 100,
            },
        })

        assert train_response.status_code == 201
        job = train_response.json()

        # Verify job response
        assert job["status"] == "queued"
        assert job["id"].startswith("train-")
        assert job["character_id"] == char_id

        # Get the job via API (uses Redis when USE_REDIS=true)
        get_response = client.get(f"/api/training/{job['id']}")
        assert get_response.status_code == 200
        retrieved_job = get_response.json()
        assert retrieved_job["id"] == job["id"]
        assert retrieved_job["status"] == "queued"
