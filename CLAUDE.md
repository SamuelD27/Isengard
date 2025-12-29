# Isengard - Project Intelligence

> Identity LoRA Training + ComfyUI Image Generation + Video Pipeline (Scaffold)

---

## Mission

Isengard is a **GUI-first platform** for creating personalized AI-generated content. Non-technical users should be able to train identity LoRAs from their photos and generate high-quality images without touching a command line.

---

## Architectural Guardrails (Locked)

> **These patterns are working. Do not deviate without explicit justification.**

### Separation of Concerns (Mandatory)
```
React UI (apps/web) ⇄ FastAPI API (apps/api) ⇄ Worker (apps/worker) ⇄ Plugins (packages/plugins)
```
- Frontend ONLY talks to API via HTTP/SSE
- API queues jobs to Redis; Worker consumes them
- Plugins are loaded by Worker, never imported directly by API

### Plugin Architecture (Mandatory)
- Training/Image/Video backends are **swappable modules** with stable interfaces
- Each plugin lives in `packages/plugins/{type}/src/` with `interface.py` defining the contract
- NO monolithic scripts; NO hardcoded AI logic in route handlers
- Adding a new backend = implement interface + register in plugin registry

### Persistent Storage (Mandatory)
- Heavy artifacts (models, outputs, uploads) → `VOLUME_ROOT` (`/runpod-volume/isengard`)
- Container filesystem = ephemeral caches only
- Path resolution via `packages/shared/src/config.py`, never hardcoded

### Fast-Test vs Production Modes (Mandatory)
- `ISENGARD_MODE=fast-test` → Mock plugins, no GPU, for CI/UI testing
- `ISENGARD_MODE=production` → Real AI-Toolkit + ComfyUI
- Both modes MUST work; tests run in fast-test, prod deploys in production

### Workflow Templates (Mandatory)
- ComfyUI graphs live in `packages/plugins/image/workflows/*.json`
- Workflows are versioned, named files (e.g., `flux-dev-lora.json`)
- NO inline workflow construction in random code paths
- Template placeholders replaced at runtime by `comfyui.py`

### UX Philosophy (Mandatory)
- GUI-first: every feature accessible through web UI
- Progressive disclosure: presets visible, advanced settings collapsed
- Minimal dark theme, professional aesthetic
- Pages: Characters → Dataset → Training → Generate (+ Video scaffold)
- Real-time feedback: SSE for progress, staging workflows for review

### Quality Discipline (Mandatory)
- Fix root causes, not symptoms
- Never disable features to make tests pass
- Add logging/tests when fixing bugs
- If it's broken, mark entire feature as not-ready rather than ship broken

---

## Implemented Features (Do Not Regress)

> **These features are working in production. Any PR that breaks them is rejected.**

### Character Management
- [x] Inline image upload during character creation (not post-creation only)
- [x] Character detail view with image preview grid
- [x] Individual image deletion with confirmation
- [x] Trigger word display and copy

### Dataset Manager
- [x] Global image grid across all characters
- [x] Search by filename or character name
- [x] Filter by character dropdown
- [x] Multi-select with visual checkboxes
- [x] Bulk delete with confirmation dialog

### Training System
- [x] Training presets (Quick/Balanced/High Quality)
- [x] Advanced parameters (optimizer, scheduler, precision, batch size)
- [x] SSE live log streaming with auto-scroll
- [x] Job history with config summary display
- [x] Estimated training time calculation

### Image Generation
- [x] 7 aspect ratio presets with dimension calculation
- [x] Quality tiers (Draft/Standard/High Quality)
- [x] Advanced toggles (ControlNet, IP-Adapter, FaceDetailer, Upscale)
- [x] LoRA selection from trained characters
- [x] Output gallery for completed jobs

### Synthetic Generation
- [x] Generate button visible only for trained characters
- [x] Staging area with Keep/Discard workflow
- [x] Batch generation (1/2/4/8 images)
- [x] Auto-save kept images to training dataset

