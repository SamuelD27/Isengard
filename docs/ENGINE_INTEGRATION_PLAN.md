# Engine Integration Plan: Vendored Internal Services

## Overview

This document describes the architecture for vendoring ComfyUI and AI-Toolkit as internal services within the Isengard repository. The goal is to have deterministic, reproducible builds with pinned dependencies that run as internal backend services.

## Current State Analysis

### ComfyUI (Current)
- **Location:** `/opt/ComfyUI` (cloned in Dockerfile)
- **Problem:** Non-deterministic (always gets latest `main`)
- **Binding:** `0.0.0.0:8188` (potentially exposed)
- **Version:** Unknown (floating)

### AI-Toolkit (Current)
- **Location:** `$VOLUME_ROOT/ai-toolkit` (cloned at runtime by start.sh)
- **Problem:** Not baked into image, cloned every pod startup
- **Venv:** `$VOLUME_ROOT/.venvs/aitoolkit/` (created at runtime)
- **Version:** Unknown (floating)

## Target Architecture

```
Isengard/
├── vendor/
│   ├── VENDOR_PINS.json           # Authoritative pins file
│   ├── comfyui/                   # Git subtree: pinned ComfyUI
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── ...
│   └── ai-toolkit/                # Git subtree: pinned AI-Toolkit
│       ├── run.py
│       ├── requirements.txt
│       └── ...
├── scripts/
│   ├── vendor/
│   │   ├── pin_status.sh          # Show current vendor status
│   │   └── update_vendor.sh       # Update a vendored repo
│   ├── runtime/
│   │   ├── entrypoint.sh          # Container entrypoint
│   │   └── health_check.sh        # Health probe script
│   └── smoke/
│       └── smoke_internal_engines.sh  # Integration smoke test
└── patches/                       # Optional patches for vendored code
    └── README.md
```

## Implementation Steps

### Step 1: Vendor Scaffolding

Create directory structure and pins file:

```bash
mkdir -p vendor/comfyui vendor/ai-toolkit
mkdir -p scripts/vendor scripts/runtime scripts/smoke
mkdir -p patches
```

Create `vendor/VENDOR_PINS.json`:
```json
{
  "comfyui": {
    "repo": "https://github.com/comfyanonymous/ComfyUI.git",
    "commit": "<pinned-commit>",
    "pinned_at": "<date>",
    "purpose": "Image generation backend (FLUX workflows)"
  },
  "ai-toolkit": {
    "repo": "https://github.com/ostris/ai-toolkit.git",
    "commit": "<pinned-commit>",
    "pinned_at": "<date>",
    "purpose": "LoRA training backend (FLUX.1-dev)"
  }
}
```

### Step 2: Git Subtree Vendoring

Using git subtree (not submodules) for simpler workflow:

```bash
# Add ComfyUI
git subtree add --prefix=vendor/comfyui \
  https://github.com/comfyanonymous/ComfyUI.git <commit> --squash

# Add AI-Toolkit
git subtree add --prefix=vendor/ai-toolkit \
  https://github.com/ostris/ai-toolkit.git <commit> --squash
```

### Step 3: Docker Updates

**Dockerfile changes:**

1. Remove old ComfyUI clone (line 99-101)
2. Use vendored paths instead
3. Install deps from vendored requirements.txt
4. Ensure ComfyUI binds to 127.0.0.1 only

**New Dockerfile sections:**
```dockerfile
# Vendored ComfyUI
COPY vendor/comfyui /opt/ComfyUI
RUN uv pip install --system -r /opt/ComfyUI/requirements.txt

# Vendored AI-Toolkit
COPY vendor/ai-toolkit /app/vendor/ai-toolkit
RUN uv pip install --system -r /app/vendor/ai-toolkit/requirements.txt
```

### Step 4: Entrypoint Updates

**start.sh changes:**

1. Remove runtime AI-Toolkit cloning (lines 679-717)
2. Start ComfyUI with `--listen 127.0.0.1` instead of `0.0.0.0`
3. Add version logging from VENDOR_PINS.json
4. Update AI-Toolkit paths to use vendored location

### Step 5: Plugin Wiring

**ComfyUI Plugin:**
- Add `COMFYUI_HOST` env var (default `127.0.0.1`)
- Add `COMFYUI_PORT` env var (default `8188`)
- Use these in plugin initialization

**AI-Toolkit Plugin:**
- Update paths:
  - `aitoolkit_run_py = "/app/vendor/ai-toolkit/run.py"`
  - Use system Python (no separate venv needed since deps in image)

### Step 6: Health Integration

- API `/health` endpoint should check ComfyUI readiness
- Return degraded status if ComfyUI is not reachable
- Log service status on startup

### Step 7: Port Exposure

**Exposed (public):**
- Port 22: SSH
- Port 3000: nginx (Web GUI + API proxy)
- Port 8000: API (direct, optional)

**NOT Exposed (internal only):**
- Port 8188: ComfyUI (bound to 127.0.0.1)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFYUI_HOST` | `127.0.0.1` | ComfyUI bind address |
| `COMFYUI_PORT` | `8188` | ComfyUI port |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | Full ComfyUI URL |
| `AITOOLKIT_PATH` | `/app/vendor/ai-toolkit` | AI-Toolkit location |

## Smoke Test

`scripts/smoke/smoke_internal_engines.sh` will:

1. Build Docker image locally
2. Run container
3. Verify API health endpoint
4. Verify ComfyUI is reachable internally (exec curl)
5. Verify ComfyUI is NOT reachable from host (port not published)
6. Run minimal generation workflow in fast-test mode

## Rollback Plan

If issues arise:
1. Revert to previous Docker image
2. Git subtree pins can be rolled back via normal git revert
3. Old runtime-clone approach still works if needed (but deprecated)

## Timeline Tracking

- [ ] Vendor scaffolding created
- [ ] ComfyUI vendored and pinned
- [ ] AI-Toolkit vendored and pinned
- [ ] Dockerfile updated
- [ ] Entrypoint updated
- [ ] Plugins updated
- [ ] Health checks integrated
- [ ] Smoke test passing
- [ ] CLAUDE.md updated

## Appendix: Pin Management Scripts

### pin_status.sh
```bash
#!/bin/bash
# Show current vendor pins and dirty status
cat vendor/VENDOR_PINS.json | jq .
echo ""
echo "Git status:"
git status vendor/ --short
```

### update_vendor.sh
```bash
#!/bin/bash
# Update a vendored repo to a new commit
# Usage: update_vendor.sh <comfyui|ai-toolkit> <commit-or-tag>
VENDOR=$1
COMMIT=$2

case $VENDOR in
  comfyui)
    REPO="https://github.com/comfyanonymous/ComfyUI.git"
    PREFIX="vendor/comfyui"
    ;;
  ai-toolkit)
    REPO="https://github.com/ostris/ai-toolkit.git"
    PREFIX="vendor/ai-toolkit"
    ;;
  *)
    echo "Unknown vendor: $VENDOR"
    exit 1
    ;;
esac

git subtree pull --prefix=$PREFIX $REPO $COMMIT --squash -m "vendor: update $VENDOR to $COMMIT"

# Update pins file
# (manual step - update VENDOR_PINS.json with new commit and date)
```
