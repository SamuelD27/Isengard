"""
Test Generation Capabilities and Toggle Validation (Part 3)

Validates that:
- Unsupported toggles are rejected with 400 error
- Supported toggles are accepted
- Toggle validation uses capabilities schema
- Error messages are descriptive
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


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


class TestToggleCapabilities:
    """Test toggle capabilities from job_executor."""

    def test_toggle_capabilities_defined(self):
        """Verify all expected toggles are defined."""
        from apps.api.src.services.job_executor import get_generation_capabilities

        caps = get_generation_capabilities()
        toggles = caps["toggles"]

        # Expected toggles
        expected = ["use_upscale", "use_facedetailer", "use_ipadapter", "use_controlnet"]
        for toggle in expected:
            assert toggle in toggles, f"Missing toggle: {toggle}"

    def test_upscale_is_supported(self):
        """Verify use_upscale is supported."""
        from apps.api.src.services.job_executor import get_generation_capabilities

        caps = get_generation_capabilities()
        assert caps["toggles"]["use_upscale"]["supported"] is True

    def test_unsupported_toggles_have_description(self):
        """Verify unsupported toggles have descriptions."""
        from apps.api.src.services.job_executor import get_generation_capabilities

        caps = get_generation_capabilities()
        unsupported = ["use_facedetailer", "use_ipadapter", "use_controlnet"]

        for toggle in unsupported:
            schema = caps["toggles"][toggle]
            assert schema["supported"] is False
            assert "description" in schema, f"Toggle {toggle} should have description"


class TestConfigValidator:
    """Test config_validator.py toggle validation."""

    def test_validate_unsupported_toggle_raises_400(self):
        """Verify unsupported toggles raise HTTPException 400."""
        from apps.api.src.services.config_validator import validate_generation_config
        from apps.api.src.services.job_executor import get_generation_capabilities
        from fastapi import HTTPException

        caps = get_generation_capabilities()

        # Try to enable controlnet (not supported)
        config = {
            "prompt": "test",
            "use_controlnet": True,
        }

        with pytest.raises(HTTPException) as exc_info:
            validate_generation_config(config, caps)

        assert exc_info.value.status_code == 400
        assert "use_controlnet" in exc_info.value.detail
        assert "not supported" in exc_info.value.detail.lower()

    def test_validate_supported_toggle_passes(self):
        """Verify supported toggles pass validation."""
        from apps.api.src.services.config_validator import validate_generation_config
        from apps.api.src.services.job_executor import get_generation_capabilities

        caps = get_generation_capabilities()

        # use_upscale is supported
        config = {
            "prompt": "test",
            "use_upscale": True,
        }

        # Should not raise
        validate_generation_config(config, caps)

    def test_validate_disabled_toggle_passes(self):
        """Verify disabled toggles pass even if unsupported."""
        from apps.api.src.services.config_validator import validate_generation_config
        from apps.api.src.services.job_executor import get_generation_capabilities

        caps = get_generation_capabilities()

        # Disabled toggles should pass even if not supported
        config = {
            "prompt": "test",
            "use_controlnet": False,
            "use_ipadapter": False,
            "use_facedetailer": False,
        }

        # Should not raise
        validate_generation_config(config, caps)

    def test_error_message_includes_backend(self):
        """Verify error message mentions the backend."""
        from apps.api.src.services.config_validator import validate_generation_config
        from apps.api.src.services.job_executor import get_generation_capabilities
        from fastapi import HTTPException

        caps = get_generation_capabilities()

        config = {
            "prompt": "test",
            "use_ipadapter": True,
        }

        with pytest.raises(HTTPException) as exc_info:
            validate_generation_config(config, caps)

        assert "comfyui" in exc_info.value.detail.lower()


class TestGenerationAPIToggleValidation:
    """Test toggle validation at API endpoint level."""

    @pytest.mark.asyncio
    async def test_unsupported_toggle_returns_400(self, client, test_volume_root):
        """Verify API returns 400 for unsupported toggles."""
        response = await client.post("/api/generation", json={
            "config": {
                "prompt": "Test image",
                "use_controlnet": True,
            },
            "count": 1,
        })

        assert response.status_code == 400
        data = response.json()
        assert "use_controlnet" in data.get("detail", "")

    @pytest.mark.asyncio
    async def test_supported_toggle_returns_201(self, client, test_volume_root):
        """Verify API returns 201 for supported toggles."""
        response = await client.post("/api/generation", json={
            "config": {
                "prompt": "Test image",
                "use_upscale": True,
            },
            "count": 1,
        })

        assert response.status_code == 201
        data = response.json()
        assert data["config"]["use_upscale"] is True

    @pytest.mark.asyncio
    async def test_multiple_unsupported_toggles_error(self, client, test_volume_root):
        """Verify first unsupported toggle triggers error."""
        response = await client.post("/api/generation", json={
            "config": {
                "prompt": "Test image",
                "use_controlnet": True,
                "use_ipadapter": True,
            },
            "count": 1,
        })

        assert response.status_code == 400
        # Should mention at least one unsupported toggle
        detail = response.json().get("detail", "")
        assert "use_controlnet" in detail or "use_ipadapter" in detail

    @pytest.mark.asyncio
    async def test_all_disabled_toggles_returns_201(self, client, test_volume_root):
        """Verify all disabled toggles returns 201."""
        response = await client.post("/api/generation", json={
            "config": {
                "prompt": "Test image",
                "use_controlnet": False,
                "use_ipadapter": False,
                "use_facedetailer": False,
                "use_upscale": False,
            },
            "count": 1,
        })

        assert response.status_code == 201


class TestParameterValidation:
    """Test parameter validation against capabilities."""

    def test_validate_parameter_out_of_range(self):
        """Verify out-of-range parameters raise error."""
        from apps.api.src.services.config_validator import validate_generation_config
        from apps.api.src.services.job_executor import get_generation_capabilities
        from fastapi import HTTPException

        caps = get_generation_capabilities()

        # Width below minimum (512)
        config = {
            "prompt": "test",
            "width": 64,  # Below min of 512
        }

        with pytest.raises(HTTPException) as exc_info:
            validate_generation_config(config, caps)

        assert exc_info.value.status_code == 400
        assert "width" in exc_info.value.detail.lower()

    def test_validate_parameter_in_range(self):
        """Verify in-range parameters pass validation."""
        from apps.api.src.services.config_validator import validate_generation_config
        from apps.api.src.services.job_executor import get_generation_capabilities

        caps = get_generation_capabilities()

        config = {
            "prompt": "test",
            "width": 1024,
            "height": 768,
            "steps": 20,
        }

        # Should not raise
        validate_generation_config(config, caps)

    def test_validate_enum_parameter(self):
        """Verify enum parameters are validated."""
        from apps.api.src.services.config_validator import validate_generation_config
        from apps.api.src.services.job_executor import get_generation_capabilities
        from fastapi import HTTPException

        caps = get_generation_capabilities()

        # Invalid model variant
        config = {
            "prompt": "test",
            "model_variant": "invalid-model",
        }

        with pytest.raises(HTTPException) as exc_info:
            validate_generation_config(config, caps)

        assert exc_info.value.status_code == 400
        assert "model_variant" in exc_info.value.detail


class TestCapabilitiesEndpoint:
    """Test capabilities can be queried."""

    @pytest.mark.asyncio
    async def test_generation_job_includes_config(self, client, test_volume_root):
        """Verify generation job response includes config."""
        response = await client.post("/api/generation", json={
            "config": {
                "prompt": "Test prompt",
                "width": 1024,
                "height": 768,
            },
            "count": 1,
        })

        assert response.status_code == 201
        data = response.json()
        assert "config" in data
        assert data["config"]["width"] == 1024
        assert data["config"]["height"] == 768


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