### FLUX Workflows
- [x] Disaggregated loader pattern: `UNETLoader` + `DualCLIPLoader` + `VAELoader`
- [x] Symlinks from checkpoints → unet folder for FLUX compatibility
- [x] Four workflow variants: schnell, dev, schnell-lora, dev-lora
- [x] LoraLoaderModelOnly for trained character LoRAs

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

### 9. Double-Apply Doctrine (Remote + Local Sync) - CRITICAL

> **Every modification made on a remote RunPod instance MUST also be applied to the local repository.**

When debugging or fixing issues on a live RunPod deployment, code changes are often made directly on the pod to quickly resolve problems. However, these changes are **ephemeral** - they will be lost when:
- The pod is restarted or terminated
- A new Docker image is deployed
- The pod is recreated from template

#### Mandatory Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Connect to RunPod                                           │
│     ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519               │
├─────────────────────────────────────────────────────────────────┤
│  2. Make fix on remote pod                                      │
│     (edit files in /app or /runpod-volume/isengard)            │
├─────────────────────────────────────────────────────────────────┤
│  3. IMMEDIATELY apply same fix to local repo                    │
│     (edit corresponding files in ~/OF/Isengard)                │
├─────────────────────────────────────────────────────────────────┤
│  4. Commit to git with descriptive message                      │
│     git add . && git commit -m "fix: <description>"            │
└─────────────────────────────────────────────────────────────────┘
```

#### Claude Code Responsibilities

When working with remote pods, Claude Code MUST:

1. **Track all remote edits** - Keep a mental list of every file modified on the pod
2. **Mirror changes immediately** - After each remote fix, apply to local repo before moving on
3. **Verify parity** - Compare remote files with local to ensure sync:
   ```bash
   # Compare remote and local file
   ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 "cat /app/path/to/file.py" > /tmp/remote.py
   diff /tmp/remote.py ~/OF/Isengard/path/to/file.py
   ```
4. **Never leave session without syncing** - At end of any remote session, confirm all changes are in local repo

#### Common Remote Locations → Local Equivalents

| Remote Path | Local Path |
|-------------|------------|
| `/app/apps/api/src/` | `apps/api/src/` |
| `/app/apps/web/src/` | `apps/web/src/` |
| `/app/packages/plugins/` | `packages/plugins/` |
| `/app/packages/shared/` | `packages/shared/` |
| `/runpod-volume/isengard/` | `data/` (for artifacts) |

#### SSH Connection Template

```bash
# Standard connection
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519

# Quick file comparison
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 "cat /app/<file>" | diff - ~/OF/Isengard/<file>

# Bulk file list for comparison
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 "find /app -name '*.py' -type f" | sort
```

#### Red Flags (Never Do These)

- ❌ Fix a bug on the pod and forget to apply locally
- ❌ Make "temporary" fixes that never get committed
- ❌ End a session with unsynced changes
- ❌ Push a new Docker image without including all pod fixes

### 10. Auto-Commit All Changes (Docker Image Sync) - CRITICAL

> **Claude Code MUST commit all changes before the user deploys a new Docker image.**

Docker images are built from the git repository. Any uncommitted changes will NOT be included in the image. This has caused deployment issues where the user sees "old" behavior because the fixes were never committed.

#### Mandatory Behavior

1. **Before ending any session** - Check `git status` for uncommitted changes
2. **If changes exist** - Commit them with a descriptive message
3. **Proactive commits** - Don't wait for user to ask; commit after completing work
4. **Atomic commits** - Group related changes; separate unrelated work

#### Commit Triggers

Claude Code MUST commit when ANY of these occur:

- ✅ Finishing a bug fix or feature
- ✅ Modifying `start.sh`, `Dockerfile`, or deployment scripts
- ✅ User mentions deploying, rebuilding, or pushing an image
- ✅ User says they're "done for now" or ending the session
- ✅ Switching to work on an unrelated task

#### Commit Message Format

```bash
git add -A && git commit -m "$(cat <<'EOF'
<type>: <short description>

<optional body with details>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `style`

