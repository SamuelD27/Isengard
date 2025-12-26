#!/bin/bash
# Development helper script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[Isengard]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[Warning]${NC} $1"
}

error() {
    echo -e "${RED}[Error]${NC} $1"
}

# Check Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        exit 1
    fi
    if ! docker info &> /dev/null; then
        error "Docker daemon is not running"
        exit 1
    fi
}

# Start all services
start() {
    check_docker
    log "Starting Isengard services..."
    docker-compose up "$@"
}

# Stop all services
stop() {
    log "Stopping Isengard services..."
    docker-compose down
}

# Build all images
build() {
    log "Building Isengard images..."
    docker-compose build "$@"
}

# View logs
logs() {
    docker-compose logs -f "$@"
}

# Run tests
test_api() {
    log "Running API tests..."
    docker-compose exec api pytest
}

# Format code
format() {
    log "Formatting Python code..."
    docker-compose exec api ruff format .

    log "Formatting TypeScript code..."
    docker-compose exec web npm run format
}

# Lint code
lint() {
    log "Linting Python code..."
    docker-compose exec api ruff check .

    log "Linting TypeScript code..."
    docker-compose exec web npm run lint
}

# Shell into a service
shell() {
    local service=${1:-api}
    log "Opening shell in $service..."
    docker-compose exec "$service" /bin/sh
}

# View health status
health() {
    log "Checking service health..."
    curl -s http://localhost:8000/health | python -m json.tool
    echo
    curl -s http://localhost:8000/info | python -m json.tool
}

# Help
usage() {
    echo "Isengard Development Helper"
    echo
    echo "Usage: ./scripts/dev.sh <command> [options]"
    echo
    echo "Commands:"
    echo "  start       Start all services (pass -d for background)"
    echo "  stop        Stop all services"
    echo "  build       Build Docker images"
    echo "  logs        View service logs (pass service name to filter)"
    echo "  test        Run API tests"
    echo "  format      Format all code"
    echo "  lint        Lint all code"
    echo "  shell       Open shell in a service (default: api)"
    echo "  health      Check service health"
    echo
    echo "Examples:"
    echo "  ./scripts/dev.sh start"
    echo "  ./scripts/dev.sh start -d"
    echo "  ./scripts/dev.sh logs api"
    echo "  ./scripts/dev.sh shell worker"
}

# Main
case "$1" in
    start)
        shift
        start "$@"
        ;;
    stop)
        stop
        ;;
    build)
        shift
        build "$@"
        ;;
    logs)
        shift
        logs "$@"
        ;;
    test)
        test_api
        ;;
    format)
        format
        ;;
    lint)
        lint
        ;;
    shell)
        shift
        shell "$@"
        ;;
    health)
        health
        ;;
    *)
        usage
        ;;
esac
