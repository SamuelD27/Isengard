"""
E2E Smoke Test Suite

Tests the full API integration from endpoints to verify:
1. All routes exist and respond
2. Request/response contracts match
3. Frontend expectations are met

Run with:
    pytest tests/test_e2e_smoke.py -v

Or standalone:
    python tests/test_e2e_smoke.py

Requires API to be running on localhost:8000 (or set API_BASE_URL env var).
"""

import os
import sys
import json
import uuid
import time
import pytest
import httpx
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT = 30.0


def generate_correlation_id() -> str:
    """Generate a test correlation ID."""
    return f"test-{uuid.uuid4().hex[:12]}"


def make_headers(correlation_id: str | None = None) -> dict:
    """Create request headers with correlation ID."""
    return {
        "X-Correlation-ID": correlation_id or generate_correlation_id(),
        "Content-Type": "application/json",
    }


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint(self):
        """GET /api/health should return healthy status."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/api/health", headers=make_headers())
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    def test_ready_endpoint(self):
        """GET /api/ready should return readiness status."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/api/ready", headers=make_headers())
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "dependencies" in data

    def test_info_endpoint(self):
        """GET /api/info should return API capabilities."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/api/info", headers=make_headers())
            assert response.status_code == 200
            data = response.json()

            # Check required fields
            assert "name" in data
            assert "version" in data
            assert "mode" in data
            assert "training" in data
            assert "image_generation" in data

            # Check training capabilities
            training = data["training"]
            assert "method" in training
            assert "backend" in training
            assert "parameters" in training

            # Check image generation capabilities
            image_gen = data["image_generation"]
            assert "backend" in image_gen
            assert "toggles" in image_gen
            assert "parameters" in image_gen

    def test_openapi_endpoint(self):
        """GET /openapi.json should return valid OpenAPI spec."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/openapi.json", headers=make_headers())
            assert response.status_code == 200
            data = response.json()

            # Basic OpenAPI structure
            assert "openapi" in data
            assert "info" in data
            assert "paths" in data

            # Check expected endpoints exist
            paths = data["paths"]
            expected_paths = [
                "/api/health",
                "/api/ready",
                "/api/info",
                "/api/characters",
                "/api/training",
                "/api/generation",
            ]
            for path in expected_paths:
                assert path in paths, f"Missing expected path: {path}"


