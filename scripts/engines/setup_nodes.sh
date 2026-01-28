#!/bin/bash
# =============================================================================
# setup_nodes.sh - Download and Setup ComfyUI Custom Node Libraries
# =============================================================================
#
# Installs curated ComfyUI custom nodes for:
#   A) Image Generation - control, identity, refinement, upscaling
#   B) Synthetic Generation - prompt randomization, batching, automation
#   C) Infrastructure - node management
#
# Usage:
#   ./scripts/engines/setup_nodes.sh [--group NAME] [--node NAME] [--all]
#
# Examples:
#   ./scripts/engines/setup_nodes.sh --all                    # Everything
#   ./scripts/engines/setup_nodes.sh --group generation       # Generation nodes
#   ./scripts/engines/setup_nodes.sh --group synthetic        # Synthetic nodes
#   ./scripts/engines/setup_nodes.sh --node controlnet        # Single node
#
# Exit codes:
#   0 = success
#   1 = missing arguments
#   2 = download failed
#   3 = installation failed
# =============================================================================
set -e

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ComfyUI paths
COMFYUI_DIR="${COMFYUI_PATH:-/opt/ComfyUI}"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

# =============================================================================
# NODE DEFINITIONS
# =============================================================================

# -----------------------------------------------------------------------------
# C) INFRASTRUCTURE (always install first)
# -----------------------------------------------------------------------------
declare -A INFRA_NODES=(
    ["manager"]="https://github.com/Comfy-Org/ComfyUI-Manager"
)

# -----------------------------------------------------------------------------
# A) IMAGE GENERATION NODES
# -----------------------------------------------------------------------------

# Core control & conditioning
declare -A CONTROLNET_NODES=(
    ["controlnet_aux"]="https://github.com/Fannovel16/comfyui_controlnet_aux"
    ["controlnet_advanced"]="https://github.com/Kosinkadink/ComfyUI-Advanced-ControlNet"
)

# Identity / reference fidelity
declare -A IDENTITY_NODES=(
    ["ipadapter_plus"]="https://github.com/cubiq/ComfyUI_IPAdapter_plus"
    ["pulid_flux"]="https://github.com/balazik/ComfyUI-PuLID-Flux"
)

# Upscaling & refinement
declare -A REFINEMENT_NODES=(
    ["ultimate_upscale"]="https://github.com/ssitu/ComfyUI_UltimateSDUpscale"
    ["impact_pack"]="https://github.com/ltdrdata/ComfyUI-Impact-Pack"
)

# Performance / formats
declare -A PERFORMANCE_NODES=(
    ["tensorrt"]="https://github.com/comfyanonymous/ComfyUI_TensorRT"
    ["gguf"]="https://github.com/city96/ComfyUI-GGUF"
)

# -----------------------------------------------------------------------------
# B) SYNTHETIC GENERATION NODES
# -----------------------------------------------------------------------------

# Prompt randomization & variation
declare -A PROMPT_NODES=(
    ["dynamic_prompts"]="https://github.com/adieyal/comfyui-dynamicprompts"
    ["ab_wildcards"]="https://github.com/a-und-b/ComfyUI_AB_Wildcard"
)

# Batching & automation
declare -A BATCH_NODES=(
    ["inspire_pack"]="https://github.com/ltdrdata/ComfyUI-Inspire-Pack"
    ["north_tools"]="https://github.com/northumber/ComfyUI-northTools"
)

# Workflow utilities
declare -A UTILITY_NODES=(
    ["kjnodes"]="https://github.com/kijai/ComfyUI-KJNodes"
)

# -----------------------------------------------------------------------------
# NODE GROUPS (for --group flag)
# -----------------------------------------------------------------------------
declare -A NODE_GROUPS=(
    ["infrastructure"]="manager"
    ["controlnet"]="controlnet_aux controlnet_advanced"
    ["ipadapter"]="ipadapter_plus"
    ["pulid"]="pulid_flux"
    ["facedetailer"]="impact_pack"
    ["upscale"]="ultimate_upscale"
    ["performance"]="tensorrt gguf"
    ["prompts"]="dynamic_prompts ab_wildcards"
    ["batch"]="inspire_pack north_tools"
    ["utility"]="kjnodes"
    # Composite groups
    ["generation"]="manager controlnet_aux controlnet_advanced ipadapter_plus pulid_flux impact_pack ultimate_upscale"
    ["synthetic"]="manager dynamic_prompts ab_wildcards inspire_pack north_tools kjnodes"
    ["minimal"]="manager controlnet_aux ipadapter_plus impact_pack ultimate_upscale"
)

