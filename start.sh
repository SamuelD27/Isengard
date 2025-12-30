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

# ============================================================
# LOGGING SYSTEM (TTY-aware, container-safe)
# ============================================================
# Detect if stdout is a TTY (interactive terminal)
IS_TTY=0; [ -t 1 ] && IS_TTY=1

# Colors - ONLY when stdout is a TTY
# RunPod logs don't render ANSI, so we output plain text there
if [ "$IS_TTY" = "1" ]; then
    RED='\x1b[31m'
    GREEN='\x1b[32m'
    YELLOW='\x1b[33m'
    BLUE='\x1b[34m'
    CYAN='\x1b[36m'
    GRAY='\x1b[90m'
    BOLD='\x1b[1m'
    NC='\x1b[0m'
else
    # No colors for non-TTY (container logs)
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    GRAY=''
    BOLD=''
    NC=''
fi

# Immutable log functions (always print newline, permanent in logs)
log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
log_info() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARN:${NC} $1"; }
log_error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; }
warn() { log_warn "$1"; }
error() { log_error "$1"; }

# Phase header (marks start of a major section)
log_phase() { echo -e "\n${CYAN}[$(date +'%H:%M:%S')] ▶ $1${NC}"; }
header() { echo -e "\n${CYAN}=== $1 ===${NC}\n"; }

# Live status line (overwrites in-place on TTY, silent on non-TTY)
log_status() {
    if [ "$IS_TTY" = "1" ]; then
        echo -ne "\x1b[2K\r  ${GRAY}$1${NC}"
    fi
}

# Finalize live status (print newline to preserve final state)
log_status_done() {
    if [ "$IS_TTY" = "1" ]; then
        echo ""
    fi
}

# Phase completion markers
log_success() { echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓${NC} $1"; }
log_fail() { echo -e "${RED}[$(date +'%H:%M:%S')] ✗${NC} $1"; }

# Progress tracking for non-TTY (prints every N seconds)
declare -A LAST_PROGRESS_TIME
log_progress() {
    local key="${1:-default}"
    local msg="$2"
    local interval="${3:-15}"  # Default 15 seconds between updates
    local now=$(date +%s)
    local last="${LAST_PROGRESS_TIME[$key]:-0}"

    if [ $((now - last)) -ge $interval ]; then
        echo "  $msg"
        LAST_PROGRESS_TIME[$key]=$now
    fi
}

# Phase failure helper (cleans up and exits)
phase_failed() {
    local phase="$1"
    local reason="$2"
    log_status_done
    log_fail "Phase '$phase' failed: $reason"
    exit 1
}

# ============================================================
# STARTUP BANNER
# ============================================================
SCRIPT_VERSION="v2.3.1-no-ansi"
BUILD_DATE="2025-12-30"

# Generate SHA256 of this script for verification
SCRIPT_SHA=$(sha256sum /start.sh 2>/dev/null | cut -c1-12 || echo "unknown")

# Banner - simplified for container logs, fancy for TTY
echo ""
if [ "$IS_TTY" = "1" ]; then
    # Full ASCII art banner for interactive terminals
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}   ${GREEN}██╗███████╗███████╗███╗   ██╗ ██████╗  █████╗ ██████╗ ██████╗${NC}  ${BLUE}║${NC}"
    echo -e "${BLUE}║${NC}   ${GREEN}██║██╔════╝██╔════╝████╗  ██║██╔════╝ ██╔══██╗██╔══██╗██╔══██╗${NC} ${BLUE}║${NC}"
    echo -e "${BLUE}║${NC}   ${GREEN}██║███████╗█████╗  ██╔██╗ ██║██║  ███╗███████║██████╔╝██║  ██║${NC} ${BLUE}║${NC}"
    echo -e "${BLUE}║${NC}   ${GREEN}██║╚════██║██╔══╝  ██║╚██╗██║██║   ██║██╔══██║██╔══██╗██║  ██║${NC} ${BLUE}║${NC}"
    echo -e "${BLUE}║${NC}   ${GREEN}██║███████║███████╗██║ ╚████║╚██████╔╝██║  ██║██║  ██║██████╔╝${NC} ${BLUE}║${NC}"
    echo -e "${BLUE}║${NC}   ${GREEN}╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝${NC}  ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
