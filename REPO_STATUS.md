# Isengard Repository Status Report

**Date:** 2025-12-27
**Version:** 0.1.0
**Status:** Production Ready (Core Features)

---

## Overview

Isengard is a GUI-first platform for creating personalized AI-generated content. It enables non-technical users to train identity LoRAs from their photos and generate high-quality images using FLUX models through ComfyUI.

---

## Repository Structure

```
isengard/
├── apps/
│   ├── api/                      # FastAPI Backend
│   │   ├── src/
│   │   │   ├── main.py           # API entry point
│   │   │   ├── middleware.py     # CORS, logging middleware
│   │   │   ├── routes/
│   │   │   │   ├── characters.py # Character CRUD + image management
│   │   │   │   ├── training.py   # Training job management
│   │   │   │   ├── generation.py # Image generation + output serving
│   │   │   │   ├── health.py     # Health check endpoint
│   │   │   │   └── logs.py       # Log streaming endpoint
│   │   │   └── services/
│   │   │       └── job_executor.py # Background job execution
│   │   └── requirements.txt
│   │
│   ├── worker/                   # Background Job Processor
│   │   ├── src/
│   │   │   ├── main.py           # Worker entry point
│   │   │   └── job_processor.py  # Redis job consumer
│   │   └── requirements.txt
│   │
│   └── web/                      # React Frontend
│       ├── src/
│       │   ├── App.tsx           # Main app with routing
│       │   ├── main.tsx          # React entry point
│       │   ├── index.css         # Global styles (dark theme)
│       │   ├── components/
│       │   │   ├── Layout.tsx    # Sidebar navigation
│       │   │   └── ui/           # Reusable UI components
│       │   │       ├── button.tsx
│       │   │       ├── card.tsx
│       │   │       ├── input.tsx
│       │   │       ├── label.tsx
│       │   │       ├── progress.tsx
│       │   │       └── textarea.tsx
│       │   ├── pages/
│       │   │   ├── Characters.tsx  # Character management + synthetic gen
│       │   │   ├── Dataset.tsx     # Global dataset manager
│       │   │   ├── Training.tsx    # Training with presets + live logs
│       │   │   ├── ImageGen.tsx    # Image generation with toggles
│       │   │   └── Video.tsx       # Placeholder (coming soon)
│       │   ├── lib/
│       │   │   ├── api.ts        # API client
│       │   │   ├── utils.ts      # Utilities (cn, correlation ID)
│       │   │   └── logger.ts     # Client-side logging
│       │   └── hooks/
│       │       └── useSSE.ts     # Server-Sent Events hook
│       ├── package.json
│       ├── vite.config.ts
│       ├── tailwind.config.js
│       └── tsconfig.json
│
├── packages/
│   ├── shared/                   # Shared Python Libraries
│   │   └── src/
│   │       ├── types.py          # Pydantic models (Character, Job, Config)
│   │       ├── config.py         # Environment configuration
│   │       ├── logging.py        # Structured JSON logging
│   │       ├── redis_client.py   # Redis job queue client
│   │       ├── capabilities.py   # Feature capability matrix
│   │       ├── rate_limit.py     # Rate limiting decorators
│   │       └── security.py       # Path sanitization
│   │
│   └── plugins/
│       ├── training/             # Training Backend
│       │   └── src/
│       │       ├── interface.py  # Abstract training interface
│       │       ├── ai_toolkit.py # AI-Toolkit LoRA trainer
│       │       ├── mock_plugin.py # Fast-test mock trainer
│       │       └── registry.py   # Plugin registry
│       │
│       ├── image/                # Image Generation Backend
│       │   ├── src/
│       │   │   ├── interface.py  # Abstract generation interface
│       │   │   ├── comfyui.py    # ComfyUI adapter
│       │   │   ├── mock_plugin.py # Fast-test mock generator
│       │   │   └── registry.py   # Plugin registry
│       │   └── workflows/        # ComfyUI workflow templates
│       │       ├── flux-dev.json
│       │       ├── flux-schnell.json
│       │       ├── flux-dev-lora.json
│       │       └── flux-schnell-lora.json
│       │
│       └── video/                # Video Generation (Scaffold)
│           └── src/
│               └── interface.py  # Abstract interface only
│
├── docs/
│   └── reports/
│       └── 2025-12-27_ui-gaps.md # Implementation report
│
├── scripts/
│   ├── dev.sh                    # Development startup
│   ├── download_models.py        # Model downloader
│   ├── validate_logs.py          # Log validation
│   └── obs_smoke_test.py         # Observability tests
│
├── tests/
│   ├── conftest.py               # Pytest fixtures
│   ├── test_workflow.py          # Workflow tests
│   └── test_redis_integration.py # Redis integration tests
│
├── deploy/
│   └── runpod/
│       ├── template.yaml         # RunPod template config
│       ├── deploy.sh             # Deployment script
│       ├── secrets.sh            # Secrets template
│       └── start.sh              # Pod startup script
│
├── start.sh                      # Main startup script
├── Dockerfile                    # Container build
├── docker-compose.yaml           # Local development
├── docker-compose.gpu.yaml       # GPU development
├── CLAUDE.md                     # Project instructions
└── README.md                     # Project documentation
```

