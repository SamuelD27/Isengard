# Isengard Deployment Ports & Routing

This document describes the canonical port configuration and routing setup for Isengard across all deployment environments.

## Principle: Single Public Entrypoint

**Users should only access ONE URL/port**. This port serves both the frontend UI and proxies API requests to the backend. This avoids CORS issues and ensures consistent routing.

---

## Port Map

| Service | Internal Port | Exposed Externally | Purpose |
|---------|---------------|-------------------|---------|
| **Nginx (Reverse Proxy)** | 80, 3000 | Yes (primary) | Public entrypoint: serves UI + proxies /api |
| **FastAPI Backend** | 8000 | No (internal only) | API server |
| **ComfyUI** | 8188 | No (internal only) | Image generation backend |
| **Redis** | 6379 | No (internal only) | Job queue |
| **Worker** | N/A | No | Background job processor |

---

## Request Flow

```
Browser/Client
     │
     │ https://pod-url:3000/  (or port 80)
     ▼
┌─────────────────────────────┐
│       Nginx Proxy           │
│  (port 80, 3000 listener)   │
└─────────────────────────────┘
     │                    │
     │ Static files       │ /api/* requests
     │ (/, /js, /css)     │
     ▼                    ▼
┌──────────────┐   ┌──────────────────────┐
│ Static Files │   │ proxy_pass           │
│ /app/apps/   │   │ http://127.0.0.1:8000│
│ web/dist/    │   └──────────────────────┘
└──────────────┘              │
                              ▼
                    ┌──────────────────────┐
                    │   FastAPI Backend    │
                    │      (port 8000)     │
                    └──────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
     ┌──────────┐      ┌──────────┐      ┌──────────┐
     │  Redis   │      │  Worker  │      │ ComfyUI  │
     │  (6379)  │      │          │      │  (8188)  │
     └──────────┘      └──────────┘      └──────────┘
```

---

## Environment Configurations

### Local Development (Vite Dev Server)

```bash
# Start all services
docker-compose up

# OR run individually:
# Terminal 1: Backend
cd apps/api && uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend (with Vite proxy)
cd apps/web && npm run dev -- --host
```

**Routing:**
- Frontend dev server: `http://localhost:3000`
- Vite proxies `/api/*` to `http://localhost:8000` (see `vite.config.ts`)
- No nginx needed in dev mode

### Docker Compose

```yaml
# docker-compose.yaml
services:
  web:
    ports:
      - "3000:80"  # Nginx serves on port 80 internally, exposed as 3000
```

**Routing:**
- User accesses: `http://localhost:3000`
- Nginx serves static files and proxies `/api/*` to `http://api:8000`

### Production (RunPod / Bare Metal)

**start.sh** launches:
1. Redis on 6379
2. ComfyUI on 8188
3. FastAPI on 8000
4. Worker process
5. **Nginx on 80 and 3000** (public entrypoints)

**Routing:**
- User accesses: `http://<pod-ip>:3000` (or RunPod proxy URL)
- Nginx serves static files from `/app/apps/web/dist/`
- Nginx proxies `/api/*` to `http://127.0.0.1:8000`

---

## Nginx Configuration

The production nginx config (created dynamically or from template):

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    listen 3000;
    listen [::]:3000;

    root /app/apps/web/dist;
    index index.html;

    # API proxy - CRITICAL for GUI→API routing
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # SSE support - CRITICAL for streaming responses
        proxy_buffering off;
        proxy_read_timeout 86400s;
    }

    # SPA routing - fallback to index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## Common Misconfigurations

### 1. Static Server Serving /api/* Requests

**Symptom:** API calls return `index.html` instead of JSON.

**Cause:** Frontend dev server or static file server (like `serve`) doesn't proxy `/api/*`.

**Fix:** Use nginx (or equivalent) with proper proxy configuration.

### 2. Wrong Port in Frontend

**Symptom:** CORS errors or "connection refused".

**Cause:** Frontend is trying to call `http://localhost:8000` directly instead of relying on proxy.

**Fix:** Ensure `API_BASE = '/api'` (relative path) in frontend code. Never hardcode ports.

### 3. Missing Proxy in Development

**Symptom:** Works in Docker but not in local dev.

**Cause:** Vite proxy configuration missing or wrong.

**Fix:** Check `vite.config.ts`:
```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

### 4. SSE/WebSocket Broken

**Symptom:** Training/generation progress doesn't update.

**Cause:** Proxy is buffering SSE responses.

**Fix:** Add `proxy_buffering off;` to nginx config.

---

## Verification Commands

### Check if routing is correct:

```bash
# Should return JSON {"status": "healthy"}
curl http://localhost:3000/api/health

# Should return JSON with debug info (not HTML)
curl http://localhost:3000/api/_debug/echo

# Should NOT return HTML - if it does, routing is broken
curl -s http://localhost:3000/api/health | head -c 50
```

### Run full wiring audit:

```bash
# Smoke test (curl-based)
./scripts/smoke_gui_api.sh http://localhost:3000

# Playwright E2E tests
cd e2e && npx playwright test gui-api-wiring.spec.ts
```

---

## Port Checklist for New Deployments

- [ ] Nginx installed and running on ports 80 and 3000
- [ ] Nginx config has `/api/` proxy to `http://127.0.0.1:8000`
- [ ] Nginx config has `proxy_buffering off` for SSE
- [ ] FastAPI backend running on port 8000
- [ ] Redis running on port 6379
- [ ] ComfyUI running on port 8188 (if not fast-test mode)
- [ ] Worker process running
- [ ] `curl http://localhost:3000/api/health` returns JSON
- [ ] Frontend loads at `http://localhost:3000`
- [ ] "Create Character" button works (end-to-end test)
