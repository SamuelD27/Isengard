#!/bin/bash
# Isengard RunPod Startup Script
#
# This script runs on pod startup to:
# 1. Configure SSH access
# 2. Download required models (R2 first, fallback to HuggingFace)
# 3. Start all services (Redis, API, Worker, ComfyUI)

set -e

# Trap to prevent script from exiting on arithmetic with zero
# This is needed because ((var++)) returns 1 when var is 0

# ============================================================
# LOAD SECRETS (from bundled secrets file)
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/secrets.sh" ]; then
    source "${SCRIPT_DIR}/secrets.sh"
elif [ -f "/secrets.sh" ]; then
    source "/secrets.sh"
fi

# Fallback defaults (will be empty if secrets not loaded)
export HF_TOKEN="${HF_TOKEN:-}"
R2_ACCESS_KEY="${R2_ACCESS_KEY:-}"
R2_SECRET_KEY="${R2_SECRET_KEY:-}"
R2_ENDPOINT="${R2_ENDPOINT:-https://e6b3925ef3896465b73c442be466db90.r2.cloudflarestorage.com}"
R2_BUCKET="${R2_BUCKET:-isengard-models}"

# ============================================================
# Configuration
# ============================================================
export VOLUME_ROOT="${VOLUME_ROOT:-/runpod-volume/isengard}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
export COMFYUI_URL="${COMFYUI_URL:-http://localhost:8188}"
export WORKER_NAME="${WORKER_NAME:-runpod-worker-1}"
export LOG_DIR="${VOLUME_ROOT}/logs"
export ISENGARD_MODE="${ISENGARD_MODE:-production}"

MODELS_DIR="${VOLUME_ROOT}/models"
COMFYUI_MODELS="${VOLUME_ROOT}/comfyui/models"
HF_CACHE="${VOLUME_ROOT}/cache/huggingface"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; }
header() { echo -e "\n${BLUE}=== $1 ===${NC}\n"; }

# ============================================================
# STARTUP BANNER
# ============================================================
SCRIPT_VERSION="v2.2.2-loop-fix"
BUILD_DATE="2025-12-30"

# Generate SHA256 of this script for verification
SCRIPT_SHA=$(sha256sum /start.sh 2>/dev/null | cut -c1-12 || echo "unknown")

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}                                                            ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   ${GREEN}██╗███████╗███████╗███╗   ██╗ ██████╗  █████╗ ██████╗ ██████╗${NC}  ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   ${GREEN}██║██╔════╝██╔════╝████╗  ██║██╔════╝ ██╔══██╗██╔══██╗██╔══██╗${NC} ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   ${GREEN}██║███████╗█████╗  ██╔██╗ ██║██║  ███╗███████║██████╔╝██║  ██║${NC} ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   ${GREEN}██║╚════██║██╔══╝  ██║╚██╗██║██║   ██║██╔══██║██╔══██╗██║  ██║${NC} ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   ${GREEN}██║███████║███████╗██║ ╚████║╚██████╔╝██║  ██║██║  ██║██████╔╝${NC} ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   ${GREEN}╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝${NC}  ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}                                                            ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   Script Version: ${GREEN}${SCRIPT_VERSION}${NC}                        ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   Build Date:     ${GREEN}${BUILD_DATE}${NC}                                  ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   Script SHA256:  ${GREEN}${SCRIPT_SHA}${NC}                              ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}                                                            ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}   Features:                                                ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     ${GREEN}✓${NC} SSH access on TCP port 22                           ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     ${GREEN}✓${NC} Fast parallel model downloads with live progress    ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     ${GREEN}✓${NC} nginx reverse proxy (port 3000 → API 8000)          ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     ${GREEN}✓${NC} AI-Toolkit isolated venv                            ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     ${GREEN}✓${NC} SSE streaming support                               ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     ${GREEN}✓${NC} Persistent volume storage                           ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}                                                            ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# 1. SSH CONFIGURATION
# ============================================================
header "Configuring SSH"

