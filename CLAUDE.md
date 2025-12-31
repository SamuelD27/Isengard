# Isengard - Project Intelligence

> Identity LoRA Training + ComfyUI Image Generation Platform

## Mission

GUI-first platform for personalized AI-generated content. Non-technical users train identity LoRAs from photos and generate images without command line.

---

## Architecture

```
React UI (apps/web) ⇄ FastAPI API (apps/api) ⇄ Worker (apps/worker) ⇄ Plugins (packages/plugins)
```

- Frontend talks to API via HTTP/SSE only
- API queues jobs to Redis; Worker consumes them
- Plugins loaded by Worker, never imported by API

### Directory Structure

```
isengard/
├── apps/
│   ├── api/              # FastAPI backend
│   ├── worker/           # Background job processor
│   └── web/              # React frontend
├── packages/
│   ├── shared/           # Shared Python utilities (logging, config, types)
│   └── plugins/
│       ├── training/     # AI-Toolkit adapter
│       ├── image/        # ComfyUI adapter
│       └── video/        # Scaffold only
├── start.sh              # Container entrypoint
└── Dockerfile
```

### Storage

| Environment | Location | Purpose |
|-------------|----------|---------|
| RunPod | `/runpod-volume/isengard/` | ALL persistent data |
| Local Dev | `./data/` | Uploads, models, outputs |
| Container | Filesystem | Ephemeral only |

Path resolution via `packages/shared/src/config.py`, never hardcoded.

---

## Modes

| Mode | Activation | Use Case |
|------|------------|----------|
| `fast-test` | `ISENGARD_MODE=fast-test` | CI/UI testing, mock plugins, no GPU |
| `production` | `ISENGARD_MODE=production` | Real AI-Toolkit + ComfyUI |

---

## Non-Negotiables

### 1. Plugin Architecture
- Training/Image/Video backends are swappable modules in `packages/plugins/*/`
- Each implements interface defined in `interface.py`
- Core code NEVER imports plugin internals

### 2. Observability First
- Structured JSON logging mandatory
- Every request has correlation ID propagated through stack
- Logs are primary source of truth for debugging

### 3. No Give Up Fixes
- Fix root causes, not symptoms
- Never disable features to make tests pass
- If broken, mark feature as not-ready

### 4. Double-Apply Doctrine (Remote + Local Sync)
When fixing on RunPod pod:
1. Make fix on remote pod
2. IMMEDIATELY apply same fix to local repo
3. Commit with descriptive message

Remote → Local path mapping:
- `/app/apps/` → `apps/`
- `/app/packages/` → `packages/`

### 5. Auto-Commit Before Deploy
Claude Code MUST commit all changes before user deploys Docker image.
- Check `git status` before ending session
- Commit after completing any work
- Never leave uncommitted changes

### 6. No Legacy in Build
When replacing a file:
1. DELETE the old file (preferred), or
2. Move to `/_legacy_dump/` (archival only)

Never leave deprecated files in active directories.

### 7. Error Tracking
All known errors awaiting fix are documented in `ERROR_LIST.md` at the project root.
- Before fixing a bug, check if it's already documented there
- After discovering a new bug, add it to ERROR_LIST.md with full analysis
- Mark errors as resolved when fixed

---

## Current Features

### Training
- [x] LoRA training via AI-Toolkit (FLUX.1-dev)
- [x] Training presets (Quick/Balanced/High Quality)
- [x] SSE live progress streaming
- [x] Loss chart with real-time updates
- [x] Sample image generation during training
- [x] GPU stats monitoring

### Image Generation
- [x] ComfyUI with FLUX workflows
- [x] 7 aspect ratio presets
- [x] LoRA selection from trained characters
- [x] Advanced toggles (ControlNet, IP-Adapter, FaceDetailer, Upscale)

### UI
- [x] Characters: CRUD, image upload, trigger word
- [x] Dataset Manager: global image grid, filters, bulk delete
- [x] Training: job monitoring with metrics
- [x] Generate: prompt-based with presets

---

## API Endpoints

### Characters
```
GET/POST /api/characters
GET/PATCH/DELETE /api/characters/{id}
POST /api/characters/{id}/images
GET/DELETE /api/characters/{id}/images/{file}
```

### Training
```
POST /api/training              # Start job
GET /api/training/{id}          # Get status
GET /api/training/{id}/stream   # SSE progress
POST /api/training/{id}/cancel
```

### Jobs (debugging)
```
GET /api/jobs/{id}/logs/view    # View logs with filtering
GET /api/jobs/{id}/artifacts    # List samples
GET /api/jobs/{id}/debug-bundle # Download debug ZIP
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ISENGARD_MODE` | Yes | `fast-test` or `production` |
| `REDIS_URL` | Yes | Redis connection string |
| `VOLUME_ROOT` | No | Defaults to `/runpod-volume/isengard` |
| `COMFYUI_URL` | No | Defaults to `http://localhost:8188` |

---

## Quick Commands

```bash
# Check status
git status

# Run locally
docker-compose up --build

# Tail logs
tail -f logs/api/latest/api.log | jq .

# Debug training job
curl http://localhost:8000/api/jobs/{job_id}/logs/view?level=ERROR
```

---

*Update this document when patterns change.*
