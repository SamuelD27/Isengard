# Isengard Dockerfile
#
# Full GPU image with SSH, vendored ComfyUI + AI-Toolkit, and all dependencies.
# For deployment on RunPod serverless or pods.
#
# EXPOSED Ports (public):
#   22   - SSH
#   3000 - Web GUI (nginx reverse proxy)
#   8000 - API (direct access, optional)
#
# INTERNAL Ports (NOT exposed, localhost only):
#   8188 - ComfyUI (internal service, bound to 127.0.0.1)
#
# Vendored Dependencies:
#   vendor/comfyui    - ComfyUI (pinned commit from VENDOR_PINS.json)
#   vendor/ai-toolkit - AI-Toolkit (pinned commit from VENDOR_PINS.json)
#
# Build:
#   docker build -t isengard:latest .
#
# Run locally (for testing):
#   docker run --gpus all -p 22:22 -p 3000:3000 -p 8000:8000 isengard:latest
#
# Note: ComfyUI port 8188 is intentionally NOT published - it's internal only.
# Note: HF_TOKEN and R2 credentials are hardcoded in start.sh

FROM nvidia/cuda:12.4.0-devel-ubuntu22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# ============================================================
# System Dependencies
# ============================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    # Build tools
    git \
    curl \
    wget \
    build-essential \
    # SSH server
    openssh-server \
    # Graphics libs (for ComfyUI)
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    # Redis
    redis-server \
    # Fast downloads
    aria2 \
    unzip \
    # Utilities
    htop \
    nvtop \
    tmux \
    vim \
    jq \
    # Web server / reverse proxy
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Install rclone for ultra-fast R2 downloads
RUN curl -O https://downloads.rclone.org/rclone-current-linux-amd64.zip \
    && unzip rclone-current-linux-amd64.zip \
    && cp rclone-*-linux-amd64/rclone /usr/local/bin/ \
    && chmod +x /usr/local/bin/rclone \
    && rm -rf rclone-*

# Make python3.11 default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Upgrade pip and install uv
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir uv

# ============================================================
# SSH Configuration
# ============================================================
RUN mkdir -p /var/run/sshd \
    && echo 'root:runpod' | chpasswd \
    && sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config \
    && sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

EXPOSE 22

# ============================================================
# PyTorch with CUDA
# ============================================================
RUN uv pip install --system \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu124

# ============================================================
# ComfyUI Installation (Vendored)
# ============================================================
# ComfyUI is vendored at a pinned commit (see vendor/VENDOR_PINS.json)
# This ensures deterministic, reproducible builds.
# ComfyUI runs as an INTERNAL service bound to 127.0.0.1:8188 only.
WORKDIR /opt

# Copy vendored ComfyUI source
COPY vendor/comfyui /opt/ComfyUI

# Install ComfyUI requirements
RUN uv pip install --system -r /opt/ComfyUI/requirements.txt

# Create model directories (will be symlinked to volume at runtime)
RUN mkdir -p /opt/ComfyUI/models/checkpoints \
    && mkdir -p /opt/ComfyUI/models/loras \
    && mkdir -p /opt/ComfyUI/models/vae \
    && mkdir -p /opt/ComfyUI/models/clip \
    && mkdir -p /opt/ComfyUI/models/unet

# NOTE: Port 8188 is NOT exposed - ComfyUI is an internal service only
# It binds to 127.0.0.1:8188 and is not accessible from outside the container

# ============================================================
# AI-Toolkit for LoRA Training (Vendored)
# ============================================================
# AI-Toolkit is vendored at a pinned commit (see vendor/VENDOR_PINS.json)
# This eliminates runtime cloning and ensures reproducible training.
# The vendored code runs directly with system Python (no separate venv).

# Copy vendored AI-Toolkit to /app/vendor for consistency
COPY vendor/ai-toolkit /app/vendor/ai-toolkit