if ! pgrep -x "sshd" > /dev/null; then
    log "Starting SSH daemon..."
    [ ! -f /etc/ssh/ssh_host_rsa_key ] && ssh-keygen -A

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

    if [ -z "$PUBLIC_KEY" ]; then
        ROOT_PASSWORD=$(openssl rand -base64 12)
        echo "root:${ROOT_PASSWORD}" | chpasswd
        log "SSH root password: ${ROOT_PASSWORD}"
    else
        mkdir -p /root/.ssh
        echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys
        chmod 600 /root/.ssh/authorized_keys
        log "SSH public key configured"
    fi

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
mkdir -p "${COMFYUI_MODELS}/unet"
mkdir -p "${HF_CACHE}"
mkdir -p "${LOG_DIR}/api"
mkdir -p "${LOG_DIR}/worker"
mkdir -p "${VOLUME_ROOT}/characters"
mkdir -p "${VOLUME_ROOT}/uploads"
mkdir -p "${VOLUME_ROOT}/outputs"
mkdir -p "${VOLUME_ROOT}/loras"

log "Directories created at ${VOLUME_ROOT}"

# ============================================================
# 3. SETUP RCLONE FOR R2
# ============================================================
header "Configuring rclone"

mkdir -p ~/.config/rclone
cat > ~/.config/rclone/rclone.conf << EOF
[r2]
type = s3
provider = Cloudflare
access_key_id = ${R2_ACCESS_KEY}
secret_access_key = ${R2_SECRET_KEY}
region = auto
endpoint = ${R2_ENDPOINT}
EOF

log "rclone configured for R2"

# ============================================================
# 4. DOWNLOAD MODELS (R2 first, fallback to HuggingFace)
# ============================================================
header "Downloading Models"

export HF_HOME="${HF_CACHE}"
export TRANSFORMERS_CACHE="${HF_CACHE}"

# Download tuning flags
PARALLEL_MODEL_DOWNLOADS="${PARALLEL_MODEL_DOWNLOADS:-1}"  # Set to 0 to disable parallel downloads
DID_DOWNLOAD=0  # Track if any files were downloaded (for sync-back gate)

# Optimized rclone flags for R2/S3
# --fast-list: Use fewer API calls by listing directories recursively (faster for many files)
# --checkers 32: Increase parallel file checkers for faster comparison
# --transfers 32: Increase parallel file transfers
# --multi-thread-streams 16: Streams per file for large files
# --multi-thread-cutoff 50M: Enable multi-thread for files >50MB
# --buffer-size 128M: Larger buffer for better throughput
# --ignore-existing: Skip files that already exist locally (idempotent cold starts)
# --progress: Show real-time progress with transfer speed
# --stats 2s: Update stats every 2 seconds
# --log-level INFO: Show transfer info without debug noise
RCLONE_COPY_FLAGS="--fast-list --checkers 32 --transfers 32 --multi-thread-streams 16 --multi-thread-cutoff 50M --buffer-size 128M --ignore-existing --progress --stats 2s --log-level INFO"

# Optimized aria2 flags for HuggingFace downloads
# -x 32: 32 connections per server
# -s 32: Split file into 32 segments
# -k 1M: Minimum split size 1MB
# --file-allocation=none: Faster startup (no preallocation)
# --disk-cache=64M: Disk cache for better write performance
# --show-console-readout=true: Show download progress bar
# --human-readable=true: Human readable sizes
# --download-result=hide: Hide per-file results, show summary only
ARIA2_FLAGS="-x 32 -s 32 -k 1M --file-allocation=none --disk-cache=64M --show-console-readout=true --human-readable=true --summary-interval=5 --download-result=hide"

# Install aria2 for fast multi-connection downloads (only if not present)
command -v aria2c > /dev/null 2>&1 || {
    log "Installing aria2..."
    apt-get update -qq && apt-get install -y -qq aria2 > /dev/null 2>&1 || true
}

