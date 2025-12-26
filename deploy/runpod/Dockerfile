# Isengard RunPod Dockerfile
#
# Full GPU image with SSH, ComfyUI, and all dependencies.
# For deployment on RunPod serverless or pods.
#
# Build:
#   docker build -t ghcr.io/samueld27/isengard-runpod:latest -f deploy/runpod/Dockerfile .
#
# Run locally (for testing):
#   docker run --gpus all -p 22:22 -p 8000:8000 -p 8188:8188 \
#     -e HF_TOKEN=xxx ghcr.io/samueld27/isengard-runpod:latest

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
    # Utilities
    htop \
    nvtop \
    tmux \
    vim \
    jq \
    && rm -rf /var/lib/apt/lists/*

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
# ComfyUI Installation
# ============================================================
WORKDIR /opt

RUN git clone https://github.com/comfyanonymous/ComfyUI.git \
    && cd ComfyUI \
    && uv pip install --system -r requirements.txt

# Create model directories
RUN mkdir -p /opt/ComfyUI/models/checkpoints \
    && mkdir -p /opt/ComfyUI/models/loras \
    && mkdir -p /opt/ComfyUI/models/vae \
    && mkdir -p /opt/ComfyUI/models/clip

EXPOSE 8188

# ============================================================
# AI-Toolkit for LoRA Training
# ============================================================
RUN uv pip install --system ostris-ai-toolkit

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

# Copy startup script
COPY deploy/runpod/start.sh /start.sh
RUN chmod +x /start.sh

# ============================================================
# Environment
# ============================================================
ENV PYTHONPATH=/app
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
ENV COMFYUI_URL=http://localhost:8188
ENV USE_REDIS=true

EXPOSE 8000

# ============================================================
# Startup
# ============================================================
CMD ["/start.sh"]
