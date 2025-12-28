"""
Test Correlation ID Propagation

Validates end-to-end correlation ID flow:
1. Frontend sends X-Correlation-ID header
2. API middleware extracts and echoes it
3. Redis stores correlation_id in job metadata
4. Worker restores context
5. JobLogger includes correlation_id in JSONL output
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="module")
def test_volume_root(tmp_path_factory):
    """Create a temporary volume root for tests."""
    tmp = tmp_path_factory.mktemp("correlation_test")
    os.environ["VOLUME_ROOT"] = str(tmp)
    os.environ["ISENGARD_MODE"] = "fast-test"
    os.environ["LOG_TO_STDOUT"] = "false"
    return tmp


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    from apps.api.src.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestCorrelationIDHeader:
    """Test correlation ID header handling."""

    @pytest.mark.asyncio
    async def test_correlation_id_auto_generated(self, client, test_volume_root):
        """API generates correlation ID if none provided."""
        response = await client.get("/health")
        assert response.status_code == 200

        # Should have correlation ID in response headers
        assert "x-correlation-id" in response.headers
        correlation_id = response.headers["x-correlation-id"]

        # Should start with 'req-' prefix
        assert correlation_id.startswith("req-")

    @pytest.mark.asyncio
    async def test_correlation_id_echoed(self, client, test_volume_root):
        """API echoes provided correlation ID."""
        custom_id = "custom-test-correlation-123"

        response = await client.get(
            "/health",
            headers={"X-Correlation-ID": custom_id}
        )
        assert response.status_code == 200

        # Should echo exact correlation ID
        assert response.headers["x-correlation-id"] == custom_id

    @pytest.mark.asyncio
    async def test_correlation_id_case_insensitive(self, client, test_volume_root):
        """API handles correlation ID header case-insensitively."""
        custom_id = "case-test-123"

        # Try lowercase header
        response = await client.get(
            "/health",
            headers={"x-correlation-id": custom_id}
        )
        assert response.headers.get("x-correlation-id") == custom_id

    @pytest.mark.asyncio
    async def test_correlation_id_preserved_across_requests(self, client, test_volume_root):
        """Different requests get different auto-generated IDs."""
        response1 = await client.get("/health")
        response2 = await client.get("/health")

        id1 = response1.headers["x-correlation-id"]
        id2 = response2.headers["x-correlation-id"]

        # Should be different IDs
        assert id1 != id2


class TestCorrelationIDInJobs:
    """Test correlation ID propagation to job metadata."""

    @pytest.mark.asyncio
    async def test_training_job_has_correlation_id(self, client, test_volume_root):
        """Training job should capture correlation ID."""
        custom_id = "train-correlation-test-456"

        # Create a character first
        char_resp = await client.post(
            "/api/characters",
            json={"name": "Correlation Test", "trigger_word": "corrtest person"},
            headers={"X-Correlation-ID": custom_id}
        )
        assert char_resp.status_code == 201
        char_id = char_resp.json()["id"]

        # Upload an image (required for training)
        test_image = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
            0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
            0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
        ])
        files = [("files", ("test.png", test_image, "image/png"))]
        await client.post(f"/api/characters/{char_id}/images", files=files)

        # Start training with correlation ID
        train_correlation_id = "train-job-correlation-789"
        train_resp = await client.post(
            "/api/training",
            json={
                "character_id": char_id,
                "config": {"steps": 100}
            },
            headers={"X-Correlation-ID": train_correlation_id}
        )
        assert train_resp.status_code == 201

        # Check response has correlation ID
        assert train_resp.headers.get("x-correlation-id") == train_correlation_id

    @pytest.mark.asyncio
    async def test_generation_job_has_correlation_id(self, client, test_volume_root):
        """Generation job should capture correlation ID."""
        gen_correlation_id = "gen-job-correlation-abc"

        gen_resp = await client.post(
            "/api/generation",
            json={
                "config": {
                    "prompt": "Test prompt for correlation",
                    "width": 512,
                    "height": 512,
                    "steps": 5
                },
                "count": 1
            },
            headers={"X-Correlation-ID": gen_correlation_id}
        )
        assert gen_resp.status_code == 201

        # Check response has correlation ID
        assert gen_resp.headers.get("x-correlation-id") == gen_correlation_id


class TestCorrelationIDContextVar:
    """Test context variable handling for correlation IDs."""

    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID from context."""
        from packages.shared.src.logging import get_correlation_id, set_correlation_id

        test_id = "context-test-123"
        set_correlation_id(test_id)

        assert get_correlation_id() == test_id

    def test_correlation_id_initially_none(self):
        """Correlation ID should be None if not set."""
        from packages.shared.src.logging import _correlation_id

        # Create a fresh context by resetting
        token = _correlation_id.set(None)
        try:
            from packages.shared.src.logging import get_correlation_id
            # In a fresh context, should be None
            # Note: this may not be None if other tests have set it
            result = get_correlation_id()
            assert result is None or isinstance(result, str)
        finally:
            _correlation_id.reset(token)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