# Function: Download from R2 with rclone (ultra fast)
# Shows live progress bar directly to terminal
download_from_r2() {
    local src="$1"
    local dst="$2"
    local start_time=$(date +%s)
    local log_file="/tmp/rclone_${RANDOM}.log"

    echo ""
    echo -e "${BLUE}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BLUE}│${NC} ${GREEN}Downloading:${NC} ${src}"
    echo -e "${BLUE}│${NC} ${GREEN}Destination:${NC} ${dst}"
    echo -e "${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"

    # Run rclone with live progress output, log to file for transfer tracking
    rclone copy "r2:${R2_BUCKET}/${src}" "${dst}" \
        ${RCLONE_COPY_FLAGS} \
        --log-file="${log_file}" \
        2>&1

    local exit_code=$?
    local end_time=$(date +%s)
    local elapsed=$((end_time - start_time))

    if [ $exit_code -eq 0 ]; then
        # Check log file for actual transfers (not just checks)
        if grep -qE "Copied|Transferred" "${log_file}" 2>/dev/null; then
            DID_DOWNLOAD=1
        fi
        echo -e "${GREEN}✓ Completed ${src} in ${elapsed}s${NC}"
    else
        echo -e "${RED}✗ Failed ${src} (exit code: ${exit_code})${NC}"
        cat "${log_file}" 2>/dev/null | tail -10
    fi

    rm -f "${log_file}" 2>/dev/null
    echo ""
    return $exit_code
}

# Function: Download from HuggingFace with aria2 (fast parallel)
# Shows live progress bar directly to terminal
download_from_hf() {
    local repo="$1"
    local file="$2"
    local dst="$3"
    local start_time=$(date +%s)

    # Skip if file already exists
    if [ -f "${dst}/${file}" ]; then
        echo -e "${GREEN}✓ ${file} already exists, skipping${NC}"
        return 0
    fi

    # Get download URL
    local url="https://huggingface.co/${repo}/resolve/main/${file}"

    echo ""
    echo -e "${BLUE}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BLUE}│${NC} ${GREEN}Downloading:${NC} ${file}"
    echo -e "${BLUE}│${NC} ${GREEN}From:${NC} ${repo}"
    echo -e "${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"

    # Use aria2c for multi-connection download with live progress
    if aria2c ${ARIA2_FLAGS} \
        --header="Authorization: Bearer ${HF_TOKEN}" \
        -d "${dst}" \
        -o "${file}" \
        "${url}"; then
        DID_DOWNLOAD=1
        local end_time=$(date +%s)
        local elapsed=$((end_time - start_time))
        echo -e "${GREEN}✓ Downloaded ${file} in ${elapsed}s${NC}"
    else
        # Fallback to wget if aria2c fails
        echo -e "${YELLOW}aria2c failed, trying wget...${NC}"
        if wget --progress=bar:force:noscroll \
            --header="Authorization: Bearer ${HF_TOKEN}" \
            -O "${dst}/${file}" \
            "${url}" 2>&1; then
            DID_DOWNLOAD=1
            local end_time=$(date +%s)
            local elapsed=$((end_time - start_time))
            echo -e "${GREEN}✓ Downloaded ${file} via wget in ${elapsed}s${NC}"
        else
            echo -e "${RED}✗ Failed to download ${file}${NC}"
            return 1
        fi
    fi
    echo ""
}

# Optimized rclone flags for S3/R2 uploads
# --s3-chunk-size 64M: Larger chunks for multipart upload (better throughput)
# --s3-upload-concurrency 8: Parallel parts per file upload
# --fast-list: Reduce API calls
RCLONE_SYNC_FLAGS="--fast-list --checkers 16 --transfers 16 --s3-chunk-size 64M --s3-upload-concurrency 8 --progress --stats 5s --log-level INFO"

# Function: Sync models to R2 (run once after HF download)
# Shows live progress bar directly to terminal
sync_to_r2() {
    local start_time=$(date +%s)

    echo ""
    echo -e "${BLUE}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BLUE}│${NC} ${GREEN}Syncing models to R2 for future fast downloads...${NC}"
    echo -e "${BLUE}│${NC} ${GREEN}Source:${NC} ${COMFYUI_MODELS}"
    echo -e "${BLUE}│${NC} ${GREEN}Dest:${NC}   r2:${R2_BUCKET}/comfyui/models"
    echo -e "${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"

    rclone sync "${COMFYUI_MODELS}" "r2:${R2_BUCKET}/comfyui/models" \
        ${RCLONE_SYNC_FLAGS} 2>&1

    local end_time=$(date +%s)
    local elapsed=$((end_time - start_time))
    echo -e "${GREEN}✓ Models synced to R2 in ${elapsed}s${NC}"
    echo ""
}

