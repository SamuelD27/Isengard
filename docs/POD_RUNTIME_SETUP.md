# Isengard Pod Fix Report v2

**Date:** 2025-12-28
**Pod:** RunPod with NVIDIA L40S (48GB VRAM)

---

## Summary

This document describes the comprehensive bootstrap system implemented to ensure reliable, idempotent pod startup with zero manual operator steps.

---

## What Was Fixed

### 1. AI-Toolkit Module Import Issue

**Problem:** The `ostris-ai-toolkit` pip package provides `ostris_ai_toolkit.toolkit`, not `toolkit` directly. The worker failed with:
```
ModuleNotFoundError: No module named 'toolkit'
```

**Solution:**
- Cloned the AI-Toolkit git repository directly to `/runpod-volume/isengard/ai-toolkit/`
- Created an isolated Python venv at `/runpod-volume/isengard/.venvs/aitoolkit/`
- Added the repo path to PYTHONPATH via a `.pth` file
- Patched `/app/packages/plugins/training/src/ai_toolkit.py` to use the venv python and `run.py` entry point

### 2. HuggingFace Token Propagation

**Problem:** Training failed with 401 Unauthorized when downloading FLUX.1-dev model.

**Solution:** Bootstrap script loads `/secrets.sh` at startup and exports `HF_TOKEN` to all subprocess environments.

### 3. PYTHONPATH Conflict

**Problem:** Adding `/app/packages/shared/src` to PYTHONPATH caused `types.py` to shadow Python's stdlib `types` module.

**Solution:** Set `PYTHONPATH=/app` only, not individual subdirectories. Imports use fully qualified paths like `packages.shared.src.types`.

### 4. Model Symlinks

**Problem:** FLUX models in `/runpod-volume/isengard/comfyui/models/checkpoints/` weren't available to ComfyUI's `unet/` folder for workflows using `UNETLoader`.

**Solution:** Bootstrap creates symlinks from checkpoints to the unet folder.

---

## File Locations

| Path | Purpose |
|------|---------|
| `/runpod-volume/isengard/` | Root persistent data directory |
| `/runpod-volume/isengard/bootstrap_v2.sh` | Main startup script |
| `/runpod-volume/isengard/restart_services.sh` | Quick service restart helper |
| `/runpod-volume/isengard/ai-toolkit/` | AI-Toolkit git clone |
| `/runpod-volume/isengard/.venvs/aitoolkit/` | Isolated Python venv |
| `/runpod-volume/isengard/logs/` | Service logs (API, Worker, ComfyUI, Web) |
| `/runpod-volume/isengard/loras/` | Trained LoRA models |
| `/runpod-volume/isengard/uploads/` | User uploaded images |
| `/runpod-volume/isengard/outputs/` | Generated images |
| `/runpod-volume/isengard/comfyui/models/` | FLUX model files |

---

## Bootstrap Script Features

The `bootstrap_v2.sh` script handles:

1. **Environment Setup**
   - Creates directory structure
   - Loads `/secrets.sh` for credentials
   - Sets required environment variables (HF_TOKEN, PYTHONPATH, etc.)

2. **AI-Toolkit Setup**
   - Clones/updates the git repository
   - Creates/verifies isolated Python venv
   - Installs dependencies from `requirements.txt`
   - Adds PYTHONPATH via `.pth` file

3. **Plugin Patching**
   - Patches `ai_toolkit.py` to use isolated venv
   - Only patches once (idempotent)

4. **Model Symlinks**
   - Links trained LoRAs to ComfyUI's loras folder
   - Links FLUX models to unet folder
   - Verifies all required models present

5. **Service Orchestration**
   - Stops existing services cleanly
   - Starts: Redis → ComfyUI → API → Worker → Web
   - Waits for each service to be healthy

6. **Health Checks**
   - Verifies Redis, API, ComfyUI, Web responding
   - Reports any failures

