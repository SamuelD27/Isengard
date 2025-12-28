#!/usr/bin/env bash
#
# Isengard E2E Test Runner
#
# Starts services, runs tests, collects logs, and reports results.
#
# Usage:
#   ./scripts/e2e.sh              # Full E2E test (starts docker, runs tests)
#   ./scripts/e2e.sh --api-only   # Only run API smoke tests (requires running API)
#   ./scripts/e2e.sh --browser    # Include Playwright browser tests
#
# Environment:
#   API_BASE_URL    - Override API URL (default: http://localhost:8000)
#   ISENGARD_MODE   - fast-test (default) or production
#   SKIP_CLEANUP    - Set to 1 to keep services running after tests
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
ISENGARD_MODE="${ISENGARD_MODE:-fast-test}"
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"
ARTIFACTS_DIR="$PROJECT_ROOT/artifacts/e2e/$TIMESTAMP"

# Parse arguments
API_ONLY=0
INCLUDE_BROWSER=0
for arg in "$@"; do
    case $arg in
        --api-only)
            API_ONLY=1
            ;;
        --browser)
            INCLUDE_BROWSER=1
            ;;
        --help)
            echo "Usage: $0 [--api-only] [--browser]"
            echo ""
            echo "Options:"
            echo "  --api-only    Only run API smoke tests (requires running API)"
            echo "  --browser     Include Playwright browser tests"
            echo ""
            echo "Environment:"
            echo "  API_BASE_URL  Override API URL (default: http://localhost:8000)"
            echo "  ISENGARD_MODE fast-test (default) or production"
            echo "  SKIP_CLEANUP  Set to 1 to keep services running after tests"
            exit 0
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create artifacts directory
mkdir -p "$ARTIFACTS_DIR"
log_info "Artifacts will be saved to: $ARTIFACTS_DIR"

# Function to check if API is ready
wait_for_api() {
    local max_attempts=30
    local attempt=1

    log_info "Waiting for API to be ready..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$API_BASE_URL/health" > /dev/null 2>&1; then
            log_info "API is ready!"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    log_error "API failed to start within timeout"
    return 1
}

# Function to start services
start_services() {
    log_info "Starting services with docker-compose..."
    cd "$PROJECT_ROOT"

    export ISENGARD_MODE
    docker-compose up -d api redis

    wait_for_api
}

# Function to stop services
stop_services() {
    if [ "$SKIP_CLEANUP" = "1" ]; then
        log_info "SKIP_CLEANUP=1, leaving services running"
        return 0
    fi

    log_info "Stopping services..."
    cd "$PROJECT_ROOT"
    docker-compose down --remove-orphans
}

# Function to collect logs
collect_logs() {
    log_info "Collecting logs..."
    "$SCRIPT_DIR/collect_logs.sh" "$ARTIFACTS_DIR" > /dev/null 2>&1 || true
}

# Function to run API smoke tests
run_api_tests() {
    log_info "Running API smoke tests..."
    cd "$PROJECT_ROOT"

    export API_BASE_URL

    # Run pytest with output capture
    if python -m pytest tests/test_e2e_smoke.py -v --tb=short \
        --junit-xml="$ARTIFACTS_DIR/api-test-results.xml" \
        2>&1 | tee "$ARTIFACTS_DIR/api-test-output.log"; then
        log_info "API tests PASSED"
        return 0
    else
        log_error "API tests FAILED"
        return 1
    fi
}

# Function to run Playwright browser tests
run_browser_tests() {
    if [ "$INCLUDE_BROWSER" != "1" ]; then
        log_info "Skipping browser tests (use --browser to include)"
        return 0
    fi

    log_info "Running Playwright browser tests..."
    cd "$PROJECT_ROOT/e2e"

    if [ ! -f "package.json" ]; then
        log_warn "Playwright tests not configured yet (e2e/package.json missing)"
        return 0
    fi

    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        npm install
        npx playwright install --with-deps chromium
    fi

    # Run tests
    if npx playwright test --reporter=html 2>&1 | tee "$ARTIFACTS_DIR/browser-test-output.log"; then
        log_info "Browser tests PASSED"
        # Copy report
        cp -r playwright-report "$ARTIFACTS_DIR/" 2>/dev/null || true
        return 0
    else
        log_error "Browser tests FAILED"
        return 1
    fi
}

# Main execution
main() {
    local exit_code=0

    echo ""
    echo "======================================"
    echo "  Isengard E2E Test Suite"
    echo "======================================"
    echo ""
    echo "Timestamp:    $TIMESTAMP"
    echo "API URL:      $API_BASE_URL"
    echo "Mode:         $ISENGARD_MODE"
    echo "Artifacts:    $ARTIFACTS_DIR"
    echo ""

    # Start services if not API-only mode
    if [ "$API_ONLY" != "1" ]; then
        start_services || exit 1
    else
        # Check if API is already running
        if ! curl -s "$API_BASE_URL/health" > /dev/null 2>&1; then
            log_error "API is not running at $API_BASE_URL"
            log_error "Start the API first or run without --api-only"
            exit 1
        fi
        log_info "Using existing API at $API_BASE_URL"
    fi

    # Run API tests
    run_api_tests || exit_code=1

    # Run browser tests
    run_browser_tests || exit_code=1

    # Collect logs
    collect_logs

    # Stop services
    if [ "$API_ONLY" != "1" ]; then
        stop_services
    fi

    # Summary
    echo ""
    echo "======================================"
    echo "  Test Results"
    echo "======================================"
    echo ""

    if [ $exit_code -eq 0 ]; then
        log_info "All tests PASSED"
    else
        log_error "Some tests FAILED"
    fi

    echo ""
    echo "Artifacts saved to: $ARTIFACTS_DIR"
    echo ""

    exit $exit_code
}

# Trap cleanup on error
cleanup_on_error() {
    log_error "Script interrupted or failed"
    collect_logs
    if [ "$API_ONLY" != "1" ]; then
        stop_services
    fi
}
trap cleanup_on_error ERR INT TERM

# Run main
main
