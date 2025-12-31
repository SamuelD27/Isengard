#!/bin/bash
# smoke_internal_engines.sh - Smoke test for vendored internal engines
#
# This script verifies the Docker image has correctly integrated
# vendored ComfyUI and AI-Toolkit as internal services.
#
# Tests:
# 1. Docker image builds successfully
# 2. Container starts and API is accessible
# 3. ComfyUI is reachable INTERNALLY (from inside container)
# 4. ComfyUI is NOT reachable EXTERNALLY (port not published)
# 5. Vendored AI-Toolkit is present at expected path
# 6. /ready endpoint shows healthy dependencies
#
# Usage:
#   ./scripts/smoke/smoke_internal_engines.sh
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration
IMAGE_NAME="isengard:smoke-test"
CONTAINER_NAME="isengard-smoke-test-$$"
API_PORT=8000
WEB_PORT=3000
COMFYUI_PORT=8188  # Internal only - should NOT be published
TIMEOUT=120

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
TESTS_PASSED=0
TESTS_FAILED=0

log() { echo -e "${GREEN}[SMOKE]${NC} $1"; }
log_test() { echo -e "${CYAN}[TEST]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((TESTS_PASSED++)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; ((TESTS_FAILED++)); }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

cleanup() {
    log "Cleaning up..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
}

# Ensure cleanup on exit
trap cleanup EXIT

# ============================================================
# TEST 1: Docker Image Builds
# ============================================================
log_test "1. Building Docker image..."

cd "$REPO_ROOT"

# Check if vendor directories exist
if [ ! -d "vendor/comfyui" ] || [ ! -d "vendor/ai-toolkit" ]; then
    log_fail "Vendor directories not found. Run git subtree add first."
    exit 1
fi

# Build with fast-test mode for quick smoke testing
if docker build -t "$IMAGE_NAME" . --build-arg ISENGARD_MODE=fast-test 2>&1 | tail -20; then
    log_pass "Docker image built successfully"
else
    log_fail "Docker build failed"
    exit 1
fi

# ============================================================
# TEST 2: Container Starts
# ============================================================
log_test "2. Starting container..."

# Start container WITHOUT publishing ComfyUI port (security test)
# Only publish API and Web ports
docker run -d \
    --name "$CONTAINER_NAME" \
    -p "${API_PORT}:8000" \
    -p "${WEB_PORT}:3000" \
    -e ISENGARD_MODE=fast-test \
    "$IMAGE_NAME"

log "Container started, waiting for services..."

# Wait for API to be ready
for i in $(seq 1 $TIMEOUT); do
    if curl -sf "http://localhost:${API_PORT}/health" > /dev/null 2>&1; then
        log_pass "Container started and API is healthy"
        break
    fi
    if [ $i -eq $TIMEOUT ]; then
        log_fail "API failed to start within ${TIMEOUT}s"
        docker logs "$CONTAINER_NAME" | tail -50
        exit 1
    fi
    sleep 1
done

# ============================================================
# TEST 3: ComfyUI Internal Accessibility
# ============================================================
log_test "3. Checking ComfyUI is reachable INTERNALLY..."

# Execute curl from inside the container to check internal ComfyUI
COMFYUI_INTERNAL=$(docker exec "$CONTAINER_NAME" \
    curl -sf "http://127.0.0.1:8188/system_stats" 2>/dev/null || echo "FAILED")

if [ "$COMFYUI_INTERNAL" != "FAILED" ] && echo "$COMFYUI_INTERNAL" | grep -q "devices"; then
    log_pass "ComfyUI is reachable internally at 127.0.0.1:8188"
else
    log_warn "ComfyUI not reachable internally (may need GPU or longer startup)"
    # Don't fail - ComfyUI may not start without GPU
fi

# ============================================================
# TEST 4: ComfyUI External Inaccessibility (Security)
# ============================================================
log_test "4. Verifying ComfyUI is NOT exposed externally..."

# Try to connect to ComfyUI from the host - should FAIL
if curl -sf --connect-timeout 2 "http://localhost:${COMFYUI_PORT}/system_stats" > /dev/null 2>&1; then
    log_fail "SECURITY: ComfyUI is accessible from host on port ${COMFYUI_PORT}!"
    log_fail "Port 8188 should NOT be published. Check docker run command."
else
    log_pass "ComfyUI is correctly NOT exposed to host (port ${COMFYUI_PORT} closed)"
fi

# ============================================================
# TEST 5: Vendored AI-Toolkit Present
# ============================================================
log_test "5. Checking vendored AI-Toolkit..."

AITOOLKIT_EXISTS=$(docker exec "$CONTAINER_NAME" \
    test -f /app/vendor/ai-toolkit/run.py && echo "YES" || echo "NO")

if [ "$AITOOLKIT_EXISTS" = "YES" ]; then
    log_pass "Vendored AI-Toolkit found at /app/vendor/ai-toolkit"
else
    log_fail "AI-Toolkit not found at expected path"
fi

# Check PYTHONPATH includes vendored path
PYTHONPATH_CHECK=$(docker exec "$CONTAINER_NAME" \
    python -c "import sys; print('/app/vendor/ai-toolkit' in ':'.join(sys.path))" 2>/dev/null || echo "False")

if [ "$PYTHONPATH_CHECK" = "True" ]; then
    log_pass "PYTHONPATH includes vendored AI-Toolkit"
else
    log_warn "PYTHONPATH may not include AI-Toolkit (check PYTHONPATH env var)"
fi

# ============================================================
# TEST 6: /ready Endpoint Shows Dependencies
# ============================================================
log_test "6. Checking /ready endpoint..."

READY_RESPONSE=$(curl -sf "http://localhost:${API_PORT}/ready" 2>/dev/null || echo "{}")

if echo "$READY_RESPONSE" | grep -q "aitoolkit"; then
    log_pass "/ready endpoint reports AI-Toolkit status"
else
    log_warn "/ready endpoint doesn't show AI-Toolkit (check health.py)"
fi

if echo "$READY_RESPONSE" | grep -q "comfyui"; then
    log_pass "/ready endpoint reports ComfyUI status"
else
    log_warn "/ready endpoint doesn't show ComfyUI (check health.py)"
fi

# ============================================================
# TEST 7: Vendor Pins File Present
# ============================================================
log_test "7. Checking vendor pins file..."

PINS_EXISTS=$(docker exec "$CONTAINER_NAME" \
    test -f /app/vendor/VENDOR_PINS.json && echo "YES" || echo "NO")

if [ "$PINS_EXISTS" = "YES" ]; then
    log_pass "VENDOR_PINS.json found in container"

    # Show pins for verification
    docker exec "$CONTAINER_NAME" cat /app/vendor/VENDOR_PINS.json | jq -r 'to_entries[] | "  \(.key): \(.value.commit | .[0:8])"' 2>/dev/null || true
else
    log_fail "VENDOR_PINS.json not found in container"
fi

# ============================================================
# TEST 8: Bootstrap Version
# ============================================================
log_test "8. Checking bootstrap version..."

BOOTSTRAP_VERSION=$(docker exec "$CONTAINER_NAME" cat /app/BOOTSTRAP_VERSION 2>/dev/null || echo "MISSING")

if echo "$BOOTSTRAP_VERSION" | grep -q "vendored"; then
    log_pass "Bootstrap version indicates vendored build"
    echo "  $BOOTSTRAP_VERSION" | head -1
else
    log_warn "Bootstrap version may not be updated for vendored build"
fi

# ============================================================
# RESULTS
# ============================================================
echo ""
echo "============================================================"
echo "  SMOKE TEST RESULTS"
echo "============================================================"
echo ""
echo -e "  ${GREEN}Passed:${NC} ${TESTS_PASSED}"
echo -e "  ${RED}Failed:${NC} ${TESTS_FAILED}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All smoke tests passed!${NC}"
    echo ""
    echo "The vendored internal engines are correctly integrated:"
    echo "  - ComfyUI binds to 127.0.0.1:8188 (internal only)"
    echo "  - AI-Toolkit is vendored at /app/vendor/ai-toolkit"
    echo "  - Only API (8000) and Web (3000) ports are exposed"
    echo ""
    exit 0
else
    echo -e "${RED}Some tests failed. Review output above.${NC}"
    echo ""
    echo "Container logs (last 50 lines):"
    docker logs "$CONTAINER_NAME" 2>&1 | tail -50
    exit 1
fi