class TestCharacterEndpoints:
    """Test character CRUD endpoints."""

    def test_list_characters_empty(self):
        """GET /api/characters should return list (possibly empty)."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/api/characters", headers=make_headers())
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_create_character(self):
        """POST /api/characters should create a new character."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            correlation_id = generate_correlation_id()
            payload = {
                "name": f"Test Character {uuid.uuid4().hex[:6]}",
                "description": "E2E test character",
                "trigger_word": f"testchar_{uuid.uuid4().hex[:6]}",
            }

            response = client.post(
                "/api/characters",
                headers=make_headers(correlation_id),
                json=payload,
            )

            assert response.status_code == 201, f"Failed: {response.text}"
            data = response.json()

            # Check response structure
            assert "id" in data
            assert data["name"] == payload["name"]
            assert data["trigger_word"] == payload["trigger_word"]
            assert "created_at" in data
            assert "image_count" in data

            # Verify correlation ID is returned
            assert response.headers.get("X-Correlation-ID") == correlation_id

            # Store ID for cleanup
            return data["id"]

    def test_get_character(self):
        """GET /api/characters/{id} should return character details."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            # First create a character
            payload = {
                "name": f"Test Character {uuid.uuid4().hex[:6]}",
                "trigger_word": f"testchar_{uuid.uuid4().hex[:6]}",
            }
            create_response = client.post(
                "/api/characters",
                headers=make_headers(),
                json=payload,
            )
            assert create_response.status_code == 201
            character_id = create_response.json()["id"]

            # Get the character
            response = client.get(
                f"/api/characters/{character_id}",
                headers=make_headers(),
            )
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == character_id
            assert data["name"] == payload["name"]

    def test_get_character_not_found(self):
        """GET /api/characters/{id} should return 404 for non-existent ID."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get(
                "/api/characters/char-nonexistent",
                headers=make_headers(),
            )
            assert response.status_code == 404

    def test_update_character(self):
        """PATCH /api/characters/{id} should update character."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            # Create character
            create_payload = {
                "name": "Original Name",
                "trigger_word": f"testchar_{uuid.uuid4().hex[:6]}",
            }
            create_response = client.post(
                "/api/characters",
                headers=make_headers(),
                json=create_payload,
            )
            assert create_response.status_code == 201
            character_id = create_response.json()["id"]

            # Update character
            update_payload = {
                "name": "Updated Name",
                "description": "Updated description",
            }
            response = client.patch(
                f"/api/characters/{character_id}",
                headers=make_headers(),
                json=update_payload,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Updated Name"
            assert data["description"] == "Updated description"

    def test_delete_character(self):
        """DELETE /api/characters/{id} should delete character."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            # Create character
            payload = {
                "name": "To Delete",
                "trigger_word": f"testchar_{uuid.uuid4().hex[:6]}",
            }
            create_response = client.post(
                "/api/characters",
                headers=make_headers(),
                json=payload,
            )
            assert create_response.status_code == 201
            character_id = create_response.json()["id"]

            # Delete character
            response = client.delete(
                f"/api/characters/{character_id}",
                headers=make_headers(),
            )
            assert response.status_code == 204

            # Verify deleted
            get_response = client.get(
                f"/api/characters/{character_id}",
                headers=make_headers(),
            )
            assert get_response.status_code == 404

    def test_list_character_images_empty(self):
        """GET /api/characters/{id}/images should return empty list initially."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            # Create character
            payload = {
                "name": "Image Test",
                "trigger_word": f"testchar_{uuid.uuid4().hex[:6]}",
            }
            create_response = client.post(
                "/api/characters",
                headers=make_headers(),
                json=payload,
            )
            assert create_response.status_code == 201
            character_id = create_response.json()["id"]

            # List images
            response = client.get(
                f"/api/characters/{character_id}/images",
                headers=make_headers(),
            )
            assert response.status_code == 200
            data = response.json()
            assert "images" in data
            assert "count" in data
            assert data["count"] == 0


class TestTrainingEndpoints:
    """Test training job endpoints."""

    def test_list_training_jobs(self):
        """GET /api/training should return list of jobs."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/api/training", headers=make_headers())
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_start_training_requires_character(self):
        """POST /api/training should fail without valid character."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            payload = {
                "character_id": "char-nonexistent",
                "config": {
                    "method": "lora",
                    "steps": 100,
                    "learning_rate": 0.0001,
                    "batch_size": 1,
                    "resolution": 512,
                    "lora_rank": 16,
                },
            }
            response = client.post(
                "/api/training",
                headers=make_headers(),
                json=payload,
            )
            assert response.status_code == 404

    def test_start_training_requires_images(self):
        """POST /api/training should fail if character has no images."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            # Create character without images
            char_payload = {
                "name": "Training Test",
                "trigger_word": f"traintest_{uuid.uuid4().hex[:6]}",
            }
            create_response = client.post(
                "/api/characters",
                headers=make_headers(),
                json=char_payload,
            )
            assert create_response.status_code == 201
            character_id = create_response.json()["id"]

            # Try to start training
            train_payload = {
                "character_id": character_id,
                "config": {
                    "method": "lora",
                    "steps": 100,
                    "learning_rate": 0.0001,
                    "batch_size": 1,
                    "resolution": 512,
                    "lora_rank": 16,
                },
            }
            response = client.post(
                "/api/training",
                headers=make_headers(),
                json=train_payload,
            )
            assert response.status_code == 400
            assert "images" in response.json()["detail"].lower()

    def test_get_training_job_not_found(self):
        """GET /api/training/{id} should return 404 for non-existent job."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get(
                "/api/training/train-nonexistent",
                headers=make_headers(),
            )
            assert response.status_code == 404


class TestGenerationEndpoints:
    """Test image generation endpoints."""

    def test_list_generation_jobs(self):
        """GET /api/generation should return list of jobs."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/api/generation", headers=make_headers())
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_start_generation_basic(self):
        """POST /api/generation should create a generation job."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            payload = {
                "config": {
                    "prompt": "A test image, simple",
                    "negative_prompt": "blurry",
                    "width": 512,
                    "height": 512,
                    "steps": 4,
                    "guidance_scale": 3.5,
                    "seed": 42,
                    "lora_id": None,
                    "lora_strength": 1.0,
                },
                "count": 1,
            }
            response = client.post(
                "/api/generation",
                headers=make_headers(),
                json=payload,
            )

            # In fast-test mode, this should work
            # In production mode without ComfyUI, it may fail
            if response.status_code == 201:
                data = response.json()
                assert "id" in data
                assert "status" in data
                assert data["status"] in ["pending", "queued", "running"]
            else:
                # Service unavailable is acceptable
                assert response.status_code in [503, 400]

    def test_get_generation_job_not_found(self):
        """GET /api/generation/{id} should return 404 for non-existent job."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get(
                "/api/generation/gen-nonexistent",
                headers=make_headers(),
            )
            assert response.status_code == 404