else
    # Clean text banner for container logs
    echo "============================================================"
    echo "  ISENGARD - Identity LoRA Training Platform"
    echo "============================================================"
fi
echo ""
echo "  Version: ${SCRIPT_VERSION}"
echo "  Build:   ${BUILD_DATE}"
echo "  SHA256:  ${SCRIPT_SHA}"
echo ""
echo "  Features:"
echo "    - SSH access on TCP port 22"
echo "    - Fast parallel model downloads"
echo "    - nginx reverse proxy (port 3000 -> API 8000)"
echo "    - AI-Toolkit isolated venv"
echo "    - SSE streaming support"
echo "    - Persistent volume storage"
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

# TTY-aware rclone flags
# Non-TTY: minimal output with periodic stats (one line every 15s)
# TTY: full progress bars
if [ "$IS_TTY" = "1" ]; then
    RCLONE_COPY_FLAGS="--fast-list --checkers 32 --transfers 32 --multi-thread-streams 16 --multi-thread-cutoff 50M --buffer-size 128M --ignore-existing --progress"
else
    # Container logs: quiet with periodic one-line stats
    RCLONE_COPY_FLAGS="--fast-list --checkers 32 --transfers 32 --multi-thread-streams 16 --multi-thread-cutoff 50M --buffer-size 128M --ignore-existing --stats-one-line --stats 15s -q"
fi

# TTY-aware aria2 flags
if [ "$IS_TTY" = "1" ]; then
    ARIA2_FLAGS="-x 16 -s 16 -k 1M --file-allocation=none --disk-cache=64M --show-console-readout=true --human-readable=true --summary-interval=5"
else
    # Container logs: quiet with periodic summary
    ARIA2_FLAGS="-x 16 -s 16 -k 1M --file-allocation=none --disk-cache=64M --console-log-level=warn --summary-interval=15 --download-result=hide"
fi

# Install aria2 for fast multi-connection downloads (only if not present)
command -v aria2c > /dev/null 2>&1 || {
    log "Installing aria2..."
    apt-get update -qq && apt-get install -y -qq aria2 > /dev/null 2>&1 || true
}

# Function: Download from R2 with rclone (ultra fast)
# TTY-aware: shows progress on interactive, quiet stats on container logs
download_from_r2() {
    local src="$1"
    local dst="$2"
    local start_time=$(date +%s)
    local log_file="/tmp/rclone_${RANDOM}.log"
    local src_name=$(basename "$src")

    log "Downloading from R2: ${src_name}"

    # Run rclone with TTY-appropriate flags
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
        log_success "Downloaded ${src_name} (${elapsed}s)"
    else
        log_fail "Failed ${src_name} (exit code: ${exit_code})"
        # Show last few lines of error on failure
        tail -5 "${log_file}" 2>/dev/null | while read line; do
            echo "  ${line}"
        done
    fi

    rm -f "${log_file}" 2>/dev/null
    return $exit_code
}

