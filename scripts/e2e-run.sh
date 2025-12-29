#!/bin/bash
#
# Isengard E2E Test Runner
#
# This script boots the full app stack and runs E2E tests locally.
# It's the single command to validate the GUI before deployment.
#
# Usage:
#   ./scripts/e2e-run.sh              # Run all tests headless
#   ./scripts/e2e-run.sh --headed     # Run with visible browser
#   ./scripts/e2e-run.sh --smoke      # Quick smoke tests only
#   ./scripts/e2e-run.sh --training   # Training GUI tests only
#   ./scripts/e2e-run.sh --visual     # Visual regression tests only
#   ./scripts/e2e-run.sh --quick      # Smoke + training tests (fast validation)
#   ./scripts/e2e-run.sh --ui         # Interactive Playwright UI
#   ./scripts/e2e-run.sh --debug      # Debug mode with inspector
#   ./scripts/e2e-run.sh --file <spec> # Run specific test file
#   ./scripts/e2e-run.sh --update-snapshots  # Update visual baselines
#
# Prerequisites:
#   - Node.js 18+
#   - Docker and Docker Compose
#   - Port 3000 and 8000 available
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[E2E]${NC} $1"; }
warn() { echo -e "${YELLOW}[E2E]${NC} $1"; }
error() { echo -e "${RED}[E2E]${NC} $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
E2E_DIR="${PROJECT_ROOT}/e2e"
ARTIFACTS_DIR="${E2E_DIR}/artifacts"

# Parse arguments
HEADED=""
SMOKE=""
TRAINING=""
VISUAL=""
QUICK=""
UPDATE_SNAPSHOTS=""
UI=""
DEBUG=""
SPEC_FILE=""
SKIP_SERVICES=""
PROJECT="chromium-desktop"

while [[ $# -gt 0 ]]; do
  case $1 in
    --headed)
      HEADED="1"
      shift
      ;;
    --smoke)
      SMOKE="1"
      shift
      ;;
    --training)
      TRAINING="1"
      shift
      ;;
    --visual)
      VISUAL="1"
      shift
      ;;
    --quick)
      QUICK="1"
      shift
      ;;
    --update-snapshots)
      UPDATE_SNAPSHOTS="1"
      shift
      ;;
    --ui)
      UI="1"
      shift
      ;;
    --debug)
      DEBUG="1"
      shift
      ;;
    --file)
      SPEC_FILE="$2"
      shift 2
      ;;
    --skip-services)
      SKIP_SERVICES="1"
      shift
      ;;
    --project)
      PROJECT="$2"
      shift 2
      ;;
    --all-browsers)
      PROJECT="chromium-desktop --project=firefox-desktop --project=webkit-desktop"
      shift
      ;;
    *)
      error "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Banner
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}          ${GREEN}Isengard E2E Test Runner${NC}                           ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# 1. ENVIRONMENT INFO
# ============================================================
log "Environment:"
echo "  Working directory: $(pwd)"
echo "  Project root: ${PROJECT_ROOT}"
echo "  E2E directory: ${E2E_DIR}"
echo "  Artifacts directory: ${ARTIFACTS_DIR}"
echo "  Node version: $(node -v)"
echo "  Playwright version: $(cd "${E2E_DIR}" && npx playwright --version 2>/dev/null || echo "not installed")"
echo ""

# ============================================================
# 2. CHECK PREREQUISITES
# ============================================================
log "Checking prerequisites..."

# Check Node.js
if ! command -v node &> /dev/null; then
  error "Node.js is not installed"
  exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
  error "Node.js 18+ required (found v$NODE_VERSION)"
  exit 1
fi
log "Node.js: $(node -v) ✓"

# Check npm
if ! command -v npm &> /dev/null; then
  error "npm is not installed"
  exit 1
fi

# ============================================================
# 3. PREPARE ARTIFACT DIRECTORIES
# ============================================================
log "Preparing artifact directories..."

mkdir -p "${ARTIFACTS_DIR}/screenshots"
mkdir -p "${ARTIFACTS_DIR}/videos"
mkdir -p "${ARTIFACTS_DIR}/traces"
mkdir -p "${ARTIFACTS_DIR}/reports"
mkdir -p "${ARTIFACTS_DIR}/har"
mkdir -p "${ARTIFACTS_DIR}/test-results"

echo "  Created: ${ARTIFACTS_DIR}/"

# ============================================================
# 4. INSTALL E2E DEPENDENCIES
# ============================================================
log "Installing E2E dependencies..."

cd "$E2E_DIR"

if [ ! -d "node_modules" ]; then
  npm install
  npx playwright install --with-deps chromium
else
  log "Dependencies already installed ✓"
fi

