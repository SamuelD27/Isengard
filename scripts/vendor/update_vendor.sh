#!/bin/bash
# update_vendor.sh - Update a vendored repo to a new commit
#
# Usage: ./scripts/vendor/update_vendor.sh <comfyui|ai-toolkit> <commit-or-tag>
#
# This script:
# 1. Pulls the new commit via git subtree
# 2. Updates VENDOR_PINS.json
# 3. Shows the changes to be committed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PINS_FILE="$REPO_ROOT/vendor/VENDOR_PINS.json"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

usage() {
    echo "Usage: $0 <comfyui|ai-toolkit> <commit-or-tag>"
    echo ""
    echo "Examples:"
    echo "  $0 comfyui abc1234"
    echo "  $0 ai-toolkit v1.0.0"
    echo "  $0 comfyui master  # Get latest from master"
    exit 1
}

if [ $# -lt 2 ]; then
    usage
fi

VENDOR="$1"
COMMIT="$2"

case "$VENDOR" in
    comfyui)
        REPO="https://github.com/comfyanonymous/ComfyUI.git"
        PREFIX="vendor/comfyui"
        BRANCH="master"
        ;;
    ai-toolkit)
        REPO="https://github.com/ostris/ai-toolkit.git"
        PREFIX="vendor/ai-toolkit"
        BRANCH="main"
        ;;
    *)
        echo -e "${RED}Unknown vendor: $VENDOR${NC}"
        echo "Valid vendors: comfyui, ai-toolkit"
        exit 1
        ;;
esac

cd "$REPO_ROOT"

echo -e "${GREEN}Updating $VENDOR to $COMMIT${NC}"
echo "  Repository: $REPO"
echo "  Prefix: $PREFIX"
echo ""

# Check if this is an initial add or an update
if [ -d "$PREFIX" ]; then
    echo "Pulling update via git subtree..."
    git subtree pull --prefix="$PREFIX" "$REPO" "$COMMIT" --squash \
        -m "vendor: update $VENDOR to $COMMIT"
else
    echo "Initial add via git subtree..."
    git subtree add --prefix="$PREFIX" "$REPO" "$COMMIT" --squash \
        -m "vendor: add $VENDOR at $COMMIT"
fi

# Get the actual commit hash if a tag/branch was given
ACTUAL_COMMIT=$(git ls-remote "$REPO" "$COMMIT" | head -1 | cut -f1)
if [ -z "$ACTUAL_COMMIT" ]; then
    # Maybe it was already a full commit hash
    ACTUAL_COMMIT="$COMMIT"
fi

# Update pins file
TODAY=$(date +%Y-%m-%d)
echo ""
echo -e "${YELLOW}Updating VENDOR_PINS.json...${NC}"

if command -v jq &> /dev/null; then
    # Use jq to update the file
    jq --arg commit "$ACTUAL_COMMIT" --arg date "$TODAY" \
        ".$VENDOR.commit = \$commit | .$VENDOR.pinned_at = \$date" \
        "$PINS_FILE" > "$PINS_FILE.tmp" && mv "$PINS_FILE.tmp" "$PINS_FILE"
    echo "Updated pins file with jq"
else
    echo -e "${YELLOW}jq not installed. Please manually update VENDOR_PINS.json:${NC}"
    echo "  $VENDOR.commit = $ACTUAL_COMMIT"
    echo "  $VENDOR.pinned_at = $TODAY"
fi

echo ""
echo -e "${GREEN}Done! Changes:${NC}"
git status --short

echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Review the changes"
echo "  2. Run: docker build -t isengard:test ."
echo "  3. Run smoke tests"
echo "  4. Commit: git add . && git commit -m 'vendor: update $VENDOR to $ACTUAL_COMMIT'"
