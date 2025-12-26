"""
M1 Integration Tests - Full Workflow Validation

Tests the complete fast-test workflow:
1. Create character
2. Upload training images
3. Start training job
4. Poll until complete
5. Verify LoRA artifact exists
6. Generate image
7. Verify output exists
8. Check logs for secrets/redaction
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.api.src.main import app
from packages.shared.src.config import get_global_config, _resolve_volume_root


# Use a temporary directory for tests
@pytest.fixture(scope="module")
def test_volume_root(tmp_path_factory):
    """Create a temporary volume root for tests."""
    tmp = tmp_path_factory.mktemp("isengard_test")
    os.environ["VOLUME_ROOT"] = str(tmp)
    return tmp


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# Small test image (1x1 red PNG)
TEST_IMAGE_DATA = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
    0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
    0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
    0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
    0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
    0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
])


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_health(self, client):
        """Test health endpoint returns 200."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_info(self, client):
        """Test info endpoint returns API info."""
        response = await client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "mode" in data


class TestCharacterWorkflow:
    """Test character CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_character(self, client, test_volume_root):
        """Test creating a character."""
        response = await client.post("/api/characters", json={
            "name": "Test Character",
            "trigger_word": "testchar person",
            "description": "A test character for integration testing"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Character"
        assert data["trigger_word"] == "testchar person"
        assert "id" in data
        assert data["id"].startswith("char-")

    @pytest.mark.asyncio
    async def test_list_characters(self, client, test_volume_root):
        """Test listing characters."""
        # Create a character first
        await client.post("/api/characters", json={
            "name": "List Test",
            "trigger_word": "listtest person"
        })

        response = await client.get("/api/characters")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_character(self, client, test_volume_root):
        """Test getting a specific character."""
        # Create a character
        create_resp = await client.post("/api/characters", json={
            "name": "Get Test",
            "trigger_word": "gettest person"
        })
        char_id = create_resp.json()["id"]

        # Get it
        response = await client.get(f"/api/characters/{char_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == char_id
        assert data["name"] == "Get Test"

    @pytest.mark.asyncio
    async def test_upload_images(self, client, test_volume_root):
        """Test uploading training images."""
        # Create a character
        create_resp = await client.post("/api/characters", json={
            "name": "Upload Test",
            "trigger_word": "uploadtest person"
        })
        char_id = create_resp.json()["id"]

        # Upload an image
        files = [("files", ("test.png", TEST_IMAGE_DATA, "image/png"))]
        response = await client.post(
            f"/api/characters/{char_id}/images",
            files=files
        )
        assert response.status_code == 201
        data = response.json()
        assert data["total_images"] == 1
        assert "test.png" in data["uploaded"]


class TestTrainingWorkflow:
    """Test training job workflow."""

    @pytest.mark.asyncio
    async def test_full_training_workflow(self, client, test_volume_root):
        """
        Full M1 training workflow:
        1. Create character
        2. Upload image
        3. Start training
        4. Poll until complete
        5. Verify artifact exists
        """
        config = get_global_config()

        # 1. Create character
        create_resp = await client.post("/api/characters", json={
            "name": "Training Test",
            "trigger_word": "traintest person"
        })
        assert create_resp.status_code == 201
        char_id = create_resp.json()["id"]

        # 2. Upload training image
        files = [("files", ("train.png", TEST_IMAGE_DATA, "image/png"))]
        upload_resp = await client.post(
            f"/api/characters/{char_id}/images",
            files=files
        )
        assert upload_resp.status_code == 201

        # 3. Start training (with minimal steps for fast testing)
        # Note: TrainingConfig.steps has ge=100 validation
        train_resp = await client.post("/api/training", json={
            "character_id": char_id,
            "config": {
                "method": "lora",
                "steps": 100,  # Minimum allowed by validation
                "learning_rate": 0.0001,
                "lora_rank": 4
            }
        })
        assert train_resp.status_code == 201
        job_id = train_resp.json()["id"]
        assert job_id.startswith("train-")

        # 4. Poll until complete (with timeout)
        max_wait = 30  # seconds
        start_time = time.time()
        final_status = None

        while time.time() - start_time < max_wait:
            status_resp = await client.get(f"/api/training/{job_id}")
            assert status_resp.status_code == 200
            final_status = status_resp.json()

            if final_status["status"] in ["completed", "failed"]:
                break

            await asyncio.sleep(0.5)

        assert final_status is not None
        assert final_status["status"] == "completed", f"Job failed: {final_status.get('error_message')}"
        assert final_status["progress"] == 100.0
        assert final_status["output_path"] is not None

        # 5. Verify LoRA artifact exists
        output_path = Path(final_status["output_path"])
        assert output_path.exists(), f"LoRA file not found at {output_path}"

        # Verify training config JSON also exists
        lora_dir = config.loras_dir / char_id
        config_path = lora_dir / "training_config.json"
        assert config_path.exists(), "training_config.json not found"


class TestGenerationWorkflow:
    """Test image generation workflow."""

    @pytest.mark.asyncio
    async def test_generation_without_lora(self, client, test_volume_root):
        """Test generating images without a LoRA."""
        config = get_global_config()

        # Start generation
        gen_resp = await client.post("/api/generation", json={
            "config": {
                "prompt": "A beautiful sunset over the ocean",
                "width": 512,
                "height": 512,
                "steps": 5  # Fast for testing
            },
            "count": 1
        })
        assert gen_resp.status_code == 201
        job_id = gen_resp.json()["id"]
        assert job_id.startswith("gen-")

        # Poll until complete
        max_wait = 30
        start_time = time.time()
        final_status = None

        while time.time() - start_time < max_wait:
            status_resp = await client.get(f"/api/generation/{job_id}")
            assert status_resp.status_code == 200
            final_status = status_resp.json()

            if final_status["status"] in ["completed", "failed"]:
                break

            await asyncio.sleep(0.3)

        assert final_status is not None
        assert final_status["status"] == "completed", f"Job failed: {final_status.get('error_message')}"
        assert len(final_status["output_paths"]) > 0

        # Verify output file exists
        output_path = Path(final_status["output_paths"][0])
        assert output_path.exists(), f"Output file not found at {output_path}"

    @pytest.mark.asyncio
    async def test_generation_with_toggles(self, client, test_volume_root):
        """Test generation with toggle options."""
        gen_resp = await client.post("/api/generation", json={
            "config": {
                "prompt": "Portrait photo with enhancement",
                "width": 512,
                "height": 512,
                "steps": 5,
                "use_controlnet": False,
                "use_ipadapter": False,
                "use_facedetailer": True,
                "use_upscale": False
            },
            "count": 1
        })
        assert gen_resp.status_code == 201

        # Verify toggles are in the config
        job_data = gen_resp.json()
        assert job_data["config"]["use_facedetailer"] is True


class TestObservability:
    """Test observability requirements."""

    @pytest.mark.asyncio
    async def test_correlation_id_in_response(self, client, test_volume_root):
        """Test that correlation ID is returned in response headers."""
        response = await client.get("/health")
        assert "x-correlation-id" in response.headers
        correlation_id = response.headers["x-correlation-id"]
        assert correlation_id.startswith("req-")

    @pytest.mark.asyncio
    async def test_custom_correlation_id(self, client, test_volume_root):
        """Test that custom correlation ID is echoed back."""
        custom_id = "test-custom-correlation-123"
        response = await client.get(
            "/health",
            headers={"X-Correlation-ID": custom_id}
        )
        assert response.headers["x-correlation-id"] == custom_id


class TestLogSecurityRedaction:
    """Test that secrets are properly redacted from logs."""

    def test_no_secrets_in_logs(self, test_volume_root, tmp_path):
        """
        Verify no secret patterns appear in log files.

        Secret patterns to check:
        - hf_* (HuggingFace tokens)
        - sk-* (OpenAI API keys)
        - ghp_* (GitHub tokens)
        - rpa_* (RunPod keys)
        """
        from packages.shared.src.logging import redact_sensitive

        # Test redaction function directly
        test_strings = [
            ("My token is hf_abc123xyz", "My token is hf_***REDACTED***"),
            ("API key sk-proj-abc123", "API key sk-***REDACTED***"),
            ("GitHub token ghp_test123456", "GitHub token ghp_***REDACTED***"),
            ("RunPod key rpa_myrunpodkey", "RunPod key rpa_***REDACTED***"),
            ("/Users/testuser/secret/path", "/[HOME]/secret/path"),
            ("/home/ubuntu/data", "/[HOME]/data"),
            ("token=abc123&other=val", "token=***&other=val"),
            ('{"password": "secret123"}', '{"password": "***"}'),
        ]

        for input_str, expected in test_strings:
            result = redact_sensitive(input_str)
            assert result == expected, f"Redaction failed for: {input_str}"


class TestFullE2EWorkflow:
    """
    Complete end-to-end workflow test as specified in M1 acceptance criteria.
    """

    @pytest.mark.asyncio
    async def test_complete_workflow(self, client, test_volume_root):
        """
        Complete E2E test:
        1. Create character
        2. Upload images
        3. Start training
        4. Wait for completion
        5. Verify LoRA artifact
        6. Generate image using trained LoRA
        7. Verify generated output
        """
        config = get_global_config()

        # 1. Create character
        char_resp = await client.post("/api/characters", json={
            "name": "E2E Test Character",
            "trigger_word": "e2etest person"
        })
        assert char_resp.status_code == 201
        char_id = char_resp.json()["id"]

        # 2. Upload training image
        files = [("files", ("e2e_test.png", TEST_IMAGE_DATA, "image/png"))]
        upload_resp = await client.post(f"/api/characters/{char_id}/images", files=files)
        assert upload_resp.status_code == 201

        # 3. Start training (steps must be >= 100 per TrainingConfig validation)
        train_resp = await client.post("/api/training", json={
            "character_id": char_id,
            "config": {"steps": 100}
        })
        assert train_resp.status_code == 201
        train_job_id = train_resp.json()["id"]

        # 4. Wait for training completion
        for _ in range(60):  # Max 30 seconds
            status = await client.get(f"/api/training/{train_job_id}")
            if status.json()["status"] == "completed":
                break
            await asyncio.sleep(0.5)

        train_status = (await client.get(f"/api/training/{train_job_id}")).json()
        assert train_status["status"] == "completed"

        # 5. Verify LoRA artifact
        lora_dir = config.loras_dir / char_id
        lora_files = list(lora_dir.glob("v*.safetensors"))
        assert len(lora_files) > 0, "No LoRA files created"

        # 6. Generate image with trained LoRA
        gen_resp = await client.post("/api/generation", json={
            "config": {
                "prompt": "e2etest person as a professional",
                "lora_id": char_id,
                "steps": 5
            },
            "count": 1
        })
        assert gen_resp.status_code == 201
        gen_job_id = gen_resp.json()["id"]

        # 7. Wait for generation completion
        for _ in range(60):
            status = await client.get(f"/api/generation/{gen_job_id}")
            if status.json()["status"] == "completed":
                break
            await asyncio.sleep(0.3)

        gen_status = (await client.get(f"/api/generation/{gen_job_id}")).json()
        assert gen_status["status"] == "completed"
        assert len(gen_status["output_paths"]) > 0

        # Verify output file exists
        output_path = Path(gen_status["output_paths"][0])
        assert output_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