# Check if models exist on R2
log "Checking R2 for cached models..."
DOWNLOAD_START_TIME=$(date +%s)
R2_HAS_MODELS=$(rclone ls "r2:${R2_BUCKET}/comfyui/models/checkpoints/" 2>/dev/null | grep -c "flux1-dev" || echo "0")

if [ "$R2_HAS_MODELS" -gt 0 ]; then
    log "Models found on R2, downloading via rclone (ultra fast)..."

    if [ "$PARALLEL_MODEL_DOWNLOADS" = "1" ]; then
        log "Parallel downloads enabled (PARALLEL_MODEL_DOWNLOADS=1)"

        # Run all three downloads in parallel
        download_from_r2 "comfyui/models/checkpoints" "${COMFYUI_MODELS}/checkpoints" &
        PID_CHECKPOINTS=$!
        download_from_r2 "comfyui/models/vae" "${COMFYUI_MODELS}/vae" &
        PID_VAE=$!
        download_from_r2 "comfyui/models/clip" "${COMFYUI_MODELS}/clip" &
        PID_CLIP=$!

        # Wait for all downloads to complete
        log "Waiting for parallel downloads to complete..."
        wait $PID_CHECKPOINTS $PID_VAE $PID_CLIP
        log "All parallel downloads finished"
    else
        log "Sequential downloads (PARALLEL_MODEL_DOWNLOADS=0)"
        download_from_r2 "comfyui/models/checkpoints" "${COMFYUI_MODELS}/checkpoints"
        download_from_r2 "comfyui/models/vae" "${COMFYUI_MODELS}/vae"
        download_from_r2 "comfyui/models/clip" "${COMFYUI_MODELS}/clip"
    fi

    DOWNLOAD_END_TIME=$(date +%s)
    DOWNLOAD_ELAPSED=$((DOWNLOAD_END_TIME - DOWNLOAD_START_TIME))
    log "✓ R2 model download complete in ${DOWNLOAD_ELAPSED}s"
else
    log "Models not on R2, downloading from HuggingFace..."

    # Validate HF_TOKEN (also check HUGGINGFACE_TOKEN as fallback)
    HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"
    if [ -z "$HF_TOKEN" ]; then
        error "HF_TOKEN (or HUGGINGFACE_TOKEN) environment variable is not set!"
        error "Cannot download from HuggingFace without authentication."
        error "Please set HF_TOKEN in secrets.sh or as an environment variable."
        # Skip HF downloads but don't exit - models might already exist
    else
        log "HF_TOKEN is set (length: ${#HF_TOKEN} chars)"

        # Login to HuggingFace (silent, only if huggingface_hub available)
        pip install -q huggingface_hub 2>/dev/null || true
        python3 -c "from huggingface_hub import login; login(token='${HF_TOKEN}', add_to_git_credential=False)" 2>/dev/null || true

        # FLUX.1-dev (~23GB)
        download_from_hf "black-forest-labs/FLUX.1-dev" "flux1-dev.safetensors" "${COMFYUI_MODELS}/checkpoints"

        # FLUX.1-schnell (~23GB)
        download_from_hf "black-forest-labs/FLUX.1-schnell" "flux1-schnell.safetensors" "${COMFYUI_MODELS}/checkpoints"

        # VAE (~167MB)
        download_from_hf "black-forest-labs/FLUX.1-dev" "ae.safetensors" "${COMFYUI_MODELS}/vae"

        # CLIP-L (~246MB)
        download_from_hf "comfyanonymous/flux_text_encoders" "clip_l.safetensors" "${COMFYUI_MODELS}/clip"

        # T5-XXL (~9.5GB)
        download_from_hf "comfyanonymous/flux_text_encoders" "t5xxl_fp16.safetensors" "${COMFYUI_MODELS}/clip"

        DOWNLOAD_END_TIME=$(date +%s)
        DOWNLOAD_ELAPSED=$((DOWNLOAD_END_TIME - DOWNLOAD_START_TIME))
        log "✓ HuggingFace model download complete in ${DOWNLOAD_ELAPSED}s"

        # Sync to R2 for next time (only if we actually downloaded something)
        if [ "$DID_DOWNLOAD" = "1" ]; then
            log "Syncing downloaded models to R2 in background..."
            sync_to_r2 &
        else
            log "No new files downloaded, skipping R2 sync"
        fi
    fi
