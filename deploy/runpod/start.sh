#!/bin/bash
# Isengard RunPod Startup Script
#
# This script runs on pod startup to:
# 1. Configure SSH access
# 2. Download required models
# 3. Start all services (Redis, API, Worker, ComfyUI)
#
# Environment variables (set in RunPod template):
#   HF_TOKEN          - HuggingFace token for model downloads
#   VOLUME_ROOT       - Data storage path (default: /runpod-volume/isengard)
#   REDIS_URL         - Redis connection (default: redis://localhost:6379)
#   COMFYUI_URL       - ComfyUI endpoint (default: http://localhost:8188)
#   WORKER_NAME       - Worker identifier (default: runpod-worker-1)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; }
header() { echo -e "\n${BLUE}=== $1 ===${NC}\n"; }

# Default configuration
export VOLUME_ROOT="${VOLUME_ROOT:-/runpod-volume/isengard}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
export COMFYUI_URL="${COMFYUI_URL:-http://localhost:8188}"
export WORKER_NAME="${WORKER_NAME:-runpod-worker-1}"
export LOG_DIR="${VOLUME_ROOT}/logs"
export ISENGARD_MODE="${ISENGARD_MODE:-production}"

# Directories
MODELS_DIR="${VOLUME_ROOT}/models"
COMFYUI_MODELS="${VOLUME_ROOT}/comfyui/models"
HF_CACHE="${VOLUME_ROOT}/cache/huggingface"

# ============================================================
# 1. SSH CONFIGURATION
# ============================================================
header "Configuring SSH"

# Start SSH daemon if not running
if ! pgrep -x "sshd" > /dev/null; then
    log "Starting SSH daemon..."

    # Generate host keys if they don't exist
    if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
        ssh-keygen -A
    fi

    # Configure SSH
    cat > /etc/ssh/sshd_config << 'SSHCONFIG'
Port 22
PermitRootLogin yes
PasswordAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding yes
PrintMotd no
AcceptEnv LANG LC_*
Subsystem sftp /usr/lib/openssh/sftp-server
SSHCONFIG

    # Set root password if PUBLIC_KEY not provided
    if [ -z "$PUBLIC_KEY" ]; then
        # Generate random password and display it
        ROOT_PASSWORD=$(openssl rand -base64 12)
        echo "root:${ROOT_PASSWORD}" | chpasswd
        log "SSH root password: ${ROOT_PASSWORD}"
        log "Save this password! It won't be shown again."
    else
        # Add public key for key-based auth
        mkdir -p /root/.ssh
        echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys
        chmod 600 /root/.ssh/authorized_keys
        log "SSH public key configured"
    fi

    # Start SSH
    /usr/sbin/sshd
    log "SSH daemon started on port 22"
else
    log "SSH daemon already running"
fi

# ============================================================
# 2. CREATE DIRECTORIES
# ============================================================
header "Creating directories"

mkdir -p "${VOLUME_ROOT}"
mkdir -p "${MODELS_DIR}"
mkdir -p "${COMFYUI_MODELS}/checkpoints"
mkdir -p "${COMFYUI_MODELS}/loras"
mkdir -p "${COMFYUI_MODELS}/vae"
mkdir -p "${COMFYUI_MODELS}/clip"
mkdir -p "${HF_CACHE}"
mkdir -p "${LOG_DIR}/api"
mkdir -p "${LOG_DIR}/worker"
mkdir -p "${VOLUME_ROOT}/characters"
mkdir -p "${VOLUME_ROOT}/uploads"
mkdir -p "${VOLUME_ROOT}/outputs"
mkdir -p "${VOLUME_ROOT}/loras"

log "Directories created at ${VOLUME_ROOT}"

# ============================================================
# 3. DOWNLOAD MODELS
# ============================================================
header "Downloading Models"

# Check for HF token
if [ -z "$HF_TOKEN" ]; then
    error "HF_TOKEN not set! Cannot download gated models."
    error "Set HF_TOKEN in RunPod template environment variables."
else
    log "HF_TOKEN is set"
    export HF_HOME="${HF_CACHE}"
    export TRANSFORMERS_CACHE="${HF_CACHE}"

    # Install huggingface_hub if not present
    pip install -q huggingface_hub

    # Login to HuggingFace
    log "Logging into HuggingFace..."
    python3 -c "from huggingface_hub import login; login(token='${HF_TOKEN}')"

    # Download FLUX.1-dev (main model for LoRA training)
    FLUX_MODEL="black-forest-labs/FLUX.1-dev"
    FLUX_LOCAL="${COMFYUI_MODELS}/checkpoints/flux1-dev.safetensors"

    if [ ! -f "$FLUX_LOCAL" ]; then
        log "Downloading FLUX.1-dev model..."
        python3 << PYEOF