# Install AI-Toolkit requirements
# Note: Some deps overlap with ComfyUI/PyTorch, uv handles deduplication
RUN uv pip install --system -r /app/vendor/ai-toolkit/requirements.txt || \
    echo "Some AI-Toolkit requirements may have failed, core deps already installed"

# ============================================================
# Node.js for Web Frontend
# ============================================================
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 3000

# ============================================================
# Isengard Application
# ============================================================
WORKDIR /app

# Copy shared packages
COPY packages/ /app/packages/

# Install API dependencies
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN uv pip install --system -r /app/apps/api/requirements.txt

# Install worker dependencies
COPY apps/worker/requirements.txt /app/apps/worker/requirements.txt
RUN uv pip install --system -r /app/apps/worker/requirements.txt

# Install additional ML dependencies
RUN uv pip install --system \
    accelerate \
    transformers \
    diffusers \
    safetensors \
    bitsandbytes \
    peft \
    huggingface_hub \
    pyyaml \
    httpx

# Copy application source
COPY apps/api/src/ /app/apps/api/src/
COPY apps/worker/src/ /app/apps/worker/src/

# Copy workflow templates
COPY packages/plugins/image/workflows/ /app/packages/plugins/image/workflows/

# Build web frontend
COPY apps/web/package.json /app/apps/web/package.json
WORKDIR /app/apps/web
RUN npm install
COPY apps/web/ /app/apps/web/
RUN npm run build

WORKDIR /app

# Copy startup script and secrets
# NOTE: start.sh is at repo root (not deploy/runpod/) - contains nginx, AI-Toolkit setup, version banner
COPY start.sh /start.sh
COPY deploy/runpod/secrets.sh /secrets.sh

# Copy vendor pins file for version verification
COPY vendor/VENDOR_PINS.json /app/vendor/VENDOR_PINS.json

# Create version marker for verification
RUN echo "BOOTSTRAP_VERSION=v3.0.0-vendored BUILD_TIME=$(date -u +%Y%m%d-%H%M%S)" > /app/BOOTSTRAP_VERSION \
    && sha256sum /start.sh >> /app/BOOTSTRAP_VERSION \
    && echo "VENDOR_COMFYUI=$(cat /app/vendor/VENDOR_PINS.json | grep -A1 'comfyui' | grep commit | cut -d'"' -f4)" >> /app/BOOTSTRAP_VERSION \
    && echo "VENDOR_AITOOLKIT=$(cat /app/vendor/VENDOR_PINS.json | grep -A1 'ai-toolkit' | grep commit | cut -d'"' -f4)" >> /app/BOOTSTRAP_VERSION

# Copy helper scripts for pod management
COPY scripts/bootstrap_pod.sh /app/scripts/bootstrap_pod.sh
COPY scripts/restart_services.sh /app/scripts/restart_services.sh

RUN chmod +x /start.sh /secrets.sh /app/scripts/*.sh

# ============================================================
# Environment
# ============================================================
ENV PYTHONPATH=/app:/app/vendor/ai-toolkit
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0

# HuggingFace cache location (on persistent volume)
ENV HF_HOME=/runpod-volume/isengard/cache/huggingface
ENV TRANSFORMERS_CACHE=/runpod-volume/isengard/cache/huggingface

# Isengard defaults
ENV ISENGARD_MODE=production
ENV VOLUME_ROOT=/runpod-volume/isengard
ENV LOG_DIR=/runpod-volume/isengard/logs
ENV REDIS_URL=redis://localhost:6379
ENV USE_REDIS=true

# ComfyUI internal service configuration
# IMPORTANT: ComfyUI binds to localhost only - it is NOT exposed externally
ENV COMFYUI_HOST=127.0.0.1
ENV COMFYUI_PORT=8188
ENV COMFYUI_URL=http://127.0.0.1:8188

# AI-Toolkit vendored path
ENV AITOOLKIT_PATH=/app/vendor/ai-toolkit

EXPOSE 8000

# ============================================================
# Startup
# ============================================================
CMD ["/start.sh"]
