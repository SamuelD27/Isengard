"""
UELR Redaction Tests

Tests for the redaction/sanitization functionality in the UELR system.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.api.src.routes.uelr import (
    redact_string,
    redact_dict,
    REDACTION_PATTERNS,
    SENSITIVE_KEYS,
)


class TestRedactString:
    """Tests for string redaction."""

    def test_redact_huggingface_token(self):
        """Should redact Hugging Face tokens."""
        text = "Using token hf_FAKE_TOKEN_FOR_TESTING_ONLY_XXX for auth"
        result = redact_string(text)
        assert "hf_***REDACTED***" in result
        assert "hf_FAKE_TOKEN_FOR_TESTING_ONLY_XXX" not in result

    def test_redact_openai_key(self):
        """Should redact OpenAI API keys."""
        text = "API key: sk-proj-abc123def456ghi789"
        result = redact_string(text)
        assert "sk-***REDACTED***" in result
        assert "sk-proj-abc123def456ghi789" not in result

    def test_redact_github_token(self):
        """Should redact GitHub tokens."""
        text = "ghp_FAKE_TOKEN_FOR_TESTING_ONLY_XXX is my token"
        result = redact_string(text)
        assert "ghp_***REDACTED***" in result
        assert "ghp_FAKE_TOKEN_FOR_TESTING_ONLY_XXX" not in result

    def test_redact_runpod_key(self):
        """Should redact RunPod API keys."""
        text = "rpa_FAKE_TOKEN_FOR_TESTING_ONLY_XXXXXXXXXXXXX"
        result = redact_string(text)
        assert "rpa_***REDACTED***" in result

    def test_redact_bearer_token(self):
        """Should redact Bearer tokens."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        result = redact_string(text)
        assert "Bearer ***REDACTED***" in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_redact_url_token(self):
        """Should redact tokens in URLs."""
        text = "https://api.example.com?token=secret123&other=value"
        result = redact_string(text)
        assert "token=***" in result
        assert "secret123" not in result

    def test_redact_password(self):
        """Should redact passwords in query strings."""
        text = "login?password=mysecretpass123"
        result = redact_string(text)
        assert "password=***" in result
        assert "mysecretpass123" not in result

    def test_redact_home_paths(self):
        """Should redact user home paths."""
        text = "/Users/johndoe/projects/secret"
        result = redact_string(text)
        assert "/[HOME]/" in result
        assert "johndoe" not in result

        text2 = "/home/ubuntu/.ssh/id_rsa"
        result2 = redact_string(text2)
        assert "/[HOME]/" in result2
        assert "ubuntu" not in result2

    def test_preserve_safe_text(self):
        """Should preserve text without sensitive patterns."""
        text = "This is a normal log message about training step 42"
        result = redact_string(text)
        assert result == text

    def test_multiple_patterns(self):
        """Should handle multiple sensitive patterns in one string."""
        text = "Using hf_token123 and ghp_abc456 with password=secret"
        result = redact_string(text)
        assert "hf_***REDACTED***" in result
        assert "ghp_***REDACTED***" in result
        assert "password=***" in result


class TestRedactDict:
    """Tests for dictionary redaction."""

    def test_redact_sensitive_key(self):
        """Should redact values for sensitive keys."""
        data = {"authorization": "Bearer token123", "message": "hello"}
        result = redact_dict(data)
        assert result["authorization"] == "***REDACTED***"
        assert result["message"] == "hello"

    def test_redact_cookie_key(self):
        """Should redact cookie values."""
        data = {"cookie": "session=abc123", "path": "/api"}
        result = redact_dict(data)
        assert result["cookie"] == "***REDACTED***"
        assert result["path"] == "/api"

    def test_redact_api_key_variations(self):
        """Should redact various API key field names."""
        data = {
            "api_key": "secret1",
            "apikey": "secret2",
            "x-api-key": "secret3",
            "name": "test",
        }
        result = redact_dict(data)
        assert result["api_key"] == "***REDACTED***"
        assert result["apikey"] == "***REDACTED***"
        assert result["x-api-key"] == "***REDACTED***"
        assert result["name"] == "test"

    def test_redact_nested_dict(self):
        """Should recursively redact nested dictionaries."""
        data = {
            "config": {
                "password": "secret",
                "host": "localhost",
            },
            "status": "ok",
        }
        result = redact_dict(data)
        assert result["config"]["password"] == "***REDACTED***"
        assert result["config"]["host"] == "localhost"
        assert result["status"] == "ok"

    def test_redact_list_values(self):
        """Should handle lists in dictionaries."""
        data = {
            "tokens": ["hf_abc123", "normal"],
            "count": 2,
        }
        result = redact_dict(data)
        assert result["tokens"][0] == "hf_***REDACTED***"
        assert result["tokens"][1] == "normal"
        assert result["count"] == 2

    def test_redact_deeply_nested(self):
        """Should handle deeply nested structures."""
        data = {
            "level1": {
                "level2": {
                    "level3": {
                        "secret": "mysecret",
                        "token": "hf_test123",
                    }
                }
            }
        }
        result = redact_dict(data)
        assert result["level1"]["level2"]["level3"]["secret"] == "***REDACTED***"
        assert "hf_***REDACTED***" in result["level1"]["level2"]["level3"]["token"]

    def test_max_depth_protection(self):
        """Should truncate deeply nested structures to prevent stack overflow."""
        data = {"a": {}}
        current = data["a"]
        for i in range(15):
            current["nested"] = {}
            current = current["nested"]

        result = redact_dict(data)
        # Should not raise and should truncate
        assert result is not None

    def test_preserve_non_string_values(self):
        """Should preserve non-string values."""
        data = {
            "count": 42,
            "enabled": True,
            "ratio": 0.95,
            "empty": None,
        }
        result = redact_dict(data)
        assert result["count"] == 42
        assert result["enabled"] is True
        assert result["ratio"] == 0.95
        assert result["empty"] is None

    def test_string_values_in_dict_pattern_redacted(self):
        """Should apply pattern redaction to string values."""
        data = {
            "message": "Error with token hf_secret123",
            "path": "/Users/john/data",
        }
        result = redact_dict(data)
        assert "hf_***REDACTED***" in result["message"]
        assert "/[HOME]/" in result["path"]


class TestSensitiveKeys:
    """Tests for sensitive key detection."""

    def test_all_sensitive_keys_defined(self):
        """Ensure all expected sensitive keys are in the set."""
        expected_keys = [
            "authorization",
            "cookie",
            "api_key",
            "token",
            "password",
            "secret",
            "credential",
        ]
        for key in expected_keys:
            assert key in SENSITIVE_KEYS or any(
                key in s for s in SENSITIVE_KEYS
            ), f"{key} should be in SENSITIVE_KEYS"

    def test_case_insensitive_matching(self):
        """Sensitive key matching should be case-insensitive in redact_dict."""
        data = {
            "Authorization": "secret",
            "COOKIE": "value",
            "Api_Key": "key",
        }
        result = redact_dict(data)
        # All should be redacted regardless of case
        for key in data:
            assert result[key] == "***REDACTED***"


class TestRedactionPatterns:
    """Tests for redaction pattern definitions."""

    def test_patterns_are_compiled_regex(self):
        """All patterns should be compiled regex objects."""
        import re

        for pattern, _ in REDACTION_PATTERNS:
            assert isinstance(pattern, re.Pattern)

    def test_patterns_have_replacements(self):
        """All patterns should have non-empty replacements."""
        for _, replacement in REDACTION_PATTERNS:
            assert replacement
            assert len(replacement) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
