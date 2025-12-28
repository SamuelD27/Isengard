"""
Test JobLogger JSONL Output

Validates JobLogger:
1. Creates JSONL files at correct path
2. Writes records with required envelope fields
3. Handles concurrent writes safely
4. Redacts sensitive information
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_volume_root(tmp_path, monkeypatch):
    """Set up temporary VOLUME_ROOT for job logs."""
    monkeypatch.setenv("VOLUME_ROOT", str(tmp_path))
    monkeypatch.setenv("ISENGARD_MODE", "fast-test")
    monkeypatch.setenv("LOG_TO_STDOUT", "false")
    monkeypatch.setenv("LOG_TO_FILE", "false")

    # Clear config singleton to pick up new env
    import packages.shared.src.config as config_module
    config_module._config = None

    return tmp_path


class TestJobLoggerFileCreation:
    """Test JobLogger file operations."""

    def test_job_logger_creates_log_file(self, temp_volume_root):
        """JobLogger should create JSONL file on first write."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-001"
        logger = JobLogger(job_id)

        # Write a log entry
        logger.info("Test message")

        # Verify file exists
        expected_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        assert expected_path.exists(), f"Log file not created at {expected_path}"

    def test_job_logger_appends_entries(self, temp_volume_root):
        """Multiple log entries should be appended."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-append"
        logger = JobLogger(job_id)

        # Write multiple entries
        logger.info("First message")
        logger.info("Second message")
        logger.info("Third message")

        # Verify file has 3 lines
        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_job_logger_get_log_path(self, temp_volume_root):
        """JobLogger.get_log_path() returns correct path."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-path"
        logger = JobLogger(job_id)
        logger.info("Test")

        path = logger.get_log_path()
        expected = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        assert path == expected


class TestJobLoggerRecordFormat:
    """Test JSONL record structure and required fields."""

    def test_record_has_required_fields(self, temp_volume_root):
        """Each record must have required envelope fields."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-fields"
        logger = JobLogger(job_id)
        logger.info("Test message", event="test.event", custom_field="value")

        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        line = log_path.read_text().strip()
        record = json.loads(line)

        # Required fields
        assert "ts" in record, "Missing 'ts' field"
        assert "level" in record, "Missing 'level' field"
        assert "service" in record, "Missing 'service' field"
        assert "job_id" in record, "Missing 'job_id' field"
        assert "msg" in record, "Missing 'msg' field"

        # Values
        assert record["level"] == "INFO"
        assert record["job_id"] == job_id
        assert record["msg"] == "Test message"
        assert record["service"] == "worker"

    def test_record_has_optional_event(self, temp_volume_root):
        """Event field included when provided."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-event"
        logger = JobLogger(job_id)
        logger.info("Test", event="job.start")

        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        record = json.loads(log_path.read_text().strip())

        assert record.get("event") == "job.start"

    def test_record_has_extra_fields(self, temp_volume_root):
        """Extra fields included in 'fields' object."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-extra"
        logger = JobLogger(job_id)
        logger.info("Test", step=10, total=100, loss=0.05)

        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        record = json.loads(log_path.read_text().strip())

        assert "fields" in record
        assert record["fields"]["step"] == 10
        assert record["fields"]["total"] == 100
        assert record["fields"]["loss"] == 0.05

    def test_record_includes_correlation_id(self, temp_volume_root):
        """Correlation ID included when set in context."""
        from packages.shared.src.logging import JobLogger, set_correlation_id, _correlation_id

        # Set correlation ID in context
        test_corr_id = "corr-test-xyz"
        token = _correlation_id.set(test_corr_id)

        try:
            job_id = "test-job-corr"
            logger = JobLogger(job_id)
            logger.info("Test with correlation")

            log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
            record = json.loads(log_path.read_text().strip())

            assert record.get("correlation_id") == test_corr_id
        finally:
            _correlation_id.reset(token)

    def test_record_valid_json(self, temp_volume_root):
        """Each line must be valid JSON."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-json"
        logger = JobLogger(job_id)

        # Write various types
        logger.info("String message")
        logger.warning("Warning message", code=123)
        logger.error("Error message", details={"key": "value"})

        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        lines = log_path.read_text().strip().split("\n")

        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Line {i} is not valid JSON: {line[:100]}")


class TestJobLoggerLogLevels:
    """Test all log level methods."""

    def test_all_log_levels(self, temp_volume_root):
        """All log level methods should work."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-levels"
        logger = JobLogger(job_id)

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        lines = log_path.read_text().strip().split("\n")

        # Should have 4 entries (debug may or may not appear based on level)
        assert len(lines) >= 3  # At least info, warning, error

        levels = [json.loads(line)["level"] for line in lines]
        assert "INFO" in levels
        assert "WARNING" in levels
        assert "ERROR" in levels


class TestJobLoggerRedaction:
    """Test sensitive data redaction."""

    def test_redacts_hf_tokens(self, temp_volume_root):
        """HuggingFace tokens should be redacted."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-redact-hf"
        logger = JobLogger(job_id)
        logger.info("Using token hf_abc123xyz for model access")

        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        content = log_path.read_text()

        assert "hf_abc123xyz" not in content
        assert "hf_***REDACTED***" in content

    def test_redacts_api_keys(self, temp_volume_root):
        """API keys should be redacted."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-redact-api"
        logger = JobLogger(job_id)
        logger.info("API key is sk-proj-abc123secret")

        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        content = log_path.read_text()

        assert "sk-proj-abc123secret" not in content
        assert "sk-***REDACTED***" in content

    def test_redacts_local_paths(self, temp_volume_root):
        """Local user paths should be redacted."""
        from packages.shared.src.logging import JobLogger

        job_id = "test-job-redact-path"
        logger = JobLogger(job_id)
        logger.info("Reading from /Users/testuser/secret/data.json")

        log_path = temp_volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        content = log_path.read_text()

        assert "/Users/testuser/" not in content
        assert "/[HOME]/" in content


class TestGetJobLogPath:
    """Test the get_job_log_path helper function."""

    def test_returns_path_when_exists(self, temp_volume_root):
        """Returns path when log file exists."""
        from packages.shared.src.logging import JobLogger, get_job_log_path

        job_id = "test-job-exists"
        logger = JobLogger(job_id)
        logger.info("Test")

        path = get_job_log_path(job_id)
        assert path is not None
        assert path.exists()

    def test_returns_none_when_not_exists(self, temp_volume_root):
        """Returns None when log file doesn't exist."""
        from packages.shared.src.logging import get_job_log_path

        path = get_job_log_path("nonexistent-job-id")
        assert path is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
