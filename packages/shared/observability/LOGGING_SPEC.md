# Isengard Logging Specification

**Version:** 1.0
**Status:** Authoritative
**Last Updated:** 2025-12-26

---

## Overview

This document defines the logging contract for all Isengard services. Compliance is **mandatory** and verified via automated scripts.

---

## Log Entry Schema

Every log entry MUST be a valid JSON object with these fields:

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string (ISO 8601) | UTC timestamp with milliseconds: `2025-01-25T14:30:00.123Z` |
| `level` | string | One of: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `service` | string | Service identifier: `api`, `worker`, `web` |
| `logger` | string | Logger name: `api.routes.training`, `worker.executor` |
| `message` | string | Human-readable log message |

### Conditional Fields

| Field | Type | When Required |
|-------|------|---------------|
| `correlation_id` | string | When processing a user request (e.g., `req-abc123`) |
| `event` | string | For structured event logging (see Event Types) |
| `context` | object | When additional structured data is available |
| `exception` | string | When logging an exception (includes traceback) |
| `job_id` | string | When processing a job (in context or top-level) |
| `character_id` | string | When operating on a character (in context) |
| `duration_ms` | number | For timing-sensitive operations (in context) |

---

## Event Types

Use the `event` field for structured event categorization:

### Request Events
- `request.start` - HTTP request received
- `request.end` - HTTP response sent
- `request.error` - Request failed with error

### Job Events
- `job.queued` - Job added to queue
- `job.start` - Job execution started
- `job.progress` - Job progress update
- `job.complete` - Job completed successfully
- `job.failed` - Job failed with error
- `job.cancelled` - Job was cancelled

### Training Events
- `training.init` - Training initialization
- `training.step` - Training step completed
- `training.checkpoint` - Checkpoint saved
- `training.complete` - Training finished

### Generation Events
- `generation.init` - Generation initialization
- `generation.step` - Generation step
- `generation.complete` - Generation finished

### System Events
- `system.startup` - Service starting
- `system.ready` - Service ready
- `system.shutdown` - Service shutting down
- `system.health` - Health check

---

## Directory Structure

```
logs/
├── api/
│   ├── latest/
│   │   └── api.log           # Current session log
│   └── archive/
│       ├── 20250125_143022/  # Previous session (timestamp)
│       │   └── api.log
│       └── 20250125_102015/
│           └── api.log
├── worker/
│   ├── latest/
│   │   ├── worker.log        # Main worker log
│   │   └── subprocess/       # Job subprocess output
│   │       ├── train-abc123.stdout.log
│   │       └── train-abc123.stderr.log
│   └── archive/
│       └── .../
└── web/
    ├── latest/
    │   └── client.log        # Client-side logs posted to server
    └── archive/
        └── .../
```

### Rules

1. **`latest/`** contains logs from the current session only
2. **`archive/YYYYMMDD_HHMMSS/`** contains logs from previous sessions
3. On service startup, `rotate_logs()` MUST be called to archive `latest/`
4. Archive directories are named with the timestamp when archiving occurred
5. Subprocess logs include job ID in filename for correlation

---

## Log Rotation

### On Service Startup

1. Check if `logs/{service}/latest/` contains files
2. If yes, move entire `latest/` to `archive/{timestamp}/`
3. Create new empty `latest/` directory
4. Begin logging to `latest/{service}.log`

### Implementation

```python
from packages.shared.src.logging import rotate_logs, configure_logging

# At service startup
rotate_logs("api")  # Archives previous session
configure_logging("api")  # Sets up new session
```

---

## Subprocess Logging

For background jobs that spawn subprocesses (training, generation):

### Capture Requirements

1. **stdout** → `logs/worker/latest/subprocess/{job_id}.stdout.log`
2. **stderr** → `logs/worker/latest/subprocess/{job_id}.stderr.log`
3. Main worker log includes references to subprocess files

### Example Worker Log Entry

```json
{
  "timestamp": "2025-01-25T14:30:00.123Z",
  "level": "INFO",
  "service": "worker",
  "event": "job.start",
  "correlation_id": "req-abc123",
  "message": "Starting training job",
  "context": {
    "job_id": "train-xyz789",
    "character_id": "char-abc",
    "subprocess_stdout": "logs/worker/latest/subprocess/train-xyz789.stdout.log",
    "subprocess_stderr": "logs/worker/latest/subprocess/train-xyz789.stderr.log"
  }
}
```

---

## Redaction Rules

These patterns MUST be redacted before logging:

