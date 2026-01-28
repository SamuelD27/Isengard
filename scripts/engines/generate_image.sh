#!/bin/bash
# =============================================================================
# generate_image.sh - Image Generation via ComfyUI
# =============================================================================
#
# Usage:
#   ./scripts/engines/generate_image.sh \
#     --prompt "photo of ohwx woman in paris" \
#     --lora /path/to/character.safetensors \
#     --output /path/to/output.png \
#     [--width 1024] \
#     [--height 1024] \
#     [--steps 30] \
#     [--cfg 7.5] \
#     [--seed 42] \
#     [--modules controlnet,ipadapter,facedetailer,upscale] \
#     [--controlnet-image /path/to/pose.png] \
#     [--controlnet-strength 0.8] \
#     [--ipadapter-image /path/to/face.png] \
#     [--ipadapter-strength 0.6]
#
# Modules (comma-separated):
#   - controlnet: Use ControlNet for pose/structure guidance
#   - ipadapter: Use IPAdapter for face/style reference
#   - facedetailer: Apply face enhancement post-processing
#   - upscale: Upscale output image
#
# Exit codes:
#   0 = success
#   1 = missing arguments
#   2 = workflow not found
#   3 = ComfyUI not reachable
#   4 = generation failed
# =============================================================================
set -e

# -----------------------------------------------------------------------------
# Argument Parsing
# -----------------------------------------------------------------------------
PROMPT=""
LORA_PATH=""
OUTPUT=""
WIDTH=1024
HEIGHT=1024
STEPS=30
CFG=7.5
SEED=""
MODULES=""
CONTROLNET_IMAGE=""
CONTROLNET_STRENGTH=0.8
IPADAPTER_IMAGE=""
IPADAPTER_STRENGTH=0.6

while [[ $# -gt 0 ]]; do
    case $1 in
        --prompt)
            PROMPT="$2"
            shift 2
            ;;
        --lora)
            LORA_PATH="$2"
            shift 2
            ;;
        --output)
            OUTPUT="$2"
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
        --seed)
            SEED="$2"
            shift 2
            ;;
        --modules)
            MODULES="$2"
            shift 2
            ;;
        --controlnet-image)
            CONTROLNET_IMAGE="$2"
            shift 2
            ;;
        --controlnet-strength)
            CONTROLNET_STRENGTH="$2"
            shift 2
            ;;
        --ipadapter-image)
            IPADAPTER_IMAGE="$2"
            shift 2
            ;;
        --ipadapter-strength)
            IPADAPTER_STRENGTH="$2"
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
if [ -z "$PROMPT" ] || [ -z "$OUTPUT" ]; then
    echo "ERROR: Missing required arguments" >&2
    echo "Usage: $0 --prompt TEXT --output PATH [--lora PATH] [--modules LIST]" >&2
    exit 1
fi

# -----------------------------------------------------------------------------
# Environment Setup
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKFLOWS_DIR="$SCRIPT_DIR/comfyui/workflows"

COMFYUI_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT")"

# Generate random seed if not provided
if [ -z "$SEED" ]; then
    SEED=$RANDOM$RANDOM
fi

echo "=== ComfyUI Image Generation ==="
echo "Prompt: $PROMPT"
echo "LoRA: ${LORA_PATH:-none}"
echo "Output: $OUTPUT"
echo "Size: ${WIDTH}x${HEIGHT}"
echo "Steps: $STEPS, CFG: $CFG, Seed: $SEED"
echo "Modules: ${MODULES:-base}"
echo "ComfyUI: $COMFYUI_URL"

# -----------------------------------------------------------------------------
# Select Workflow Based on Modules
# -----------------------------------------------------------------------------
# Parse modules into sorted array for consistent naming
IFS=',' read -ra MODULE_ARRAY <<< "$MODULES"
SORTED_MODULES=$(printf '%s\n' "${MODULE_ARRAY[@]}" | sort | tr '\n' '_' | sed 's/_$//')

if [ -z "$SORTED_MODULES" ]; then
    WORKFLOW_NAME="base"
else
    WORKFLOW_NAME="$SORTED_MODULES"
fi

WORKFLOW_FILE="$WORKFLOWS_DIR/${WORKFLOW_NAME}.json"

echo "Workflow: $WORKFLOW_FILE"

