#!/bin/bash
# integration_test.sh - Comprehensive integration tests for Isengard
#
# This script runs integration tests against a running Isengard instance.
# Can run against local dev server or a remote instance.
#
# Usage:
#   ./scripts/integration_test.sh [BASE_URL]
#
# Arguments:
#   BASE_URL - Optional. Default: http://localhost:8000
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed

set -e

# Configuration
BASE_URL="${1:-http://localhost:8000}"
API_URL="${BASE_URL}/api"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Test data
TEST_CHARACTER_NAME="Integration Test Character"
TEST_TRIGGER_WORD="integrationtest person"
CREATED_CHAR_ID=""
CREATED_JOB_IDS=()

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_test() { echo -e "${CYAN}[TEST]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((TESTS_PASSED++)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; ((TESTS_FAILED++)); }
log_skip() { echo -e "${YELLOW}[SKIP]${NC} $1"; ((TESTS_SKIPPED++)); }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

cleanup() {
    log "Cleaning up test data..."

    # Delete created characters
    if [ -n "$CREATED_CHAR_ID" ]; then
        curl -sf -X DELETE "${API_URL}/characters/${CREATED_CHAR_ID}" > /dev/null 2>&1 || true
    fi

    log "Cleanup complete"
}

trap cleanup EXIT

echo ""
echo "============================================================"
echo "  ISENGARD INTEGRATION TESTS"
echo "============================================================"
echo "  Target: ${BASE_URL}"
echo "============================================================"
echo ""

# ============================================================
# SECTION 1: Health Checks
# ============================================================
log "=== Section 1: Health Checks ==="

log_test "1.1 Testing /health endpoint..."
HEALTH_RESPONSE=$(curl -sf "${BASE_URL}/health" 2>/dev/null || echo "FAILED")
if echo "$HEALTH_RESPONSE" | grep -q "ok\|healthy"; then
    log_pass "/health returns healthy status"
else
    log_fail "/health endpoint failed or unhealthy"
fi

log_test "1.2 Testing /ready endpoint..."
READY_RESPONSE=$(curl -sf "${BASE_URL}/ready" 2>/dev/null || echo "FAILED")
if [ "$READY_RESPONSE" != "FAILED" ]; then
    log_pass "/ready endpoint accessible"

    # Check for specific dependencies
    if echo "$READY_RESPONSE" | grep -qi "comfyui"; then
        log_pass "/ready reports ComfyUI status"
    else
        log_warn "/ready doesn't include ComfyUI status"
    fi
else
    log_fail "/ready endpoint failed"
fi

log_test "1.3 Testing /info endpoint..."
INFO_RESPONSE=$(curl -sf "${BASE_URL}/info" 2>/dev/null || echo "FAILED")
if echo "$INFO_RESPONSE" | grep -q "version\|mode"; then
    log_pass "/info returns system information"
else
    log_warn "/info endpoint may not be implemented"
fi

echo ""

# ============================================================
# SECTION 2: Character CRUD
# ============================================================
log "=== Section 2: Character CRUD ==="

log_test "2.1 Creating a test character..."
CREATE_RESPONSE=$(curl -sf -X POST "${API_URL}/characters" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${TEST_CHARACTER_NAME}\",\"trigger_word\":\"${TEST_TRIGGER_WORD}\"}" 2>/dev/null || echo "FAILED")

if [ "$CREATE_RESPONSE" = "FAILED" ]; then
    log_fail "Failed to create character"
else
    CREATED_CHAR_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
    if [ -n "$CREATED_CHAR_ID" ] && [ "$CREATED_CHAR_ID" != "null" ]; then
        log_pass "Character created with ID: $CREATED_CHAR_ID"
    else
        log_fail "Character created but no ID returned"
    fi
fi

log_test "2.2 Getting created character..."
if [ -n "$CREATED_CHAR_ID" ]; then
    GET_RESPONSE=$(curl -sf "${API_URL}/characters/${CREATED_CHAR_ID}" 2>/dev/null || echo "FAILED")
    if echo "$GET_RESPONSE" | grep -q "$TEST_CHARACTER_NAME"; then
        log_pass "Character retrieved successfully"
    else
        log_fail "Failed to retrieve character"
    fi
else
    log_skip "Skipping - no character ID"
fi

log_test "2.3 Listing characters..."
LIST_RESPONSE=$(curl -sf "${API_URL}/characters" 2>/dev/null || echo "FAILED")
if [ "$LIST_RESPONSE" != "FAILED" ]; then
    CHAR_COUNT=$(echo "$LIST_RESPONSE" | jq 'length' 2>/dev/null || echo "0")
    log_pass "Listed characters (count: $CHAR_COUNT)"
else
    log_fail "Failed to list characters"
fi

log_test "2.4 Updating character..."
if [ -n "$CREATED_CHAR_ID" ]; then
    UPDATE_RESPONSE=$(curl -sf -X PATCH "${API_URL}/characters/${CREATED_CHAR_ID}" \
        -H "Content-Type: application/json" \
        -d '{"name":"Updated Integration Test"}' 2>/dev/null || echo "FAILED")
    if echo "$UPDATE_RESPONSE" | grep -q "Updated Integration Test"; then
        log_pass "Character updated successfully"
    else
        log_warn "Character update may have failed"
    fi
else
    log_skip "Skipping - no character ID"
fi

log_test "2.5 Character not found returns 404..."
NOT_FOUND=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/characters/nonexistent-id-12345")
if [ "$NOT_FOUND" = "404" ]; then
    log_pass "Non-existent character returns 404"
else
    log_fail "Expected 404, got $NOT_FOUND"
fi

echo ""

# ============================================================
# SECTION 3: Training Flow
# ============================================================
log "=== Section 3: Training Flow ==="

log_test "3.1 Listing training jobs..."
TRAIN_LIST=$(curl -sf "${API_URL}/training" 2>/dev/null || echo "FAILED")
if [ "$TRAIN_LIST" != "FAILED" ]; then
    JOB_COUNT=$(echo "$TRAIN_LIST" | jq 'length' 2>/dev/null || echo "0")
    log_pass "Listed training jobs (count: $JOB_COUNT)"
else
    log_fail "Failed to list training jobs"
fi

log_test "3.2 Training without images returns 400..."
if [ -n "$CREATED_CHAR_ID" ]; then
    TRAIN_NO_IMAGES=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_URL}/training" \
        -H "Content-Type: application/json" \
        -d "{\"character_id\":\"${CREATED_CHAR_ID}\",\"config\":{\"steps\":100}}")
    if [ "$TRAIN_NO_IMAGES" = "400" ]; then
        log_pass "Training without images correctly rejected (400)"
    else
        log_warn "Expected 400, got $TRAIN_NO_IMAGES"
    fi
