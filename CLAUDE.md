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

### 4. Double-Apply Doctrine (Phase 1 — Superseded by Phase 2)

> **Note:** This was the Phase 1 approach for container-based development. For current workflow using network volumes, see **Phase 2: RunPod Network Volume Beta Hardening** below.

<details>
<summary>Phase 1 Reference (click to expand)</summary>

When fixing on RunPod pod (container filesystem):
1. Make fix on remote pod
2. IMMEDIATELY apply same fix to local repo
3. Commit with descriptive message

Remote → Local path mapping:
- `/app/apps/` → `apps/`
- `/app/packages/` → `packages/`

</details>

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

## Phase 2: RunPod Network Volume Beta Hardening

> **Status: ACTIVE** — This section defines the current development workflow.

### Goal

Full-proof the beta on RunPod using persistent network volume storage. The network volume persists across pod restarts, enabling rapid iteration without rebuilding Docker images for every code change.

### Sources of Truth

| Source | Role | Uncommitted Changes? |
|--------|------|----------------------|
| **Local repo `main` branch** | Canonical Git history | NEVER — always committed |
| **RunPod network volume** | Reusable execution workspace | ALLOWED — but must sync back |

**Risk Statement:** Uncommitted changes on the network volume can be lost (pod termination, volume issues) or become unreviewable. Therefore, sync-back to local must be **frequent** and **controlled** via the procedure below.

### Directory Conventions on the Network Volume

All Phase 2 work uses this standardized layout on the RunPod network volume:

```
/runpod-volume/
├── isengard/                    # Standard project root (persistent data)
│   ├── repo/                    # Git working copy (synced from local)
│   ├── models/                  # FLUX, LoRA checkpoints
│   ├── outputs/                 # Generated images, training artifacts
│   ├── logs/                    # All service logs
│   │   ├── api/
│   │   ├── worker/
│   │   ├── comfyui.log
│   │   └── phase2/              # Phase 2 specific logs
│   └── reports/                 # Testing reports and artifacts
│       ├── test-report.md       # Canonical test report (see below)
│       └── screenshots/         # UI screenshots referenced in reports
└── .baseline-marker             # Sync state file (see below)
```

**Canonical paths:**
- Network volume mount: `/runpod-volume`
- Project data root: `/runpod-volume/isengard`
- Repo working copy: `/runpod-volume/isengard/repo`
- Test report: `/runpod-volume/isengard/reports/test-report.md`
- Baseline marker: `/runpod-volume/.baseline-marker`

### Phase 2 Workflow (SOP)

#### A. Pod Bring-Up

1. **Start pod with network volume attached**
   - Ensure volume is mounted at `/runpod-volume`

2. **Initialize or verify repo working copy**
   ```bash
   # First time: clone from local (via SSH/rsync)
   rsync -avz --exclude='.git/objects' user@local:/path/to/isengard/ /runpod-volume/isengard/repo/

   # Subsequent: verify copy exists
   ls -la /runpod-volume/isengard/repo/
   ```

3. **Create or update baseline marker**
   ```bash
   cat > /runpod-volume/.baseline-marker << EOF
   baseline_sha=$(cd /runpod-volume/isengard/repo && git rev-parse HEAD)
   synced_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   pod_id=${RUNPOD_POD_ID:-unknown}
   volume_path=/runpod-volume/isengard/repo
   EOF
   ```

4. **Start services**
   ```bash
   cd /runpod-volume/isengard/repo
   ./start.sh
   ```

#### B. Testing Loop (Chrome Claude Code)

The testing workflow uses two Claude Code instances:
- **Claude Code for Chrome**: Performs GUI testing, inspects DevTools
- **VS Claude Code (SSH)**: Implements fixes on the pod

**Test Execution:**

1. User opens the GUI at `https://<pod-id>-3000.proxy.runpod.net`

2. Claude Code (Chrome) performs systematic testing:
   - Navigate through all major UI flows
   - Open DevTools Console (check for errors/warnings)
   - Open DevTools Network tab (check for failed requests)
   - Test edge cases and error states

3. Document findings in the canonical report file:

   **File:** `/runpod-volume/isengard/reports/test-report.md`

   **Format:**
   ```markdown
   # Phase 2 Test Report

   Last updated: YYYY-MM-DD HH:MM UTC
   Pod ID: <pod-id>
   Baseline SHA: <sha>

   ## Test Session: YYYY-MM-DD

   ### Test: <Feature/Flow Name>

   **Steps:**
   1. Navigate to /characters
   2. Click "Add Character"
   3. ...

   **Expected:** Form submits successfully, character appears in list
   **Actual:** 500 error, character not created

   **Console Errors:**
   ```
   TypeError: Cannot read property 'id' of undefined
       at CharacterForm.jsx:45
   ```

   **Network Failures:**
   - `POST /api/characters` → 500 Internal Server Error
   - Response: `{"detail": "Database connection failed"}`

   **Screenshots:** `screenshots/2024-01-15-char-create-error.png`

   **Status:** 🔴 FAILING

   ---

   ### Fix Applied: YYYY-MM-DD HH:MM

   **Issue:** Database connection pool exhausted
   **Changed:** `apps/api/src/db.py:23` - increased pool size
   **Re-test:** Character creation flow

   ---
   ```