fi

# ============================================================
# 5. START REDIS
# ============================================================
header "Starting Redis"

if ! pgrep -x "redis-server" > /dev/null; then
    log "Starting Redis server..."
    redis-server --daemonize yes --port 6379
    sleep 2
    redis-cli ping > /dev/null 2>&1 && log "Redis started" || error "Redis failed"
else
    log "Redis already running"
fi

# ============================================================
# 6. START COMFYUI
# ============================================================
header "Starting ComfyUI"

COMFYUI_DIR="/opt/ComfyUI"

if [ -d "$COMFYUI_DIR" ]; then
    if ! pgrep -f "main.py.*ComfyUI" > /dev/null; then
        log "Starting ComfyUI..."

        # Link models to ComfyUI directories
        mkdir -p "${COMFYUI_DIR}/models/checkpoints" "${COMFYUI_DIR}/models/loras" "${COMFYUI_DIR}/models/vae" "${COMFYUI_DIR}/models/clip" "${COMFYUI_DIR}/models/unet"
        ln -sf "${COMFYUI_MODELS}/checkpoints"/* "${COMFYUI_DIR}/models/checkpoints/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/loras"/* "${COMFYUI_DIR}/models/loras/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/vae"/* "${COMFYUI_DIR}/models/vae/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/clip"/* "${COMFYUI_DIR}/models/clip/" 2>/dev/null || true
        # FLUX requires models in unet folder (symlink from checkpoints)
        ln -sf "${COMFYUI_MODELS}/checkpoints"/* "${COMFYUI_DIR}/models/unet/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/unet"/* "${COMFYUI_DIR}/models/unet/" 2>/dev/null || true
        # Also link user-trained LoRAs
        ln -sf "${VOLUME_ROOT}/loras"/*/*.safetensors "${COMFYUI_DIR}/models/loras/" 2>/dev/null || true

        cd "$COMFYUI_DIR"
        nohup python main.py --listen 0.0.0.0 --port 8188 > "${LOG_DIR}/comfyui.log" 2>&1 &

        log "Waiting for ComfyUI..."
        for i in {1..30}; do
            curl -s http://localhost:8188/system_stats > /dev/null 2>&1 && { log "ComfyUI started"; break; }
            sleep 2
        done
    else
        log "ComfyUI already running"
    fi
else
    warn "ComfyUI not installed"
fi

# ============================================================
# 7. START ISENGARD API
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

    log "Waiting for API..."
    for i in {1..30}; do
        curl -s http://localhost:8000/health > /dev/null 2>&1 && { log "API started"; break; }
        sleep 1
    done
else
    log "API already running"
fi

# ============================================================
# 8. BUILD AND START WEB FRONTEND (nginx reverse proxy)
# ============================================================
header "Starting Web Frontend"

WEB_DIR="/app/apps/web"

# Build frontend if not already built
if [ ! -d "${WEB_DIR}/dist" ]; then
    log "Building web frontend..."
    cd "${WEB_DIR}"
    npm install --legacy-peer-deps 2>/dev/null || npm install
    npm run build
    cd /app
fi

if [ -d "${WEB_DIR}/dist" ]; then
    # Configure nginx as reverse proxy (serves frontend + proxies /api to backend)
    if ! pgrep -x "nginx" > /dev/null; then
        log "Configuring nginx reverse proxy..."

        # Create nginx config for Isengard
        mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
        cat > /etc/nginx/sites-available/isengard << 'NGINX_CONF'