from huggingface_hub import hf_hub_download
import shutil

# Download the model
path = hf_hub_download(
    repo_id="black-forest-labs/FLUX.1-dev",
    filename="flux1-dev.safetensors",
    local_dir="${COMFYUI_MODELS}/checkpoints",
    local_dir_use_symlinks=False
)
print(f"Downloaded to: {path}")
PYEOF
        log "FLUX.1-dev downloaded"
    else
        log "FLUX.1-dev already exists"
    fi

    # Download FLUX.1-schnell (fast inference)
    SCHNELL_LOCAL="${COMFYUI_MODELS}/checkpoints/flux1-schnell.safetensors"

    if [ ! -f "$SCHNELL_LOCAL" ]; then
        log "Downloading FLUX.1-schnell model..."
        python3 << PYEOF
from huggingface_hub import hf_hub_download

path = hf_hub_download(
    repo_id="black-forest-labs/FLUX.1-schnell",
    filename="flux1-schnell.safetensors",
    local_dir="${COMFYUI_MODELS}/checkpoints",
    local_dir_use_symlinks=False
)
print(f"Downloaded to: {path}")
PYEOF
        log "FLUX.1-schnell downloaded"
    else
        log "FLUX.1-schnell already exists"
    fi

    # Download VAE
    VAE_LOCAL="${COMFYUI_MODELS}/vae/ae.safetensors"

    if [ ! -f "$VAE_LOCAL" ]; then
        log "Downloading FLUX VAE..."
        python3 << PYEOF
from huggingface_hub import hf_hub_download

path = hf_hub_download(
    repo_id="black-forest-labs/FLUX.1-dev",
    filename="ae.safetensors",
    local_dir="${COMFYUI_MODELS}/vae",
    local_dir_use_symlinks=False
)
print(f"Downloaded to: {path}")
PYEOF
        log "FLUX VAE downloaded"
    else
        log "FLUX VAE already exists"
    fi

    # Download CLIP models
    log "Downloading CLIP models..."
    python3 << PYEOF
from huggingface_hub import hf_hub_download
import os

clip_dir = "${COMFYUI_MODELS}/clip"

# CLIP-L
clip_l = os.path.join(clip_dir, "clip_l.safetensors")
if not os.path.exists(clip_l):
    hf_hub_download(
        repo_id="comfyanonymous/flux_text_encoders",
        filename="clip_l.safetensors",
        local_dir=clip_dir,
        local_dir_use_symlinks=False
    )
    print("Downloaded CLIP-L")

# T5-XXL
t5_xxl = os.path.join(clip_dir, "t5xxl_fp16.safetensors")
if not os.path.exists(t5_xxl):
    hf_hub_download(
        repo_id="comfyanonymous/flux_text_encoders",
        filename="t5xxl_fp16.safetensors",
        local_dir=clip_dir,
        local_dir_use_symlinks=False
    )
    print("Downloaded T5-XXL")
PYEOF
    log "CLIP models downloaded"
fi

# ============================================================
# 4. START REDIS
# ============================================================
header "Starting Redis"

if ! pgrep -x "redis-server" > /dev/null; then
    log "Starting Redis server..."
    redis-server --daemonize yes --port 6379
    sleep 2

    if redis-cli ping > /dev/null 2>&1; then
        log "Redis started successfully"
    else
        error "Failed to start Redis"
    fi
else
    log "Redis already running"
fi

# ============================================================
# 5. START COMFYUI
# ============================================================
header "Starting ComfyUI"

COMFYUI_DIR="/opt/ComfyUI"

