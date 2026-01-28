#!/bin/bash
# =============================================================================
# generate_synthetic.sh - Synthetic Dataset Generation via ComfyUI
# =============================================================================
#
# Generates synthetic training images for a character. Used to bootstrap
# a character dataset without real photos, or to augment existing datasets.
#
# Usage:
#   ./scripts/engines/generate_synthetic.sh \
#     --description "young woman with brown hair and blue eyes" \
#     --output-dir /path/to/output/ \
#     --count 20 \
#     [--base-lora /path/to/base.safetensors] \
#     [--trigger-word "ohwx"] \
#     [--styles "portrait,full body,casual,professional"]
#
# Output:
#   - {count} images saved to output-dir as synthetic_001.png, synthetic_002.png, etc.
#   - metadata.json with generation parameters for each image
#
# Exit codes:
#   0 = success
#   1 = missing arguments
#   2 = ComfyUI not reachable
#   3 = generation failed
# =============================================================================
set -e

# -----------------------------------------------------------------------------
# Argument Parsing
# -----------------------------------------------------------------------------
DESCRIPTION=""
OUTPUT_DIR=""
COUNT=20
BASE_LORA=""
TRIGGER_WORD="ohwx"
STYLES="portrait,half body,full body"
WIDTH=1024
HEIGHT=1024
STEPS=30
CFG=7.5

while [[ $# -gt 0 ]]; do
    case $1 in
        --description)
            DESCRIPTION="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --count)
            COUNT="$2"
            shift 2
            ;;
        --base-lora)
            BASE_LORA="$2"
            shift 2
            ;;
        --trigger-word)
            TRIGGER_WORD="$2"
            shift 2
            ;;
        --styles)
            STYLES="$2"
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
        --steps)
            STEPS="$2"
            shift 2
            ;;
        --cfg)
            CFG="$2"
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
if [ -z "$DESCRIPTION" ] || [ -z "$OUTPUT_DIR" ]; then
    echo "ERROR: Missing required arguments" >&2
    echo "Usage: $0 --description TEXT --output-dir PATH [--count N]" >&2
    exit 1
fi

# -----------------------------------------------------------------------------
# Environment Setup
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKFLOWS_DIR="$SCRIPT_DIR/comfyui/workflows"

COMFYUI_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "=== Synthetic Dataset Generation ==="
echo "Description: $DESCRIPTION"
echo "Output: $OUTPUT_DIR"
echo "Count: $COUNT"
echo "Styles: $STYLES"
echo "Trigger word: $TRIGGER_WORD"
echo "Base LoRA: ${BASE_LORA:-none}"
echo "ComfyUI: $COMFYUI_URL"

# -----------------------------------------------------------------------------
# Check ComfyUI Availability
# -----------------------------------------------------------------------------
echo "Checking ComfyUI availability..."
if ! curl -s --max-time 5 "$COMFYUI_URL/system_stats" > /dev/null 2>&1; then
    echo "ERROR: ComfyUI not reachable at $COMFYUI_URL" >&2
    exit 2
fi
echo "ComfyUI is ready"

# -----------------------------------------------------------------------------
# Workflow Selection
# -----------------------------------------------------------------------------
# Use base workflow for synthetic generation (no advanced modules needed)
WORKFLOW_FILE="$WORKFLOWS_DIR/base.json"

if [ ! -f "$WORKFLOW_FILE" ]; then
    echo "ERROR: Base workflow not found: $WORKFLOW_FILE" >&2
    exit 3
fi

# -----------------------------------------------------------------------------
# Generate Prompt Variations
# -----------------------------------------------------------------------------
# Parse styles into array
IFS=',' read -ra STYLE_ARRAY <<< "$STYLES"
STYLE_COUNT=${#STYLE_ARRAY[@]}

# Prompt templates for variety
PROMPT_TEMPLATES=(
    "professional photo of $TRIGGER_WORD $DESCRIPTION, STYLE, high quality, detailed"
    "photograph of $TRIGGER_WORD $DESCRIPTION, STYLE, natural lighting, sharp focus"
    "studio portrait of $TRIGGER_WORD $DESCRIPTION, STYLE, professional lighting"
    "$TRIGGER_WORD $DESCRIPTION, STYLE, photorealistic, 8k, detailed face"
    "candid photo of $TRIGGER_WORD $DESCRIPTION, STYLE, natural pose"
)
TEMPLATE_COUNT=${#PROMPT_TEMPLATES[@]}

# Initialize metadata
METADATA_FILE="$OUTPUT_DIR/metadata.json"
echo "[" > "$METADATA_FILE"

# -----------------------------------------------------------------------------
# Generate Images
# -----------------------------------------------------------------------------
GENERATED=0
FAILED=0

for i in $(seq 1 $COUNT); do
    # Select random template and style
    TEMPLATE_IDX=$((RANDOM % TEMPLATE_COUNT))
    STYLE_IDX=$((RANDOM % STYLE_COUNT))

    TEMPLATE="${PROMPT_TEMPLATES[$TEMPLATE_IDX]}"
    STYLE="${STYLE_ARRAY[$STYLE_IDX]}"

    # Build prompt
    PROMPT="${TEMPLATE//STYLE/$STYLE}"

    # Generate unique seed
    SEED=$RANDOM$RANDOM

    # Output filename
    OUTPUT_FILE="$OUTPUT_DIR/synthetic_$(printf '%03d' $i).png"

    echo ""
    echo "[$i/$COUNT] Generating: $OUTPUT_FILE"
    echo "  Prompt: $PROMPT"
    echo "  Seed: $SEED"

    # Call generate_image.sh
    if "$SCRIPT_DIR/generate_image.sh" \
        --prompt "$PROMPT" \
        --output "$OUTPUT_FILE" \
        --width "$WIDTH" \
        --height "$HEIGHT" \
        --steps "$STEPS" \
        --cfg "$CFG" \
        --seed "$SEED" \
        ${BASE_LORA:+--lora "$BASE_LORA"} \
        2>&1; then

        GENERATED=$((GENERATED + 1))

        # Add to metadata
        if [ $GENERATED -gt 1 ]; then
            echo "," >> "$METADATA_FILE"
        fi

        cat >> "$METADATA_FILE" << EOF
  {
    "filename": "synthetic_$(printf '%03d' $i).png",
    "prompt": "$(echo "$PROMPT" | sed 's/"/\\"/g')",
    "seed": $SEED,
    "style": "$STYLE",
    "width": $WIDTH,
    "height": $HEIGHT,
    "steps": $STEPS,
    "cfg": $CFG
  }
EOF
    else
        echo "  WARNING: Generation failed for image $i"
        FAILED=$((FAILED + 1))
    fi
done

# Close metadata JSON
echo "" >> "$METADATA_FILE"
echo "]" >> "$METADATA_FILE"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Generation Complete ==="
echo "Generated: $GENERATED / $COUNT"
echo "Failed: $FAILED"
echo "Output: $OUTPUT_DIR"
echo "Metadata: $METADATA_FILE"

if [ $GENERATED -eq 0 ]; then
    echo "ERROR: No images were generated" >&2
    exit 3
fi

exit 0