if [ ! -f "$WORKFLOW_FILE" ]; then
    echo "ERROR: Workflow not found: $WORKFLOW_FILE" >&2
    echo "Available workflows:" >&2
    ls -1 "$WORKFLOWS_DIR"/*.json 2>/dev/null | xargs -n1 basename >&2 || echo "  (none)" >&2
    exit 2
fi

# -----------------------------------------------------------------------------
# Check ComfyUI Availability
# -----------------------------------------------------------------------------
echo "Checking ComfyUI availability..."
if ! curl -s --max-time 5 "$COMFYUI_URL/system_stats" > /dev/null 2>&1; then
    echo "ERROR: ComfyUI not reachable at $COMFYUI_URL" >&2
    exit 3
fi
echo "ComfyUI is ready"

# -----------------------------------------------------------------------------
# Prepare Workflow with Runtime Values
# -----------------------------------------------------------------------------
TEMP_WORKFLOW=$(mktemp /tmp/workflow.XXXXXX.json)

# Read workflow and substitute placeholders
# Placeholders in workflow JSON:
#   {{PROMPT}} - text prompt
#   {{NEGATIVE_PROMPT}} - negative prompt
#   {{LORA_PATH}} - path to LoRA file
#   {{WIDTH}} - image width
#   {{HEIGHT}} - image height
#   {{STEPS}} - sampling steps
#   {{CFG}} - CFG scale
#   {{SEED}} - random seed
#   {{CONTROLNET_IMAGE}} - ControlNet input image
#   {{CONTROLNET_STRENGTH}} - ControlNet strength
#   {{IPADAPTER_IMAGE}} - IPAdapter reference image
#   {{IPADAPTER_STRENGTH}} - IPAdapter strength

# Escape special characters in prompt for JSON
ESCAPED_PROMPT=$(echo "$PROMPT" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')

sed -e "s|{{PROMPT}}|$ESCAPED_PROMPT|g" \
    -e "s|{{NEGATIVE_PROMPT}}|blurry, low quality, deformed|g" \
    -e "s|{{LORA_PATH}}|$LORA_PATH|g" \
    -e "s|{{WIDTH}}|$WIDTH|g" \
    -e "s|{{HEIGHT}}|$HEIGHT|g" \
    -e "s|{{STEPS}}|$STEPS|g" \
    -e "s|{{CFG}}|$CFG|g" \
    -e "s|{{SEED}}|$SEED|g" \
    -e "s|{{CONTROLNET_IMAGE}}|$CONTROLNET_IMAGE|g" \
    -e "s|{{CONTROLNET_STRENGTH}}|$CONTROLNET_STRENGTH|g" \
    -e "s|{{IPADAPTER_IMAGE}}|$IPADAPTER_IMAGE|g" \
    -e "s|{{IPADAPTER_STRENGTH}}|$IPADAPTER_STRENGTH|g" \
    "$WORKFLOW_FILE" > "$TEMP_WORKFLOW"

# -----------------------------------------------------------------------------
# Submit to ComfyUI
# -----------------------------------------------------------------------------
echo "Submitting workflow to ComfyUI..."

# Generate client ID
CLIENT_ID=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "isengard-$$")

# Submit prompt
RESPONSE=$(curl -s -X POST "$COMFYUI_URL/prompt" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\": $(cat "$TEMP_WORKFLOW"), \"client_id\": \"$CLIENT_ID\"}")

PROMPT_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('prompt_id', ''))" 2>/dev/null || echo "")

if [ -z "$PROMPT_ID" ]; then
    echo "ERROR: Failed to submit workflow" >&2
    echo "Response: $RESPONSE" >&2
    rm -f "$TEMP_WORKFLOW"
    exit 4
fi

echo "Prompt ID: $PROMPT_ID"

# -----------------------------------------------------------------------------
# Wait for Completion
# -----------------------------------------------------------------------------
echo "Waiting for generation..."

MAX_WAIT=300  # 5 minutes timeout
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    HISTORY=$(curl -s "$COMFYUI_URL/history/$PROMPT_ID")

    # Check if prompt is in history (completed)
    HAS_OUTPUTS=$(echo "$HISTORY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if '$PROMPT_ID' in data:
    outputs = data['$PROMPT_ID'].get('outputs', {})
    if outputs:
        print('yes')
    else:
        status = data['$PROMPT_ID'].get('status', {})
        if status.get('completed', False):
            print('yes')
" 2>/dev/null || echo "")

    if [ "$HAS_OUTPUTS" = "yes" ]; then
        echo "Generation complete!"
        break
    fi

    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))

    # Progress indicator every 10 seconds
    if [ $((WAIT_COUNT % 10)) -eq 0 ]; then
        echo "  Still generating... (${WAIT_COUNT}s)"
    fi
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo "ERROR: Generation timed out after ${MAX_WAIT}s" >&2
    rm -f "$TEMP_WORKFLOW"
    exit 4
fi

# -----------------------------------------------------------------------------
# Download Output Image
# -----------------------------------------------------------------------------
echo "Downloading output image..."

# Extract output image info from history
OUTPUT_INFO=$(curl -s "$COMFYUI_URL/history/$PROMPT_ID" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if '$PROMPT_ID' in data:
    outputs = data['$PROMPT_ID'].get('outputs', {})
    for node_id, node_output in outputs.items():
        if 'images' in node_output:
            img = node_output['images'][0]
            print(f\"{img['filename']}|{img.get('subfolder', '')}|{img.get('type', 'output')}\")
            break
" 2>/dev/null || echo "")

if [ -z "$OUTPUT_INFO" ]; then
    echo "ERROR: No output image found in results" >&2
    rm -f "$TEMP_WORKFLOW"
    exit 4
fi

IFS='|' read -r FILENAME SUBFOLDER TYPE <<< "$OUTPUT_INFO"

# Download image
IMAGE_URL="$COMFYUI_URL/view?filename=$FILENAME&subfolder=$SUBFOLDER&type=$TYPE"
curl -s "$IMAGE_URL" -o "$OUTPUT"

if [ ! -f "$OUTPUT" ]; then
    echo "ERROR: Failed to download output image" >&2
    rm -f "$TEMP_WORKFLOW"
    exit 4
fi

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
rm -f "$TEMP_WORKFLOW"

echo "Image saved: $OUTPUT"
exit 0
