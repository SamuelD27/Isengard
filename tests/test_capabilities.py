"""
Test Plugin Capabilities Schema

Validates that get_capabilities() returns well-formed schemas
with required fields and valid types.

NOTE: Plugin abstraction was removed. Capabilities are now inlined
in apps/api/src/services/job_executor.py. These tests validate the
capabilities schema contract.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.api.src.services.job_executor import (
    get_training_capabilities,
    get_generation_capabilities,
)


class TestTrainingCapabilitiesSchema:
    """Test training capabilities schema invariants."""

    def test_training_capabilities_structure(self):
        """Verify training capabilities has required fields."""
        caps = get_training_capabilities()

        # Required top-level fields
        assert "method" in caps
        assert "backend" in caps
        assert "parameters" in caps

        # Check method and backend values
        assert caps["method"] == "lora"
        assert caps["backend"] == "ai-toolkit"

    def test_training_parameters_schema(self):
        """Verify each parameter has required schema fields."""
        caps = get_training_capabilities()
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

    def test_training_has_core_parameters(self):
        """Verify core training parameters exist."""
        caps = get_training_capabilities()
        params = caps["parameters"]

        # Core parameters that must exist
        core_params = ["steps", "learning_rate", "lora_rank", "resolution"]

        for param in core_params:
            assert param in params, f"Missing core parameter: {param}"

    def test_training_wired_parameters_have_defaults(self):
        """Verify wired parameters have default values."""
        caps = get_training_capabilities()
        params = caps["parameters"]

        for param_name, schema in params.items():
            if schema.get("wired", False):
                assert "default" in schema, \
                    f"Wired parameter '{param_name}' should have a default value"


class TestImageCapabilitiesSchema:
    """Test image/generation capabilities schema invariants."""

    def test_generation_capabilities_structure(self):
        """Verify generation capabilities has required fields."""
        caps = get_generation_capabilities()

        # Required top-level fields
        assert "backend" in caps
        assert "model_variants" in caps
        assert "toggles" in caps
        assert "parameters" in caps

        # Check backend value
        assert caps["backend"] == "comfyui"

    def test_generation_toggles_schema(self):
        """Verify toggle schema has supported and optional reason."""
        caps = get_generation_capabilities()
        toggles = caps["toggles"]

        # Should have toggle entries
        assert len(toggles) >= 1

        for toggle_name, schema in toggles.items():
            # Must have supported field
            assert "supported" in schema, f"Toggle '{toggle_name}' missing 'supported' field"
            assert isinstance(schema["supported"], bool)

            # All toggles should have a description
            assert "description" in schema, \
                f"Toggle '{toggle_name}' should have description"

    def test_generation_parameters_schema(self):
        """Verify parameter schema structure."""
        caps = get_generation_capabilities()
        params = caps["parameters"]

        required_fields = {"type", "wired"}
        valid_types = {"int", "float", "enum", "bool", "string"}

        for param_name, schema in params.items():
            for field in required_fields:
                assert field in schema, f"Parameter '{param_name}' missing required field '{field}'"

            assert schema["type"] in valid_types, f"Parameter '{param_name}' has invalid type"

    def test_generation_model_variants(self):
        """Verify model_variants is a non-empty list."""
        caps = get_generation_capabilities()

        assert isinstance(caps["model_variants"], list)
        assert len(caps["model_variants"]) > 0
        # All variants should be strings
        for variant in caps["model_variants"]:
            assert isinstance(variant, str)


class TestCapabilitiesConsistency:
    """Test consistency between capability types."""

    def test_wired_vs_unwired_distinction(self):
        """Verify parameters clearly distinguish wired vs unwired."""
        caps = get_training_capabilities()
        params = caps["parameters"]

        wired_count = sum(1 for p in params.values() if p.get("wired", False))
        unwired_count = sum(1 for p in params.values() if not p.get("wired", True))

        # Should have at least some wired parameters
        assert wired_count > 0, "Should have at least one wired parameter"

    def test_toggle_names_follow_convention(self):
        """Verify toggle names follow use_* convention."""
        caps = get_generation_capabilities()
        toggles = caps["toggles"]

        for toggle_name in toggles.keys():
            assert toggle_name.startswith("use_"), \
                f"Toggle '{toggle_name}' should follow use_* naming convention"

    def test_unsupported_toggles_have_reasons(self):
        """Verify unsupported toggles explain why."""
        caps = get_generation_capabilities()
        toggles = caps["toggles"]

        for toggle_name, schema in toggles.items():
            if not schema.get("supported", True):
                # Unsupported toggles should have description (acts as reason)
                assert "description" in schema, \
                    f"Unsupported toggle '{toggle_name}' should have description"


class TestCapabilitiesValidation:
    """Test capabilities validation logic."""

    def test_training_step_bounds(self):
        """Verify training steps has reasonable bounds."""
        caps = get_training_capabilities()
        steps = caps["parameters"]["steps"]

        assert steps["min"] >= 1, "Minimum steps should be at least 1"
        assert steps["min"] <= 1000, "Minimum steps should be reasonable for quick tests"
        assert steps["max"] >= 1000, "Maximum steps should allow quality training"
        assert steps["default"] >= steps["min"]
        assert steps["default"] <= steps["max"]

    def test_generation_dimension_bounds(self):
        """Verify generation dimensions have valid bounds."""
        caps = get_generation_capabilities()
        width = caps["parameters"]["width"]
        height = caps["parameters"]["height"]

        # Width/height bounds
        assert width["min"] >= 64, "Minimum width should be at least 64"
        assert width["max"] <= 4096, "Maximum width should be reasonable"
        assert height["min"] >= 64, "Minimum height should be at least 64"
        assert height["max"] <= 4096, "Maximum height should be reasonable"

    def test_lora_rank_options(self):
        """Verify lora_rank has valid options."""
        caps = get_training_capabilities()
        lora_rank = caps["parameters"]["lora_rank"]

        assert lora_rank["type"] == "enum"
        # Common LoRA ranks
        common_ranks = [4, 8, 16, 32]
        for rank in common_ranks:
            assert rank in lora_rank["options"], f"Missing common LoRA rank: {rank}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