---

## Implemented Features

### 1. Character Management
- **Create characters** with name, description, and trigger word
- **Inline image upload** during character creation
- **Image preview** with lazy loading
- **Individual image delete** from character
- **Character detail view** with image grid
- **Training guidelines** displayed in UI

### 2. Dataset Manager
- **Global image grid** across all characters
- **Search** by filename or character name
- **Filter** by character
- **Multi-select** for bulk operations
- **Bulk delete** with confirmation
- **Character summary cards** with image counts

### 3. Training System
- **Training presets** (Quick, Balanced, High Quality)
- **Advanced parameters** (optimizer, scheduler, precision, batch size)
- **Live log streaming** via SSE
- **Real-time progress** display
- **Job history** with config summary
- **LoRA overwrite warning**

### 4. Image Generation
- **7 aspect ratio presets** (1:1, 4:5, 3:4, 9:16, 5:4, 4:3, 16:9)
- **Quality tiers** (Draft, Standard, High Quality)
- **Advanced toggles** (ControlNet, IP-Adapter, Face Detailer, Upscale)
- **LoRA selection** from trained characters
- **Real-time progress** display
- **Output gallery** for completed jobs

### 5. Synthetic Image Generation
- **Generate button** for trained characters
- **Prompt input** with trigger word pre-filled
- **Batch generation** (1, 2, 4, or 8 images)
- **Staging area** for preview
- **Keep/Discard workflow** for each image
- **Auto-save** kept images to training dataset

### 6. FLUX Workflows
- **flux-dev.json** - Standard FLUX.1-dev generation
- **flux-schnell.json** - Fast FLUX.1-schnell generation
- **flux-dev-lora.json** - FLUX.1-dev with LoRA
- **flux-schnell-lora.json** - FLUX.1-schnell with LoRA

All workflows use disaggregated architecture:
- UNETLoader (from unet/ folder)
- DualCLIPLoader (CLIP-L + T5-XXL)
- VAELoader (ae.safetensors)

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/info` | GET | System info and capabilities |
| `/api/characters` | GET | List all characters |
| `/api/characters` | POST | Create character |
| `/api/characters/{id}` | GET | Get character details |
| `/api/characters/{id}` | DELETE | Delete character |
| `/api/characters/{id}/images` | GET | List images |
| `/api/characters/{id}/images` | POST | Upload images |
| `/api/characters/{id}/images/{file}` | GET | Serve image |
| `/api/characters/{id}/images/{file}` | DELETE | Delete image |
| `/api/training` | GET | List training jobs |
| `/api/training` | POST | Start training |
| `/api/training/{id}` | GET | Get job status |
| `/api/training/{id}/stream` | GET | SSE progress stream |
| `/api/training/{id}/cancel` | POST | Cancel job |
| `/api/generation` | GET | List generation jobs |
| `/api/generation` | POST | Start generation |
| `/api/generation/{id}` | GET | Get job status |
| `/api/generation/{id}/stream` | GET | SSE progress stream |
| `/api/generation/{id}/cancel` | POST | Cancel job |
| `/api/generation/output/{file}` | GET | Serve generated image |

---

## Tech Stack

### Backend
- **FastAPI** - REST API framework
- **Redis** - Job queue and pub/sub
- **Pydantic** - Data validation
- **SSE-Starlette** - Server-Sent Events

### Frontend
- **React 18** - UI framework
- **TypeScript** - Type safety
- **TanStack Query** - Data fetching
- **Tailwind CSS** - Styling
- **Vite** - Build tool

### AI/ML
- **ComfyUI** - Image generation backend
- **AI-Toolkit** - LoRA training
- **FLUX.1** - Base model (dev + schnell)

### Infrastructure
- **Docker** - Containerization
- **RunPod** - GPU cloud
- **Cloudflare R2** - Model storage

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ISENGARD_MODE` | `production` or `fast-test` | `production` |
| `VOLUME_ROOT` | Persistent storage path | `/runpod-volume/isengard` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379` |
| `COMFYUI_URL` | ComfyUI API endpoint | `http://localhost:8188` |
| `USE_REDIS` | Enable Redis mode | `true` |
| `HF_TOKEN` | HuggingFace API token | Required for model download |

