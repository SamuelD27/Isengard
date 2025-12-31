#!/bin/bash
# pin_status.sh - Show current vendor pins and dirty status
#
# Usage: ./scripts/vendor/pin_status.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PINS_FILE="$REPO_ROOT/vendor/VENDOR_PINS.json"

echo "========================================"
echo "  Isengard Vendor Pin Status"
echo "========================================"
echo ""

if [ ! -f "$PINS_FILE" ]; then
    echo "ERROR: Pins file not found at $PINS_FILE"
    exit 1
fi

# Check if jq is available
if command -v jq &> /dev/null; then
    echo "Pinned Versions:"
    echo "----------------"
    jq -r 'to_entries[] | "  \(.key):\n    Commit: \(.value.commit)\n    Pinned: \(.value.pinned_at)\n    Purpose: \(.value.purpose)\n"' "$PINS_FILE"
else
    echo "Pins file contents (install jq for pretty output):"
    cat "$PINS_FILE"
fi

echo ""
echo "Vendor Directory Status:"
echo "------------------------"

# Check if vendor directories exist
for vendor in comfyui ai-toolkit; do
    vendor_dir="$REPO_ROOT/vendor/$vendor"
    if [ -d "$vendor_dir" ]; then
        file_count=$(find "$vendor_dir" -type f | wc -l | tr -d ' ')
        echo "  $vendor: present ($file_count files)"
    else
        echo "  $vendor: NOT VENDORED"
    fi
done

echo ""
echo "Git Status (vendor/):"
echo "---------------------"
cd "$REPO_ROOT"
git status vendor/ --short 2>/dev/null || echo "  (not a git repository)"

echo ""
