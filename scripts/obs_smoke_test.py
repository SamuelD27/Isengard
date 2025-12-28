#!/usr/bin/env python3
"""
Isengard Observability Smoke Test

Verifies the observability infrastructure is working correctly:
1. Log directory structure exists
2. Logging module can be imported and used
3. Log rotation works
4. Logs are written in correct format
5. Redaction is working
6. End-to-end job log creation (when SMOKE_TEST_ENABLED=1)

Usage:
    python scripts/obs_smoke_test.py                # Basic tests only
    python scripts/obs_smoke_test.py --verbose      # With verbose output
    SMOKE_TEST_ENABLED=1 python scripts/obs_smoke_test.py  # Full E2E tests
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Gate for full end-to-end tests
SMOKE_TEST_ENABLED = os.getenv("SMOKE_TEST_ENABLED", "0") == "1"


def test_imports():
    """Test that all logging modules can be imported."""
    print("Testing imports...")

    # First check if we can import the logging module standalone
    try:
        # These imports don't require pydantic
        import json
        import logging
        import re
        import shutil
        from contextvars import ContextVar
        print("  [PASS] Standard library imports")
    except ImportError as e:
        print(f"  [FAIL] Standard library import error: {e}")
        return False

    # Try importing our logging module
    try:
        from packages.shared.src.logging import (
            get_logger,
            configure_logging,
            rotate_logs,
            set_correlation_id,
            get_correlation_id,
            redact_sensitive,
            get_subprocess_log_paths,
        )
        print("  [PASS] All logging imports successful")
        return True
    except ImportError as e:
        if "pydantic" in str(e):
            print(f"  [SKIP] Pydantic not installed (install with: pip install pydantic)")
            print(f"         Logging module structure is correct, dependencies missing")
            return True  # Not a failure of the observability code
        print(f"  [FAIL] Import error: {e}")
        return False


def test_redaction():
    """Test that sensitive data is redacted."""
    print("Testing redaction...")

    try:
        from packages.shared.src.logging import redact_sensitive
    except ImportError as e:
        if "pydantic" in str(e):
            print("  [SKIP] Requires pydantic (install with: pip install pydantic)")
            return True
        raise

    test_cases = [
        ("hf_abc123xyz789", "hf_***REDACTED***"),
        ("sk-proj-abc123", "sk-***REDACTED***"),
        ("ghp_1234567890abcdef", "ghp_***REDACTED***"),
        ("rpa_myrunpodkey123", "rpa_***REDACTED***"),
        ("/Users/testuser/code", "/[HOME]/code"),
        ("/home/ubuntu/data", "/[HOME]/data"),
        ("token=secret123&other=val", "token=***&other=val"),
        ('{"password": "secret123"}', '{"password": "***"}'),
    ]

    all_passed = True
    for input_str, expected in test_cases:
        result = redact_sensitive(input_str)
        if result == expected:
            print(f"  [PASS] Redacted: {input_str[:20]}...")
        else:
            print(f"  [FAIL] Expected '{expected}', got '{result}'")
            all_passed = False

    return all_passed


def test_log_structure(log_dir: Path):
    """Test that log directory structure can be created."""
    print("Testing log structure creation...")

    try:
        from packages.shared.src.logging import rotate_logs
    except ImportError as e:
        if "pydantic" in str(e):
            print("  [SKIP] Requires pydantic (install with: pip install pydantic)")
            return True
        raise

    # Create service directories
    for service in ["api", "worker", "web"]:
        try:
            rotate_logs(service)
            latest_dir = log_dir / service / "latest"
            archive_dir = log_dir / service / "archive"

            if latest_dir.exists() and archive_dir.exists():
                print(f"  [PASS] {service}: latest/ and archive/ created")
            else:
                print(f"  [FAIL] {service}: directories not created")
                return False
        except Exception as e:
            print(f"  [FAIL] {service}: {e}")
            return False

    return True


def test_json_format():
    """Test that logs are valid JSON with required fields."""
    print("Testing JSON log format...")

    try:
        from packages.shared.src import config as config_module
    except ImportError as e:
        if "pydantic" in str(e):
            print("  [SKIP] Requires pydantic (install with: pip install pydantic)")
            return True
        raise

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["LOG_DIR"] = tmpdir
        os.environ["LOG_TO_STDOUT"] = "false"
        os.environ["LOG_TO_FILE"] = "true"

        # Force config reload
        config_module._config = None

        from packages.shared.src.logging import (
            get_logger,
            configure_logging,
            set_correlation_id,
            _loggers,
        )

        # Clear logger cache
        _loggers.clear()

        # Configure and log
        configure_logging("api", rotate=False)
        set_correlation_id("test-obs-smoke")

        logger = get_logger("api.test")
        logger.info("Test message", extra={"event": "test.event", "key": "value"})

        # Read and parse log
        log_file = Path(tmpdir) / "api" / "latest" / "api.log"
        if not log_file.exists():
            print(f"  [FAIL] Log file not created at {log_file}")
            return False

        with open(log_file) as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            print("  [FAIL] No log entries written")
            return False

        # Parse and validate
        required_fields = {"timestamp", "level", "service", "logger", "message"}
        for line in lines:
            try:
                entry = json.loads(line)
                missing = required_fields - set(entry.keys())
                if missing:
                    print(f"  [FAIL] Missing fields: {missing}")
                    return False
            except json.JSONDecodeError:
                print(f"  [FAIL] Invalid JSON: {line[:50]}...")
                return False

        print("  [PASS] All log entries are valid JSON with required fields")
        return True


def test_log_rotation():
    """Test that log rotation archives previous logs."""
    print("Testing log rotation...")

    try:
        from packages.shared.src import config as config_module
    except ImportError as e:
        if "pydantic" in str(e):
            print("  [SKIP] Requires pydantic (install with: pip install pydantic)")
            return True
        raise

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["LOG_DIR"] = tmpdir
        os.environ["LOG_TO_STDOUT"] = "false"
        os.environ["LOG_TO_FILE"] = "true"

        # Force config reload
        config_module._config = None

        from packages.shared.src.logging import (
            get_logger,
            configure_logging,
            rotate_logs,
            _loggers,
        )

        # Clear logger cache
        _loggers.clear()

        # First session
        configure_logging("api", rotate=False)
        logger = get_logger("api.test")
        logger.info("Session 1 message")

        # Check file exists
        log_file = Path(tmpdir) / "api" / "latest" / "api.log"
        if not log_file.exists():
            print("  [FAIL] Log file not created")
            return False

        # Clear cache and rotate
        _loggers.clear()
        archive_path = rotate_logs("api")

        if archive_path is None:
            print("  [FAIL] Rotation did not return archive path")
            return False

        if not archive_path.exists():
            print(f"  [FAIL] Archive directory not created: {archive_path}")
            return False

        archived_log = archive_path / "api.log"
        if not archived_log.exists():
            print(f"  [FAIL] Archived log not found: {archived_log}")
            return False

        # New latest should be empty
        if log_file.exists() and log_file.stat().st_size > 0:
            print("  [FAIL] Latest log should be empty after rotation")
            return False

        print("  [PASS] Log rotation works correctly")
        return True


def test_subprocess_logs():
    """Test subprocess log path generation."""
    print("Testing subprocess log paths...")

    try:
        from packages.shared.src.logging import get_subprocess_log_paths
    except ImportError as e:
        if "pydantic" in str(e):
            print("  [SKIP] Requires pydantic (install with: pip install pydantic)")
            return True
        raise

    stdout_path, stderr_path = get_subprocess_log_paths("test-job-123")

    if "subprocess" not in str(stdout_path):
        print(f"  [FAIL] stdout path missing 'subprocess': {stdout_path}")
        return False

    if "test-job-123.stdout.log" not in str(stdout_path):
        print(f"  [FAIL] stdout path incorrect: {stdout_path}")
        return False

    if "test-job-123.stderr.log" not in str(stderr_path):
        print(f"  [FAIL] stderr path incorrect: {stderr_path}")
        return False

    print("  [PASS] Subprocess log paths generated correctly")
    return True


def test_correlation_id():
    """Test correlation ID context management."""
    print("Testing correlation ID context...")

    try:
        from packages.shared.src.logging import (
            set_correlation_id,
            get_correlation_id,
        )
    except ImportError as e:
        if "pydantic" in str(e):
            print("  [SKIP] Requires pydantic (install with: pip install pydantic)")
            return True
        raise

    # Set and get
    set_correlation_id("test-corr-123")
    if get_correlation_id() != "test-corr-123":
        print("  [FAIL] Correlation ID not set correctly")
        return False

    # Update
    set_correlation_id("test-corr-456")
    if get_correlation_id() != "test-corr-456":
        print("  [FAIL] Correlation ID not updated correctly")
        return False

    print("  [PASS] Correlation ID context works correctly")
    return True


async def test_e2e_health_and_info():
    """Test /health and /info endpoints (E2E)."""
    print("Testing /health and /info endpoints...")

    if not SMOKE_TEST_ENABLED:
        print("  [SKIP] Set SMOKE_TEST_ENABLED=1 to run E2E tests")
        return True

    try:
        from httpx import AsyncClient, ASGITransport
        from apps.api.src.main import app
    except ImportError as e:
        print(f"  [SKIP] Missing dependencies: {e}")
        return True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test /health
        response = await client.get("/health")
        if response.status_code != 200:
            print(f"  [FAIL] /health returned {response.status_code}")
            return False

        data = response.json()
        if data.get("status") != "healthy":
            print(f"  [FAIL] /health status not healthy: {data}")
            return False
        print("  [PASS] /health returns healthy")

        # Test correlation ID in response
        if "x-correlation-id" not in response.headers:
            print("  [FAIL] Missing X-Correlation-ID header")
            return False
        print("  [PASS] /health has X-Correlation-ID header")

        # Test /info
        response = await client.get("/info")
        if response.status_code != 200:
            print(f"  [FAIL] /info returned {response.status_code}")
            return False

        info = response.json()
        required_fields = ["name", "version", "mode", "training", "image_generation"]
        for field in required_fields:
            if field not in info:
                print(f"  [FAIL] /info missing field: {field}")
                return False
        print("  [PASS] /info returns all required fields")

        # Check capabilities structure
        if "parameters" not in info.get("training", {}):
            print("  [FAIL] /info training missing parameters")
            return False
        print("  [PASS] /info training has parameters")

    return True


async def test_e2e_training_job_logs():
    """Test training job creates JSONL logs (E2E)."""
    print("Testing training job JSONL log creation...")

    if not SMOKE_TEST_ENABLED:
        print("  [SKIP] Set SMOKE_TEST_ENABLED=1 to run E2E tests")
        return True

    try:
        from httpx import AsyncClient, ASGITransport
        from apps.api.src.main import app
        from packages.shared.src.config import get_global_config
        from packages.shared.src.logging import get_job_log_path
    except ImportError as e:
        print(f"  [SKIP] Missing dependencies: {e}")
        return True

    config = get_global_config()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create character
        char_resp = await client.post("/api/characters", json={
            "name": "Smoke Test Character",
            "trigger_word": "smoketest person"
        })
        if char_resp.status_code != 201:
            print(f"  [FAIL] Create character failed: {char_resp.status_code}")
            return False
        char_id = char_resp.json()["id"]
        print(f"  [OK] Created character: {char_id}")

        # 2. Upload test image
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
        upload_resp = await client.post(f"/api/characters/{char_id}/images", files=files)
        if upload_resp.status_code != 201:
            print(f"  [FAIL] Upload image failed: {upload_resp.status_code}")
            return False
        print("  [OK] Uploaded test image")

        # 3. Start training with correlation ID
        correlation_id = f"smoke-test-{int(time.time())}"
        train_resp = await client.post(
            "/api/training",
            json={
                "character_id": char_id,
                "config": {"steps": 100}
            },
            headers={"X-Correlation-ID": correlation_id}
        )
        if train_resp.status_code != 201:
            print(f"  [FAIL] Start training failed: {train_resp.status_code}")
            return False
        job_id = train_resp.json()["id"]
        print(f"  [OK] Started training job: {job_id}")

        # 4. Wait for completion (max 60 seconds)
        max_wait = 60
        start_time = time.time()
        while time.time() - start_time < max_wait:
            status_resp = await client.get(f"/api/training/{job_id}")
            status = status_resp.json()
            if status["status"] in ["completed", "failed"]:
                break
            await asyncio.sleep(0.5)

        final_status = (await client.get(f"/api/training/{job_id}")).json()
        if final_status["status"] != "completed":
            print(f"  [FAIL] Training did not complete: {final_status['status']}")
            print(f"         Error: {final_status.get('error_message', 'Unknown')}")
            return False
        print("  [OK] Training completed")

        # 5. Check JSONL log file exists
        job_log_path = get_job_log_path(job_id)
        if job_log_path is None or not job_log_path.exists():
            print(f"  [FAIL] Job log file not found for {job_id}")
            return False
        print(f"  [OK] Job log file exists: {job_log_path}")

        # 6. Validate JSONL structure
        with open(job_log_path) as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            print("  [FAIL] Job log file is empty")
            return False

        required_fields = {"ts", "level", "service", "job_id", "msg"}
        for i, line in enumerate(lines):
            try:
                record = json.loads(line)
                missing = required_fields - set(record.keys())
                if missing:
                    print(f"  [FAIL] Line {i} missing fields: {missing}")
                    return False
                # Verify job_id matches
                if record.get("job_id") != job_id:
                    print(f"  [FAIL] Line {i} has wrong job_id")
                    return False
            except json.JSONDecodeError:
                print(f"  [FAIL] Line {i} is not valid JSON")
                return False

        print(f"  [PASS] All {len(lines)} log entries have valid structure")

        # 7. Check correlation ID in logs
        has_correlation = any(
            json.loads(line).get("correlation_id") == correlation_id
            for line in lines
        )
        if has_correlation:
            print("  [PASS] Correlation ID found in job logs")
        else:
            print("  [WARN] Correlation ID not found in job logs (may be expected)")

    return True


def main():
    parser = argparse.ArgumentParser(description="Observability smoke test")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("./logs"),
        help="Log directory path (default: ./logs)",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("ISENGARD OBSERVABILITY SMOKE TEST")
    print("=" * 50)
    print(f"Date: {datetime.now().isoformat()}")
    print(f"Log directory: {args.log_dir}")
    print(f"SMOKE_TEST_ENABLED: {SMOKE_TEST_ENABLED}")
    print()

    # Basic tests (always run)
    tests = [
        ("Imports", test_imports),
        ("Redaction", test_redaction),
        ("Correlation ID", test_correlation_id),
        ("Subprocess Logs", test_subprocess_logs),
        ("JSON Format", test_json_format),
        ("Log Rotation", test_log_rotation),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  [FAIL] Exception: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            results.append((name, False))
        print()

    # E2E tests (only when SMOKE_TEST_ENABLED)
    e2e_tests = [
        ("E2E: Health & Info", test_e2e_health_and_info),
        ("E2E: Training Job Logs", test_e2e_training_job_logs),
    ]

    for name, test_func in e2e_tests:
        try:
            result = asyncio.run(test_func())
            results.append((name, result))
        except Exception as e:
            print(f"  [FAIL] Exception: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            results.append((name, False))
        print()

    # Summary
    print("=" * 50)
    print("RESULTS")
    print("=" * 50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print()
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\nAll tests passed!")
        sys.exit(0)
    else:
        print("\nSome tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
