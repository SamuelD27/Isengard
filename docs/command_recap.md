# Isengard Command Recap

A comprehensive guide to all available commands in the Isengard project.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Development Commands](#development-commands)
3. [Testing Commands](#testing-commands)
4. [Docker Commands](#docker-commands)
5. [Deployment Commands](#deployment-commands)
6. [Utility Scripts](#utility-scripts)
7. [Environment Variables](#environment-variables)

---

## Quick Start

### Start Everything (Development)

```bash
# Option 1: Docker Compose (recommended)
docker-compose up

# Option 2: Helper script
./scripts/dev.sh start

# Option 3: Background mode
docker-compose up -d
./scripts/dev.sh start -d
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | Web UI |
| API | http://localhost:8000 | Backend API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| ComfyUI | http://localhost:8188 | Image generation (production mode) |

---

## Development Commands

### Frontend (apps/web/)

**Run from:** `apps/web/` directory

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server with hot reload |
| `npm run build` | TypeScript compile + production build |
| `npm run lint` | ESLint check (strict, no warnings allowed) |
| `npm run format` | Format code with Prettier |
| `npm run preview` | Preview production build locally |

**Examples:**
```bash
# Start frontend development
cd apps/web
npm install
npm run dev

# Build for production
npm run build

# Fix linting issues
npm run lint
npm run format
```

### Backend (apps/api/)

**Run from:** `apps/api/` directory or project root

| Command | Description |
|---------|-------------|
| `uvicorn apps.api.src.main:app --reload` | Start API with hot reload |
| `pytest` | Run Python tests |
| `ruff check .` | Lint Python code |
| `ruff format .` | Format Python code |

**Examples:**
```bash
# Start backend development
cd apps/api
pip install -r requirements.txt
uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
pytest -v

# Lint and format
ruff check . --fix
ruff format .
```

### Dev Helper Script

**Run from:** Project root

The `scripts/dev.sh` script provides convenient shortcuts:

```bash
./scripts/dev.sh start              # Start all services
./scripts/dev.sh start -d           # Start in background (detached)
./scripts/dev.sh stop               # Stop all services
./scripts/dev.sh build              # Rebuild Docker images
./scripts/dev.sh logs               # Follow all service logs
./scripts/dev.sh logs api           # Follow specific service logs
./scripts/dev.sh logs worker        # Follow worker logs
./scripts/dev.sh test               # Run API tests
./scripts/dev.sh format             # Format Python + TypeScript
./scripts/dev.sh lint               # Lint Python + TypeScript
./scripts/dev.sh shell              # Open shell in API container
./scripts/dev.sh shell worker       # Open shell in worker container
./scripts/dev.sh health             # Check service health endpoints
```

---

## Testing Commands

### E2E Tests (Playwright)

**Run from:** `e2e/` directory

| Command | Description |
|---------|-------------|
| `npm test` | Run all Playwright tests (headless) |
| `npm run test:headed` | Run with browser visible |
| `npm run test:ui` | Interactive UI mode |
| `npm run report` | View HTML test report |

**Examples:**
```bash
cd e2e
npm install

# Run all E2E tests
npm test

# Run specific test file
npx playwright test gui-api-wiring.spec.ts

# Run with browser visible (debugging)
npm run test:headed

# Interactive mode
npm run test:ui

# Generate and view report
npm run report
```

### Test Files

| File | Purpose |
|------|---------|
| `e2e/tests/characters.spec.ts` | Character CRUD operations |
| `e2e/tests/training.spec.ts` | Training job flow |
| `e2e/tests/uelr.spec.ts` | User End Log Register |
| `e2e/tests/gui-api-wiring.spec.ts` | API routing verification |

### E2E Test Runner Script

**Run from:** Project root

```bash
./scripts/e2e.sh                   # Full E2E suite (starts services)
./scripts/e2e.sh --api-only        # API smoke tests only
./scripts/e2e.sh --browser         # Include Playwright browser tests
./scripts/e2e.sh --help            # Show help
```

**Environment options:**
```bash
# Use custom API URL
API_BASE_URL=http://my-server:8000 ./scripts/e2e.sh

# Keep services running after tests
SKIP_CLEANUP=1 ./scripts/e2e.sh
```

### Smoke Test (API Wiring)

**Run from:** Project root

Quick curl-based verification of API routing:

```bash
# Test local development
./scripts/smoke_gui_api.sh

# Test specific URL
./scripts/smoke_gui_api.sh http://localhost:3000

# Test remote pod
./scripts/smoke_gui_api.sh http://pod-url:3000
```

**What it checks:**
- `/api/health` returns JSON
- `/api/info` returns capability schema
- `/api/characters` returns character list
- `/api/training` returns job list
- `/api/generation` returns job list
- No HTML fallback (detects static server misrouting)

**Output:**
- Console: Pass/fail for each endpoint
- Artifacts: `artifacts/e2e/{timestamp}/` with response files

---

## Docker Commands

### Docker Compose

**Run from:** Project root

| Command | Description |
|---------|-------------|
| `docker-compose up` | Start all services (foreground) |
| `docker-compose up -d` | Start in background |
| `docker-compose up --build` | Rebuild images and start |
| `docker-compose down` | Stop and remove containers |
| `docker-compose logs -f` | Follow all logs |
| `docker-compose logs -f api` | Follow specific service |
| `docker-compose ps` | Show running containers |
| `docker-compose restart api` | Restart specific service |

### Running Commands in Containers

```bash
# Open shell in API container
docker-compose exec api bash

# Run tests in API container
docker-compose exec api pytest -v

# Run linting in API container
docker-compose exec api ruff check .

# Run npm commands in web container
docker-compose exec web npm run lint

# Check API health
docker-compose exec api curl http://localhost:8000/api/health
```

### Services Defined

| Service | Port | Description |
|---------|------|-------------|
| `redis` | 6379 | Job queue |
| `api` | 8000 | FastAPI backend |
| `worker` | - | Background job processor |
| `web` | 3000 | React frontend (Vite) |

---

## Deployment Commands

### RunPod Deployment

**Run from:** Project root

#### Create/Manage Pods

```bash
# Create a new GPU pod
./deploy/runpod/deploy.sh create

# Check pod status
./deploy/runpod/deploy.sh status

# Delete pod
./deploy/runpod/deploy.sh delete

# Update (delete + recreate)
./deploy/runpod/deploy.sh update
```

#### Required Environment Variables

```bash
export RUNPOD_API_KEY="rpa_xxx"      # RunPod API key
export RUNPOD_VOLUME_ID="vol_xxx"    # Network volume ID
export HF_TOKEN="hf_xxx"             # HuggingFace token
```

#### Optional Environment Variables

```bash
export POD_NAME="isengard-worker-1"  # Pod name
export GPU_TYPE="RTX_4090"           # GPU type
export GPU_COUNT="1"                 # Number of GPUs
export IMAGE="ghcr.io/xxx:latest"    # Docker image
```

### SSH to RunPod

```bash
# Get connection info from RunPod dashboard, then:
ssh root@<pod-ip> -p <port> -i ~/.ssh/id_ed25519

# Quick health check on pod
ssh root@<pod-ip> -p <port> -i ~/.ssh/id_ed25519 "curl http://localhost:3000/api/health"
```

### Pod Service Management

Once connected to pod via SSH:

```bash
# Check all services
ps aux | grep -E '(python|uvicorn|node|nginx|redis)'

# Check nginx status
nginx -t && nginx -s reload

# Restart API
pkill -f uvicorn && uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 &

# View logs
tail -f /runpod-volume/isengard/logs/api/latest/api.log
```

---

## Utility Scripts

### Log Collection

**Run from:** Project root

```bash
# Collect all logs into archive
./scripts/collect_logs.sh

# Specify output directory
./scripts/collect_logs.sh /path/to/output
```

**Output:** `logs/bundle-{timestamp}.tar.gz`

**Contents:**
- API logs
- Worker logs
- Job logs
- System information
- Environment details

### Observability Smoke Test

**Run from:** Project root

```bash
# Test logging infrastructure
python scripts/obs_smoke_test.py
```

---

## Environment Variables

### Core Configuration

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `ISENGARD_MODE` | `fast-test`, `production` | `fast-test` | Operating mode |
| `VOLUME_ROOT` | Path | `./data` | Persistent storage root |
| `REDIS_URL` | URL | `redis://localhost:6379` | Redis connection |
| `LOG_DIR` | Path | `./logs` | Log directory |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARN`, `ERROR` | `INFO` | Log level |

### API Configuration

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `API_PORT` | Port number | `8000` | API server port |
| `COMFYUI_URL` | URL | `http://localhost:8188` | ComfyUI endpoint |
| `CORS_ORIGINS` | Comma-separated URLs | `*` | Allowed CORS origins |
| `DEBUG_ENDPOINTS` | `true`, `false` | `false` | Enable debug endpoints |

### API Keys (from CLAUDE.md)

```bash
# HuggingFace
export HF_TOKEN="hf_FAKE_TOKEN_FOR_TESTING_ONLY_XXX"

# RunPod
export RUNPOD_API_KEY="rpa_FAKE_TOKEN_FOR_TESTING_ONLY_XXXXXXXXXXXXX"

# Cloudflare R2
export CLOUDFLARE_ACCESS_KEY="4fcb7a2f5b18934a841f1c45860c1343"
export CLOUDFLARE_SECRET_ACCESS_KEY="75f51f60a84d6e4d554ec876bbd8b9d2dbae114d2298085d91655afbd75a8897"
```

---

## Cheat Sheet

### Daily Development

```bash
# Start working
docker-compose up -d
cd apps/web && npm run dev

# Before committing
npm run lint && npm run format
cd ../api && ruff check . --fix && ruff format .

# Run tests
cd e2e && npm test
```

### Debugging

```bash
# Check service health
curl http://localhost:3000/api/health
curl http://localhost:3000/api/_debug/echo

# View logs
docker-compose logs -f api
tail -f logs/api/latest/api.log

# Shell into container
docker-compose exec api bash
```

### Deployment

```bash
# Build production image
docker build -t isengard .

# Deploy to RunPod
./deploy/runpod/deploy.sh create

# Verify deployment
./scripts/smoke_gui_api.sh http://pod-url:3000
```

---

## File Locations

| Purpose | Location |
|---------|----------|
| Frontend code | `apps/web/src/` |
| Backend code | `apps/api/src/` |
| Worker code | `apps/worker/src/` |
| Shared utilities | `packages/shared/src/` |
| Plugins | `packages/plugins/` |
| E2E tests | `e2e/tests/` |
| Scripts | `scripts/` |
| Deployment | `deploy/` |
| Documentation | `docs/` |
| Reports | `reports/` |