# -----------------------------------------------------------------------------
# ALL NODES COMBINED (for URL lookup)
# -----------------------------------------------------------------------------
declare -A ALL_NODES
for key in "${!INFRA_NODES[@]}"; do ALL_NODES[$key]="${INFRA_NODES[$key]}"; done
for key in "${!CONTROLNET_NODES[@]}"; do ALL_NODES[$key]="${CONTROLNET_NODES[$key]}"; done
for key in "${!IDENTITY_NODES[@]}"; do ALL_NODES[$key]="${IDENTITY_NODES[$key]}"; done
for key in "${!REFINEMENT_NODES[@]}"; do ALL_NODES[$key]="${REFINEMENT_NODES[$key]}"; done
for key in "${!PERFORMANCE_NODES[@]}"; do ALL_NODES[$key]="${PERFORMANCE_NODES[$key]}"; done
for key in "${!PROMPT_NODES[@]}"; do ALL_NODES[$key]="${PROMPT_NODES[$key]}"; done
for key in "${!BATCH_NODES[@]}"; do ALL_NODES[$key]="${BATCH_NODES[$key]}"; done
for key in "${!UTILITY_NODES[@]}"; do ALL_NODES[$key]="${UTILITY_NODES[$key]}"; done

# -----------------------------------------------------------------------------
# Argument Parsing
# -----------------------------------------------------------------------------
NODES_TO_INSTALL=()
INSTALL_ALL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --node)
            NODES_TO_INSTALL+=("$2")
            shift 2
            ;;
        --group)
            GROUP_NODES="${NODE_GROUPS[$2]}"
            if [ -z "$GROUP_NODES" ]; then
                echo "ERROR: Unknown group: $2" >&2
                echo "Available groups: ${!NODE_GROUPS[*]}" >&2
                exit 1
            fi
            for node in $GROUP_NODES; do
                NODES_TO_INSTALL+=("$node")
            done
            shift 2
            ;;
        --all)
            INSTALL_ALL=true
            shift
            ;;
        --list)
            echo "=== Available Nodes ==="
            echo ""
            echo "Infrastructure:"
            for node in "${!INFRA_NODES[@]}"; do echo "  $node"; done
            echo ""
            echo "ControlNet:"
            for node in "${!CONTROLNET_NODES[@]}"; do echo "  $node"; done
            echo ""
            echo "Identity (IPAdapter/PuLID):"
            for node in "${!IDENTITY_NODES[@]}"; do echo "  $node"; done
            echo ""
            echo "Refinement (FaceDetailer/Upscale):"
            for node in "${!REFINEMENT_NODES[@]}"; do echo "  $node"; done
            echo ""
            echo "Performance:"
            for node in "${!PERFORMANCE_NODES[@]}"; do echo "  $node"; done
            echo ""
            echo "Prompt Randomization:"
            for node in "${!PROMPT_NODES[@]}"; do echo "  $node"; done
            echo ""
            echo "Batching:"
            for node in "${!BATCH_NODES[@]}"; do echo "  $node"; done
            echo ""
            echo "Utility:"
            for node in "${!UTILITY_NODES[@]}"; do echo "  $node"; done
            echo ""
            echo "=== Available Groups ==="
            for group in "${!NODE_GROUPS[@]}"; do
                echo "  $group: ${NODE_GROUPS[$group]}"
            done
            exit 0
            ;;
        --help|-h)
            echo "Usage: $0 [--group NAME] [--node NAME] [--all] [--list]"
            echo ""
            echo "Options:"
            echo "  --node NAME    Install specific node"
            echo "  --group NAME   Install node group (generation, synthetic, minimal, etc.)"
            echo "  --all          Install all nodes"
            echo "  --list         List available nodes and groups"
            echo ""
            echo "Recommended:"
            echo "  --group minimal      Core generation (ControlNet, IPAdapter, FaceDetailer, Upscale)"
            echo "  --group generation   Full generation stack"
            echo "  --group synthetic    Synthetic dataset generation"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