#### Red Flags (Never Do These)

- ❌ Leave uncommitted changes when user mentions Docker/deployment
- ❌ Assume user will commit later
- ❌ Let a session end with `git status` showing modified files
- ❌ Wait for user to explicitly ask for a commit

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

## Training Debugging Workflow

> **When a training bug occurs, Claude Code MUST follow this exact workflow.**

### 5-Step Debug Protocol (Mandatory)

When investigating any training failure:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 1: Identify job_id + correlation_id                               │
│  ────────────────────────────────────────────────────────────────────── │
│  • Check UI error message for job_id (e.g., "train-abc123")            │
│  • Check API response headers for X-Correlation-ID                      │
│  • If missing, search logs: grep "job_id" logs/api/latest/api.log      │
├─────────────────────────────────────────────────────────────────────────┤
│  STEP 2: Pull events.jsonl + service logs                               │
│  ────────────────────────────────────────────────────────────────────── │
│  • Per-job log: logs/jobs/{job_id}/events.jsonl                        │
│  • API logs: logs/api/latest/api.log                                   │
│  • Worker logs: logs/worker/latest/worker.log                          │
│  • Or use API: GET /api/jobs/{job_id}/logs                             │
├─────────────────────────────────────────────────────────────────────────┤
│  STEP 3: Find first error event                                         │
│  ────────────────────────────────────────────────────────────────────── │
│  • In events.jsonl: grep -n '"level":"ERROR"' events.jsonl | head -1   │
│  • Note timestamp, event type, error message, stack trace              │
│  • Or use API: GET /api/jobs/{job_id}/logs/view?level=ERROR            │
├─────────────────────────────────────────────────────────────────────────┤
│  STEP 4: Provide root cause + minimal fix                               │
│  ────────────────────────────────────────────────────────────────────── │
│  • Cite specific log entries as evidence                               │
│  • Trace error back through correlation_id                             │
│  • Identify which component failed (API/Worker/Plugin)                 │
│  • Propose targeted fix (not shotgun debugging)                        │
├─────────────────────────────────────────────────────────────────────────┤
│  STEP 5: Add regression test or Fast-Test reproduction                  │
│  ────────────────────────────────────────────────────────────────────── │
│  • Add test to tests/test_training_observability.py                    │
│  • Or create minimal Fast-Test reproduction script                     │
│  • Verify fix with: ISENGARD_MODE=fast-test pytest -v                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Per-Job Log Structure

Every training job creates its own log directory:

```
logs/
├── jobs/
│   └── {job_id}/
│       ├── events.jsonl          # Main structured event log
│       └── samples/              # Sample images generated during training
│           ├── step_100.png
│           ├── step_200.png
│           └── ...
└── bundles/
    └── {job_id}_debug.zip        # Debug bundle (on-demand)
```

### events.jsonl Schema

Each line in events.jsonl is a JSON object:

```json
{
  "ts": "2025-01-28T10:30:00.000Z",
  "level": "INFO",
  "service": "api",
  "job_id": "train-abc123",
  "correlation_id": "req-xyz789",
  "event": "training.step",
  "msg": "Training step 100/1000",
  "fields": {
    "step": 100,
    "loss": 0.0523,
    "lr": 0.0001,
    "eta_seconds": 3600
  }
}
```

**Key Event Types:**

| Event | Description |
|-------|-------------|
| `training.start` | Job began, includes config summary |
| `training.step` | Progress update with loss/lr/step |
| `training.sample` | Sample image generated |
| `training.complete` | Job finished successfully |
| `training.failed` | Job failed with error details |
| `subprocess.stdout` | Raw trainer subprocess output |
| `subprocess.stderr` | Raw trainer subprocess errors |

### Debug Bundle Generation

Create a comprehensive debug package for any job:

```bash
# Via CLI
python scripts/debug_bundle.py train-abc123

# Via CLI with custom output path
python scripts/debug_bundle.py train-abc123 --output /tmp/debug.zip

# Via CLI showing first error
python scripts/debug_bundle.py train-abc123 --show-error

# Via API (download ZIP)
curl -O http://localhost:8000/api/jobs/train-abc123/debug-bundle
```

