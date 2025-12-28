#!/bin/bash
# Isengard RunPod Startup Script
#
# This script runs on pod startup to:
# 1. Configure SSH access
# 2. Download required models (R2 first, fallback to HuggingFace)
# 3. Start all services (Redis, API, Worker, ComfyUI)

set -e

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

# Install aria2 for fast multi-connection downloads
apt-get update -qq && apt-get install -y -qq aria2 > /dev/null 2>&1 || true

# Function: Download from R2 with rclone (ultra fast)
download_from_r2() {
    local src="$1"
    local dst="$2"
    log "Downloading from R2: $src"
    rclone copy "r2:${R2_BUCKET}/${src}" "${dst}" \
        --transfers 16 \
        --checkers 8 \
        --multi-thread-streams 8 \
        --buffer-size 64M \
        --progress \
        --stats-one-line \
        2>&1 | tail -1
}

# Function: Download from HuggingFace with aria2 (fast parallel)
download_from_hf() {
    local repo="$1"
    local file="$2"
    local dst="$3"

    log "Downloading from HuggingFace: $repo/$file"

    # Get download URL
    local url="https://huggingface.co/${repo}/resolve/main/${file}"

    # Use aria2c for multi-connection download
    aria2c -x 16 -s 16 -k 1M \
        --header="Authorization: Bearer ${HF_TOKEN}" \
        -d "${dst}" \
        -o "${file}" \
        "${url}" \
        --console-log-level=warn \
        --summary-interval=10 \
        2>&1 || {
            # Fallback to wget if aria2c fails
            warn "aria2c failed, using wget..."
            wget -q --show-progress \
                --header="Authorization: Bearer ${HF_TOKEN}" \
                -O "${dst}/${file}" \
                "${url}"
        }
}

# Function: Sync models to R2 (run once after HF download)
sync_to_r2() {
    log "Syncing models to R2 for future fast downloads..."
    rclone sync "${COMFYUI_MODELS}" "r2:${R2_BUCKET}/comfyui/models" \
        --transfers 8 \
        --progress \
        --stats-one-line \
        2>&1 | tail -5
    log "Models synced to R2"
}

# Check if models exist on R2
log "Checking R2 for cached models..."
R2_HAS_MODELS=$(rclone ls "r2:${R2_BUCKET}/comfyui/models/checkpoints/" 2>/dev/null | grep -c "flux1-dev" || echo "0")

if [ "$R2_HAS_MODELS" -gt 0 ]; then
    log "Models found on R2, downloading via rclone (ultra fast)..."

    download_from_r2 "comfyui/models/checkpoints" "${COMFYUI_MODELS}/checkpoints"
    download_from_r2 "comfyui/models/vae" "${COMFYUI_MODELS}/vae"
    download_from_r2 "comfyui/models/clip" "${COMFYUI_MODELS}/clip"

    log "All models downloaded from R2"
