# Isengard - Project Intelligence

> Identity LoRA Training + ComfyUI Image Generation + Video Pipeline (Scaffold)

---

## Mission

Isengard is a **GUI-first platform** for creating personalized AI-generated content. Non-technical users should be able to train identity LoRAs from their photos and generate high-quality images without touching a command line.

---

## Non-Negotiables

These rules are **absolute** and override any convenience shortcuts:

### 1. GUI-First, Refined UX
- Every feature must be usable through the web interface
- Progressive disclosure: simple defaults, advanced options hidden until needed
- Clear tooltips and explanations for technical parameters
- Real-time feedback for long-running operations (training, generation)

### 2. Plugin Architecture - No Monoliths
- Training backends, image pipelines, and video pipelines are **swappable modules**
- Each plugin implements a stable interface defined in `packages/plugins/*/interface.py`
- Core application code NEVER imports plugin internals directly
- Adding a new training backend should require only implementing the interface + config

### 3. Persistent Storage Correctness
| Environment | Location | Purpose |
|-------------|----------|---------|
| Local Dev | `./data/uploads/` | User-uploaded training images |
| Local Dev | `./data/models/` | Trained LoRA models |
| Local Dev | `./data/outputs/` | Generated images/videos |
| Local Dev | `./logs/` | Observability logs (persisted) |
| Local Dev | `./tmp/` | Ephemeral scratch space |
| RunPod | `/runpod-volume/` or `/workspace/` | ALL persistent data |
| RunPod | Container filesystem | Ephemeral only |

**Rule:** Never assume local paths exist in production. Use environment-based path resolution.