**Bundle Contents:**

```
train-abc123_debug.zip
└── train-abc123/
    ├── README.txt           # Quick reference guide
    ├── metadata.json        # Job configuration (secrets redacted)
    ├── events.jsonl         # Full event log (secrets redacted)
    ├── environment.json     # Runtime environment snapshot
    ├── service_logs/
    │   ├── api.log          # Last 1000 lines from API
    │   └── worker.log       # Last 1000 lines from Worker
    └── samples/
        ├── step_100.png     # Sample images
        └── step_200.png
```

### API Endpoints for Debugging

| Endpoint | Purpose | Example |
|----------|---------|---------|
| `GET /api/jobs/{id}/logs` | Download full events.jsonl | `curl -O .../logs` |
| `GET /api/jobs/{id}/logs/view` | View logs with filtering | `?level=ERROR&limit=50` |
| `GET /api/jobs/{id}/stream` | SSE live progress stream | EventSource in browser |
| `GET /api/jobs/{id}/artifacts` | List all job artifacts | Returns JSON array |
| `GET /api/jobs/{id}/artifacts/samples/{file}` | Download sample image | `step_100.png` |
| `GET /api/jobs/{id}/debug-bundle` | Download ZIP bundle | For offline analysis |
| `GET /api/jobs/{id}/summary` | Quick status check | progress, status, last error |

### Fast-Test Mode Validation

Before deploying fixes, validate in Fast-Test mode:

```bash
# Run full observability test suite
ISENGARD_MODE=fast-test pytest tests/test_training_observability.py -v

# Test specific scenarios
pytest tests/test_training_observability.py::TestLogRedaction -v
pytest tests/test_training_observability.py::TestTrainingProgressEvent -v
pytest tests/test_training_observability.py::TestEventBus -v
pytest tests/test_training_observability.py::TestTrainingJobLogger -v
pytest tests/test_training_observability.py::TestMockPluginSampleGeneration -v
```

### Common Debugging Scenarios

#### Scenario: Training never starts

```bash
# 1. Check if job was created
curl http://localhost:8000/api/jobs/train-xxx/summary

# 2. Check API logs for queue errors
grep "train-xxx" logs/api/latest/api.log | jq .

# 3. Check worker is running and consuming
grep "job.start" logs/worker/latest/worker.log | tail -10
```

#### Scenario: Training fails mid-run

```bash
# 1. Get events around failure
curl "http://localhost:8000/api/jobs/train-xxx/logs/view?level=ERROR"

# 2. Check for subprocess errors
grep "subprocess" logs/jobs/train-xxx/events.jsonl | jq .

# 3. Generate debug bundle for full context
python scripts/debug_bundle.py train-xxx --show-error
```

#### Scenario: Samples not appearing in UI

```bash
# 1. Check if samples were generated
ls logs/jobs/train-xxx/samples/

# 2. Check sample events in log
grep "training.sample" logs/jobs/train-xxx/events.jsonl | jq .

# 3. Verify artifact endpoint
curl http://localhost:8000/api/jobs/train-xxx/artifacts
```

#### Scenario: SSE stream not updating

```bash
# 1. Check EventBus is publishing
grep "event_bus.publish" logs/api/latest/api.log | tail -20

# 2. Verify SSE endpoint responds
curl -N http://localhost:8000/api/jobs/train-xxx/stream

# 3. Check for subscription errors
grep "subscribe" logs/api/latest/api.log | jq .
```

### Debugging Checklist for Claude Code

When debugging any training issue, verify:

- [ ] `job_id` identified from error message or logs
- [ ] `correlation_id` traced through all services
- [ ] Per-job `events.jsonl` located and examined
- [ ] First ERROR event timestamp noted
- [ ] Root cause identified with log evidence
- [ ] Fix proposed and tested in Fast-Test mode
- [ ] Regression test added or reproduction documented

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

## UI Flows (Current)

