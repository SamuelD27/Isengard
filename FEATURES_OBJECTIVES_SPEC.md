# Isengard Features & Objectives Specification

> **Document Status:** Authoritative specification for Claude Code (VS) and Claude-in-Chrome testing workflows.
>
> **Generated:** 2026-01-03
> **Repo Version:** `33fef9f` (Phase 2 documentation update)

---

## Table of Contents

1. [Scope](#1-scope)
2. [System Goals](#2-system-goals)
3. [Feature List with Acceptance Criteria](#3-feature-list-with-acceptance-criteria)
   - 3.1 [Global Architecture & Modes](#31-global-architecture--modes)
   - 3.2 [Character System](#32-character-system)
   - 3.3 [Dataset Management](#33-dataset-management)
   - 3.4 [Training System](#34-training-system)
   - 3.5 [Logging & Observability](#35-logging--observability)
   - 3.6 [Image Generation](#36-image-generation)
   - 3.7 [Model & Artifact Management](#37-model--artifact-management)
   - 3.8 [Infrastructure & DevOps Rules](#38-infrastructure--devops-rules)
   - 3.9 [Claude Code Integration Rules](#39-claude-code-integration-rules)
4. [Gap Analysis (Prioritized)](#4-gap-analysis-prioritized)
5. [Verification Plan](#5-verification-plan)
6. [Traceability Map](#6-traceability-map)
7. [Glossary](#7-glossary)

---

## 1. Scope

### In Scope

| Area | Description |
|------|-------------|
| Character System | Create, manage, and configure characters with trigger words and training images |
| Dataset Management | Upload, preview, filter, and delete training images across characters |
| Training System | LoRA training via AI-Toolkit with presets, live progress, sample images, checkpoints |
| Image Generation | ComfyUI-based image generation with trained LoRAs |
| Observability/Logging | Structured JSON logging, per-job logs, SSE streaming, log download |
| Infrastructure/DevOps | Docker builds, RunPod network volume persistence, startup scripts |
| Plugin Architecture | Abstracted training/generation backends (currently AI-Toolkit/ComfyUI) |
| Fast-test vs Production | Mode-based behavior switching for CI/testing vs real GPU workloads |

### Out of Scope

| Area | Status |
|------|--------|
| **Video Generation** | Scaffold only - not implemented. `apps/web/src/pages/Video.tsx` is a placeholder. |

---

## 2. System Goals

Isengard is a **GUI-first platform** for personalized AI-generated content. Non-technical users train identity LoRAs from photos and generate images without command line access.

**Core Principles:**

1. **GUI-First**: All operations accessible via web interface; no CLI required for end users
2. **Plugin Architecture**: Training and generation backends are swappable modules (`packages/plugins/*/`)
3. **No-Skip Culture**: Fix root causes, not symptoms; never disable features to make tests pass
4. **Persistent Storage Correctness**: All stateful data on RunPod network volume (`/runpod-volume/isengard/`)
5. **Full Observability**: Structured JSON logging for every action; logs are source of truth for debugging

---

## 3. Feature List with Acceptance Criteria

### 3.1 Global Architecture & Modes

#### Objective
Provide a consistent runtime model from local development to Docker container to RunPod deployment with network volume persistence.

#### User-Visible Behavior
- System operates identically across environments (local, Docker, RunPod)
- `/api/ready` endpoint shows dependency status and mode
- `/api/info` endpoint returns capability schemas for frontend rendering

#### Backend Responsibilities
- **Files:**
  - `packages/shared/src/config.py` - Global configuration with path resolution
  - `apps/api/src/routes/health.py` - Health/ready/info endpoints
  - `start.sh` - Container entrypoint
- **Routes:**
  - `GET /api/health` - Basic health check
  - `GET /api/ready` - Dependency status (ComfyUI, AI-Toolkit, storage)
  - `GET /api/info` - Capability schemas for training and generation

#### Data & Persistence
| Environment | Volume Root | Purpose |
|-------------|-------------|---------|
| RunPod | `/runpod-volume/isengard/` | All persistent data |
| Local Dev | `./data/` | Uploads, models, outputs |
| Container | Ephemeral filesystem | Non-persistent runtime data |

Path resolution via `get_global_config().volume_root` - never hardcoded.

#### Observability
- Startup logs include mode, paths, and dependency status
- `GET /api/ready` returns JSON with dependency health

#### Acceptance Criteria
- [ ] `ISENGARD_MODE=fast-test` runs without GPU, uses mock training
- [ ] `ISENGARD_MODE=production` runs with real AI-Toolkit and ComfyUI
- [ ] `/api/ready` correctly reports ComfyUI as internal service (not exposed externally)
- [ ] Config paths resolve correctly on RunPod network volume

#### Current Status: **Implemented**

#### Evidence
- `packages/shared/src/config.py:21-78` - GlobalConfig class with mode detection
- `apps/api/src/routes/health.py:31-85` - `/ready` endpoint with dependency checks
- `CLAUDE.md` documents the mode system and volume paths

#### Gaps
- None identified for basic mode switching

---

### 3.2 Character System

#### Objective
Allow users to create and manage characters (identities) for LoRA training and generation.

#### User-Visible Behavior
- Character gallery listing all characters with image counts
- Create character form: name, description, trigger word, initial image upload
- Character detail view with image management
- Delete character with confirmation

#### Backend Responsibilities
- **Files:**
  - `apps/api/src/routes/characters.py` - CRUD endpoints
  - `apps/web/src/pages/Characters.tsx` - UI component
  - `packages/shared/src/types.py:42-79` - Character model
- **Routes:**
  - `GET /api/characters` - List all characters
  - `POST /api/characters` - Create character
  - `GET /api/characters/{id}` - Get character detail
  - `PATCH /api/characters/{id}` - Update character
  - `DELETE /api/characters/{id}` - Delete character
  - `POST /api/characters/{id}/images` - Upload images
  - `GET /api/characters/{id}/images/{filename}` - Get image
  - `DELETE /api/characters/{id}/images/{filename}` - Delete image

#### Data & Persistence
- Character metadata: JSON file at `{volume_root}/data/characters/{id}/metadata.json`
- Training images: `{volume_root}/data/characters/{id}/images/`
- Trained LoRA: `{volume_root}/models/loras/{character_id}/`

#### Observability
- Character CRUD operations logged with correlation ID
- Image upload/delete events logged

#### Acceptance Criteria
- [ ] Can create character with name, trigger word, and optional description
- [ ] Can upload multiple images to character
- [ ] Can preview/delete individual images
- [ ] Can delete entire character (with confirmation)
- [ ] Character list shows image count and LoRA trained status
- [ ] Trigger word appears in character detail

#### Current Status: **Implemented**

#### Evidence
- `apps/api/src/routes/characters.py` - Full CRUD implementation (lines 1-247)
- `apps/web/src/pages/Characters.tsx` - UI with create/delete/upload (lines 1-150)
- Image upload working via `POST /api/characters/{id}/images`

#### Gaps
| Gap | Priority |
|-----|----------|
| **Synthetic image generation during creation** - User should be able to generate reference images during character creation | P1 |

**Detail on Synthetic Image Gap:**
- User expectation: During character creation, option to generate/preview/accept/reject synthetic images
- Current state: Only manual image upload supported
- Missing components:
  - UI: No "Generate Preview" button in create form
  - API: No endpoint for generating synthetic images for a character
  - Backend: No integration point between character creation and generation workflow
- Likely location for fix: `apps/web/src/pages/Characters.tsx`, `apps/api/src/routes/characters.py`

---

### 3.3 Dataset Management

#### Objective
Provide a first-class view of all training images across characters with filtering and bulk operations.

#### User-Visible Behavior
- Global image grid showing all images from all characters
- Filter by character
- Search by filename or character name
- Select multiple images
- Bulk delete with confirmation
- Character summary cards with image counts

#### Backend Responsibilities
- **Files:**
  - `apps/web/src/pages/Dataset.tsx` - Dataset page UI
  - Uses existing character image endpoints
- **Routes:** (reuses character routes)
  - `GET /api/characters` - Get all characters
  - `GET /api/characters/{id}/images` - List images per character
  - `DELETE /api/characters/{id}/images/{filename}` - Delete image

#### Data & Persistence
- Images stored per-character at `{volume_root}/data/characters/{id}/images/`
- No separate dataset storage - derived from character images

#### Observability
- Bulk delete operations logged

#### Acceptance Criteria
- [ ] Dataset page shows all images across all characters
- [ ] Can filter by character
- [ ] Can search images
- [ ] Can select multiple images
- [ ] Can bulk delete selected images
- [ ] Shows character name badge on each image

#### Current Status: **Implemented**

#### Evidence
- `apps/web/src/pages/Dataset.tsx` - Full implementation (lines 1-322)
- Grid view with filtering (lines 54-62)
- Bulk delete mutation (lines 65-76)
- Character overview cards (lines 287-316)

#### Gaps
| Gap | Priority |
|-----|----------|
| **Dataset snapshot per training run** - Should capture dataset state at training start | P2 |

**Detail on Snapshot Gap:**
- User expectation: Each training run records which images were used
- Current state: No snapshot mechanism; dataset can change after training starts
- Missing components: Snapshot creation logic, storage of snapshot metadata
- Likely location: `apps/api/src/services/job_executor.py` (training initialization)

---

### 3.4 Training System

#### Objective
Enable users to train LoRA models from character datasets with presets and custom configuration.

#### User-Visible Behavior

**Training History Page** (`/training`):
- List of ONLY successful (completed) training jobs
- Each job shows: character name, base model, preset, steps, date, duration
- Clicking job navigates to detail page
- Badge showing count of ongoing jobs

**Start Training Page** (`/training/start`):
- Character selector (dropdown)
- 3 default presets: Quick (500 steps), Balanced (1000 steps), High Quality (2000 steps)
- Custom option for manual configuration
- Advanced settings (collapsible): optimizer, scheduler, precision, sampling, checkpoints
- No "training tips" or educational content
- On submit: redirects to job detail page

**Ongoing Training Page** (`/training/ongoing`):
- List of running/queued jobs as cards
- Each card shows: character, progress bar, step/total, loss, it/s, elapsed, ETA
- Cancel button per job
- Clicking card navigates to detail page

**Training Detail Page** (`/training/{jobId}`):
- Live progress bar derived from logs
- Full raw logs viewer (no summaries) with filtering
- Sample images panel (generated samples visible)
- Checkpoints panel with download buttons
- Metrics: step, total, progress %, loss, it/s, ETA, elapsed
- GPU stats (utilization, memory, temperature, power)
- Loss chart with real-time updates
- Cancel button (if running)
- Debug bundle download

#### Backend Responsibilities
- **Files:**
  - `apps/api/src/routes/training.py` - Training endpoints (lines 1-221)
  - `apps/api/src/services/job_executor.py` - Training execution (lines 1-600+)
  - `packages/shared/src/types.py:85-165` - TrainingConfig, TrainingJob models
  - `packages/shared/src/events.py` - Event bus and TrainingProgressEvent
- **Routes:**
  - `POST /api/training` - Start training job
  - `GET /api/training` - List all training jobs
  - `GET /api/training/ongoing` - List running jobs
  - `GET /api/training/successful` - List completed jobs
  - `GET /api/training/{id}` - Get job details
  - `POST /api/training/{id}/cancel` - Cancel job
  - `GET /api/jobs/{id}/stream` - SSE progress stream

#### Data & Persistence
- Job metadata: In-memory (volatile across restarts)
- Job logs: `{volume_root}/logs/jobs/{job_id}.jsonl`
- Samples: `{volume_root}/artifacts/jobs/{job_id}/samples/`
- Checkpoints: `{volume_root}/artifacts/jobs/{job_id}/checkpoints/`
- Final model: `{volume_root}/models/loras/{character_id}/`

#### Observability
- TrainingJobLogger writes to JSONL and emits SSE events
- All training steps logged with loss, lr, ETA
- Sample generation events include paths
- Checkpoint saves logged
- Errors captured with full stack traces

#### Acceptance Criteria
- [ ] Training history shows only completed jobs
- [ ] Ongoing training page shows running jobs with live progress
- [ ] Start training form has 3 presets + custom
- [ ] Can select character from dropdown
- [ ] Progress bar updates in real-time via SSE
- [ ] Sample images appear as they're generated
- [ ] Checkpoints downloadable via UI
- [ ] Loss chart updates in real-time
- [ ] GPU stats displayed during training
- [ ] Can cancel running job
- [ ] Debug bundle downloadable

#### Current Status: **Partial**

#### Evidence
- Training history page: `apps/web/src/pages/TrainingHistory.tsx` (complete)
- Ongoing training page: `apps/web/src/pages/OngoingTraining.tsx` (complete)
- Start training page: `apps/web/src/pages/StartTraining.tsx` (complete with presets)
- Training detail page: `apps/web/src/pages/TrainingDetail.tsx` (complete with all panels)
- Job executor: `apps/api/src/services/job_executor.py` (handles mock and production)
- SSE streaming: `apps/api/src/routes/jobs.py:482-551`

#### Gaps
| Gap | Priority |
|-----|----------|
| **Job persistence across restarts** - Training jobs are in-memory only | P1 |
| **Base model selector hidden** - No UI control for base model selection (currently hardcoded flux-dev) | P2 |

**Detail on Persistence Gap:**
- Current state: `_training_jobs` dict in `training.py` is in-memory
- Impact: Restarting API loses all job history
- Likely fix: Persist job metadata to JSON/SQLite on volume

**Detail on Base Model Gap:**
- CLAUDE.md states "Ongoing Training page should NOT expose backend/base-model selection controls"
- However, Start Training should allow base model selection if multiple are supported
- Currently: hardcoded to `flux-dev` in `api.startTraining()` call

---

### 3.5 Logging & Observability

#### Objective
Provide comprehensive, structured logging that enables debugging without additional instrumentation.

#### User-Visible Behavior
- Logs page showing service logs
- Per-job logs downloadable as JSONL
- Debug bundle download (ZIP with logs + metadata + samples)
- Live log streaming during training

#### Backend Responsibilities
- **Files:**
  - `packages/shared/src/logging.py` - Structured logging framework
  - `apps/api/src/routes/jobs.py` - Log endpoints
  - `apps/web/src/pages/Logs.tsx` - Logs viewer
  - `apps/web/src/components/training/TrainingLogsPanel.tsx` - Job logs panel
- **Routes:**
  - `GET /api/jobs/{id}/logs` - Download JSONL log file
  - `GET /api/jobs/{id}/logs/view` - View logs with pagination/filtering
  - `GET /api/jobs/{id}/debug-bundle` - Download debug ZIP

#### Data & Persistence
Log locations on network volume:
```
{volume_root}/
├── logs/
│   ├── api/
│   │   ├── latest/
│   │   │   └── api.log
│   │   └── archive/
│   │       └── {timestamp}/
│   ├── worker/
│   │   └── latest/
│   └── jobs/
│       └── {job_id}.jsonl
```

#### Observability
- Every log entry: timestamp, level, service, correlation_id, message, event type
- Secret redaction for tokens, API keys, passwords
- Log rotation: previous session archived on startup

#### Acceptance Criteria
- [ ] JSON structured logs with timestamps and correlation IDs
- [ ] Per-job logs isolated in `{job_id}.jsonl`
- [ ] Log download works via API
- [ ] Debug bundle includes logs + metadata + samples
- [ ] Logs viewer supports filtering by level
- [ ] Secrets automatically redacted in logs
- [ ] Log rotation archives previous sessions
- [ ] Startup logs readable (no ANSI colors for RunPod viewer)

#### Current Status: **Partial**

#### Evidence
- Logging framework: `packages/shared/src/logging.py` (complete, lines 1-728)
- JobLogger class (lines 427-545)
- TrainingJobLogger class (lines 592-728)
- Log endpoints: `apps/api/src/routes/jobs.py:142-262`
- Debug bundle: `apps/api/src/routes/jobs.py:558-661`

#### Gaps
| Gap | Priority |
|-----|----------|
| **ANSI color stripping** - Startup logs may have ANSI codes; RunPod viewer doesn't render them | P2 |
| **"Same lines updating" UX** - Not implemented; logs append only | P2 |

**Detail on ANSI Gap:**
- RunPod's log viewer shows raw text without ANSI interpretation
- Grep search: found ANSI references in `start.sh` and vendor code
- Need to strip ANSI from logs written to files

**Detail on Updating Lines Gap:**
- Current: Logs append new lines, SSE sends new events
- Desired: Progress bars update in place (like tqdm)
- Partially addressed: `progress_bar` fields in TrainingProgressEvent support this pattern
- UI implementation: `TrainingLogsPanel.tsx` handles progressBars state (line 84-85 of TrainingDetail.tsx)

---

### 3.6 Image Generation

#### Objective
Enable users to generate images using trained LoRA models via ComfyUI backend.

#### User-Visible Behavior
- Generation page with prompt textarea
- Character/LoRA selector (trained characters only)
- Aspect ratio selector (7 presets)
- Quality tier selector (Draft/Standard/High Quality)
- Seed input for reproducibility
- Advanced toggles: ControlNet, IP-Adapter, FaceDetailer, Upscale
- Recent generation jobs list with previews
- Generated image download

#### Backend Responsibilities
- **Files:**
  - `apps/api/src/routes/generation.py` - Generation endpoints
  - `apps/api/src/services/job_executor.py:148-168` - Generation capabilities
  - `apps/web/src/pages/ImageGen.tsx` - Generation page
  - `packages/shared/src/types.py:171-246` - GenerationConfig, GenerationJob
- **Routes:**
  - `POST /api/generation` - Start generation job
  - `GET /api/generation` - List generation jobs
  - `GET /api/generation/{id}` - Get job details
  - `GET /api/generation/{id}/images` - Get generated images

#### Data & Persistence
- Generated images: `{volume_root}/outputs/generation/{job_id}/`
- LoRA models: `{volume_root}/models/loras/{character_id}/`

#### Observability
- Generation job events logged
- ComfyUI workflow execution logged

#### Acceptance Criteria
- [ ] Can select trained character LoRA
- [ ] 7 aspect ratio presets work correctly
- [ ] Seed produces reproducible results
- [ ] Generated images downloadable
- [ ] Recent jobs show with thumbnails
- [ ] Advanced toggles map to capabilities

#### Current Status: **Partial**

#### Evidence
- Generation page: `apps/web/src/pages/ImageGen.tsx` (lines 1-200+)
- Aspect ratios: 7 presets defined (lines 12-20)
- LoRA selector: trained characters filter (line 163)
- Capabilities endpoint: `job_executor.py:148-168`

#### Gaps
| Gap | Priority |
|-----|----------|
| **ControlNet not wired** - Toggle exists but marked `supported: false` | P1 |
| **IP-Adapter not wired** - Toggle exists but marked `supported: false` | P1 |
| **FaceDetailer not wired** - Toggle exists but marked `supported: false` | P1 |
| **LoRA upload** - UI exists but may not persist correctly | P2 |

**Detail on Toggle Gaps:**
- `job_executor.py:153-157` shows:
  ```python
  "use_upscale": {"supported": True, ...},
  "use_facedetailer": {"supported": False, ...},
  "use_ipadapter": {"supported": False, ...},
  "use_controlnet": {"supported": False, ...},
  ```
- Only upscale is currently wired
- Likely fix: Implement ComfyUI workflow nodes for each feature

---

### 3.7 Model & Artifact Management

#### Objective
Manage model files, checkpoints, and generated artifacts on network volume.

#### User-Visible Behavior
- Checkpoints panel in training detail page
- Download checkpoint button per checkpoint
- Final model saved to character LoRA folder
- Sample images visible in training detail

#### Backend Responsibilities
- **Files:**
  - `apps/api/src/routes/jobs.py:400-475` - Checkpoint endpoints
  - `packages/shared/src/logging.py:558-590` - Artifact path helpers
- **Routes:**
  - `GET /api/jobs/{id}/checkpoints` - List checkpoints
  - `GET /api/jobs/{id}/checkpoints/{filename}/download` - Download checkpoint
  - `GET /api/jobs/{id}/artifacts` - List all artifacts
  - `GET /api/jobs/{id}/artifacts/samples/{filename}` - Get sample image

#### Data & Persistence
Storage locations on network volume:
```
{volume_root}/
├── models/
│   ├── loras/
│   │   └── {character_id}/
│   │       └── {model}.safetensors
│   ├── base/
│   │   └── flux-dev/
│   └── controlnet/
├── artifacts/
│   └── jobs/
│       └── {job_id}/
│           ├── samples/
│           │   └── step_{n}.png
│           └── checkpoints/
│               └── checkpoint_step_{n}.safetensors
└── outputs/
    └── generation/
        └── {job_id}/
```

#### Observability
- Checkpoint saves logged with path and step
- Model exports logged

#### Acceptance Criteria
- [ ] Checkpoints listed in UI during training
- [ ] Checkpoints downloadable as .safetensors
- [ ] Sample images viewable in training detail
- [ ] Final model saved to character folder
- [ ] Model files persist across pod restarts

#### Current Status: **Implemented**

#### Evidence
- Checkpoint listing: `apps/api/src/routes/jobs.py:400-435`
- Checkpoint download: `apps/api/src/routes/jobs.py:438-475`
- Sample images: `apps/api/src/routes/jobs.py:364-393`
- UI panel: `apps/web/src/components/training/CheckpointsPanel.tsx`

#### Gaps
- None identified for basic checkpoint management

---

### 3.8 Infrastructure & DevOps Rules

#### Objective
Maintain clean, deterministic builds with no legacy code or silent fallbacks.

#### User-Visible Behavior
- Startup script shows service status
- Container starts reliably with all services

#### Backend Responsibilities
- **Files:**
  - `Dockerfile` - Container build
  - `start.sh` - Entrypoint script
  - `scripts/bootstrap_pod.sh` - Pod initialization
  - `scripts/restart_services.sh` - Service management
  - `scripts/runtime/health_check.sh` - Health verification

#### Data & Persistence
- Docker image contains vendored code (ComfyUI, AI-Toolkit)
- Models downloaded to volume at runtime (not in image)

#### Observability
- Startup logs capture service status
- Health checks logged

#### Acceptance Criteria (from CLAUDE.md)
- [ ] No legacy code in active directories (delete or move to `/_legacy_dump/`)
- [ ] Legacy dump folder is gitignored and dockerignored
- [ ] Deterministic startup scripts with explicit service ordering
- [ ] No fallback/skip patterns that mask failures
- [ ] Vendored code at pinned commits (`vendor/VENDOR_PINS.json`)

#### Current Status: **Implemented**

#### Evidence
- `Dockerfile` exists with UV-based dependency installation
- `start.sh` is entrypoint (modified in working directory)
- `vendor/VENDOR_PINS.json` tracks ComfyUI and AI-Toolkit pins
- `scripts/vendor/*.sh` manage vendor updates

#### Gaps
| Gap | Priority |
|-----|----------|
| **`.gitignore` for legacy dump** - Verify `/_legacy_dump/` is ignored | P3 |
| **`.dockerignore` for legacy dump** - Verify excluded from builds | P3 |

---

### 3.9 Claude Code Integration Rules

#### Objective
Ensure Claude Code operates correctly within Isengard codebase following established patterns.

#### User-Visible Behavior
N/A - developer experience only

#### Backend Responsibilities
- **Files:**
  - `CLAUDE.md` - Living contract for Claude Code
  - `.claude/` - Claude Code configuration

#### Observability
- CLAUDE.md documents logging locations and patterns

#### Acceptance Criteria (from CLAUDE.md)
- [ ] Always check logs before proposing fixes
- [ ] Update CLAUDE.md when patterns change
- [ ] Follow double-apply doctrine (Phase 1) or sync-back procedure (Phase 2)
- [ ] Never commit secrets
- [ ] Auto-commit before deploy

#### Current Status: **Implemented**

#### Evidence
- `CLAUDE.md` at 400+ lines with comprehensive documentation
- Phase 2 workflow documented for network volume development

#### Gaps
- None identified

---

## 4. Gap Analysis (Prioritized)

### P0 - Blockers

| # | Gap | Description | Likely Location | Verification |
|---|-----|-------------|-----------------|--------------|
| - | None identified | - | - | - |

### P1 - Important

| # | Gap | Description | Likely Location | Verification |
|---|-----|-------------|-----------------|--------------|
| 1 | **Job persistence** | Training jobs lost on API restart | `apps/api/src/routes/training.py` (persist `_training_jobs` to file) | Restart API, verify job history persists |
| 2 | **Synthetic image generation** | No option to generate preview images during character creation | `apps/web/src/pages/Characters.tsx`, `apps/api/src/routes/characters.py` (add generation endpoint) | Create character, click "Generate Previews", accept/reject images |
| 3 | **ControlNet toggle** | Marked unsupported but UI shows toggle | `apps/api/src/services/job_executor.py:157` (implement workflow) | Enable ControlNet, verify generation uses it |
| 4 | **IP-Adapter toggle** | Marked unsupported but UI shows toggle | `apps/api/src/services/job_executor.py:156` (implement workflow) | Enable IP-Adapter, verify style transfer works |
| 5 | **FaceDetailer toggle** | Marked unsupported but UI shows toggle | `apps/api/src/services/job_executor.py:155` (implement workflow) | Enable FaceDetailer, verify face enhancement |

### P2 - Nice to Have

| # | Gap | Description | Likely Location | Verification |
|---|-----|-------------|-----------------|--------------|
| 6 | **ANSI stripping** | Startup logs have ANSI codes | `start.sh`, logging handlers | View logs in RunPod, verify no escape codes |
| 7 | **Dataset snapshot** | No record of which images were used in training | `apps/api/src/services/job_executor.py` (training init) | Check job metadata for image list |
| 8 | **Base model selector** | UI hardcoded to flux-dev | `apps/web/src/pages/StartTraining.tsx:185` | Show dropdown with flux-dev, flux-schnell options |
| 9 | **"Updating lines" UX** | Progress bars don't update in place | `apps/web/src/components/training/TrainingLogsPanel.tsx` | Progress shows updating bars, not appending lines |

### P3 - Low Priority

| # | Gap | Description | Likely Location | Verification |
|---|-----|-------------|-----------------|--------------|
| 10 | **Legacy dump gitignore** | Verify `/_legacy_dump/` ignored | `.gitignore` | `git status` doesn't show legacy folder |
| 11 | **Legacy dump dockerignore** | Verify excluded from builds | `.dockerignore` | Build image, verify no legacy files |

---

## 5. Verification Plan

### API Smoke Checks

```bash
# Run locally or in container

# Health check
curl -s http://localhost:8000/api/health | jq .
# Expected: {"status": "healthy"}

# Ready check (shows dependencies)
curl -s http://localhost:8000/api/ready | jq .
# Expected: status=ready, dependencies.comfyui.status=healthy (production) or status=degraded (fast-test)

# Info/capabilities check
curl -s http://localhost:8000/api/info | jq .
# Expected: training and image_generation capability schemas

# List characters
curl -s http://localhost:8000/api/characters | jq .
# Expected: array of characters

# Create character (requires form data)
curl -X POST http://localhost:8000/api/characters \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","trigger_word":"ohwx person"}' | jq .
# Expected: character object with id

# List training jobs
curl -s http://localhost:8000/api/training | jq .
# Expected: array of training jobs

# List generation jobs
curl -s http://localhost:8000/api/generation | jq .
# Expected: array of generation jobs
```

### Training Job Checks

```bash
# Start training (fast-test mode)
CHAR_ID="<character_id_with_images>"
curl -X POST http://localhost:8000/api/training \
  -H "Content-Type: application/json" \
  -d "{
    \"character_id\": \"$CHAR_ID\",
    \"config\": {\"method\": \"lora\", \"steps\": 100},
    \"preset_name\": \"quick\",
    \"base_model\": \"flux-dev\"
  }" | jq .
# Expected: training job object with id

# Get job status
JOB_ID="<job_id>"
curl -s http://localhost:8000/api/training/$JOB_ID | jq .

# SSE stream (use curl with -N for streaming)
curl -N http://localhost:8000/api/jobs/$JOB_ID/stream

# List checkpoints
curl -s http://localhost:8000/api/jobs/$JOB_ID/checkpoints | jq .

# View logs
curl -s "http://localhost:8000/api/jobs/$JOB_ID/logs/view?limit=50" | jq .
```

### Log Streaming Checks

```bash
# Verify log file created
JOB_ID="<job_id>"
ls -la /runpod-volume/isengard/logs/jobs/$JOB_ID.jsonl

# Verify log content is JSON
head -5 /runpod-volume/isengard/logs/jobs/$JOB_ID.jsonl | jq .

# Verify no ANSI codes in logs (should return empty)
grep -P '\x1b\[' /runpod-volume/isengard/logs/api/latest/api.log || echo "No ANSI codes found"
```

### Download/Checkpoint Checks

```bash
# Download checkpoint (if exists)
JOB_ID="<job_id>"
CHECKPOINT="checkpoint_step_100.safetensors"
curl -O http://localhost:8000/api/jobs/$JOB_ID/checkpoints/$CHECKPOINT/download

# Download debug bundle
curl -O http://localhost:8000/api/jobs/$JOB_ID/debug-bundle

# Verify ZIP contents
unzip -l ${JOB_ID}_debug.zip
```

### Generation Checks

```bash
# Generate image
curl -X POST http://localhost:8000/api/generation \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "prompt": "a photo of a person",
      "width": 512,
      "height": 512,
      "steps": 10
    },
    "count": 1
  }' | jq .
# Expected: generation job object

# List generated images
GEN_JOB_ID="<generation_job_id>"
curl -s http://localhost:8000/api/generation/$GEN_JOB_ID | jq .
```

### Persistence Checks

```bash
# Verify volume paths exist
ls -la /runpod-volume/isengard/
# Expected: data/, logs/, models/, outputs/, artifacts/

# Verify character data persists
ls -la /runpod-volume/isengard/data/characters/

# Verify model storage
ls -la /runpod-volume/isengard/models/loras/
```

---

## 6. Traceability Map

### Feature → Artifacts

| Feature | Frontend | API Routes | Backend Services | Types | Config |
|---------|----------|------------|------------------|-------|--------|
| Characters | `pages/Characters.tsx` | `routes/characters.py` | - | `types.py:42-79` | - |
| Dataset | `pages/Dataset.tsx` | (reuses characters) | - | - | - |
| Training History | `pages/TrainingHistory.tsx` | `routes/training.py` | `job_executor.py` | `types.py:85-165` | `config.py` |
| Start Training | `pages/StartTraining.tsx` | `routes/training.py` | `job_executor.py` | `types.py:85-165` | - |
| Ongoing Training | `pages/OngoingTraining.tsx` | `routes/training.py` | `job_executor.py` | `types.py:121-156` | - |
| Training Detail | `pages/TrainingDetail.tsx` | `routes/jobs.py` | `job_executor.py` | `events.py` | - |
| Image Generation | `pages/ImageGen.tsx` | `routes/generation.py` | `job_executor.py` | `types.py:171-246` | - |
| Logs | `pages/Logs.tsx`, `components/training/TrainingLogsPanel.tsx` | `routes/jobs.py` | - | - | `logging.py` |
| Health/Info | - | `routes/health.py` | `job_executor.py` | - | `config.py` |

### Route → Handler → Types

| Route | Handler Function | Request Type | Response Type |
|-------|-----------------|--------------|---------------|
| `POST /api/characters` | `create_character` | `CharacterCreate` | `Character` |
| `POST /api/training` | `start_training` | `StartTrainingRequest` | `TrainingJob` |
| `GET /api/training/{id}` | `get_training_job` | - | `TrainingJob` |
| `GET /api/jobs/{id}/stream` | `stream_job_events` | - | SSE (`TrainingProgressEvent`) |
| `GET /api/jobs/{id}/logs` | `download_job_logs` | - | `FileResponse` |
| `POST /api/generation` | `generate_images` | `GenerateImageRequest` | `GenerationJob` |
| `GET /api/info` | `api_info` | - | Capability dict |

### Log Event Types

| Event | Location | Fields |
|-------|----------|--------|
| `training.start` | `logging.py:615-625` | job_id, total_steps, config |
| `training.step` | `logging.py:627-661` | step, total_steps, loss, lr, eta |
| `training.sample` | `logging.py:663-674` | sample_path, step |
| `training.checkpoint` | `logging.py:676-684` | checkpoint_path, step |
| `training.complete` | `logging.py:699-709` | output_path, training_time_seconds, final_loss |
| `training.failed` | `logging.py:711-723` | error, error_type, stack_trace |

---

## 7. Glossary

| Term | Definition |
|------|------------|
| **Character** | A named identity with trigger word and training images. Container for a person/subject to be trained. |
| **Dataset** | The collection of training images associated with a character. |
| **Training Run** | A single execution of LoRA training on a character's dataset. Produces a trained model. |
| **Job** | A background task (training or generation). Has a unique ID and lifecycle (pending→running→completed/failed). |
| **Job ID** | Unique identifier for a job, format: `train-{uuid}` or `gen-{uuid}`. |
| **Checkpoint** | Intermediate model snapshot saved during training at configured intervals. |
| **Sample Image** | Preview image generated during training to show progress. |
| **LoRA** | Low-Rank Adaptation - efficient fine-tuning method that produces small adapter files. |
| **Trigger Word** | Special token that activates the trained LoRA (e.g., "ohwx person"). |
| **SSE** | Server-Sent Events - one-way streaming from server to client for real-time updates. |
| **JSONL** | JSON Lines format - one JSON object per line for streaming logs. |
| **Correlation ID** | Unique identifier propagated through all log entries for a single request. |
| **Fast-test Mode** | Development mode without GPU; uses mock training/generation. |
| **Production Mode** | Real mode with GPU; uses AI-Toolkit and ComfyUI. |
| **Network Volume** | Persistent storage on RunPod that survives pod restarts. Mounted at `/runpod-volume`. |
| **Capability Schema** | JSON schema describing available parameters and their constraints for training/generation. |
| **Debug Bundle** | ZIP file containing logs, metadata, and samples for troubleshooting failed jobs. |

---

## Document Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-03 | Claude Code (VS) | Initial specification created from repo audit |

---

*This document is the authoritative source for feature requirements and current implementation status. Update when features are implemented or requirements change.*
