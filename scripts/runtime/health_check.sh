#!/bin/bash
# health_check.sh - Health probe script for container orchestration
#
# Exit codes:
#   0 - All critical services healthy
#   1 - One or more critical services unhealthy
#
# Usage:
#   ./scripts/runtime/health_check.sh        # Check all services
#   ./scripts/runtime/health_check.sh api    # Check API only
#   ./scripts/runtime/health_check.sh comfyui # Check ComfyUI only

set -e

# Configuration
COMFYUI_HOST="${COMFYUI_HOST:-127.0.0.1}"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"

# Check mode
CHECK_MODE="${1:-all}"

check_api() {
    curl -sf "http://${API_HOST}:${API_PORT}/health" > /dev/null 2>&1
    return $?
}

check_comfyui() {
    curl -sf "http://${COMFYUI_HOST}:${COMFYUI_PORT}/system_stats" > /dev/null 2>&1
    return $?
}

check_redis() {
    redis-cli ping 2>/dev/null | grep -q PONG
    return $?
}

# Output as JSON for structured logging
output_status() {
    local api_status="unknown"
    local comfyui_status="unknown"
    local redis_status="unknown"
    local overall="healthy"

    if check_api; then
        api_status="healthy"
    else
        api_status="unhealthy"
        overall="unhealthy"
    fi

    if check_comfyui; then
        comfyui_status="healthy"
    else
        comfyui_status="unhealthy"
        # ComfyUI being down doesn't fail the whole container
        # but we note it as degraded
        [ "$overall" = "healthy" ] && overall="degraded"
    fi

    if check_redis; then
        redis_status="healthy"
    else
        redis_status="unhealthy"
        overall="unhealthy"
    fi

    echo "{\"status\": \"${overall}\", \"api\": \"${api_status}\", \"comfyui\": \"${comfyui_status}\", \"redis\": \"${redis_status}\"}"

    if [ "$overall" = "unhealthy" ]; then
        return 1
    fi
    return 0
}

case "$CHECK_MODE" in
    api)
        if check_api; then
            echo '{"status": "healthy", "service": "api"}'
            exit 0
        else
            echo '{"status": "unhealthy", "service": "api"}'
            exit 1
        fi
        ;;
    comfyui)
        if check_comfyui; then
            echo '{"status": "healthy", "service": "comfyui"}'
            exit 0
        else
            echo '{"status": "unhealthy", "service": "comfyui"}'
            exit 1
        fi
        ;;
    redis)
        if check_redis; then
            echo '{"status": "healthy", "service": "redis"}'
            exit 0
        else
            echo '{"status": "unhealthy", "service": "redis"}'
            exit 1
        fi
        ;;
    all|*)
        output_status
        exit $?
        ;;
esac
