#!/bin/bash
# =============================================================================
# train_lora.sh - LoRA Training via AI-Toolkit
# =============================================================================
#
# Usage:
#   ./scripts/engines/train_lora.sh /path/to/config.yaml
#
# Input:
#   - config.yaml: AI-Toolkit training configuration
#
# Output:
#   - LoRA safetensors file at path specified in config
#   - Training logs to stdout (parsed by worker for progress)
#
# Exit codes:
#   0 = success
#   1 = missing arguments
#   2 = config file not found
#   3 = AI-Toolkit execution failed
# =============================================================================
set -e

CONFIG_PATH="$1"

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
if [ -z "$CONFIG_PATH" ]; then
    echo "ERROR: Usage: $0 /path/to/config.yaml" >&2
    exit 1
fi

if [ ! -f "$CONFIG_PATH" ]; then
    echo "ERROR: Config file not found: $CONFIG_PATH" >&2
    exit 2
fi

# -----------------------------------------------------------------------------
# Environment Setup
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# AI-Toolkit location (vendored in repo)
AI_TOOLKIT_DIR="${AITOOLKIT_PATH:-$PROJECT_ROOT/vendor/ai-toolkit}"

if [ ! -d "$AI_TOOLKIT_DIR" ]; then
    echo "ERROR: AI-Toolkit not found at: $AI_TOOLKIT_DIR" >&2
    exit 3
fi

# Detect volume root for logs
if [ -n "$VOLUME_ROOT" ]; then
    LOG_DIR="$VOLUME_ROOT/logs/training"
elif [ -d "/workspace/isengard" ]; then
    LOG_DIR="/workspace/isengard/logs/training"
elif [ -d "/runpod-volume/isengard" ]; then
    LOG_DIR="/runpod-volume/isengard/logs/training"
else
    LOG_DIR="$PROJECT_ROOT/data/logs/training"
fi
mkdir -p "$LOG_DIR"

# -----------------------------------------------------------------------------
# Virtual Environment
# -----------------------------------------------------------------------------
VENV_DIR="$AI_TOOLKIT_DIR/.venv"

echo "=== AI-Toolkit LoRA Training ==="
echo "Config: $CONFIG_PATH"
echo "AI-Toolkit: $AI_TOOLKIT_DIR"
echo "Venv: $VENV_DIR"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install/update dependencies (using uv for speed)
echo "Installing dependencies..."
if command -v uv &> /dev/null; then
    GIT_LFS_SKIP_SMUDGE=1 uv pip install --compile-bytecode -r "$AI_TOOLKIT_DIR/requirements.txt"
else
    GIT_LFS_SKIP_SMUDGE=1 pip install -r "$AI_TOOLKIT_DIR/requirements.txt"
fi

# -----------------------------------------------------------------------------
# HuggingFace Token
# -----------------------------------------------------------------------------
if [ -n "$HF_TOKEN" ]; then
    echo "HF_TOKEN detected, exporting to environment"
    export HF_TOKEN="$HF_TOKEN"
fi

# -----------------------------------------------------------------------------
# Run Training
# -----------------------------------------------------------------------------
echo "Starting training..."
echo "---"

cd "$AI_TOOLKIT_DIR"

# Run AI-Toolkit - output goes to stdout for worker to parse
# Worker looks for lines like:
#   step: 100/1000
#   loss: 0.0234
#   saving checkpoint...
#   sample image saved: /path/to/sample.png
python run.py "$CONFIG_PATH"
TRAIN_EXIT_CODE=$?

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
deactivate

if [ $TRAIN_EXIT_CODE -ne 0 ]; then
    echo "ERROR: Training failed with exit code $TRAIN_EXIT_CODE" >&2
    exit 3
fi

echo "---"
echo "Training complete!"
exit 0