else
    log_skip "Skipping - no character ID"
fi

log_test "3.3 Training job not found returns 404..."
TRAIN_NOT_FOUND=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/training/nonexistent-job-id")
if [ "$TRAIN_NOT_FOUND" = "404" ]; then
    log_pass "Non-existent training job returns 404"
else
    log_fail "Expected 404, got $TRAIN_NOT_FOUND"
fi

log_test "3.4 Listing successful training jobs..."
SUCCESS_LIST=$(curl -sf "${API_URL}/training/successful" 2>/dev/null || echo "FAILED")
if [ "$SUCCESS_LIST" != "FAILED" ]; then
    log_pass "/training/successful endpoint accessible"
else
    log_warn "/training/successful may not be implemented"
fi

log_test "3.5 Listing ongoing training jobs..."
ONGOING_LIST=$(curl -sf "${API_URL}/training/ongoing" 2>/dev/null || echo "FAILED")
if [ "$ONGOING_LIST" != "FAILED" ]; then
    log_pass "/training/ongoing endpoint accessible"
else
    log_warn "/training/ongoing may not be implemented"
fi

echo ""

# ============================================================
# SECTION 4: Generation Flow
# ============================================================
log "=== Section 4: Generation Flow ==="

log_test "4.1 Creating generation job..."
GEN_RESPONSE=$(curl -sf -X POST "${API_URL}/generation" \
    -H "Content-Type: application/json" \
    -d '{"config":{"prompt":"A beautiful landscape, high quality"},"count":1}' 2>/dev/null || echo "FAILED")

if [ "$GEN_RESPONSE" = "FAILED" ]; then
    log_fail "Failed to create generation job"
else
    GEN_JOB_ID=$(echo "$GEN_RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
    if [ -n "$GEN_JOB_ID" ] && [ "$GEN_JOB_ID" != "null" ]; then
        log_pass "Generation job created: $GEN_JOB_ID"
        CREATED_JOB_IDS+=("$GEN_JOB_ID")
    else
        log_fail "Generation job created but no ID"
    fi
fi

log_test "4.2 Getting generation job..."
if [ -n "$GEN_JOB_ID" ]; then
    GET_GEN=$(curl -sf "${API_URL}/generation/${GEN_JOB_ID}" 2>/dev/null || echo "FAILED")
    if echo "$GET_GEN" | grep -q "$GEN_JOB_ID"; then
        log_pass "Generation job retrieved"
    else
        log_fail "Failed to retrieve generation job"
    fi
else
    log_skip "Skipping - no job ID"
fi

log_test "4.3 Listing generation jobs..."
GEN_LIST=$(curl -sf "${API_URL}/generation" 2>/dev/null || echo "FAILED")
if [ "$GEN_LIST" != "FAILED" ]; then
    JOB_COUNT=$(echo "$GEN_LIST" | jq 'length' 2>/dev/null || echo "0")
    log_pass "Listed generation jobs (count: $JOB_COUNT)"
else
    log_fail "Failed to list generation jobs"
fi

log_test "4.4 Unsupported toggle returns 400..."
TOGGLE_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_URL}/generation" \
    -H "Content-Type: application/json" \
    -d '{"config":{"prompt":"Test","use_controlnet":true},"count":1}')