7. **E2E Smoke Test**
   - Tests API endpoints (characters, training, generation)
   - Tests ComfyUI node availability
   - Tests AI-Toolkit module import

---

## Usage

### Full Bootstrap (after pod restart)
```bash
source /secrets.sh
/runpod-volume/isengard/bootstrap_v2.sh
```

### Quick Restart (services only)
```bash
/runpod-volume/isengard/bootstrap_v2.sh --restart-only
```

### Skip E2E Tests
```bash
/runpod-volume/isengard/bootstrap_v2.sh --skip-e2e
```

### Restart Individual Service
```bash
/runpod-volume/isengard/restart_services.sh api
/runpod-volume/isengard/restart_services.sh worker
/runpod-volume/isengard/restart_services.sh comfyui
/runpod-volume/isengard/restart_services.sh web
/runpod-volume/isengard/restart_services.sh all
```

---

## Service Ports

| Service | Port | URL |
|---------|------|-----|
| API | 8000 | http://localhost:8000 |
| ComfyUI | 8188 | http://localhost:8188 |
| Web | 3000 | http://localhost:3000 |
| Redis | 6379 | redis://localhost:6379 |

---

## Log Locations

```bash
# Real-time logs
tail -f /runpod-volume/isengard/logs/api/api.log
tail -f /runpod-volume/isengard/logs/worker/worker.log
tail -f /runpod-volume/isengard/logs/comfyui/comfyui.log
tail -f /runpod-volume/isengard/logs/web/web.log
```

---

## Validation Commands

```bash
# Check all services
ss -tlnp | grep -E "8000|8188|3000|6379"

# Health checks
curl -s http://localhost:8000/health
curl -s http://localhost:8188/system_stats | head -1
redis-cli ping

# Test AI-Toolkit
/runpod-volume/isengard/.venvs/aitoolkit/bin/python -c "from toolkit.job import run_job; print('OK')"

# List trained LoRAs
ls -la /runpod-volume/isengard/loras/

# List FLUX models
ls -la /opt/ComfyUI/models/unet/
ls -la /opt/ComfyUI/models/checkpoints/
```

---

## Patched File

The following file was patched to use the isolated AI-Toolkit environment:

**`/app/packages/plugins/training/src/ai_toolkit.py`**

Changes:
```python
# Original:
cmd = ["python", "-m", "toolkit.job", str(config_path)]

# Patched:
aitoolkit_venv_python = "/runpod-volume/isengard/.venvs/aitoolkit/bin/python"
aitoolkit_run_py = "/runpod-volume/isengard/ai-toolkit/run.py"
cmd = [aitoolkit_venv_python, aitoolkit_run_py, str(config_path)]

# Also added cwd and env to subprocess.Popen:
cwd="/runpod-volume/isengard/ai-toolkit",
env={**os.environ, "PYTHONUNBUFFERED": "1", "HF_HOME": "/runpod-volume/isengard/.cache/huggingface"}
```

---

## Troubleshooting

### API Not Starting
```bash
tail -20 /runpod-volume/isengard/logs/api/api.log
```
Common issues:
- PYTHONPATH conflict (should be just `/app`)
- Redis not running

### Worker Not Processing Jobs
```bash
tail -20 /runpod-volume/isengard/logs/worker/worker.log
```
Common issues:
- HF_TOKEN not set (load `/secrets.sh`)
- AI-Toolkit venv not found

### ComfyUI Not Generating
```bash
tail -20 /runpod-volume/isengard/logs/comfyui/comfyui.log
```
Common issues:
- Model files missing
- GPU memory exhausted

---

## Important Notes

1. **Persistence:** All data in `/runpod-volume/isengard/` survives pod restarts
2. **Idempotency:** Bootstrap can be run multiple times safely
3. **Secrets:** Never commit `/secrets.sh` - it contains HF_TOKEN
4. **Models:** FLUX models are stored on network volume, not container