# ============================================================
# 5. START SERVICES (if not skipped)
# ============================================================
if [ -z "$SKIP_SERVICES" ]; then
  log "Starting services..."

  cd "$PROJECT_ROOT"

  # Check if services are already running
  API_RUNNING=$(curl -s http://localhost:8000/health 2>/dev/null | grep -c "healthy" || echo "0")
  WEB_RUNNING=$(curl -s http://localhost:3000 2>/dev/null | grep -c "html" || echo "0")

  if [ "$API_RUNNING" = "1" ] && [ "$WEB_RUNNING" = "1" ]; then
    log "Services already running ✓"
  else
    # Start with docker-compose
    if command -v docker-compose &> /dev/null; then
      log "Starting services with docker-compose..."
      docker-compose up -d redis api web 2>/dev/null || {
        warn "docker-compose failed, trying manual start..."
      }
    fi

    # Wait for services
    log "Waiting for services to be ready..."
    TIMEOUT=60
    ELAPSED=0

    while [ $ELAPSED -lt $TIMEOUT ]; do
      API_READY=$(curl -s http://localhost:8000/health 2>/dev/null | grep -c "healthy" || echo "0")
      WEB_READY=$(curl -s http://localhost:3000 2>/dev/null | grep -c "" || echo "0")

      if [ "$API_READY" = "1" ] && [ "$WEB_READY" -gt "0" ]; then
        log "Services ready! ✓"
        break
      fi

      sleep 2
      ELAPSED=$((ELAPSED + 2))
      echo -n "."
    done

    if [ $ELAPSED -ge $TIMEOUT ]; then
      error "Services did not start within ${TIMEOUT}s"
      echo ""
      echo "Please start services manually:"
      echo "  docker-compose up -d"
      echo "  # or"
      echo "  cd apps/api && uvicorn src.main:app --reload --port 8000"
      echo "  cd apps/web && npm run dev"
      exit 1
    fi
  fi
else
  log "Skipping service start (--skip-services)"
fi

# ============================================================
# 6. RUN TESTS
# ============================================================
log "Running E2E tests..."

cd "$E2E_DIR"

# Build Playwright command
PW_CMD="npx playwright test"

# Add project
PW_CMD="$PW_CMD --project=$PROJECT"

# Add options
if [ -n "$HEADED" ]; then
  export HEADED=1
fi

if [ -n "$SMOKE" ]; then
  PW_CMD="$PW_CMD --grep @smoke"
fi

if [ -n "$TRAINING" ]; then
  PW_CMD="$PW_CMD tests/training-gui.spec.ts"
fi

if [ -n "$VISUAL" ]; then
  PW_CMD="$PW_CMD tests/visual/"
fi

if [ -n "$QUICK" ]; then
  PW_CMD="$PW_CMD tests/smoke/ tests/training-gui.spec.ts"
fi

if [ -n "$UPDATE_SNAPSHOTS" ]; then
  PW_CMD="$PW_CMD --update-snapshots tests/visual/"
fi

if [ -n "$UI" ]; then
  PW_CMD="npx playwright test --ui"
fi

if [ -n "$DEBUG" ]; then
  export PWDEBUG=1
fi

if [ -n "$SPEC_FILE" ]; then
  PW_CMD="$PW_CMD $SPEC_FILE"
fi

# Set environment
export E2E_BASE_URL="http://localhost:3000"
export E2E_API_URL="http://localhost:8000"
export E2E_SKIP_SERVER=1

log "Running: $PW_CMD"
echo ""

# Run tests (allow failure, we'll check exit code)
set +e
$PW_CMD
TEST_EXIT_CODE=$?
set -e

# ============================================================
# 7. ARTIFACT VERIFICATION
# ============================================================
echo ""
log "Test run complete (exit code: $TEST_EXIT_CODE)"

# Check for artifacts
ARTIFACT_COUNT=0
SCREENSHOT_COUNT=0
VIDEO_COUNT=0
TRACE_COUNT=0

if [ -d "${ARTIFACTS_DIR}/test-results" ]; then
  SCREENSHOT_COUNT=$(find "${ARTIFACTS_DIR}/test-results" -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
  VIDEO_COUNT=$(find "${ARTIFACTS_DIR}/test-results" -name "*.webm" 2>/dev/null | wc -l | tr -d ' ')
  TRACE_COUNT=$(find "${ARTIFACTS_DIR}/test-results" -name "trace.zip" 2>/dev/null | wc -l | tr -d ' ')
  ARTIFACT_COUNT=$((SCREENSHOT_COUNT + VIDEO_COUNT + TRACE_COUNT))
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    ARTIFACT SUMMARY${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Screenshots: ${SCREENSHOT_COUNT}"
echo "  Videos:      ${VIDEO_COUNT}"
echo "  Traces:      ${TRACE_COUNT}"
echo "  Total:       ${ARTIFACT_COUNT}"
echo ""

# Show actual artifact paths
if [ "$ARTIFACT_COUNT" -gt 0 ]; then
  echo "  Artifact locations:"
  find "${ARTIFACTS_DIR}/test-results" -type f \( -name "*.png" -o -name "*.webm" -o -name "trace.zip" \) 2>/dev/null | head -10 | while read -r f; do
    echo "    - $f"
  done
  echo ""
fi

# Check for failure report
if [ -f "${ARTIFACTS_DIR}/reports/FAILURE_REPORT.txt" ]; then
  echo ""
  echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${RED}                    FAILURE REPORT${NC}"
  echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
  cat "${ARTIFACTS_DIR}/reports/FAILURE_REPORT.txt"
fi

# Verify artifacts exist on failure
if [ "$TEST_EXIT_CODE" -ne 0 ]; then
  if [ "$ARTIFACT_COUNT" -eq 0 ]; then
    echo ""
    error "╔════════════════════════════════════════════════════════════════════╗"
    error "║  CRITICAL: Tests failed but NO ARTIFACTS were generated!          ║"
    error "║  This indicates a configuration problem with Playwright.          ║"
    error "║                                                                    ║"
    error "║  Check:                                                            ║"
    error "║    1. playwright.config.ts outputDir setting                       ║"
    error "║    2. screenshot/video/trace settings in use block                 ║"
    error "║    3. Directory permissions for ${ARTIFACTS_DIR}  ║"
    error "╚════════════════════════════════════════════════════════════════════╝"
    echo ""
  fi
fi

# Show how to view reports
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    VIEW RESULTS${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "  HTML Report:     cd e2e && npx playwright show-report"
echo "  View Trace:      npx playwright show-trace <path-to-trace.zip>"
echo "  Failure Report:  cat ${ARTIFACTS_DIR}/reports/FAILURE_REPORT.txt"
echo ""

# ============================================================
# 8. EXIT
# ============================================================
exit $TEST_EXIT_CODE
