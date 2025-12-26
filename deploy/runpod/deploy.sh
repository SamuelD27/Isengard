#!/bin/bash
# Isengard RunPod Deployment Script
#
# Deploy GPU worker pods to RunPod.
#
# Prerequisites:
#   - RunPod CLI installed: pip install runpodctl
#   - RUNPOD_API_KEY environment variable set
#   - Network volume created on RunPod
#
# Usage:
#   ./deploy.sh [create|update|delete|status]

set -e

# Configuration
POD_NAME="${POD_NAME:-isengard-worker-1}"
GPU_TYPE="${GPU_TYPE:-RTX_4090}"
GPU_COUNT="${GPU_COUNT:-1}"
IMAGE="${IMAGE:-ghcr.io/samueld27/isengard-worker-gpu:latest}"
VOLUME_SIZE="${VOLUME_SIZE:-100}"

# Required environment variables
: "${RUNPOD_API_KEY:?RUNPOD_API_KEY is required}"
: "${RUNPOD_VOLUME_ID:?RUNPOD_VOLUME_ID is required}"
: "${HF_TOKEN:?HF_TOKEN is required}"
: "${REDIS_URL:?REDIS_URL is required}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

create_pod() {
    log "Creating RunPod: $POD_NAME"
    log "GPU: $GPU_TYPE x $GPU_COUNT"
    log "Image: $IMAGE"
    log "Volume: $RUNPOD_VOLUME_ID"

    runpodctl create pod \
        --name "$POD_NAME" \
        --gpuType "$GPU_TYPE" \
        --gpuCount "$GPU_COUNT" \
        --imageName "$IMAGE" \
        --volumeId "$RUNPOD_VOLUME_ID" \
        --volumeMountPath "/runpod-volume" \
        --env "ISENGARD_MODE=production" \
        --env "VOLUME_ROOT=/runpod-volume/isengard" \
        --env "LOG_DIR=/runpod-volume/isengard/logs" \
        --env "LOG_LEVEL=INFO" \
        --env "HF_TOKEN=$HF_TOKEN" \
        --env "REDIS_URL=$REDIS_URL" \
        --env "COMFYUI_URL=http://localhost:8188" \
        --env "WORKER_NAME=$POD_NAME" \
        --ports "8000/http,8188/http"

    log "Pod creation initiated. Check status with: ./deploy.sh status"
}

delete_pod() {
    log "Deleting RunPod: $POD_NAME"
    runpodctl remove pod "$POD_NAME" || warn "Pod may not exist"
}

status() {
    log "Checking RunPod status..."
    runpodctl get pods | grep -E "^$POD_NAME|NAME" || warn "No pods found"
}

update_pod() {
    warn "Update requires delete + create cycle for RunPod"
    read -p "Delete and recreate pod? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        delete_pod
        sleep 5
        create_pod
    fi
}

logs() {
    POD_ID=$(runpodctl get pods -o json | jq -r ".[] | select(.name == \"$POD_NAME\") | .id")
    if [ -z "$POD_ID" ]; then
        error "Pod not found: $POD_NAME"
    fi
    log "Streaming logs for pod: $POD_ID"
    runpodctl logs "$POD_ID" -f
}

ssh_pod() {
    POD_ID=$(runpodctl get pods -o json | jq -r ".[] | select(.name == \"$POD_NAME\") | .id")
    if [ -z "$POD_ID" ]; then
        error "Pod not found: $POD_NAME"
    fi
    log "Connecting to pod: $POD_ID"
    runpodctl ssh "$POD_ID"
}

usage() {
    echo "Isengard RunPod Deployment"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  create    Create a new worker pod"
    echo "  delete    Delete the worker pod"
    echo "  update    Update pod (delete + create)"
    echo "  status    Check pod status"
    echo "  logs      Stream pod logs"
    echo "  ssh       SSH into pod"
    echo ""
    echo "Environment variables:"
    echo "  RUNPOD_API_KEY     RunPod API key (required)"
    echo "  RUNPOD_VOLUME_ID   RunPod network volume ID (required)"
    echo "  HF_TOKEN           HuggingFace token (required)"
    echo "  REDIS_URL          Redis connection URL (required)"
    echo "  POD_NAME           Pod name (default: isengard-worker-1)"
    echo "  GPU_TYPE           GPU type (default: RTX_4090)"
    echo "  IMAGE              Docker image (default: ghcr.io/samueld27/isengard-worker-gpu:latest)"
}

case "${1:-}" in
    create)
        create_pod
        ;;
    delete)
        delete_pod
        ;;
    update)
        update_pod
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    ssh)
        ssh_pod
        ;;
    *)
        usage
        exit 1
        ;;
esac
