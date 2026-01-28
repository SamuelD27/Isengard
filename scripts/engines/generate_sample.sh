#!/bin/bash
# =============================================================================
# generate_sample.sh - Sample Image Generation During Training (AI-Toolkit)
# =============================================================================
#
# Usage:
#   ./scripts/engines/generate_sample.sh \
#     --checkpoint /path/to/checkpoint.safetensors \
#     --prompt "photo of ohwx person" \
#     --output /path/to/sample.png \
#     [--steps 20] \
#     [--cfg 7.5] \
#     [--seed 42]
#
# This uses AI-Toolkit's built-in sampling capability to generate preview
# images during training. Lightweight, no ComfyUI needed.
#
# Exit codes:
#   0 = success
#   1 = missing arguments
#   2 = checkpoint not found
#   3 = generation failed
# =============================================================================
set -e

# -----------------------------------------------------------------------------
# Argument Parsing
# -----------------------------------------------------------------------------
CHECKPOINT=""
PROMPT=""
OUTPUT=""
STEPS=20
CFG=7.5
SEED=""
WIDTH=1024
HEIGHT=1024

while [[ $# -gt 0 ]]; do
    case $1 in
        --checkpoint)
            CHECKPOINT="$2"
            shift 2
            ;;
        --prompt)
            PROMPT="$2"
            shift 2
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        --steps)
            STEPS="$2"
            shift 2
            ;;
        --cfg)
            CFG="$2"
            shift 2
            ;;
        --seed)
            SEED="$2"
            shift 2
            ;;
        --width)
            WIDTH="$2"
            shift 2
            ;;
        --height)
            HEIGHT="$2"
            shift 2
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
if [ -z "$CHECKPOINT" ] || [ -z "$PROMPT" ] || [ -z "$OUTPUT" ]; then
    echo "ERROR: Missing required arguments" >&2
    echo "Usage: $0 --checkpoint PATH --prompt TEXT --output PATH" >&2
    exit 1
fi

if [ ! -f "$CHECKPOINT" ]; then
    echo "ERROR: Checkpoint not found: $CHECKPOINT" >&2
    exit 2
fi

# -----------------------------------------------------------------------------
# Environment Setup
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

AI_TOOLKIT_DIR="${AITOOLKIT_PATH:-$PROJECT_ROOT/vendor/ai-toolkit}"
VENV_DIR="$AI_TOOLKIT_DIR/.venv"

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT")"

echo "=== Sample Image Generation ==="
echo "Checkpoint: $CHECKPOINT"
echo "Prompt: $PROMPT"
echo "Output: $OUTPUT"
echo "Steps: $STEPS, CFG: $CFG, Size: ${WIDTH}x${HEIGHT}"

# -----------------------------------------------------------------------------
# Virtual Environment
# -----------------------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: AI-Toolkit venv not found. Run train_lora.sh first." >&2
    exit 3
fi

source "$VENV_DIR/bin/activate"

# -----------------------------------------------------------------------------
# Generate Sample
# -----------------------------------------------------------------------------
# Create a minimal sampling config
SAMPLE_CONFIG=$(mktemp /tmp/sample_config.XXXXXX.yaml)

cat > "$SAMPLE_CONFIG" << EOF
# Auto-generated sample config
job: sample
config:
  name: sample_generation
  process:
    - type: sample
      checkpoint: "$CHECKPOINT"
      prompt: "$PROMPT"
      output: "$OUTPUT"
      steps: $STEPS
      cfg_scale: $CFG
      width: $WIDTH
      height: $HEIGHT
      $([ -n "$SEED" ] && echo "seed: $SEED")
EOF

echo "Running sample generation..."
cd "$AI_TOOLKIT_DIR"

# TODO: Verify AI-Toolkit supports this sampling mode
# If not, we'll need to use ComfyUI for sampling
python run.py "$SAMPLE_CONFIG"
GEN_EXIT_CODE=$?

# Cleanup temp config
rm -f "$SAMPLE_CONFIG"

deactivate

if [ $GEN_EXIT_CODE -ne 0 ]; then
    echo "ERROR: Sample generation failed" >&2
    exit 3
fi

if [ ! -f "$OUTPUT" ]; then
    echo "ERROR: Output file not created: $OUTPUT" >&2
    exit 3
fi

echo "Sample generated: $OUTPUT"
exit 0