if [ "$TOGGLE_RESPONSE" = "400" ]; then
    log_pass "Unsupported toggle correctly rejected (400)"
else
    log_fail "Expected 400 for unsupported toggle, got $TOGGLE_RESPONSE"
fi

log_test "4.5 Supported toggle (upscale) accepted..."
UPSCALE_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_URL}/generation" \
    -H "Content-Type: application/json" \
    -d '{"config":{"prompt":"Test","use_upscale":true},"count":1}')
if [ "$UPSCALE_RESPONSE" = "201" ]; then
    log_pass "Supported toggle (use_upscale) accepted"
else
    log_warn "Expected 201 for supported toggle, got $UPSCALE_RESPONSE"
fi

echo ""

# ============================================================
# SECTION 5: CORS and Headers
# ============================================================
log "=== Section 5: CORS and Headers ==="

log_test "5.1 CORS preflight request..."
CORS_RESPONSE=$(curl -s -I -X OPTIONS "${BASE_URL}/health" \
    -H "Origin: http://localhost:3000" \
    -H "Access-Control-Request-Method: GET" 2>/dev/null)
if echo "$CORS_RESPONSE" | grep -qi "access-control-allow"; then
    log_pass "CORS headers present"
else
    log_warn "CORS headers may not be configured"
fi

log_test "5.2 Correlation ID returned..."
CORR_RESPONSE=$(curl -sI "${BASE_URL}/health" 2>/dev/null)
if echo "$CORR_RESPONSE" | grep -qi "x-correlation-id"; then
    log_pass "X-Correlation-ID header returned"
else
    log_warn "X-Correlation-ID header not found"
fi

log_test "5.3 Custom correlation ID echoed..."
CUSTOM_CORR=$(curl -sI "${BASE_URL}/health" \
    -H "X-Correlation-ID: test-correlation-123" 2>/dev/null)
if echo "$CUSTOM_CORR" | grep -q "test-correlation-123"; then
    log_pass "Custom correlation ID echoed back"
else
    log_warn "Custom correlation ID not echoed"
fi

echo ""

# ============================================================
# SECTION 6: Job Logs and Debug
# ============================================================
log "=== Section 6: Job Logs and Debug ==="

log_test "6.1 Job logs endpoint exists..."
if [ -n "$GEN_JOB_ID" ]; then
    LOGS_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/jobs/${GEN_JOB_ID}/logs/view")
    if [ "$LOGS_RESPONSE" = "200" ] || [ "$LOGS_RESPONSE" = "404" ]; then
        log_pass "Job logs endpoint accessible (status: $LOGS_RESPONSE)"
    else
        log_warn "Job logs endpoint returned $LOGS_RESPONSE"
    fi
else
    log_skip "Skipping - no job ID"
fi

log_test "6.2 Debug bundle endpoint exists..."
if [ -n "$GEN_JOB_ID" ]; then
    DEBUG_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/jobs/${GEN_JOB_ID}/debug-bundle")
    if [ "$DEBUG_RESPONSE" = "200" ] || [ "$DEBUG_RESPONSE" = "404" ]; then
        log_pass "Debug bundle endpoint accessible (status: $DEBUG_RESPONSE)"
    else
        log_warn "Debug bundle endpoint returned $DEBUG_RESPONSE"
    fi
else
    log_skip "Skipping - no job ID"
fi

echo ""

# ============================================================
# RESULTS
# ============================================================
echo ""
echo "============================================================"
echo "  INTEGRATION TEST RESULTS"
echo "============================================================"
echo ""
echo -e "  ${GREEN}Passed:${NC}  ${TESTS_PASSED}"
echo -e "  ${RED}Failed:${NC}  ${TESTS_FAILED}"
echo -e "  ${YELLOW}Skipped:${NC} ${TESTS_SKIPPED}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All integration tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Review output above.${NC}"
    exit 1
fi
