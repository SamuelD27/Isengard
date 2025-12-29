#!/bin/bash
#
# Isengard Dev Environment Stopper
#
# Usage:
#   ./scripts/dev-down.sh              # Stop all services
#   ./scripts/dev-down.sh --clean      # Stop and remove volumes
#   ./scripts/dev-down.sh --native     # Stop native services (non-Docker)
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[dev-down]${NC} $1"; }
warn() { echo -e "${YELLOW}[dev-down]${NC} $1"; }
error() { echo -e "${RED}[dev-down]${NC} $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Parse arguments
CLEAN=""
NATIVE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --clean|-c)
      CLEAN="1"
      shift
      ;;
    --native|-n)
      NATIVE="1"
      shift
      ;;
    -h|--help)
      echo "Usage: ./scripts/dev-down.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --clean, -c   Remove volumes and data"
      echo "  --native, -n  Stop native services (non-Docker)"
      exit 0
      ;;
    *)
      error "Unknown option: $1"
      exit 1
      ;;
  esac
done

cd "$PROJECT_ROOT"

# ============================================================
# NATIVE MODE
# ============================================================
if [ -n "$NATIVE" ]; then
  log "Stopping native services..."

  # Stop processes by PID files
  for pidfile in "$PROJECT_ROOT/.pids/"*.pid; do
    if [ -f "$pidfile" ]; then
      pid=$(cat "$pidfile")
      if kill -0 "$pid" 2>/dev/null; then
        log "Stopping PID $pid..."
        kill "$pid" 2>/dev/null || true
      fi
      rm -f "$pidfile"
    fi
  done

  # Stop Redis if we started it
  if pgrep -x redis-server > /dev/null; then
    log "Stopping Redis..."
    pkill redis-server || true
  fi

  # Kill any stray uvicorn/node processes for our ports
  log "Cleaning up port 8000..."
  lsof -ti:8000 | xargs kill -9 2>/dev/null || true

  log "Cleaning up port 3000..."
  lsof -ti:3000 | xargs kill -9 2>/dev/null || true

  log "Native services stopped"
  exit 0
fi

# ============================================================
# DOCKER MODE
# ============================================================

if ! command -v docker &> /dev/null; then
  error "Docker is not installed"
  exit 1
fi

log "Stopping Docker services..."

if [ -n "$CLEAN" ]; then
  log "Removing volumes and cleaning up..."
  docker-compose -f docker-compose.yaml down -v --remove-orphans 2>/dev/null || true
  rm -rf "$PROJECT_ROOT/data" 2>/dev/null || true
else
  docker-compose -f docker-compose.yaml down 2>/dev/null || true
fi

log "Services stopped"

# Show any remaining containers
REMAINING=$(docker ps --filter "label=com.docker.compose.project=isengard" -q 2>/dev/null | wc -l | tr -d ' ')
if [ "$REMAINING" -gt 0 ]; then
  warn "Found $REMAINING lingering containers. Run with --clean to remove."
fi
