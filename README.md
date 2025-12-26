# Isengard

> Identity LoRA Training + ComfyUI Image Generation Platform

A GUI-first platform for training personalized LoRA models and generating AI images with identity consistency.

## Quick Start

```bash
# Clone and enter the repo
cd Isengard

# Start all services (fast-test mode)
docker-compose up

# Open the UI
open http://localhost:3000
```

The application starts in **fast-test mode** by default, which uses mock plugins to validate the full workflow without GPU or large model downloads.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                      │
│   http://localhost:3000                                  │
│   Characters | Training | Image Gen | Video (Soon)       │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   Backend API (FastAPI)                  │
│   http://localhost:8000                                  │
│   REST + SSE for real-time progress                      │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  Worker (Background Jobs)                │
│   Training via AI-Toolkit plugin                         │
│   Generation via ComfyUI plugin                          │
└─────────────────────────────────────────────────────────┘
```

## Operating Modes

| Mode | Purpose | Requirements |
|------|---------|--------------|
| `fast-test` | Validate wiring, UI flow | CPU only, no models |
| `production` | Full training & generation | GPU, downloaded models |

```bash
# Fast-test mode (default)
docker-compose up

# Production mode
ISENGARD_MODE=production docker-compose up
```

## Directory Structure

```
isengard/
├── apps/
│   ├── api/          # FastAPI backend
│   ├── worker/       # Background job processor
│   └── web/          # React frontend
├── packages/
│   ├── shared/       # Shared utilities (logging, config, types)
│   └── plugins/      # Swappable backends (training, image, video)
├── data/             # User data (gitignored)
│   ├── uploads/      # Training images
│   ├── models/       # Trained LoRAs
│   └── outputs/      # Generated images
├── logs/             # Observability logs
└── reports/          # Documentation
```

## Storage Layout

### Local Development
- `./data/` - All user artifacts (uploads, models, outputs)
- `./logs/` - Structured JSON logs per service
- `./tmp/` - Ephemeral scratch space

### Production (RunPod)
- `/runpod-volume/` or `/workspace/` - Persistent storage
- Container filesystem - Ephemeral only

## Development

### Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.11+ (for backend development)

### Run Locally

```bash
# All services via Docker
docker-compose up

# Or run services individually:

# Backend API
cd apps/api
pip install -r requirements.txt
uvicorn src.main:app --reload

# Worker
cd apps/worker
pip install -r requirements.txt
python -m src.main

# Frontend
cd apps/web
npm install
npm run dev
```

### Helper Script

```bash
./scripts/dev.sh start      # Start all services
./scripts/dev.sh stop       # Stop all services
./scripts/dev.sh logs api   # View API logs
./scripts/dev.sh health     # Check service health
./scripts/dev.sh shell api  # Open shell in API container
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/info` | GET | API info & capabilities |
| `/api/characters` | GET, POST | List/create characters |
| `/api/characters/{id}` | GET, PATCH, DELETE | Character CRUD |
| `/api/characters/{id}/images` | GET, POST | Training images |
| `/api/training` | GET, POST | Training jobs |
| `/api/training/{id}` | GET | Job status |
| `/api/training/{id}/stream` | GET | SSE progress stream |
| `/api/generation` | GET, POST | Generation jobs |
| `/api/generation/{id}/stream` | GET | SSE progress stream |

## Capabilities

| Feature | Status | Notes |
|---------|--------|-------|
| LoRA Training | Supported | Via AI-Toolkit |
| DoRA Training | Not Supported | Future consideration |
| Full Fine-tune | Not Supported | Out of scope |
| Image Generation | Supported | Via ComfyUI |
| Video Generation | Scaffold Only | In development |

## Observability

All services emit structured JSON logs with correlation IDs:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "level": "INFO",
  "service": "api",
  "correlation_id": "req-abc123",
  "message": "Training job started",
  "context": {"job_id": "train-xyz"}
}
```

View logs:
```bash
# Via Docker
docker-compose logs -f api

# Direct file access
tail -f logs/api/$(date +%Y-%m-%d).log | jq .
```

## Configuration

See `.env.example` for all available options:

```bash
cp .env.example .env
# Edit .env as needed
```

Key variables:
- `ISENGARD_MODE` - `fast-test` or `production`
- `LOG_LEVEL` - `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `REDIS_URL` - Redis connection string
- `COMFYUI_URL` - ComfyUI server (production mode)

## License

Private - All rights reserved
