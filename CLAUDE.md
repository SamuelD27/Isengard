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
├── vendor/               # Vendored upstream repos (pinned commits)
│   ├── VENDOR_PINS.json  # Authoritative pins file
│   ├── comfyui/          # ComfyUI (git subtree)
│   └── ai-toolkit/       # AI-Toolkit (git subtree)
├── scripts/
│   ├── vendor/           # Pin management scripts
│   ├── runtime/          # Health checks, entrypoints
│   └── smoke/            # Integration tests
├── patches/              # Vendor patches (if needed)
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
| `COMFYUI_HOST` | No | ComfyUI bind address (default: `127.0.0.1` - internal only) |
| `COMFYUI_PORT` | No | ComfyUI port (default: `8188`) |
| `COMFYUI_URL` | No | Full ComfyUI URL (default: `http://127.0.0.1:8188`) |
| `AITOOLKIT_PATH` | No | Vendored AI-Toolkit path (default: `/app/vendor/ai-toolkit`) |

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

## Vendored Engines: ComfyUI + AI-Toolkit (Internal Services)

Both ComfyUI and AI-Toolkit are **vendored** into the repository at pinned commits for deterministic, reproducible builds.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                      │
├─────────────────────────────────────────────────────────┤
│  EXPOSED (to host):                                     │
│    - Port 22:   SSH                                     │
│    - Port 3000: Web GUI (nginx)                         │
│    - Port 8000: API (direct)                            │
├─────────────────────────────────────────────────────────┤
│  INTERNAL (not exposed):                                │
│    - 127.0.0.1:8188  ComfyUI (vendored, localhost only) │
│    - 127.0.0.1:6379  Redis                              │
└─────────────────────────────────────────────────────────┘
```

### Current Pins

See `vendor/VENDOR_PINS.json` for authoritative versions:
- **ComfyUI**: `6ca3d5c0` (pinned 2025-12-31)
- **AI-Toolkit**: `4d5a649a` (pinned 2025-12-31)

### How Vendor Pins Work

1. **Pins file**: `vendor/VENDOR_PINS.json` contains commit hashes and metadata
2. **Git subtree**: Both repos are added via `git subtree add --squash`
3. **Docker build**: `COPY vendor/comfyui /opt/ComfyUI` bakes code into image
4. **No runtime cloning**: Everything is in the image, no network needed at startup

### Updating Vendor Versions

```bash
# Check current status
./scripts/vendor/pin_status.sh

# Update ComfyUI to a new commit
./scripts/vendor/update_vendor.sh comfyui <commit-or-tag>

# Update AI-Toolkit to a new commit
./scripts/vendor/update_vendor.sh ai-toolkit <commit-or-tag>

# After update: rebuild and test
docker build -t isengard:test .
./scripts/smoke/smoke_internal_engines.sh
```

### Where Logs Live

| Service | Log Location |
|---------|--------------|
| ComfyUI | `/runpod-volume/isengard/logs/comfyui.log` |
| API | `/runpod-volume/isengard/logs/api/startup.log` |
| Worker | `/runpod-volume/isengard/logs/worker/startup.log` |

### Internal Ports

| Service | Bind Address | Port | Exposed? |
|---------|--------------|------|----------|
| ComfyUI | `127.0.0.1` | 8188 | NO (internal only) |
| Redis | `127.0.0.1` | 6379 | NO (internal only) |
| API | `0.0.0.0` | 8000 | YES |
| Web | `0.0.0.0` | 3000 | YES |
| SSH | `0.0.0.0` | 22 | YES |

### Smoke Test

Run the smoke test to verify the vendored engines are correctly integrated:

```bash
./scripts/smoke/smoke_internal_engines.sh
```

This test verifies:
1. Docker image builds with vendored code
2. ComfyUI is reachable internally (from inside container)
3. ComfyUI is NOT reachable externally (security)
4. AI-Toolkit is present at `/app/vendor/ai-toolkit`
5. `/ready` endpoint shows dependency status

### Troubleshooting

**ComfyUI not starting:**
- Check logs: `docker exec <container> tail -f /runpod-volume/isengard/logs/comfyui.log`
- Verify models are downloaded: models are on the volume, not in the image

**AI-Toolkit training fails:**
- Check PYTHONPATH includes `/app/vendor/ai-toolkit`
- Verify `run.py` exists: `docker exec <container> ls /app/vendor/ai-toolkit/run.py`

**Pins out of date:**
- Run `./scripts/vendor/pin_status.sh` to check
- Update with `./scripts/vendor/update_vendor.sh`

---

*Update this document when patterns change.*
