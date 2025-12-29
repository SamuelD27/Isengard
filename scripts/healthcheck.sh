#!/bin/bash
#
# Isengard Health Check Script
#
# Verifies all services are ready for E2E testing.
# Returns exit code 0 if all checks pass, non-zero otherwise.
#
# Usage:
#   ./scripts/healthcheck.sh              # Check all services
#   ./scripts/healthcheck.sh --wait       # Wait for services to be ready
#   ./scripts/healthcheck.sh --quick      # Skip worker check
#   ./scripts/healthcheck.sh --json       # Output JSON report
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

REDIS_URL="${REDIS_URL:-localhost:6379}"
API_URL="${E2E_API_URL:-http://localhost:8000}"
WEB_URL="${E2E_BASE_URL:-http://localhost:3000}"

# Parse arguments
WAIT_MODE=""
QUICK_MODE=""
JSON_MODE=""
TIMEOUT=60

while [[ $# -gt 0 ]]; do
  case $1 in
    --wait|-w)
      WAIT_MODE="1"
      shift
      ;;
    --quick|-q)
      QUICK_MODE="1"
      shift
      ;;
    --json|-j)
      JSON_MODE="1"
      shift
      ;;
    --timeout|-t)
      TIMEOUT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: ./scripts/healthcheck.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --wait, -w      Wait for services to become ready"
      echo "  --quick, -q     Skip worker check (faster)"
      echo "  --json, -j      Output JSON report"
      echo "  --timeout, -t   Timeout in seconds (default: 60)"
      echo ""
      echo "Environment:"
      echo "  E2E_API_URL     API URL (default: http://localhost:8000)"
      echo "  E2E_BASE_URL    Web URL (default: http://localhost:3000)"
      echo "  REDIS_URL       Redis URL (default: localhost:6379)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

log() {
  if [ -z "$JSON_MODE" ]; then
    echo -e "${GREEN}[health]${NC} $1"
  fi
}

warn() {
  if [ -z "$JSON_MODE" ]; then
    echo -e "${YELLOW}[health]${NC} $1"
  fi
}

error() {
  if [ -z "$JSON_MODE" ]; then
    echo -e "${RED}[health]${NC} $1"
  fi
}

check_pass() {
  if [ -z "$JSON_MODE" ]; then
    echo -e "  ${GREEN}✓${NC} $1"
  fi
}

check_fail() {
  if [ -z "$JSON_MODE" ]; then
    echo -e "  ${RED}✗${NC} $1"
  fi
}

# Results storage (POSIX-compatible, no associative arrays)
RESULT_REDIS="unknown"
RESULT_API="unknown"
RESULT_WEB="unknown"
RESULT_API_INFO="unknown"
RESULT_PROXY="unknown"
OVERALL_STATUS="pass"

# ============================================================
# CHECK FUNCTIONS
# ============================================================

check_redis() {
  local host="${REDIS_URL%%:*}"
  local port="${REDIS_URL#*:}"

  if nc -z "$host" "$port" 2>/dev/null; then
    RESULT_REDIS="pass"
    check_pass "Redis: $REDIS_URL"
    return 0
  else
    RESULT_REDIS="fail"
    OVERALL_STATUS="fail"
    check_fail "Redis: $REDIS_URL (not reachable)"
    return 1
  fi
}

check_api() {
  local response
  response=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/health" 2>/dev/null || echo "000")

  if [ "$response" = "200" ]; then
    # Verify JSON response
    local body
    body=$(curl -s "${API_URL}/health" 2>/dev/null || echo "{}")

    if echo "$body" | grep -q '"status"'; then
      RESULT_API="pass"
      check_pass "API: ${API_URL}/health (healthy)"
      return 0
    else
      RESULT_API="fail"
      OVERALL_STATUS="fail"
      check_fail "API: ${API_URL}/health (invalid JSON response)"
      return 1
    fi
  else
    RESULT_API="fail"
    OVERALL_STATUS="fail"
    check_fail "API: ${API_URL}/health (HTTP $response)"
    return 1
  fi
}