if [ -d "$COMFYUI_DIR" ]; then
    if ! pgrep -f "main.py.*ComfyUI" > /dev/null; then
        log "Starting ComfyUI..."

        # Link models to ComfyUI
        ln -sf "${COMFYUI_MODELS}/checkpoints"/* "${COMFYUI_DIR}/models/checkpoints/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/loras"/* "${COMFYUI_DIR}/models/loras/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/vae"/* "${COMFYUI_DIR}/models/vae/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/clip"/* "${COMFYUI_DIR}/models/clip/" 2>/dev/null || true

        # Start ComfyUI in background
        cd "$COMFYUI_DIR"
        nohup python main.py --listen 0.0.0.0 --port 8188 > "${LOG_DIR}/comfyui.log" 2>&1 &

        # Wait for startup
        log "Waiting for ComfyUI to start..."
        for i in {1..30}; do
            if curl -s http://localhost:8188/system_stats > /dev/null 2>&1; then
                log "ComfyUI started successfully"
                break
            fi
            sleep 2
        done
    else
        log "ComfyUI already running"
    fi
else
    warn "ComfyUI not installed at ${COMFYUI_DIR}"
fi

# ============================================================
# 6. START ISENGARD API
# ============================================================
header "Starting Isengard API"

cd /app

if ! pgrep -f "uvicorn.*apps.api" > /dev/null; then
    log "Starting API server..."

    export PYTHONPATH=/app
    export USE_REDIS=true

    nohup uvicorn apps.api.src.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        > "${LOG_DIR}/api/startup.log" 2>&1 &

    # Wait for API
    log "Waiting for API to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            log "API started successfully"
            break
        fi
        sleep 1
    done
else
    log "API already running"
fi

# ============================================================
# 7. START WEB FRONTEND
# ============================================================
header "Starting Web Frontend"

WEB_DIR="/app/apps/web"

if [ -d "${WEB_DIR}/dist" ]; then
    if ! pgrep -f "serve.*3000" > /dev/null; then
        log "Starting web frontend..."

        # Install serve if not present
        npm install -g serve 2>/dev/null || true

        # Serve the built frontend
        nohup serve -s "${WEB_DIR}/dist" -l 3000 > "${LOG_DIR}/web.log" 2>&1 &

        sleep 2
        if curl -s http://localhost:3000 > /dev/null 2>&1; then
            log "Web frontend started on port 3000"
        else
            warn "Web frontend may not have started. Check ${LOG_DIR}/web.log"
        fi
    else
        log "Web frontend already running"
    fi
else
    warn "Web frontend not built. Run 'npm run build' in ${WEB_DIR}"
fi

# ============================================================
# 8. START ISENGARD WORKER
# ============================================================
header "Starting Isengard Worker"

if ! pgrep -f "apps.worker.src.main" > /dev/null; then
    log "Starting Worker..."

    export PYTHONPATH=/app
    export USE_REDIS=true

    nohup python -m apps.worker.src.main \
        > "${LOG_DIR}/worker/startup.log" 2>&1 &

    sleep 3

    if pgrep -f "apps.worker.src.main" > /dev/null; then
        log "Worker started successfully"
    else
        error "Worker failed to start. Check ${LOG_DIR}/worker/startup.log"
    fi
else
    log "Worker already running"
fi

# ============================================================
# 9. FINAL STATUS
# ============================================================
header "Startup Complete"

echo ""
log "Services Status:"
echo "  - SSH:     $(pgrep -x sshd > /dev/null && echo '✓ Running on port 22' || echo '✗ Not running')"
echo "  - Redis:   $(redis-cli ping 2>/dev/null | grep -q PONG && echo '✓ Running on port 6379' || echo '✗ Not running')"
echo "  - ComfyUI: $(curl -s http://localhost:8188/system_stats > /dev/null 2>&1 && echo '✓ Running on port 8188' || echo '✗ Not running')"
echo "  - API:     $(curl -s http://localhost:8000/health > /dev/null 2>&1 && echo '✓ Running on port 8000' || echo '✗ Not running')"
echo "  - Web GUI: $(curl -s http://localhost:3000 > /dev/null 2>&1 && echo '✓ Running on port 3000' || echo '✗ Not running')"
echo "  - Worker:  $(pgrep -f 'apps.worker.src.main' > /dev/null && echo '✓ Running' || echo '✗ Not running')"
echo ""
log "Models:"
echo "  - FLUX.1-dev:     $([ -f '${COMFYUI_MODELS}/checkpoints/flux1-dev.safetensors' ] && echo '✓ Downloaded' || echo '✗ Missing')"
echo "  - FLUX.1-schnell: $([ -f '${COMFYUI_MODELS}/checkpoints/flux1-schnell.safetensors' ] && echo '✓ Downloaded' || echo '✗ Missing')"
echo ""
log "Access:"
echo "  - Web GUI: http://\$(hostname -I | awk '{print \$1}'):3000"
echo "  - API:     http://\$(hostname -I | awk '{print \$1}'):8000"
echo "  - ComfyUI: http://\$(hostname -I | awk '{print \$1}'):8188"
echo "  - SSH:     ssh root@\$(hostname -I | awk '{print \$1}')"
echo ""
log "Logs: ${LOG_DIR}/"
echo ""

# Keep container running
log "Startup complete. Container will keep running..."
tail -f /dev/null