if [ "$INSTALL_ALL" = true ]; then
    NODES_TO_INSTALL=(${!ALL_NODES[@]})
fi

# Remove duplicates
NODES_TO_INSTALL=($(echo "${NODES_TO_INSTALL[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))

if [ ${#NODES_TO_INSTALL[@]} -eq 0 ]; then
    echo "ERROR: No nodes specified. Use --node NAME, --group NAME, or --all" >&2
    echo "Use --list to see available options" >&2
    exit 1
fi

# -----------------------------------------------------------------------------
# Pre-flight Checks
# -----------------------------------------------------------------------------
echo "=== ComfyUI Node Setup ==="
echo "ComfyUI: $COMFYUI_DIR"
echo "Custom Nodes: $CUSTOM_NODES_DIR"
echo "Nodes to install: ${NODES_TO_INSTALL[*]}"
echo ""

if [ ! -d "$COMFYUI_DIR" ]; then
    echo "ERROR: ComfyUI not found at $COMFYUI_DIR" >&2
    exit 3
fi

mkdir -p "$CUSTOM_NODES_DIR"

# -----------------------------------------------------------------------------
# Installation Function
# -----------------------------------------------------------------------------
install_node() {
    local NODE_NAME="$1"
    local REPO_URL="${ALL_NODES[$NODE_NAME]}"

    if [ -z "$REPO_URL" ]; then
        echo "ERROR: Unknown node: $NODE_NAME" >&2
        return 1
    fi

    echo ""
    echo "=== Installing: $NODE_NAME ==="
    echo "URL: $REPO_URL"

    # Extract repo name from URL for directory
    local DIR_NAME=$(basename "$REPO_URL" .git)
    local NODE_PATH="$CUSTOM_NODES_DIR/$DIR_NAME"

    # Clone or update repository
    if [ -d "$NODE_PATH" ]; then
        echo "Updating existing installation..."
        cd "$NODE_PATH"
        git fetch origin
        git reset --hard origin/HEAD 2>/dev/null || git reset --hard origin/main 2>/dev/null || git reset --hard origin/master
        cd - > /dev/null
    else
        echo "Cloning repository..."
        git clone "$REPO_URL" "$NODE_PATH"
    fi

    # Install requirements if present
    if [ -f "$NODE_PATH/requirements.txt" ]; then
        echo "Installing Python requirements..."
        cd "$NODE_PATH"
        if command -v uv &> /dev/null; then
            uv pip install --system -r requirements.txt 2>/dev/null || \
            uv pip install -r requirements.txt 2>/dev/null || \
            pip install -r requirements.txt
        else
            pip install -r requirements.txt
        fi
        cd - > /dev/null
    fi

    # Run install script if present
    if [ -f "$NODE_PATH/install.py" ]; then
        echo "Running install.py..."
        cd "$NODE_PATH"
        python install.py || echo "Warning: install.py had issues"
        cd - > /dev/null
    fi

    echo "$NODE_NAME installed successfully!"
    return 0
}

# -----------------------------------------------------------------------------
# Main Installation Loop
# -----------------------------------------------------------------------------

# Always install manager first if it's in the list
if [[ " ${NODES_TO_INSTALL[*]} " =~ " manager " ]]; then
    install_node "manager" || true
    # Remove manager from list so we don't install twice
    NODES_TO_INSTALL=(${NODES_TO_INSTALL[@]/manager/})
fi

INSTALLED=()
FAILED=()

for node in "${NODES_TO_INSTALL[@]}"; do
    [ -z "$node" ] && continue  # Skip empty entries

    if install_node "$node"; then
        INSTALLED+=("$node")
    else
        FAILED+=("$node")
    fi
done

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "=== Setup Complete ==="
echo "=========================================="
echo "Installed: ${INSTALLED[*]:-none}"
echo "Failed: ${FAILED[*]:-none}"
echo ""

if [ ${#FAILED[@]} -gt 0 ]; then
    echo "Some installations failed. Check errors above."
    exit 2
fi

echo "Restart ComfyUI to load the new nodes."
echo ""
echo "Quick verification:"
echo "  ls $CUSTOM_NODES_DIR"

exit 0