# Function: Download from HuggingFace with aria2 (fast parallel)
# TTY-aware: shows progress on interactive, quiet on container logs
download_from_hf() {
    local repo="$1"
    local file="$2"
    local dst="$3"
    local start_time=$(date +%s)

    # Skip if file already exists
    if [ -f "${dst}/${file}" ]; then
        log_success "${file} already exists, skipping"
        return 0
    fi

    # Get download URL
    local url="https://huggingface.co/${repo}/resolve/main/${file}"

    log "Downloading from HuggingFace: ${file}"

    # Use aria2c for multi-connection download with TTY-appropriate flags
    if aria2c ${ARIA2_FLAGS} \
        --header="Authorization: Bearer ${HF_TOKEN}" \
        -d "${dst}" \
        -o "${file}" \
        "${url}" 2>&1; then
        DID_DOWNLOAD=1
        local end_time=$(date +%s)
        local elapsed=$((end_time - start_time))
        log_success "Downloaded ${file} (${elapsed}s)"
    else
        # Fallback to wget if aria2c fails
        log_warn "aria2c failed, trying wget..."
        local wget_flags="--no-verbose"
        [ "$IS_TTY" = "1" ] && wget_flags="--progress=bar:force:noscroll"

        if wget ${wget_flags} \
            --header="Authorization: Bearer ${HF_TOKEN}" \
            -O "${dst}/${file}" \
            "${url}" 2>&1; then
            DID_DOWNLOAD=1
            local end_time=$(date +%s)
            local elapsed=$((end_time - start_time))
            log_success "Downloaded ${file} via wget (${elapsed}s)"
        else
            log_fail "Failed to download ${file}"
            return 1
        fi
    fi
}

# TTY-aware rclone sync flags for R2 uploads
if [ "$IS_TTY" = "1" ]; then
    RCLONE_SYNC_FLAGS="--fast-list --checkers 16 --transfers 16 --s3-chunk-size 64M --s3-upload-concurrency 8 --progress"
else
    RCLONE_SYNC_FLAGS="--fast-list --checkers 16 --transfers 16 --s3-chunk-size 64M --s3-upload-concurrency 8 --stats-one-line --stats 15s -q"
fi

# Function: Sync models to R2 (run once after HF download)
# TTY-aware output
sync_to_r2() {
    local start_time=$(date +%s)

    log "Syncing models to R2 for future fast downloads..."

    rclone sync "${COMFYUI_MODELS}" "r2:${R2_BUCKET}/comfyui/models" \
        ${RCLONE_SYNC_FLAGS} 2>&1

    local end_time=$(date +%s)
    local elapsed=$((end_time - start_time))
    log_success "Models synced to R2 (${elapsed}s)"
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
log_phase "Model Validation"

# Required models list
REQUIRED_MODELS=(
    "${COMFYUI_MODELS}/checkpoints/flux1-dev.safetensors"
    "${COMFYUI_MODELS}/checkpoints/flux1-schnell.safetensors"
    "${COMFYUI_MODELS}/vae/ae.safetensors"
    "${COMFYUI_MODELS}/clip/clip_l.safetensors"
    "${COMFYUI_MODELS}/clip/t5xxl_fp16.safetensors"
)

MODELS_OK=0
MODELS_MISSING=0
for model in "${REQUIRED_MODELS[@]}"; do
    model_name=$(basename "$model")
    if [ -f "$model" ]; then
        size=$(ls -lh "$model" 2>/dev/null | awk '{print $5}')
        echo -e "  ${GREEN}✓${NC} ${model_name} (${size})"
        MODELS_OK=$((MODELS_OK + 1))
    else
        echo -e "  ${RED}✗${NC} ${model_name} MISSING"
        MODELS_MISSING=$((MODELS_MISSING + 1))
    fi
done

if [ $MODELS_MISSING -eq 0 ]; then
    log_success "All ${MODELS_OK} required models present"
else
    log_warn "${MODELS_MISSING} of $((MODELS_OK + MODELS_MISSING)) required models missing!"
fi

# ============================================================
# STARTUP COMPLETE
# ============================================================
log_phase "Startup Complete"
log_success "Isengard ${SCRIPT_VERSION} ready"
log "Container will now stay running. Services available:"
echo "  - API:     http://localhost:8000"
echo "  - Web GUI: http://localhost:3000"
echo "  - ComfyUI: http://localhost:8188"
echo "  - SSH:     port 22"

# Keep container running
tail -f /dev/null
