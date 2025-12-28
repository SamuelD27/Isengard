#!/bin/bash
#
# GUI→API Wiring Smoke Test
#
# This script validates that the frontend can communicate with the backend
# by testing key API endpoints for proper routing (no static server fallback).
#
# Usage:
#   ./scripts/smoke_gui_api.sh                    # Test against localhost:3000
#   ./scripts/smoke_gui_api.sh http://pod-url    # Test against specific URL
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed
#

set -e

# Configuration
BASE_URL="${1:-http://localhost:3000}"
API_BASE="${BASE_URL}/api"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARTIFACTS_DIR="artifacts/e2e/${TIMESTAMP}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Results tracking
TESTS_PASSED=0
TESTS_FAILED=0
FAILURES=""

# Create artifacts directory
mkdir -p "${ARTIFACTS_DIR}"

echo "=========================================="
echo "GUI→API Wiring Smoke Test"
echo "=========================================="
echo "Base URL: ${BASE_URL}"
echo "API Base: ${API_BASE}"
echo "Artifacts: ${ARTIFACTS_DIR}"
echo ""

# Helper function to test an endpoint
test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local expected_content_type="$4"
    local data="$5"

    echo -n "Testing ${name}... "

    local url="${API_BASE}${endpoint}"
    local response_file="${ARTIFACTS_DIR}/${name//\//_}.response"
    local headers_file="${ARTIFACTS_DIR}/${name//\//_}.headers"

    # Make request
    if [ "$method" = "GET" ]; then
        http_code=$(curl -s -w "%{http_code}" -o "${response_file}" -D "${headers_file}" \
            -H "X-Correlation-ID: smoke-test-${TIMESTAMP}" \
            "${url}" 2>/dev/null)
    else
        http_code=$(curl -s -w "%{http_code}" -o "${response_file}" -D "${headers_file}" \
            -X "${method}" \
            -H "Content-Type: application/json" \
            -H "X-Correlation-ID: smoke-test-${TIMESTAMP}" \
            -d "${data}" \
            "${url}" 2>/dev/null)
    fi

    # Check HTTP status
    if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 400 ]; then
        echo -e "${RED}FAIL${NC} (HTTP ${http_code})"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILURES="${FAILURES}\n  - ${name}: HTTP ${http_code}"
        return 1
    fi

    # Check content-type
    content_type=$(grep -i "content-type" "${headers_file}" | head -1 | tr -d '\r')
    if ! echo "${content_type}" | grep -qi "${expected_content_type}"; then
        echo -e "${RED}FAIL${NC} (wrong content-type: ${content_type})"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILURES="${FAILURES}\n  - ${name}: Expected ${expected_content_type}, got ${content_type}"
        return 1
    fi

    # Check for HTML in response (misroute detection)
    if grep -qi "<!doctype html\|<html\|<div id=\"root\">" "${response_file}" 2>/dev/null; then
        echo -e "${RED}FAIL${NC} (HTML response - API misrouted to static server)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILURES="${FAILURES}\n  - ${name}: HTML response instead of JSON (check proxy config)"
        return 1
    fi

    # Check JSON is valid
    if [ "${expected_content_type}" = "application/json" ]; then
        if ! python3 -c "import json; json.load(open('${response_file}'))" 2>/dev/null; then
            echo -e "${RED}FAIL${NC} (invalid JSON)"
            TESTS_FAILED=$((TESTS_FAILED + 1))
            FAILURES="${FAILURES}\n  - ${name}: Response is not valid JSON"
            return 1
        fi
    fi

    echo -e "${GREEN}PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    return 0
}

# Wait for service to be ready
echo "Waiting for service to be ready..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s "${API_BASE}/health" >/dev/null 2>&1; then
        echo "Service is ready!"
        break
    fi
    attempt=$((attempt + 1))
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "${RED}ERROR: Service not ready after ${max_attempts} seconds${NC}"
    exit 1
fi

echo ""
echo "Running endpoint tests..."
echo ""

# Test health endpoints
test_endpoint "health" "GET" "/health" "application/json"
test_endpoint "info" "GET" "/info" "application/json"

# Test debug echo (if enabled)
test_endpoint "debug_echo" "GET" "/_debug/echo" "application/json" || true

# Test characters endpoints
test_endpoint "list_characters" "GET" "/characters" "application/json"

# Test training endpoints
test_endpoint "list_training_jobs" "GET" "/training" "application/json"

# Test generation endpoints
test_endpoint "list_generation_jobs" "GET" "/generation?limit=10" "application/json"

# Summary
echo ""
echo "=========================================="
echo "Results"
echo "=========================================="
echo -e "Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Failed: ${RED}${TESTS_FAILED}${NC}"

if [ $TESTS_FAILED -gt 0 ]; then
    echo ""
    echo -e "${RED}Failures:${NC}"
    echo -e "${FAILURES}"
    echo ""
    echo "Artifacts saved to: ${ARTIFACTS_DIR}"
    exit 1
fi

echo ""
echo -e "${GREEN}All tests passed!${NC}"
echo "Artifacts saved to: ${ARTIFACTS_DIR}"
exit 0