class TestJobEndpoints:
    """Test job utility endpoints."""

    def test_get_job_logs_not_found(self):
        """GET /api/jobs/{id}/logs should return 404 for non-existent job."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get(
                "/api/jobs/job-nonexistent/logs",
                headers=make_headers(),
            )
            assert response.status_code == 404


class TestClientLogsEndpoint:
    """Test client-side log submission."""

    def test_submit_client_logs(self):
        """POST /api/client-logs should accept log entries."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            payload = {
                "entries": [
                    {
                        "timestamp": "2025-01-15T10:30:00.000Z",
                        "level": "INFO",
                        "message": "Test log entry",
                        "event": "ui.test",
                        "context": {"test": True},
                    }
                ]
            }
            response = client.post(
                "/api/client-logs",
                headers=make_headers(),
                json=payload,
            )
            assert response.status_code in [200, 201, 204]


class TestCORS:
    """Test CORS configuration."""

    def test_cors_preflight(self):
        """OPTIONS request should return CORS headers."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.options(
                "/api/characters",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-correlation-id",
                },
            )
            # Should succeed with CORS headers
            assert response.status_code == 200
            assert "access-control-allow-origin" in response.headers


class TestCorrelationID:
    """Test correlation ID propagation."""

    def test_correlation_id_returned(self):
        """Correlation ID should be returned in response headers."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            correlation_id = generate_correlation_id()
            response = client.get(
                "/health",
                headers={"X-Correlation-ID": correlation_id},
            )
            assert response.status_code == 200
            assert response.headers.get("X-Correlation-ID") == correlation_id

    def test_correlation_id_generated(self):
        """Correlation ID should be generated if not provided."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert "X-Correlation-ID" in response.headers
            assert response.headers["X-Correlation-ID"].startswith("req-")


class TestContractAlignment:
    """Verify frontend/backend contract alignment."""

    def test_character_schema_matches_frontend(self):
        """Character response should match frontend Character interface."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            # Create character
            payload = {
                "name": "Schema Test",
                "description": "Testing schema",
                "trigger_word": f"schematest_{uuid.uuid4().hex[:6]}",
            }
            response = client.post(
                "/api/characters",
                headers=make_headers(),
                json=payload,
            )
            assert response.status_code == 201
            data = response.json()

            # Fields expected by frontend (from api.ts Character interface)
            expected_fields = [
                "id",
                "name",
                "description",
                "trigger_word",
                "created_at",
                "updated_at",
                "image_count",
                "lora_path",
                "lora_trained_at",
            ]

            for field in expected_fields:
                assert field in data, f"Missing expected field: {field}"

    def test_info_schema_matches_frontend(self):
        """Info response should match frontend ApiInfo interface."""
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.get("/api/info", headers=make_headers())
            assert response.status_code == 200
            data = response.json()

            # Fields expected by frontend (from api.ts ApiInfo interface)
            assert "name" in data
            assert "version" in data
            assert "mode" in data
            assert "training" in data
            assert "image_generation" in data

            # Training capabilities schema
            training = data["training"]
            assert "method" in training
            assert "backend" in training
            assert "parameters" in training

            # Image generation capabilities schema
            image_gen = data["image_generation"]
            assert "backend" in image_gen
            assert "model_variants" in image_gen
            assert "toggles" in image_gen
            assert "parameters" in image_gen


def run_smoke_tests():
    """Run all smoke tests and report results."""
    import subprocess
    result = subprocess.run(
        ["pytest", __file__, "-v", "--tb=short"],
        capture_output=False,
    )
    return result.returncode


if __name__ == "__main__":
    # Allow running directly
    exit(run_smoke_tests())
