# Isengard Observability Guide

This document explains how to trace any GUI action through the system using correlation IDs and structured logs.

## Architecture Overview

```
Frontend (React)           Backend (FastAPI)           Worker (Async)
    │                           │                          │
    ├─ Generate Correlation ID  │                          │
    │                           │                          │
    ├─ X-Correlation-ID: abc123 │                          │
    ├─────────────────────────► │                          │
    │                           ├─ Log request.start       │
    │                           ├─ Process request         │
    │                           ├─ Submit job (if async)   │
    │                           │                          │
    │                           ├──────────────────────────►
    │                           │                          ├─ Log job.start
    │                           │                          ├─ Process job
    │                           │                          ├─ Log progress
    │◄──────────────────────────┤◄─────────────────────────┤
    │  Response + SSE stream    │   Progress updates       │
```

## Correlation ID Flow

Every user action in the GUI generates a unique correlation ID that flows through the entire system:

1. **Frontend**: Generates `corr-{timestamp}-{random}` for each action
2. **API Request**: Sent via `X-Correlation-ID` header
3. **Backend**: Extracts from header or generates if missing
4. **Logs**: All log entries include the correlation ID
5. **Worker**: Receives correlation ID with job payload
6. **Response**: Returned in `X-Correlation-ID` header

## Log Locations

### Service Logs

| Service | Location | Format |
|---------|----------|--------|
| API | `logs/api/latest/api.log` | JSON lines |
| Worker | `logs/worker/latest/worker.log` | JSON lines |
| Web | Browser console + `logs/web/latest/` (if configured) | JSON |

### Job-Specific Logs

Each background job gets a dedicated log file:
- **Location**: `$VOLUME_ROOT/logs/jobs/{job_id}.jsonl`
- **Format**: JSON lines with full context
- **Access**: `GET /api/jobs/{job_id}/logs`

### Log Rotation

On each service restart:
1. `logs/{service}/latest/` is moved to `logs/{service}/archive/{timestamp}/`
2. A fresh `logs/{service}/latest/` directory is created

## Log Entry Format

All log entries follow this schema:

```json
{
  "timestamp": "2025-01-15T10:30:00.000Z",
  "level": "INFO",
  "service": "api",
  "logger": "api.routes.training",
  "correlation_id": "corr-1705312200000-abc123",
  "message": "Training job created",
  "event": "job.created",
  "context": {
    "job_id": "train-abc123def456",
    "character_id": "char-xyz789",
    "steps": 1000
  }
}
```

## Tracing a GUI Action

### Example: Create Character

1. **Find the correlation ID** from browser DevTools:
   - Network tab → Request Headers → `X-Correlation-ID`
   - Example: `corr-1705312200000-abc123`

2. **Search backend logs**:
   ```bash
   grep "corr-1705312200000-abc123" logs/api/latest/api.log | jq .
   ```

3. **Expected log sequence**:
   ```
   request.start  → POST /api/characters
   job.created    → Character created
   request.end    → 201 Created
   ```

### Example: Start Training

1. **Find correlation ID** from browser or response header

2. **Search API logs**:
   ```bash
   grep "corr-xxx" logs/api/latest/api.log | jq .
   ```

3. **Search worker logs** (if using Redis):
   ```bash
   grep "corr-xxx" logs/worker/latest/worker.log | jq .
   ```

4. **Get job-specific logs**:
   ```bash
   cat $VOLUME_ROOT/logs/jobs/train-abc123.jsonl | jq .
   ```

## Event Types

### Request Events
| Event | Description |
|-------|-------------|
| `request.start` | HTTP request received |
| `request.end` | HTTP response sent |
| `request.error` | Unhandled exception |

### Job Events
| Event | Description |
|-------|-------------|
| `job.created` | Job created and queued |
| `job.queued` | Job submitted to Redis |
| `job.start` | Worker started processing |
| `job.progress` | Progress update |
| `job.completed` | Job finished successfully |
| `job.failed` | Job failed with error |
| `job.cancelled` | Job cancelled by user |

### System Events
| Event | Description |
|-------|-------------|
| `system.startup` | Service starting |
| `system.ready` | Service ready |
| `system.shutdown` | Service shutting down |

## Useful Commands

### Tail API Logs (Pretty Print)
```bash
tail -f logs/api/latest/api.log | jq .
```

### Find Errors
```bash
grep '"level":"ERROR"' logs/api/latest/api.log | jq .
```

### Find Slow Requests (>1s)
```bash
grep '"event":"request.end"' logs/api/latest/api.log | \
  jq 'select(.context.duration_ms > 1000)'
```

### List Recent Job IDs
```bash
grep '"event":"job.created"' logs/api/latest/api.log | \
  jq -r '.context.job_id' | tail -20
```

### Collect All Logs for Debugging
```bash
./scripts/collect_logs.sh
# Creates: logs/bundle-{timestamp}.tar.gz
```

## Secret Redaction

The logging system automatically redacts sensitive data:

| Pattern | Replacement |
|---------|-------------|
| `hf_*` | `hf_***REDACTED***` |
| `sk-*` | `sk-***REDACTED***` |
| `ghp_*` | `ghp_***REDACTED***` |
| `/Users/*/` | `/[HOME]/` |
| `token=*` | `token=***` |
| `password=*` | `password=***` |

## Debugging Checklist

When investigating a failed GUI action:

1. [ ] Get correlation ID from browser DevTools
2. [ ] Search API logs for the correlation ID
3. [ ] Check for `request.error` events
4. [ ] If async job, search worker logs
5. [ ] Check job-specific log file
6. [ ] Look for the last successful event before failure
7. [ ] Check response status code in `request.end`

## Log Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum log level |
| `LOG_DIR` | `./logs` | Log directory |
| `LOG_TO_FILE` | `true` | Write to files |
| `LOG_TO_STDOUT` | `true` | Write to console |

## Frontend Logging

The frontend logs all API requests via the `api.ts` client:

```javascript
// All requests automatically include:
// - X-Correlation-ID header
// - Request timing
// - Response status

// View in browser console:
// [API] POST /api/characters → 201 (45ms) corr-xxx
```

To enable persistent frontend logs, configure the `logger.ts` module to send logs to `/api/client-logs`.