### Frontend Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Redirect | Redirects to `/characters` |
| `/characters` | Characters | Character CRUD, image upload/view/delete |
| `/dataset` | Dataset Manager | Global image browser with filters and bulk actions |
| `/training` | Training | LoRA training configuration and job monitoring |
| `/generate` | Image Generation | Prompt-based generation with advanced toggles |
| `/video` | Video | Scaffold only (Coming Soon) |

### Character Management Flow

```
Create Character → Upload Images → View/Manage Images → Start Training
     ↓                 ↓                 ↓                   ↓
POST /characters  POST /images    GET/DELETE /images   POST /training
```

### Image Generation Flow

```
Select Aspect Ratio → Configure Toggles → Enter Prompt → Generate
        ↓                    ↓                 ↓            ↓
  Update W×H         use_controlnet      prompt text   POST /generation
                     use_ipadapter
                     use_facedetailer
                     use_upscale
```

---

## API Contracts (Current)

### Character Endpoints

```
GET  /api/characters                    → List all characters
POST /api/characters                    → Create character
GET  /api/characters/{id}               → Get character
PATCH /api/characters/{id}              → Update character
DELETE /api/characters/{id}             → Delete character
POST /api/characters/{id}/images        → Upload images (multipart)
GET  /api/characters/{id}/images        → List images
GET  /api/characters/{id}/images/{file} → Serve image file
DELETE /api/characters/{id}/images/{file} → Delete image
```

### Training Endpoints

```
POST /api/training                      → Start training job
GET  /api/training                      → List jobs
GET  /api/training/{id}                 → Get job status
GET  /api/training/{id}/stream          → SSE progress stream
POST /api/training/{id}/cancel          → Cancel job
```

### Generation Endpoints

```
POST /api/generation                    → Start generation job
GET  /api/generation                    → List jobs
GET  /api/generation/{id}               → Get job status
GET  /api/generation/{id}/stream        → SSE progress stream
POST /api/generation/{id}/cancel        → Cancel job
```

### Generation Request Schema

```typescript
interface GenerationConfig {
  prompt: string
  negative_prompt: string
  width: number          // 512-2048
  height: number         // 512-2048
  steps: number          // 1-100
  guidance_scale: number // 1-20
  seed: number | null
  lora_id: string | null
  lora_strength: number  // 0-1.5
  // Advanced toggles
  use_controlnet: boolean
  use_ipadapter: boolean
  use_facedetailer: boolean
  use_upscale: boolean
}
```

---

## ComfyUI Workflow Architecture

### FLUX Model Requirements

FLUX models use a **disaggregated architecture** with separate components:

| Component | Node Type | Model File |
|-----------|-----------|------------|
| UNET | `UNETLoader` | `flux1-dev.safetensors` or `flux1-schnell.safetensors` |
| CLIP-L | `DualCLIPLoader` | `clip_l.safetensors` |
| T5-XXL | `DualCLIPLoader` | `t5xxl_fp16.safetensors` |
| VAE | `VAELoader` | `ae.safetensors` |

### Workflow Files

| Workflow | Use Case | Key Nodes |
|----------|----------|-----------|
| `flux-schnell.json` | Fast generation (4 steps) | UNETLoader, DualCLIPLoader, VAELoader |
| `flux-dev.json` | Quality generation (20 steps) | Same as schnell |
| `flux-schnell-lora.json` | Fast + LoRA | + LoraLoaderModelOnly |
| `flux-dev-lora.json` | Quality + LoRA | + LoraLoaderModelOnly |

### Template Processing

Workflows use placeholder values that are replaced at runtime:

```python
# In comfyui.py _load_workflow()
workflow_text = re.sub(r'{{WIDTH}}', '512', workflow_text)
workflow_text = re.sub(r'{{HEIGHT}}', '512', workflow_text)
# ... etc

# In _inject_parameters()
workflow_str = workflow_str.replace('"width": 512', f'"width": {config.width}')
```

---

*This document is the source of truth for project conventions. Update it when patterns change.*
