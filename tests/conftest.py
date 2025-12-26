"""
Pytest Configuration and Fixtures

Shared fixtures for all tests.
"""

import os
import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    os.environ["ISENGARD_MODE"] = "fast-test"
    os.environ["LOG_TO_STDOUT"] = "false"  # Reduce noise in tests
    os.environ["LOG_LEVEL"] = "WARNING"


@pytest.fixture(scope="module")
def test_data_dir(tmp_path_factory):
    """Create a temporary data directory for tests."""
    data_dir = tmp_path_factory.mktemp("test_data")
    os.environ["VOLUME_ROOT"] = str(data_dir)
    return data_dir
