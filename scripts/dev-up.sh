#!/bin/bash
#
# Isengard Dev Environment Starter
#
# Usage:
#   ./scripts/dev-up.sh              # Start all services in background
#   ./scripts/dev-up.sh --foreground # Start with logs attached
#   ./scripts/dev-up.sh --clean      # Clean volumes and restart fresh
#   ./scripts/dev-up.sh --no-worker  # Start without worker (for fast E2E)
#   ./scripts/dev-up.sh --native     # Start services natively (no Docker)
#
# Services:
#   - Redis:  localhost:6379
#   - API:    localhost:8000
#   - Web:    localhost:3000
#   - Worker: (optional, for training jobs)
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[dev-up]${NC} $1"; }
warn() { echo -e "${YELLOW}[dev-up]${NC} $1"; }
error() { echo -e "${RED}[dev-up]${NC} $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Parse arguments
FOREGROUND=""
CLEAN=""
NO_WORKER=""
NATIVE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --foreground|-f)
      FOREGROUND="1"
      shift
      ;;
    --clean|-c)
      CLEAN="1"
      shift
      ;;
    --no-worker)
      NO_WORKER="1"
      shift
      ;;
    --native|-n)
      NATIVE="1"
      shift
      ;;
    -h|--help)
      echo "Usage: ./scripts/dev-up.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --foreground, -f   Attach to logs (don't run in background)"
      echo "  --clean, -c        Remove volumes and start fresh"
      echo "  --no-worker        Skip worker service (faster for UI testing)"
      echo "  --native, -n       Run services natively (no Docker)"
      echo ""
      echo "Services started:"
      echo "  Redis:  localhost:6379"
      echo "  API:    localhost:8000"
      echo "  Web:    localhost:3000"
      echo "  Worker: (unless --no-worker)"
      exit 0
      ;;
    *)
      error "Unknown option: $1"
      exit 1
      ;;
  esac
done

cd "$PROJECT_ROOT"

# Banner
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}          ${GREEN}Isengard Dev Environment${NC}                           ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# NATIVE MODE (no Docker)
# ============================================================
if [ -n "$NATIVE" ]; then
  log "Starting services natively (no Docker)..."

  # Check for Redis
  if ! command -v redis-server &> /dev/null; then
    error "redis-server not found. Install with: brew install redis"
    exit 1
  fi

  # Check for Python/uvicorn
  if ! command -v uvicorn &> /dev/null; then
    error "uvicorn not found. Install with: pip install uvicorn"
    exit 1
  fi

  # Check for Node
  if ! command -v node &> /dev/null; then
    error "node not found. Install Node.js 18+"
    exit 1
  fi

  # Create PID directory
  mkdir -p "$PROJECT_ROOT/.pids"

  # Start Redis
  log "Starting Redis..."
  if ! pgrep -x redis-server > /dev/null; then
    redis-server --daemonize yes --pidfile "$PROJECT_ROOT/.pids/redis.pid"
    log "Redis started"
  else
    log "Redis already running"
  fi

  # Start API
  log "Starting API..."
  cd "$PROJECT_ROOT/apps/api"
  ISENGARD_MODE=fast-test REDIS_URL=redis://localhost:6379 \
    uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload &
  echo $! > "$PROJECT_ROOT/.pids/api.pid"
  cd "$PROJECT_ROOT"

  # Start Web
  log "Starting Web..."
  cd "$PROJECT_ROOT/apps/web"
  npm install --silent 2>/dev/null || true
  VITE_API_URL=http://localhost:8000 npm run dev -- --host --port 3000 &
  echo $! > "$PROJECT_ROOT/.pids/web.pid"
  cd "$PROJECT_ROOT"

  log "Services starting in background..."
  log "Run './scripts/healthcheck.sh' to verify readiness"
  log "Run './scripts/dev-down.sh --native' to stop"
  exit 0
fi

# ============================================================
# DOCKER MODE
# ============================================================

# Check Docker
if ! command -v docker &> /dev/null; then
  error "Docker is not installed"
  exit 1
fi

if ! docker info &> /dev/null 2>&1; then
  error "Docker daemon is not running"
  exit 1
fi

log "Docker: $(docker --version | head -1)"

# Clean if requested
if [ -n "$CLEAN" ]; then
  log "Cleaning volumes and containers..."
  docker-compose -f docker-compose.yaml down -v --remove-orphans 2>/dev/null || true
  rm -rf "$PROJECT_ROOT/data" 2>/dev/null || true
  mkdir -p "$PROJECT_ROOT/data"
  log "Clean complete"
fi

# Build services list
SERVICES="redis api web"
if [ -z "$NO_WORKER" ]; then
  SERVICES="$SERVICES worker"
fi

# Set environment
export ISENGARD_MODE="${ISENGARD_MODE:-fast-test}"
export VOLUME_ROOT="${VOLUME_ROOT:-./data}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

log "Mode: $ISENGARD_MODE"
log "Services: $SERVICES"

# Start services
if [ -n "$FOREGROUND" ]; then
  log "Starting services (foreground)..."
  docker-compose -f docker-compose.yaml up $SERVICES
else
  log "Starting services (background)..."
  docker-compose -f docker-compose.yaml up -d $SERVICES

  echo ""
  log "Services starting in background"
  log "Ports:"
  echo "  - Redis:  localhost:6379"
  echo "  - API:    localhost:8000"
  echo "  - Web:    localhost:3000"
  if [ -z "$NO_WORKER" ]; then
    echo "  - Worker: (background)"
  fi
  echo ""
  log "Run './scripts/healthcheck.sh' to verify readiness"
  log "Run './scripts/dev-down.sh' to stop"
  log "Run 'docker-compose logs -f' to view logs"
fi
