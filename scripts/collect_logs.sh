#!/usr/bin/env bash
#
# Isengard Log Collection Script
#
# Collects all logs from API, Worker, and Job logs into a single
# timestamped archive for debugging and sharing.
#
# Usage:
#   ./scripts/collect_logs.sh [output_dir]
#
# Output:
#   logs/bundle-{timestamp}.tar.gz
#

set -euo pipefail

# Configuration
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Determine log locations
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
VOLUME_ROOT="${VOLUME_ROOT:-$PROJECT_ROOT/data}"
OUTPUT_DIR="${1:-$LOG_DIR}"
BUNDLE_NAME="bundle-$TIMESTAMP"
BUNDLE_DIR="$OUTPUT_DIR/$BUNDLE_NAME"

echo "=== Isengard Log Collection ==="
echo "Timestamp: $TIMESTAMP"
echo "Log Dir: $LOG_DIR"
echo "Volume Root: $VOLUME_ROOT"
echo "Output: $BUNDLE_DIR.tar.gz"
echo ""

# Create bundle directory
mkdir -p "$BUNDLE_DIR"

# Collect API logs
echo "[1/4] Collecting API logs..."
if [ -d "$LOG_DIR/api/latest" ]; then
    cp -r "$LOG_DIR/api/latest" "$BUNDLE_DIR/api-latest" 2>/dev/null || true
    echo "  ✓ API latest logs"
fi
if [ -d "$LOG_DIR/api/archive" ]; then
    # Only copy most recent archive
    LATEST_ARCHIVE=$(ls -t "$LOG_DIR/api/archive" 2>/dev/null | head -1)
    if [ -n "$LATEST_ARCHIVE" ]; then
        cp -r "$LOG_DIR/api/archive/$LATEST_ARCHIVE" "$BUNDLE_DIR/api-archive-$LATEST_ARCHIVE" 2>/dev/null || true
        echo "  ✓ API archive: $LATEST_ARCHIVE"
    fi
fi

# Collect Worker logs
echo "[2/4] Collecting Worker logs..."
if [ -d "$LOG_DIR/worker/latest" ]; then
    cp -r "$LOG_DIR/worker/latest" "$BUNDLE_DIR/worker-latest" 2>/dev/null || true
    echo "  ✓ Worker latest logs"
fi
if [ -d "$LOG_DIR/worker/archive" ]; then
    LATEST_ARCHIVE=$(ls -t "$LOG_DIR/worker/archive" 2>/dev/null | head -1)
    if [ -n "$LATEST_ARCHIVE" ]; then
        cp -r "$LOG_DIR/worker/archive/$LATEST_ARCHIVE" "$BUNDLE_DIR/worker-archive-$LATEST_ARCHIVE" 2>/dev/null || true
        echo "  ✓ Worker archive: $LATEST_ARCHIVE"
    fi
fi

# Collect Job logs
echo "[3/4] Collecting Job logs..."
JOB_LOG_DIR="$VOLUME_ROOT/logs/jobs"
if [ -d "$JOB_LOG_DIR" ]; then
    mkdir -p "$BUNDLE_DIR/jobs"
    # Copy only recent job logs (last 50)
    find "$JOB_LOG_DIR" -name "*.jsonl" -type f -mtime -7 | head -50 | while read -r f; do
        cp "$f" "$BUNDLE_DIR/jobs/" 2>/dev/null || true
    done
    JOB_COUNT=$(ls -1 "$BUNDLE_DIR/jobs" 2>/dev/null | wc -l | tr -d ' ')
    echo "  ✓ Job logs: $JOB_COUNT files"
fi

# Collect system info
echo "[4/4] Collecting system info..."
{
    echo "=== System Info ==="
    echo "Collection Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Hostname: $(hostname)"
    echo "OS: $(uname -s) $(uname -r)"
    echo ""
    echo "=== Environment ==="
    echo "ISENGARD_MODE: ${ISENGARD_MODE:-not set}"
    echo "LOG_DIR: ${LOG_DIR:-not set}"
    echo "VOLUME_ROOT: ${VOLUME_ROOT:-not set}"
    echo "USE_REDIS: ${USE_REDIS:-not set}"
    echo ""
    echo "=== Directory Sizes ==="
    du -sh "$LOG_DIR" 2>/dev/null || echo "Log dir not found"
    du -sh "$VOLUME_ROOT" 2>/dev/null || echo "Volume root not found"
    echo ""
    echo "=== Recent API Errors ==="
    if [ -f "$LOG_DIR/api/latest/api.log" ]; then
        grep '"level":"ERROR"' "$LOG_DIR/api/latest/api.log" 2>/dev/null | tail -20 || echo "No errors found"
    else
        echo "API log not found"
    fi
    echo ""
    echo "=== Recent Worker Errors ==="
    if [ -f "$LOG_DIR/worker/latest/worker.log" ]; then
        grep '"level":"ERROR"' "$LOG_DIR/worker/latest/worker.log" 2>/dev/null | tail -20 || echo "No errors found"
    else
        echo "Worker log not found"
    fi
} > "$BUNDLE_DIR/system_info.txt"
echo "  ✓ System info"

# Create archive
echo ""
echo "Creating archive..."
cd "$OUTPUT_DIR"
tar -czf "$BUNDLE_NAME.tar.gz" "$BUNDLE_NAME"
rm -rf "$BUNDLE_NAME"

ARCHIVE_SIZE=$(du -h "$BUNDLE_NAME.tar.gz" | cut -f1)
echo ""
echo "=== Collection Complete ==="
echo "Archive: $OUTPUT_DIR/$BUNDLE_NAME.tar.gz ($ARCHIVE_SIZE)"
echo ""
echo "To extract:"
echo "  tar -xzf $BUNDLE_NAME.tar.gz"
echo ""
echo "To view logs:"
echo "  cat $BUNDLE_NAME/api-latest/api.log | jq ."
