#!/bin/bash
###############################################################################
# Quick Service Restart Script
# Usage: ./restart_services.sh [api|worker|comfyui|web|all]
###############################################################################

set -e

VOLUME_ROOT="/runpod-volume/isengard"
APP_ROOT="/app"
COMFYUI_ROOT="/opt/ComfyUI"
LOGS_DIR="${VOLUME_ROOT}/logs"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load secrets
source /secrets.sh 2>/dev/null || true

# Set environment
export PYTHONPATH="${APP_ROOT}"
export HF_HOME="${VOLUME_ROOT}/.cache/huggingface"
export DATA_DIR="${VOLUME_ROOT}"
export COMFYUI_URL="http://localhost:8188"
export REDIS_URL="redis://localhost:6379"
export PYTHONUNBUFFERED=1

restart_api() {
    log_info "Restarting API..."
    pkill -f "uvicorn.*8000" 2>/dev/null || true
    sleep 1
    cd "${APP_ROOT}"
    nohup python -m uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 \
        > "${LOGS_DIR}/api/api.log" 2>&1 &
    sleep 2
    curl -sf http://localhost:8000/health > /dev/null && log_success "API restarted" || log_error "API failed"
}

restart_worker() {
    log_info "Restarting Worker..."
    pkill -f "apps.worker" 2>/dev/null || true
    sleep 1
    cd "${APP_ROOT}"
    nohup python -m apps.worker.src.main \
        > "${LOGS_DIR}/worker/worker.log" 2>&1 &
    sleep 2
    pgrep -f "apps.worker" > /dev/null && log_success "Worker restarted" || log_error "Worker failed"
}

restart_comfyui() {
    log_info "Restarting ComfyUI..."
    pkill -f "python.*ComfyUI" 2>/dev/null || true
    pkill -f "main.py.*8188" 2>/dev/null || true
    sleep 2
    cd "${COMFYUI_ROOT}"
    nohup python main.py --listen 0.0.0.0 --port 8188 \
        > "${LOGS_DIR}/comfyui/comfyui.log" 2>&1 &
    sleep 5
    curl -sf http://localhost:8188 > /dev/null && log_success "ComfyUI restarted" || log_error "ComfyUI failed"
}

restart_web() {
    log_info "Restarting Web..."
    pkill -f "node.*vite" 2>/dev/null || true
    pkill -f "npm.*dev" 2>/dev/null || true
    sleep 1
    cd "${APP_ROOT}/apps/web"
    nohup npm run dev -- --host 0.0.0.0 --port 3000 \
        > "${LOGS_DIR}/web/web.log" 2>&1 &
    sleep 3
    curl -sf http://localhost:3000 > /dev/null && log_success "Web restarted" || log_error "Web failed"
}

case "${1:-all}" in
    api)
        restart_api
        ;;
    worker)
        restart_worker
        ;;
    comfyui)
        restart_comfyui
        ;;
    web)
        restart_web
        ;;
    all)
        restart_comfyui
        restart_api
        restart_worker
        restart_web
        ;;
    *)
        echo "Usage: $0 [api|worker|comfyui|web|all]"
        exit 1
        ;;
esac

echo ""
echo "Service status:"
ss -tlnp | grep -E "8188|8000|3000|6379" | awk '{print "  " $4 " " $6}'