---

## Startup Sequence

The `start.sh` script performs:

1. **SSH Configuration** - Set up SSH access for debugging
2. **Directory Creation** - Create persistent storage structure
3. **Rclone Setup** - Configure R2 access for model download
4. **Model Download** - Download FLUX models (R2 first, HF fallback)
5. **Redis Start** - Start Redis server
6. **ComfyUI Start** - Start ComfyUI with model symlinks
7. **API Start** - Start FastAPI backend
8. **Frontend Build** - Build React app if needed
9. **Frontend Start** - Serve static files
10. **Worker Start** - Start background job processor
11. **Status Check** - Verify all services running

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         React Frontend                               │
│  Characters | Dataset | Training | Generate | Video                  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ HTTP / SSE
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                              │
│  Routes → Services → Redis Queue                                     │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ Redis Streams
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Worker Process                               │
│  Job Processor → Plugin Executor                                     │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌─────────┐     ┌─────────┐     ┌─────────┐
        │Training │     │ Image   │     │ Video   │
        │ Plugin  │     │ Plugin  │     │ Plugin  │
        │AI-Toolkit│    │ComfyUI │     │Scaffold │
        └─────────┘     └─────────┘     └─────────┘
```

---

## Known Limitations

### Not Implemented
1. Caption editing for dataset images
2. Image tagging system
3. Dataset export as ZIP
4. Split management (reference/train/synthetic)
5. Training sample previews during training
6. ControlNet/IP-Adapter/FaceDetailer workflow variants
7. Video generation (scaffold only)

### Technical Limitations
- Advanced training parameters passed to API but not fully utilized by AI-Toolkit
- Synthetic images mixed with uploaded images (no separate tracking)
- Mobile responsiveness needs improvement

---

## Quick Start

### Local Development
```bash
# Start with Docker Compose
docker-compose up --build

# Or start services individually
cd apps/api && uvicorn src.main:app --reload
cd apps/web && npm run dev
```

### RunPod Deployment
```bash
# Build Docker image
docker build -t isengard:latest .

# Push to registry
docker tag isengard:latest <registry>/isengard:latest
docker push <registry>/isengard:latest

# Deploy to RunPod with template
```

---

## Files Changed in This Session

### Frontend (apps/web/src/)
- `pages/Characters.tsx` - Added synthetic generation panel
- `pages/Dataset.tsx` - Created global dataset manager
- `pages/Training.tsx` - Added presets, advanced params, live logs
- `pages/ImageGen.tsx` - Added aspect ratio, toggles
- `components/Layout.tsx` - Added Dataset nav item
- `components/ui/textarea.tsx` - Created new component
- `lib/api.ts` - Extended types and endpoints
- `App.tsx` - Added /dataset route

### Backend (apps/api/src/)
- `routes/characters.py` - Added image serve/delete endpoints
- `routes/generation.py` - Added output file serving

### Workflows (packages/plugins/image/workflows/)
- `flux-dev.json` - Created FLUX-compatible workflow
- `flux-schnell.json` - Fixed existing workflow
- `flux-dev-lora.json` - Updated for FLUX + LoRA
- `flux-schnell-lora.json` - Created new workflow

### Infrastructure
- `start.sh` - Updated with unet symlinks, frontend build

---

*Generated: 2025-12-27*