### 4. Observability First
- Structured JSON logging is **mandatory** from day 1
- Every request has a correlation ID propagated through the entire stack
- Logging is not optional, not "added later"
- See [Observability Standard](#observability-standard) for details

### 5. No "Give Up" Fixes
- Failing tests must be fixed at the root cause
- Never disable/skip features to make tests pass
- Never comment out code that "doesn't work yet"
- If something is broken, fix it or mark the entire feature as not ready

### 6. Training Scope (Current)
| Method | Status | Notes |
|--------|--------|-------|
| LoRA | **Supported** | Primary training method via AI-Toolkit |
| DoRA | Not Supported | May be added in future |
| Full Fine-Tune | Not Supported | Out of scope |

### 7. Video is Scaffold-Only
- Video pipeline interface exists for future implementation
- UI shows "In Development" banner
- No video generation code should be executed
- This is clearly communicated to users

### 8. No Fragile Version Assumptions
- ComfyUI workflows should use stable node names, not version-specific hacks
- Pin critical dependencies in requirements.txt / package.json
- Design for safe upgrades: isolate version-specific code in adapters

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐│
│  │Characters│ │ Training │ │ Image Gen│ │ Video (In Dev)       ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP/SSE
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend API (FastAPI)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐│
│  │  Routes  │ │ Services │ │  Queue   │ │   Shared Logging     ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │ Redis Queue
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Worker (Background Jobs)                    │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                    Plugin Executor                           ││
│  └──────────────────────────────────────────────────────────────┘│
│       │                    │                    │                │
│       ▼                    ▼                    ▼                │
│  ┌─────────┐         ┌──────────┐         ┌─────────┐           │
│  │Training │         │  Image   │         │  Video  │           │
│  │ Plugin  │         │  Plugin  │         │ Plugin  │           │
│  │(AI-Tklt)│         │(ComfyUI) │         │(Scaffold│           │
│  └─────────┘         └──────────┘         └─────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Shared Libraries                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐│
│  │  Types   │ │  Config  │ │ Logging  │ │   Utilities          ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
isengard/
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── src/
│   │   │   ├── routes/      # HTTP endpoints
│   │   │   ├── services/    # Business logic
│   │   │   └── models/      # Pydantic models
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── worker/              # Background job processor
│   │   ├── src/
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── web/                 # React frontend
│       ├── src/
│       │   ├── components/  # Reusable UI components
│       │   ├── pages/       # Route-based pages
│       │   ├── hooks/       # Custom React hooks
│       │   └── lib/         # Utilities
│       ├── package.json
│       └── Dockerfile
├── packages/
│   ├── shared/              # Shared Python utilities
│   │   └── src/
│   │       ├── logging.py   # Structured logging
│   │       ├── config.py    # Environment config
│   │       └── types.py     # Shared type definitions
│   └── plugins/
│       ├── training/        # Training backend plugins
│       │   ├── src/
│       │   │   ├── interface.py    # Abstract base class
│       │   │   └── ai_toolkit.py   # AI-Toolkit adapter
│       │   └── __init__.py
│       ├── image/           # Image generation plugins
│       │   ├── src/
│       │   │   ├── interface.py    # Abstract base class
│       │   │   └── comfyui.py      # ComfyUI adapter
│       │   └── __init__.py
│       └── video/           # Video generation (scaffold)
│           ├── src/
│           │   └── interface.py    # Abstract base class only
│           └── __init__.py
├── infra/
│   └── docker/              # Docker configurations
├── scripts/                 # Development helper scripts
├── reports/                 # Generated reports
├── data/                    # Local dev artifacts (gitignored)
├── logs/                    # Observability logs
└── tmp/                     # Ephemeral scratch space
```

---

## Fast-Test vs Production Modes

### Fast-Test Mode
**Purpose:** Validate wiring, endpoints, and UI flow without GPU or large models.

| Aspect | Configuration |
|--------|---------------|
| Training | Mock trainer that creates placeholder `.safetensors` file |
| Image Gen | Returns pre-cached sample images or solid color placeholders |
| Models | No model downloads; use stubs |
| Hardware | CPU-only, minimal RAM |
| Use Case | CI/CD, local development, UI testing |

**Activation:** `ISENGARD_MODE=fast-test`

### Production Mode
**Purpose:** Full-quality training and generation with SOTA models.

| Aspect | Configuration |
|--------|---------------|
| Training | AI-Toolkit with FLUX.1-dev LoRA (or best pinned version) |
| Image Gen | ComfyUI with FLUX/SDXL workflows |
| Models | Full model downloads to persistent volume |
| Hardware | GPU required (minimum: RTX 3090/A5000) |
| Use Case | Actual user-facing deployments |

**Activation:** `ISENGARD_MODE=production`

---

## Observability Standard

### Structured Logging Requirements

All services MUST emit JSON-formatted logs with these fields:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "level": "INFO",
  "service": "api",
  "correlation_id": "req-abc123",
  "message": "Training job started",
  "context": {
    "character_id": "char-xyz",
    "job_id": "job-456"
  }
}
```

### Correlation ID Propagation

```
Frontend                  Backend API              Worker
   │                          │                       │
   │ X-Correlation-ID: abc123 │                       │
   ├─────────────────────────►│                       │
   │                          │ correlation_id: abc123│
   │                          ├──────────────────────►│
   │                          │                       │
   │   SSE: job progress      │                       │
   │◄─────────────────────────┤◄──────────────────────┤
```

- Frontend generates `X-Correlation-ID` header for each user action
- Backend extracts and propagates to all downstream calls
- Worker includes in all job-related log messages
- SSE events include correlation ID for client-side matching

### Log File Layout

```
logs/
├── api/
│   ├── 2024-01-15.log
│   └── 2024-01-16.log
├── worker/
│   ├── 2024-01-15.log
│   └── 2024-01-16.log
└── frontend/
    └── 2024-01-15.log
```

### Retention Policy
- Keep 30 days of logs locally
- Rotate daily, compress after 7 days
- In production, ship to external log aggregator (phase 2)

### Redaction Rules

The logging module MUST redact these patterns before writing:

| Pattern | Replacement | Example |
|---------|-------------|---------|
| `hf_[A-Za-z0-9]+` | `hf_***REDACTED***` | HuggingFace tokens |
| `sk-[A-Za-z0-9]+` | `sk-***REDACTED***` | API keys |
| `/Users/*/` | `/[HOME]/` | Local user paths |
| `token=[^&\s]+` | `token=***` | URL tokens |
| `password=.*` | `password=***` | Passwords |

### 🔒 Logging-First Troubleshooting Doctrine (Non-Negotiable)

This doctrine is **MANDATORY** for all development and debugging activities in Isengard.

#### Core Principles

1. **All services MUST emit structured JSON logs for every action**
   - Not just errors — INFO-level and above for every meaningful operation
   - Every request, job start/stop, state transition, and external call must be logged
   - Silence is failure; if something happens and there's no log, the code is incomplete

2. **Logs are the PRIMARY source of truth for system behavior**
   - The question "what happened?" is answered by logs, not by reading code
   - If logs contradict code, investigate the discrepancy — don't assume code is correct
   - Debug sessions start with logs, not breakpoints

3. **Claude Code MUST inspect, organize, and summarize logs BEFORE reasoning about any bug**
   - Step 1: Locate the relevant log files
   - Step 2: Organize by correlation ID and timestamp
   - Step 3: Read end-to-end, noting anomalies
   - Step 4: Summarize findings in writing
   - Step 5: ONLY THEN propose hypotheses

4. **Claude Code MUST automatically rotate logs per service per day and archive previous runs**
   - Log directory structure: `logs/{service}/latest/` and `logs/{service}/archive/YYYYMMDD_HHMMSS/`
   - On each run, move `latest/` to `archive/{timestamp}/` before writing new logs
   - Each session boundary is clearly marked

5. **Claude Code is NOT allowed to propose solutions without citing evidence from logs**
   - Every bug fix proposal must reference specific log entries
   - "I suspect X" without log evidence is not acceptable
   - If logs don't show the problem, add logging first

6. **If logs are insufficient, improving logging is the first fix**
   - Missing logs > Missing features in priority
   - A feature without observability is not complete
   - "Add logging" is never tech debt — it's the primary deliverable

#### Log Directory Structure (Target State)

```
logs/
├── api/
│   ├── latest/
│   │   └── api.log
│   └── archive/
│       ├── 20250125_143022/
│       │   └── api.log
│       └── 20250125_102015/
│           └── api.log
├── worker/
│   ├── latest/
│   │   ├── worker.log
│   │   └── subprocess/
│   │       ├── train-abc123.stdout.log
│   │       └── train-abc123.stderr.log
│   └── archive/
│       └── .../
└── web/
    ├── latest/
    │   └── client.log
    └── archive/
        └── .../
```

#### Required Log Schema

Every log entry MUST contain:

```json
{
  "timestamp": "2025-01-25T14:30:00.000Z",
  "level": "INFO|WARN|ERROR|DEBUG",
  "service": "api|worker|web",
  "correlation_id": "req-abc123",
  "message": "Human-readable description",
  "event": "request.start|job.progress|error.unhandled",
  "context": { }
}
```

#### Verification Commands

```bash
# Check log structure
scripts/validate_logs.py

# Run observability smoke test
scripts/obs_smoke_test.py

# Tail structured logs with formatting
tail -f logs/api/latest/api.log | jq .
```

---

## Development Workflow

### Local Run (One Command)

```bash
# Start all services
docker-compose up

# Or with build
docker-compose up --build
```

### Individual Services (Development)

```bash
# Backend API
cd apps/api && pip install -r requirements.txt && uvicorn src.main:app --reload

# Worker
cd apps/worker && pip install -r requirements.txt && python -m src.main

# Frontend
cd apps/web && npm install && npm run dev
```

### Lint, Format, Test

```bash
# Python (backend + worker)
ruff check .
ruff format .
pytest

# TypeScript (frontend)
npm run lint
npm run format
npm test
```

### Definition of Done (PR/Commit Checklist)

Before any PR is merged:

- [ ] All tests pass (`pytest` / `npm test`)
- [ ] Linting passes (`ruff check` / `npm run lint`)
- [ ] No new warnings introduced
- [ ] Structured logging added for new code paths
- [ ] Correlation IDs propagated correctly
- [ ] Documentation updated if behavior changed
- [ ] No secrets or local paths in code
- [ ] Tested in both fast-test and production modes (if applicable)

---

## Training Backend Protection Rule

> **Core training logic must be treated as stable infrastructure.**

Once a training backend plugin (e.g., AI-Toolkit adapter) is integrated and working:

1. **Changes to training internals require:**
   - Explicit design note in PR description
   - Version bump in plugin metadata
   - Before/after comparison of training results

2. **Typical fixes should be in:**
   - Configuration handling
   - I/O and file management
   - Logging and error reporting
   - Interface compliance

3. **Never modify directly without justification:**
   - Optimizer settings
   - Learning rate schedules
   - Loss calculations
   - Data augmentation pipelines

---

## Capability Matrix

This matrix is authoritative for what features are supported:

```python
# packages/shared/src/capabilities.py

CAPABILITIES = {
    "training": {
        "lora": {
            "supported": True,
            "backend": "ai-toolkit",
            "status": "production"
        },
        "dora": {
            "supported": False,
            "status": "not_implemented",
            "notes": "May be added in future versions"
        },
        "full_finetune": {
            "supported": False,
            "status": "out_of_scope",
            "notes": "Not planned for this project"
        }
    },
    "image_generation": {
        "comfyui": {
            "supported": True,
            "status": "production"
        }
    },
    "video_generation": {
        "any": {
            "supported": False,
            "status": "scaffold_only",
            "notes": "Interface defined, no implementation"
        }
    }
}
```

---

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `ISENGARD_MODE` | Operating mode | `fast-test` or `production` |
| `DATA_DIR` | Persistent data directory | `/data` or `/runpod-volume/data` |
| `REDIS_URL` | Redis connection for job queue | `redis://localhost:6379` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Minimum log level | `INFO` |
| `LOG_DIR` | Log file directory | `./logs` |
| `API_PORT` | Backend API port | `8000` |
| `WORKER_CONCURRENCY` | Max parallel jobs | `1` |
| `COMFYUI_URL` | ComfyUI server endpoint | `http://localhost:8188` |

---

## Common Patterns

### Adding a New API Endpoint

```python
# apps/api/src/routes/example.py
from fastapi import APIRouter, Depends
from packages.shared.src.logging import get_logger, with_correlation_id

router = APIRouter()
logger = get_logger("api.example")

@router.post("/example")
@with_correlation_id
async def example_endpoint(request: ExampleRequest):
    logger.info("Processing example request", extra={"input": request.dict()})
    # ... implementation
    return {"status": "ok"}
```

### Adding a New Plugin

1. Create interface in `packages/plugins/<type>/src/interface.py`
2. Implement adapter in `packages/plugins/<type>/src/<adapter>.py`
3. Register in plugin registry
4. Add capability to matrix
5. Add tests for interface compliance

---

## Quick Reference Commands

```bash
# Run in fast-test mode
ISENGARD_MODE=fast-test docker-compose up

# Run in production mode
ISENGARD_MODE=production docker-compose up

# View logs
tail -f logs/api/$(date +%Y-%m-%d).log | jq .

# Run tests
docker-compose exec api pytest
docker-compose exec web npm test

# Check capabilities
python -c "from packages.shared.src.capabilities import CAPABILITIES; print(CAPABILITIES)"
```

---

*This document is the source of truth for project conventions. Update it when patterns change.*