server {
    listen 3000;
    server_name _;

    root /app/apps/web/dist;
    index index.html;

    # API proxy to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE streaming support
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        chunked_transfer_encoding on;
    }

    # Health endpoint proxy
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
}
NGINX_CONF

        # Enable site
        ln -sf /etc/nginx/sites-available/isengard /etc/nginx/sites-enabled/isengard
        rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

        # Start nginx
        nginx -t && nginx
        sleep 2
        curl -s http://localhost:3000/api/health > /dev/null 2>&1 && log "Web + API proxy started on port 3000" || warn "nginx may not be running"
    else
        log "nginx already running"
    fi
else
    warn "Web build failed"
fi

# ============================================================
# 9. START ISENGARD WORKER
# ============================================================
header "Starting Isengard Worker"

if ! pgrep -f "apps.worker.src.main" > /dev/null; then
    log "Starting Worker..."

    export PYTHONPATH=/app
    export USE_REDIS=true

    nohup python -m apps.worker.src.main > "${LOG_DIR}/worker/startup.log" 2>&1 &
    sleep 3
    pgrep -f "apps.worker.src.main" > /dev/null && log "Worker started" || error "Worker failed"
else
    log "Worker already running"
fi

# ============================================================
# 10. FINAL STATUS
# ============================================================
header "Startup Complete"

echo ""
log "Services:"
echo "  SSH:     $(pgrep -x sshd > /dev/null && echo '✓ port 22' || echo '✗')"
echo "  Redis:   $(redis-cli ping 2>/dev/null | grep -q PONG && echo '✓ port 6379' || echo '✗')"
echo "  ComfyUI: $(curl -s http://localhost:8188/system_stats > /dev/null 2>&1 && echo '✓ port 8188' || echo '✗')"
echo "  API:     $(curl -s http://localhost:8000/health > /dev/null 2>&1 && echo '✓ port 8000' || echo '✗')"
echo "  Web:     $(curl -s http://localhost:3000 > /dev/null 2>&1 && echo '✓ port 3000' || echo '✗')"
echo "  Worker:  $(pgrep -f 'apps.worker.src.main' > /dev/null && echo '✓' || echo '✗')"
echo ""
log "Models:"
echo "  FLUX.1-dev:     $([ -f "${COMFYUI_MODELS}/checkpoints/flux1-dev.safetensors" ] && echo '✓' || echo '✗')"
echo "  FLUX.1-schnell: $([ -f "${COMFYUI_MODELS}/checkpoints/flux1-schnell.safetensors" ] && echo '✓' || echo '✗')"
echo "  VAE:            $([ -f "${COMFYUI_MODELS}/vae/ae.safetensors" ] && echo '✓' || echo '✗')"
echo "  CLIP-L:         $([ -f "${COMFYUI_MODELS}/clip/clip_l.safetensors" ] && echo '✓' || echo '✗')"
echo "  T5-XXL:         $([ -f "${COMFYUI_MODELS}/clip/t5xxl_fp16.safetensors" ] && echo '✓' || echo '✗')"
echo ""

# ============================================================
# 11. AI-TOOLKIT SETUP (for training)
# ============================================================
header "Setting up AI-Toolkit"

AITOOLKIT_REPO="${VOLUME_ROOT}/ai-toolkit"
AITOOLKIT_VENV="${VOLUME_ROOT}/.venvs/aitoolkit"

# Clone AI-Toolkit if not present
if [ ! -d "${AITOOLKIT_REPO}/.git" ]; then
    log "Cloning AI-Toolkit..."
    git clone --depth 1 https://github.com/ostris/ai-toolkit.git "${AITOOLKIT_REPO}"
else
    log "AI-Toolkit repo exists"
fi

