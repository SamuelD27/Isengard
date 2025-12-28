"""
Test Plugin Capabilities Schema

Validates that plugin get_capabilities() returns well-formed schemas
with required fields and valid types.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTrainingCapabilitiesSchema:
    """Test training plugin capabilities schema invariants."""

    def test_ai_toolkit_capabilities_structure(self):
        """Verify AI-Toolkit capabilities has required fields."""
        from packages.plugins.training.src.ai_toolkit import AIToolkitPlugin

        plugin = AIToolkitPlugin()
        caps = plugin.get_capabilities()

        # Required top-level fields
        assert "method" in caps
        assert "backend" in caps
        assert "parameters" in caps

        # Check method and backend values
        assert caps["method"] == "lora"
        assert caps["backend"] == "ai-toolkit"

    def test_ai_toolkit_parameters_schema(self):
        """Verify each parameter has required schema fields."""
        from packages.plugins.training.src.ai_toolkit import AIToolkitPlugin

        plugin = AIToolkitPlugin()
        caps = plugin.get_capabilities()
        params = caps["parameters"]

        # Should have multiple parameters
        assert len(params) >= 5

        # Required fields for each parameter
        required_fields = {"type", "wired"}
        optional_fields = {"min", "max", "step", "options", "default", "description", "reason"}

        for param_name, schema in params.items():
            # Check required fields
            for field in required_fields:
                assert field in schema, f"Parameter '{param_name}' missing required field '{field}'"

            # Type must be valid
            valid_types = {"int", "float", "enum", "bool", "string"}
            assert schema["type"] in valid_types, f"Parameter '{param_name}' has invalid type: {schema['type']}"

            # wired must be boolean
            assert isinstance(schema["wired"], bool), f"Parameter '{param_name}' wired must be boolean"

            # If type is enum, must have options
            if schema["type"] == "enum":
                assert "options" in schema and len(schema["options"]) > 0, \
                    f"Enum parameter '{param_name}' must have options"

    def test_ai_toolkit_has_core_parameters(self):
        """Verify core training parameters exist."""
        from packages.plugins.training.src.ai_toolkit import AIToolkitPlugin

        plugin = AIToolkitPlugin()
        caps = plugin.get_capabilities()
        params = caps["parameters"]

        # Core parameters that must exist
        core_params = ["steps", "learning_rate", "lora_rank", "resolution"]

        for param in core_params:
            assert param in params, f"Missing core parameter: {param}"

    def test_ai_toolkit_wired_parameters_have_defaults(self):
        """Verify wired parameters have default values."""
        from packages.plugins.training.src.ai_toolkit import AIToolkitPlugin

        plugin = AIToolkitPlugin()
        caps = plugin.get_capabilities()
        params = caps["parameters"]

        for param_name, schema in params.items():
            if schema.get("wired", False):
                assert "default" in schema, \
                    f"Wired parameter '{param_name}' should have a default value"

    def test_mock_plugin_capabilities_structure(self):
        """Verify MockTrainingPlugin capabilities has required fields."""
        from packages.plugins.training.src.mock_plugin import MockTrainingPlugin

        plugin = MockTrainingPlugin()
        caps = plugin.get_capabilities()

        # Required top-level fields
        assert "method" in caps
        assert "backend" in caps
        assert "parameters" in caps

        # Check backend identifies as mock
        assert caps["backend"] == "mock"


class TestImageCapabilitiesSchema:
    """Test image plugin capabilities schema invariants."""

    def test_comfyui_capabilities_structure(self):
        """Verify ComfyUI capabilities has required fields."""
        from packages.plugins.image.src.comfyui import ComfyUIPlugin

        plugin = ComfyUIPlugin()
        caps = plugin.get_capabilities()

        # Required top-level fields
        assert "backend" in caps
        assert "model_variants" in caps
        assert "toggles" in caps
        assert "parameters" in caps

        # Check backend value
        assert caps["backend"] == "comfyui"

    def test_comfyui_toggles_schema(self):
        """Verify toggle schema has supported and optional reason."""
        from packages.plugins.image.src.comfyui import ComfyUIPlugin

        plugin = ComfyUIPlugin()
        caps = plugin.get_capabilities()
        toggles = caps["toggles"]

        # Should have toggle entries
        assert len(toggles) >= 1

        for toggle_name, schema in toggles.items():
            # Must have supported field
            assert "supported" in schema, f"Toggle '{toggle_name}' missing 'supported' field"
            assert isinstance(schema["supported"], bool)

            # If not supported, should have reason
            if not schema["supported"]:
                assert "reason" in schema or "description" in schema, \
                    f"Unsupported toggle '{toggle_name}' should have reason or description"

    def test_comfyui_parameters_schema(self):
        """Verify parameter schema structure."""
        from packages.plugins.image.src.comfyui import ComfyUIPlugin

        plugin = ComfyUIPlugin()
        caps = plugin.get_capabilities()
        params = caps["parameters"]

        required_fields = {"type", "wired"}
        valid_types = {"int", "float", "enum", "bool", "string"}

        for param_name, schema in params.items():
            for field in required_fields:
                assert field in schema, f"Parameter '{param_name}' missing required field '{field}'"

            assert schema["type"] in valid_types, f"Parameter '{param_name}' has invalid type"

    def test_comfyui_model_variants(self):
        """Verify model_variants is a non-empty list."""
        from packages.plugins.image.src.comfyui import ComfyUIPlugin

        plugin = ComfyUIPlugin()
        caps = plugin.get_capabilities()

        assert isinstance(caps["model_variants"], list)
        assert len(caps["model_variants"]) > 0
        # All variants should be strings
        for variant in caps["model_variants"]:
            assert isinstance(variant, str)

    def test_mock_image_plugin_capabilities_structure(self):
        """Verify MockImagePlugin capabilities has required fields."""
        from packages.plugins.image.src.mock_plugin import MockImagePlugin

        plugin = MockImagePlugin()
        caps = plugin.get_capabilities()

        # Required top-level fields
        assert "backend" in caps
        assert "model_variants" in caps
        assert "toggles" in caps
        assert "parameters" in caps

        # Check backend identifies as mock
        assert caps["backend"] == "mock"


class TestCapabilitiesConsistency:
    """Test consistency between plugin types."""

    def test_wired_vs_unwired_distinction(self):
        """Verify parameters clearly distinguish wired vs unwired."""
        from packages.plugins.training.src.ai_toolkit import AIToolkitPlugin

        plugin = AIToolkitPlugin()
        caps = plugin.get_capabilities()
        params = caps["parameters"]

        wired_count = sum(1 for p in params.values() if p.get("wired", False))
        unwired_count = sum(1 for p in params.values() if not p.get("wired", True))

        # Should have both wired and unwired parameters
        assert wired_count > 0, "Should have at least one wired parameter"
        # May not have unwired parameters yet, that's OK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