| Pattern | Replacement | Example |
|---------|-------------|---------|
| `hf_[A-Za-z0-9]+` | `hf_***REDACTED***` | HuggingFace tokens |
| `sk-[A-Za-z0-9]+` | `sk-***REDACTED***` | OpenAI API keys |
| `ghp_[A-Za-z0-9]+` | `ghp_***REDACTED***` | GitHub tokens |
| `rpa_[A-Za-z0-9]+` | `rpa_***REDACTED***` | RunPod API keys |
| `/Users/*/` | `/[HOME]/` | macOS home paths |
| `/home/*/` | `/[HOME]/` | Linux home paths |
| `token=[^&\s]+` | `token=***` | URL token params |
| `password=[^\s&]+` | `password=***` | Password params |
| `api_key=[^\s&]+` | `api_key=***` | API key params |
| `"password": "..."` | `"password": "***"` | JSON passwords |
| `"token": "..."` | `"token": "***"` | JSON tokens |

---

## Client-Side Logging

Frontend (web) logs are collected via a dedicated API endpoint.

### Collection Endpoint

```
POST /api/client-logs
Content-Type: application/json
X-Correlation-ID: req-abc123

{
  "entries": [
    {
      "timestamp": "2025-01-25T14:30:00.123Z",
      "level": "INFO",
      "event": "ui.button.click",
      "message": "User clicked Start Training",
      "context": {
        "component": "TrainingForm",
        "character_id": "char-abc"
      }
    }
  ]
}
```

### Client Log Schema

Client entries include:

| Field | Required | Description |
|-------|----------|-------------|
| `timestamp` | Yes | Client-side timestamp |
| `level` | Yes | Log level |
| `message` | Yes | Log message |
| `event` | No | UI event type |
| `context` | No | Additional data |

### UI Event Types

- `ui.page.view` - Page navigation
- `ui.button.click` - Button interaction
- `ui.form.submit` - Form submission
- `ui.error.boundary` - React error boundary triggered
- `ui.api.request` - API call initiated
- `ui.api.response` - API response received
- `ui.sse.connect` - SSE connection established
- `ui.sse.message` - SSE message received
- `ui.sse.error` - SSE error

---

## Validation

Logs are validated using `scripts/validate_logs.py`:

### Checks Performed

1. **Schema Validation** - Required fields present
2. **JSON Validity** - Each line is valid JSON
3. **Timestamp Format** - ISO 8601 compliance
4. **Level Values** - Only valid levels
5. **Redaction** - No secret patterns detected
6. **Correlation** - IDs propagate correctly

### Running Validation

```bash
# Validate all logs
python scripts/validate_logs.py

# Validate specific service
python scripts/validate_logs.py --service api

# Strict mode (warnings are errors)
python scripts/validate_logs.py --strict
```

---

## Examples

### Request Lifecycle

```json
{"timestamp":"2025-01-25T14:30:00.001Z","level":"INFO","service":"api","event":"request.start","correlation_id":"req-abc123","message":"POST /api/training","context":{"method":"POST","path":"/api/training","client_ip":"127.0.0.1"}}
{"timestamp":"2025-01-25T14:30:00.050Z","level":"INFO","service":"api","event":"job.queued","correlation_id":"req-abc123","message":"Training job queued","context":{"job_id":"train-xyz789","character_id":"char-abc"}}
{"timestamp":"2025-01-25T14:30:00.055Z","level":"INFO","service":"api","event":"request.end","correlation_id":"req-abc123","message":"Request completed","context":{"status_code":201,"duration_ms":54}}
```

### Job Execution

```json
{"timestamp":"2025-01-25T14:30:01.000Z","level":"INFO","service":"worker","event":"job.start","correlation_id":"req-abc123","message":"Starting training job","context":{"job_id":"train-xyz789"}}
{"timestamp":"2025-01-25T14:30:05.000Z","level":"INFO","service":"worker","event":"job.progress","correlation_id":"req-abc123","message":"Training progress","context":{"job_id":"train-xyz789","progress":25,"step":25,"total_steps":100}}
{"timestamp":"2025-01-25T14:30:20.000Z","level":"INFO","service":"worker","event":"job.complete","correlation_id":"req-abc123","message":"Training completed","context":{"job_id":"train-xyz789","output_path":"/[HOME]/data/loras/char-abc/v1.safetensors"}}
```

### Error with Exception

```json
{"timestamp":"2025-01-25T14:30:00.100Z","level":"ERROR","service":"api","event":"request.error","correlation_id":"req-abc123","message":"Training request failed","context":{"error":"Character not found","character_id":"char-invalid"},"exception":"Traceback (most recent call last):\n  File \"routes/training.py\", line 45, in start_training\n    character = get_character(character_id)\n  File \"services/characters.py\", line 23, in get_character\n    raise CharacterNotFoundError(character_id)\nCharacterNotFoundError: char-invalid"}
```

---

*This specification is the source of truth for Isengard logging. All services MUST comply.*