# Create venv if needed
if [ ! -f "${AITOOLKIT_VENV}/bin/python" ]; then
    log "Creating AI-Toolkit venv..."
    mkdir -p "${VOLUME_ROOT}/.venvs"
    python3 -m venv --system-site-packages "${AITOOLKIT_VENV}"
    "${AITOOLKIT_VENV}/bin/pip" install --quiet --upgrade pip wheel

    log "Installing AI-Toolkit requirements..."
    "${AITOOLKIT_VENV}/bin/pip" install --quiet -r "${AITOOLKIT_REPO}/requirements.txt" 2>&1 | tail -5 || {
        warn "Some requirements may have failed, attempting individual installs..."
        "${AITOOLKIT_VENV}/bin/pip" install --quiet torch torchvision torchaudio
        "${AITOOLKIT_VENV}/bin/pip" install --quiet transformers accelerate safetensors peft
        "${AITOOLKIT_VENV}/bin/pip" install --quiet diffusers bitsandbytes scipy pyyaml
    }

    log "AI-Toolkit venv created"
else
    log "AI-Toolkit venv exists"
fi

# Add AI-Toolkit to venv's PYTHONPATH via .pth file
SITE_PACKAGES=$("${AITOOLKIT_VENV}/bin/python" -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "${AITOOLKIT_VENV}/lib/python3.11/site-packages")
echo "${AITOOLKIT_REPO}" > "${SITE_PACKAGES}/aitoolkit.pth" 2>/dev/null || true

# Verify installation
if "${AITOOLKIT_VENV}/bin/python" -c "import torch; print(f'PyTorch {torch.__version__}')" 2>/dev/null; then
    log "AI-Toolkit setup complete"
    echo "  AI-Toolkit: ✓ ${AITOOLKIT_REPO}"
    echo "  Venv:       ✓ ${AITOOLKIT_VENV}"
else
    warn "AI-Toolkit setup may be incomplete"
fi

echo ""

# ============================================================
# 12. MODEL VALIDATION SELF-CHECK
# ============================================================
header "Model Validation Self-Check"

# Print rclone version for debugging
log "Tool versions:"
echo "  rclone: $(rclone --version 2>/dev/null | head -1 || echo 'not installed')"
echo "  aria2c: $(aria2c --version 2>/dev/null | head -1 || echo 'not installed')"

# Required models list
REQUIRED_MODELS=(
    "${COMFYUI_MODELS}/checkpoints/flux1-dev.safetensors"
    "${COMFYUI_MODELS}/checkpoints/flux1-schnell.safetensors"
    "${COMFYUI_MODELS}/vae/ae.safetensors"
    "${COMFYUI_MODELS}/clip/clip_l.safetensors"
    "${COMFYUI_MODELS}/clip/t5xxl_fp16.safetensors"
)

log "Required model files:"
MODELS_OK=0
MODELS_MISSING=0
for model in "${REQUIRED_MODELS[@]}"; do
    model_name=$(basename "$model")
    if [ -f "$model" ]; then
        # Get file size in human-readable format
        size=$(ls -lh "$model" 2>/dev/null | awk '{print $5}')
        echo "  ✓ ${model_name} (${size})"
        MODELS_OK=$((MODELS_OK + 1))
    else
        echo "  ✗ ${model_name} MISSING"
        MODELS_MISSING=$((MODELS_MISSING + 1))
    fi
done

# Directory stats
log "Model directory stats:"
for dir in checkpoints vae clip; do
    dir_path="${COMFYUI_MODELS}/${dir}"
    if [ -d "$dir_path" ]; then
        file_count=$(find "$dir_path" -type f -name "*.safetensors" 2>/dev/null | wc -l | tr -d ' ')
        total_size=$(du -sh "$dir_path" 2>/dev/null | cut -f1)
        echo "  ${dir}/: ${file_count} files, ${total_size:-0}"
    else
        echo "  ${dir}/: directory not found"
    fi
done

echo ""
if [ $MODELS_MISSING -eq 0 ]; then
    log "✓ All ${MODELS_OK} required models present"
else
    warn "✗ ${MODELS_MISSING} of $((MODELS_OK + MODELS_MISSING)) required models missing!"
fi
echo ""

# Keep container running
tail -f /dev/null
