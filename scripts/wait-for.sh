#!/bin/bash
#
# Generic Wait-For Script
#
# Waits for a condition to be met with timeout and retries.
#
# Usage:
#   ./scripts/wait-for.sh http://localhost:8000/health
#   ./scripts/wait-for.sh tcp://localhost:6379
#   ./scripts/wait-for.sh http://localhost:3000 --timeout 60
#   ./scripts/wait-for.sh http://localhost:8000/health --expect-json '{"status":"healthy"}'
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Defaults
TIMEOUT=30
INTERVAL=2
EXPECT_JSON=""
QUIET=""

# Parse arguments
TARGET=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --timeout|-t)
      TIMEOUT="$2"
      shift 2
      ;;
    --interval|-i)
      INTERVAL="$2"
      shift 2
      ;;
    --expect-json|-e)
      EXPECT_JSON="$2"
      shift 2
      ;;
    --quiet|-q)
      QUIET="1"
      shift
      ;;
    -h|--help)
      echo "Usage: ./scripts/wait-for.sh <target> [OPTIONS]"
      echo ""
      echo "Targets:"
      echo "  http://host:port/path   Wait for HTTP 200 response"
      echo "  tcp://host:port         Wait for TCP connection"
      echo ""
      echo "Options:"
      echo "  --timeout, -t SECONDS   Timeout (default: 30)"
      echo "  --interval, -i SECONDS  Check interval (default: 2)"
      echo "  --expect-json, -e JSON  Expect specific JSON in response"
      echo "  --quiet, -q             Suppress output"
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      TARGET="$1"
      shift
      ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "Error: No target specified" >&2
  echo "Usage: ./scripts/wait-for.sh <target>" >&2
  exit 1
fi

log() {
  if [ -z "$QUIET" ]; then
    echo -e "${GREEN}[wait-for]${NC} $1"
  fi
}

warn() {
  if [ -z "$QUIET" ]; then
    echo -e "${YELLOW}[wait-for]${NC} $1"
  fi
}

error() {
  echo -e "${RED}[wait-for]${NC} $1" >&2
}

# Parse target
if [[ "$TARGET" == http://* ]] || [[ "$TARGET" == https://* ]]; then
  PROTOCOL="http"
  URL="$TARGET"
elif [[ "$TARGET" == tcp://* ]]; then
  PROTOCOL="tcp"
  HOST_PORT="${TARGET#tcp://}"
  HOST="${HOST_PORT%%:*}"
  PORT="${HOST_PORT#*:}"
else
  error "Invalid target: $TARGET"
  error "Expected: http://... or tcp://..."
  exit 1
fi

# Wait loop
ELAPSED=0
LAST_ERROR=""

log "Waiting for $TARGET (timeout: ${TIMEOUT}s)..."

while [ $ELAPSED -lt $TIMEOUT ]; do
  if [ "$PROTOCOL" = "http" ]; then
    # HTTP check
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null || echo "000")

    if [ "$RESPONSE" = "200" ]; then
      # Check JSON content if required
      if [ -n "$EXPECT_JSON" ]; then
        BODY=$(curl -s "$URL" 2>/dev/null || echo "{}")
        if echo "$BODY" | grep -q "$EXPECT_JSON"; then
          log "Ready! (HTTP 200, JSON matched)"
          exit 0
        else
          LAST_ERROR="HTTP 200 but JSON mismatch"
        fi
      else
        log "Ready! (HTTP $RESPONSE)"
        exit 0
      fi
    else
      LAST_ERROR="HTTP $RESPONSE"
    fi
  else
    # TCP check
    if nc -z "$HOST" "$PORT" 2>/dev/null; then
      log "Ready! (TCP connected)"
      exit 0
    else
      LAST_ERROR="Connection refused"
    fi
  fi

  sleep "$INTERVAL"
  ELAPSED=$((ELAPSED + INTERVAL))

  if [ -z "$QUIET" ]; then
    echo -n "."
  fi
done

echo ""
error "Timeout after ${TIMEOUT}s waiting for $TARGET"
error "Last error: $LAST_ERROR"
exit 1