check_web() {
  local response
  response=$(curl -s -o /dev/null -w "%{http_code}" "${WEB_URL}/" 2>/dev/null || echo "000")

  if [ "$response" = "200" ]; then
    # Verify it's actually HTML/app content
    local body
    body=$(curl -s "${WEB_URL}/" 2>/dev/null | head -100)

    if echo "$body" | grep -q '<div id="root">\|<div id="app">\|<!DOCTYPE html>'; then
      RESULT_WEB="pass"
      check_pass "Web: ${WEB_URL} (serving app)"
      return 0
    else
      RESULT_WEB="warn"
      check_pass "Web: ${WEB_URL} (HTTP 200, but unclear if app)"
      return 0
    fi
  else
    RESULT_WEB="fail"
    OVERALL_STATUS="fail"
    check_fail "Web: ${WEB_URL} (HTTP $response)"
    return 1
  fi
}

check_api_info() {
  local response
  response=$(curl -s "${API_URL}/api/info" 2>/dev/null || echo "{}")

  if echo "$response" | grep -q '"name":"Isengard API"'; then
    RESULT_API_INFO="pass"
    local version
    version=$(echo "$response" | grep -o '"version":"[^"]*"' | head -1 | cut -d'"' -f4)
    check_pass "API Info: v${version:-unknown}"
    return 0
  else
    RESULT_API_INFO="warn"
    warn "  API Info: Could not verify (non-critical)"
    return 0
  fi
}

check_api_from_browser() {
  # This check verifies the proxy/CORS is working by checking if
  # the API is reachable from the web server's perspective
  local response
  response=$(curl -s -o /dev/null -w "%{http_code}" "${WEB_URL}/api/health" 2>/dev/null || echo "000")

  if [ "$response" = "200" ]; then
    RESULT_PROXY="pass"
    check_pass "Proxy: /api/health accessible from web"
    return 0
  else
    RESULT_PROXY="warn"
    warn "  Proxy: /api/health not accessible from web (may need Vite proxy)"
    return 0
  fi
}

# ============================================================
# WAIT MODE
# ============================================================

wait_for_services() {
  log "Waiting for services (timeout: ${TIMEOUT}s)..."

  local elapsed=0
  local interval=2

  while [ $elapsed -lt $TIMEOUT ]; do
    # Reset results
    OVERALL_STATUS="pass"
    RESULT_REDIS="unknown"
    RESULT_API="unknown"
    RESULT_WEB="unknown"

    # Run checks silently
    JSON_MODE="1"
    check_redis >/dev/null 2>&1 || true
    check_api >/dev/null 2>&1 || true
    check_web >/dev/null 2>&1 || true
    JSON_MODE=""

    if [ "$RESULT_REDIS" = "pass" ] && [ "$RESULT_API" = "pass" ] && [ "$RESULT_WEB" = "pass" ]; then
      log "All services ready!"
      return 0
    fi

    echo -n "."
    sleep $interval
    elapsed=$((elapsed + interval))
  done

  echo ""
  error "Timeout waiting for services"
  return 1
}

# ============================================================
# MAIN
# ============================================================

if [ -z "$JSON_MODE" ]; then
  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}                    ISENGARD HEALTH CHECK${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
  echo ""
fi

# Wait mode
if [ -n "$WAIT_MODE" ]; then
  wait_for_services
  WAIT_RESULT=$?
fi

# Run all checks
log "Checking services..."
echo ""

check_redis || true
check_api || true
check_web || true
check_api_info || true
check_api_from_browser || true

echo ""

# Output JSON if requested
if [ -n "$JSON_MODE" ]; then
  echo "{"
  echo "  \"status\": \"$OVERALL_STATUS\","
  echo "  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"checks\": {"
  echo "    \"redis\": \"$RESULT_REDIS\","
  echo "    \"api\": \"$RESULT_API\","
  echo "    \"web\": \"$RESULT_WEB\","
  echo "    \"api_info\": \"$RESULT_API_INFO\","
  echo "    \"proxy\": \"$RESULT_PROXY\""
  echo "  },"
  echo "  \"urls\": {"
  echo "    \"redis\": \"$REDIS_URL\","
  echo "    \"api\": \"$API_URL\","
  echo "    \"web\": \"$WEB_URL\""
  echo "  }"
  echo "}"
fi

# Summary
if [ -z "$JSON_MODE" ]; then
  if [ "$OVERALL_STATUS" = "pass" ]; then
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  All checks passed! Ready for E2E testing.${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
  else
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  Some checks failed. Fix issues before running E2E tests.${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "To start services: ./scripts/dev-up.sh"
    echo "To wait for ready: ./scripts/healthcheck.sh --wait"
  fi
fi

# Exit with appropriate code
if [ "$OVERALL_STATUS" = "pass" ]; then
  exit 0
else
  exit 1
fi