#### C. Fix Loop (VS Claude Code over SSH)

1. **Connect to pod via SSH**
   ```bash
   ssh root@<pod-ip> -p 22
   cd /runpod-volume/isengard/repo
   ```

2. **Review logs before fixing** (mandatory)
   ```bash
   # API logs
   tail -100 /runpod-volume/isengard/logs/api/startup.log

   # Worker logs
   tail -100 /runpod-volume/isengard/logs/worker/startup.log

   # ComfyUI logs
   tail -100 /runpod-volume/isengard/logs/comfyui.log
   ```

3. **Apply fix to the volume working copy**
   - Edit files directly on `/runpod-volume/isengard/repo/`
   - Restart affected services as needed

4. **Update the test report** with:
   - What was changed (file:line)
   - What to re-test
   - Timestamp

5. **Notify Chrome Claude Code to re-test**

6. **Repeat until stable**

### Safe Sync-Back Procedure (Volume → Local)

**Policy:** NEVER sync directly into local `main`. Always use a dedicated worktree branch.

#### Method 1: Patch-Based Import (Preferred)

**On the pod:**
```bash
cd /runpod-volume/isengard/repo

# Get baseline SHA from marker
BASELINE_SHA=$(grep baseline_sha /runpod-volume/.baseline-marker | cut -d= -f2)

# Create patch bundle
git add -A
git diff --cached $BASELINE_SHA > /tmp/phase2-changes.patch

# Or create a patch series for review
git format-patch $BASELINE_SHA --stdout > /tmp/phase2-patches.mbox
```

**Transfer to local:**
```bash
scp root@<pod-ip>:/tmp/phase2-changes.patch ./
# or
scp root@<pod-ip>:/tmp/phase2-patches.mbox ./
```

**On local machine:**
```bash
# Create or switch to import worktree branch
BRANCH_NAME="phase2/import-$(date +%Y%m%d-%H%M)"
git checkout -b $BRANCH_NAME

# Apply patches
git apply phase2-changes.patch
# or
git am phase2-patches.mbox

# Review changes
git diff main

# Run tests
./scripts/smoke/smoke_internal_engines.sh

# Commit with clear message
git add -A
git commit -m "phase2: import fixes from pod session YYYY-MM-DD

Changes:
- Fixed X in file:line
- Updated Y in file:line

Tested on pod: <pod-id>
Report: /runpod-volume/isengard/reports/test-report.md"

# Merge to main when ready
git checkout main
git merge --no-ff $BRANCH_NAME
```

#### Method 2: Rsync + Manual Review (Fallback)

```bash
# On local machine
mkdir -p /tmp/isengard-import
rsync -avz root@<pod-ip>:/runpod-volume/isengard/repo/ /tmp/isengard-import/

# Compare against local
git diff --no-index . /tmp/isengard-import/ > /tmp/volume-diff.txt

# Review and manually apply changes to worktree branch
```

#### After Successful Sync

**Update baseline marker on pod:**
```bash
ssh root@<pod-ip>
NEW_SHA=$(cd /path/to/local/repo && git rev-parse main)
cat > /runpod-volume/.baseline-marker << EOF
baseline_sha=$NEW_SHA
synced_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
pod_id=${RUNPOD_POD_ID:-unknown}
volume_path=/runpod-volume/isengard/repo
EOF
```

### Operational Rules

1. **Sync Frequency:** Sync back at least daily OR after any meaningful fix-set. No long-lived divergence (>24 hours) without sync.

2. **No Silent Drift:** Every remote fix MUST be documented in the test report with:
   - Date/time
   - What was addressed
   - Files changed

3. **No Legacy Clutter:** When replacing files, delete the old file or move to `/_legacy_dump/`. This folder is gitignored and dockerignored.

4. **Logs Before Fixes:** ALWAYS check logs before proposing a fix. Phase 2 logs live at:
   - `/runpod-volume/isengard/logs/api/`
   - `/runpod-volume/isengard/logs/worker/`
   - `/runpod-volume/isengard/logs/comfyui.log`
   - `/runpod-volume/isengard/logs/phase2/` (session-specific)

5. **Report is Mandatory:** The test report at `/runpod-volume/isengard/reports/test-report.md` must be updated for every test session and every fix. This is the audit trail.

6. **Commit Before Deploy:** Before deploying a new Docker image, ALL volume changes must be synced back and committed to local main.

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