else
    log "Models not on R2, downloading from HuggingFace..."

    # Login to HuggingFace
    pip install -q huggingface_hub
    python3 -c "from huggingface_hub import login; login(token='${HF_TOKEN}')"

    # FLUX.1-dev
    FLUX_DEV="${COMFYUI_MODELS}/checkpoints/flux1-dev.safetensors"
    if [ ! -f "$FLUX_DEV" ]; then
        download_from_hf "black-forest-labs/FLUX.1-dev" "flux1-dev.safetensors" "${COMFYUI_MODELS}/checkpoints"
    else
        log "FLUX.1-dev already exists"
    fi

    # FLUX.1-schnell
    FLUX_SCHNELL="${COMFYUI_MODELS}/checkpoints/flux1-schnell.safetensors"
    if [ ! -f "$FLUX_SCHNELL" ]; then
        download_from_hf "black-forest-labs/FLUX.1-schnell" "flux1-schnell.safetensors" "${COMFYUI_MODELS}/checkpoints"
    else
        log "FLUX.1-schnell already exists"
    fi

    # VAE
    VAE="${COMFYUI_MODELS}/vae/ae.safetensors"
    if [ ! -f "$VAE" ]; then
        download_from_hf "black-forest-labs/FLUX.1-dev" "ae.safetensors" "${COMFYUI_MODELS}/vae"
    else
        log "VAE already exists"
    fi

    # CLIP-L
    CLIP_L="${COMFYUI_MODELS}/clip/clip_l.safetensors"
    if [ ! -f "$CLIP_L" ]; then
        download_from_hf "comfyanonymous/flux_text_encoders" "clip_l.safetensors" "${COMFYUI_MODELS}/clip"
    else
        log "CLIP-L already exists"
    fi

    # T5-XXL
    T5="${COMFYUI_MODELS}/clip/t5xxl_fp16.safetensors"
    if [ ! -f "$T5" ]; then
        download_from_hf "comfyanonymous/flux_text_encoders" "t5xxl_fp16.safetensors" "${COMFYUI_MODELS}/clip"
    else
        log "T5-XXL already exists"
    fi

    log "All models downloaded from HuggingFace"

    # Sync to R2 for next time (run in background)
    sync_to_r2 &
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

        # Link models
        ln -sf "${COMFYUI_MODELS}/checkpoints"/* "${COMFYUI_DIR}/models/checkpoints/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/loras"/* "${COMFYUI_DIR}/models/loras/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/vae"/* "${COMFYUI_DIR}/models/vae/" 2>/dev/null || true
        ln -sf "${COMFYUI_MODELS}/clip"/* "${COMFYUI_DIR}/models/clip/" 2>/dev/null || true

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
# 8. START WEB FRONTEND
# ============================================================
header "Starting Web Frontend"

WEB_DIR="/app/apps/web"

if [ -d "${WEB_DIR}/dist" ]; then
    if ! pgrep -f "serve.*3000" > /dev/null; then
        log "Starting web frontend..."
        npm install -g serve 2>/dev/null || true
        nohup serve -s "${WEB_DIR}/dist" -l 3000 > "${LOG_DIR}/web.log" 2>&1 &
        sleep 2
        curl -s http://localhost:3000 > /dev/null 2>&1 && log "Web started on port 3000" || warn "Web may not be running"
    else
        log "Web already running"
    fi
else
    warn "Web not built"
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
echo "  FLUX.1-dev:     $([ -f '${COMFYUI_MODELS}/checkpoints/flux1-dev.safetensors' ] && echo '✓' || echo '✗')"
echo "  FLUX.1-schnell: $([ -f '${COMFYUI_MODELS}/checkpoints/flux1-schnell.safetensors' ] && echo '✓' || echo '✗')"
echo "  VAE:            $([ -f '${COMFYUI_MODELS}/vae/ae.safetensors' ] && echo '✓' || echo '✗')"
echo "  CLIP-L:         $([ -f '${COMFYUI_MODELS}/clip/clip_l.safetensors' ] && echo '✓' || echo '✗')"
echo "  T5-XXL:         $([ -f '${COMFYUI_MODELS}/clip/t5xxl_fp16.safetensors' ] && echo '✓' || echo '✗')"
echo ""

# Keep container running
tail -f /dev/null

# ============================================================
# 11. AI-TOOLKIT SETUP (for training)
# ============================================================
header "Setting up AI-Toolkit"

AITOOLKIT_REPO="${VOLUME_ROOT}/ai-toolkit"
AITOOLKIT_VENV="${VOLUME_ROOT}/.venvs/aitoolkit"

# Clone or update AI-Toolkit
if [ -d "${AITOOLKIT_REPO}/.git" ]; then
    log "AI-Toolkit repo exists"
else
    log "Cloning AI-Toolkit..."
    git clone https://github.com/ostris/ai-toolkit.git "${AITOOLKIT_REPO}"
fi

# Create venv if needed
if [ \! -f "${AITOOLKIT_VENV}/bin/python" ]; then
    log "Creating AI-Toolkit venv..."
    python3.11 -m venv --system-site-packages "${AITOOLKIT_VENV}"
    "${AITOOLKIT_VENV}/bin/pip" install --quiet --upgrade pip
    "${AITOOLKIT_VENV}/bin/pip" install --quiet -r "${AITOOLKIT_REPO}/requirements.txt"
fi

# Add to PYTHONPATH via .pth
SITE_PACKAGES=$("${AITOOLKIT_VENV}/bin/python" -c "import site; print(site.getsitepackages()[0])")
echo "${AITOOLKIT_REPO}" > "${SITE_PACKAGES}/aitoolkit.pth"

# Patch AI-Toolkit plugin if not already patched
PLUGIN_FILE="/app/packages/plugins/training/src/ai_toolkit.py"
if [ -f "$PLUGIN_FILE" ] && \! grep -q "aitoolkit_venv_python" "$PLUGIN_FILE"; then
    log "Patching AI-Toolkit plugin..."
    python3 << 'PATCHPY'
import re
plugin_file = "/app/packages/plugins/training/src/ai_toolkit.py"
with open(plugin_file, "r") as f:
    content = f.read()
old_pattern = r'cmd = \["python", "-m", "toolkit\.job", str\(config_path\)\]'
new_cmd = '# AI-Toolkit venv path
        aitoolkit_venv_python = "/runpod-volume/isengard/.venvs/aitoolkit/bin/python"
        aitoolkit_run_py = "/runpod-volume/isengard/ai-toolkit/run.py"
        cmd = [aitoolkit_venv_python, aitoolkit_run_py, str(config_path)]'
content = re.sub(old_pattern, new_cmd, content)
if "cwd=\"/runpod-volume" not in content:
    content = re.sub(
        r'(process = subprocess\.Popen\(\s*cmd,\s*stdout=subprocess\.PIPE,\s*stderr=subprocess\.STDOUT,\s*text=True,\s*bufsize=1,)',
        r'\1\n            cwd="/runpod-volume/isengard/ai-toolkit",\n            env={**os.environ, "PYTHONUNBUFFERED": "1", "HF_HOME": "/runpod-volume/isengard/.cache/huggingface"},',
        content
    )
with open(plugin_file, "w") as f:
    f.write(content)
PATCHPY
    log "Plugin patched"
else
    log "Plugin already patched or not found"
fi

# Create unet symlinks
mkdir -p /opt/ComfyUI/models/unet
ln -sf "${COMFYUI_MODELS}/checkpoints/flux1-dev.safetensors" /opt/ComfyUI/models/unet/ 2>/dev/null || true
ln -sf "${COMFYUI_MODELS}/checkpoints/flux1-schnell.safetensors" /opt/ComfyUI/models/unet/ 2>/dev/null || true

log "AI-Toolkit setup complete"


# Keep container running
tail -f /dev/null
