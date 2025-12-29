# Startup Script Image Fix Report

**Date:** 2025-12-28
**Issue:** New pods run old startup script despite image rebuild

---

## Root Cause

The Dockerfile was copying the **WRONG** `start.sh` file:

```dockerfile
# OLD (WRONG)
COPY deploy/runpod/start.sh /start.sh

# NEW (CORRECT)
COPY start.sh /start.sh
```

**Two `start.sh` files existed in the repo:**

| File | SHA256 (12 chars) | Lines | Has nginx? | Has AI-Toolkit? | Has version banner? |
|------|-------------------|-------|-----------|-----------------|---------------------|
| `start.sh` (repo root) | `aa0d95a8fba0` | 543 | Yes (15 refs) | Yes | Yes (`v2.1.0`) |
| `deploy/runpod/start.sh` | `ada66a126819` | 465 | No | No | No |

The Dockerfile was copying the OLD `deploy/runpod/start.sh`, so all the fixes (nginx reverse proxy, AI-Toolkit setup, version banner) were never included in the Docker image.

---

## Files Changed

1. **`Dockerfile`** (lines 173-180):
   - Changed `COPY deploy/runpod/start.sh /start.sh` → `COPY start.sh /start.sh`
   - Added version marker file creation

2. **`start.sh`** (repo root):
   - Updated version to `v2.1.0-nginx-aitoolkit`
   - Added SHA256 self-verification on startup

---

## How to Build and Push

### Quick Build
```bash
docker build --no-cache -t sdukmedjian/isengard:latest .
docker push sdukmedjian/isengard:latest
```

### Versioned Tag (Recommended)
```bash
TAG="$(date +%Y%m%d-%H%M)-$(git rev-parse --short HEAD)"
docker build --no-cache -t sdukmedjian/isengard:${TAG} -t sdukmedjian/isengard:latest .
docker push sdukmedjian/isengard:${TAG}
docker push sdukmedjian/isengard:latest
echo "Pushed: sdukmedjian/isengard:${TAG}"
```

---

## RunPod Template Start Command

The template should use the default entrypoint (no override needed):

```
# Leave "Start Command" empty or set to:
/start.sh
```

---

## How to Verify on Next Pod

When the pod starts, you should see this banner in the logs:

```
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║   ██╗███████╗███████╗███╗   ██╗ ██████╗  █████╗ ██████╗ ██████╗  ║
║   ...                                                      ║
║   Script Version: v2.1.0-nginx-aitoolkit                   ║
║   Build Date:     2025-12-28                               ║
║   Script SHA256:  aa0d95a8fba0                             ║
║                                                            ║
║   Features:                                                ║
║     ✓ nginx reverse proxy (port 3000 → API 8000)          ║
║     ✓ AI-Toolkit isolated venv                            ║
║     ✓ SSE streaming support                               ║
║     ✓ Persistent volume storage                           ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
```

### Verification Checklist

1. **Banner visible:** Look for `v2.1.0-nginx-aitoolkit` in pod startup logs
2. **SHA256 matches:** Should show `aa0d95a8fba0` (or recalculated if script changes)
3. **nginx running:** `pgrep nginx` should return a PID
4. **API proxy works:** `curl http://localhost:3000/api/health` should return JSON (not HTML)
5. **Version file exists:** `cat /app/BOOTSTRAP_VERSION` should show version and SHA

### SSH Commands to Verify

```bash
# Connect to pod
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519

# Check version file
cat /app/BOOTSTRAP_VERSION

# Check script SHA matches
sha256sum /start.sh

# Check nginx is running
pgrep -a nginx

# Test API proxy
curl -s http://localhost:3000/api/health | head
```

---

## Prevention

1. **Single source of truth:** `start.sh` at repo root is THE startup script
2. **`deploy/runpod/start.sh` is deprecated:** Consider removing or making it a symlink
3. **Version banner:** Every future change should bump `SCRIPT_VERSION`
4. **SHA256 in logs:** Makes it trivial to verify which script is running

---

## Summary

| Before | After |
|--------|-------|
| Dockerfile copied wrong file | Dockerfile copies correct `start.sh` |
| No version banner | Version `v2.1.0-nginx-aitoolkit` with SHA256 |
| No nginx | nginx reverse proxy on port 3000 |
| No AI-Toolkit setup | AI-Toolkit venv created at boot |
| `serve` static server | nginx with API proxy |
