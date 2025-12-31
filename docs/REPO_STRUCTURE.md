# Isengard Repository Structure

## Visual Repository Tree

```
isengard/
├── apps/                                    # 🖥️  APPLICATION SERVICES
│   ├── api/                                 # FastAPI backend (Port 8000)
│   │   └── src/
│   │       ├── main.py                      # App initialization
│   │       ├── middleware.py                # Correlation ID middleware
│   │       ├── routes/
│   │       │   ├── health.py                # Health checks & capabilities
│   │       │   ├── characters.py            # Character CRUD
│   │       │   ├── training.py              # Training job management
│   │       │   ├── generation.py            # Image generation
│   │       │   ├── loras.py                 # LoRA model endpoints
│   │       │   ├── jobs.py                  # Job status & artifacts
│   │       │   └── logs.py                  # Client log ingestion
│   │       └── services/
│   │           ├── config_validator.py      # Training config validation
│   │           └── job_executor.py          # Job execution logic
│   │
│   ├── web/                                 # React frontend (Port 3000)
│   │   └── src/
│   │       ├── main.tsx                     # React entry point
│   │       ├── App.tsx                      # Router & layout
│   │       ├── pages/
│   │       │   ├── Characters.tsx           # Character management
│   │       │   ├── StartTraining.tsx        # Training form
│   │       │   ├── OngoingTraining.tsx      # Active job monitoring
│   │       │   ├── TrainingHistory.tsx      # Job history
│   │       │   ├── TrainingDetail.tsx       # Job detail + loss chart
│   │       │   ├── Dataset.tsx              # Global image grid
│   │       │   ├── ImageGen.tsx             # Image generation UI
│   │       │   └── Video.tsx                # (scaffold)
│   │       ├── components/
│   │       │   ├── Layout.tsx               # Main layout
│   │       │   ├── training/
│   │       │   │   ├── LossChart.tsx        # Loss visualization
│   │       │   │   ├── SampleImagesPanel.tsx
│   │       │   │   ├── CheckpointsPanel.tsx
│   │       │   │   └── TrainingLogsPanel.tsx
│   │       │   └── ui/                      # Radix-based components
│   │       ├── hooks/
│   │       │   └── useSSE.ts                # Server-sent events
│   │       ├── lib/
│   │       │   ├── api.ts                   # API client
│   │       │   ├── api-errors.ts            # Error handling
│   │       │   └── logger.ts                # Client logging
│   │       └── uelr/                        # URL Error Logging & Redaction
│   │
│   └── worker/                              # Background job processor
│       └── src/
│           ├── main.py                      # Worker startup
│           └── job_processor.py             # Redis consumer
│
├── packages/                                # 📦  SHARED PACKAGES & PLUGINS
│   ├── shared/                              # Shared utilities (all services import)
│   │   └── src/
│   │       ├── config.py                    # Centralized config & paths
│   │       ├── types.py                     # Canonical type definitions
│   │       ├── events.py                    # Event schemas (SSE)
│   │       ├── logging.py                   # Structured JSON logging
│   │       ├── capabilities.py              # Plugin introspection
│   │       ├── redis_client.py              # Redis wrapper
│   │       ├── rate_limit.py                # Rate limiting
│   │       └── security.py                  # Security helpers
│   │
│   └── plugins/                             # Pluggable backends
│       ├── training/                        # LoRA training plugin
│       │   └── src/
│       │       ├── interface.py             # TrainingPlugin ABC
│       │       ├── ai_toolkit.py            # Real FLUX.1-dev training
│       │       ├── mock_plugin.py           # Fast-test simulation
│       │       └── registry.py              # Plugin loader
│       │
│       ├── image/                           # Image generation plugin
│       │   └── src/
│       │       ├── interface.py             # ImagePlugin ABC
│       │       ├── comfyui.py               # ComfyUI implementation
│       │       ├── mock_plugin.py           # Fast-test simulation
│       │       ├── registry.py              # Plugin loader
│       │       └── workflows/               # ComfyUI workflow JSONs
│       │
│       └── video/                           # Video plugin (scaffold only)
│           └── src/
│               └── interface.py             # VideoPlugin ABC
│
├── tests/                                   # 🧪  UNIT TESTS (Python/pytest)
│   ├── conftest.py                          # Fixtures
│   ├── test_capabilities.py
│   ├── test_redis_integration.py
│   ├── test_correlation.py
│   └── ...
│
├── e2e/                                     # 🎭  E2E TESTS (Playwright)
│   ├── tests/
│   │   ├── smoke/                           # Startup sanity
│   │   ├── edge-cases/                      # Error handling
│   │   ├── flows/                           # User flows
│   │   └── visual/                          # Visual regression
│   ├── pages/                               # Page objects
│   └── playwright.config.ts
│
├── data/                                    # 💾  LOCAL DEV DATA
│   ├── characters/                          # Character metadata
│   ├── uploads/                             # Raw training images
│   ├── datasets/                            # Processed datasets
│   ├── loras/                               # Trained models
│   └── outputs/                             # Generated images
│
├── docs/                                    # 📄  Documentation
├── deploy/                                  # Deployment configs
├── scripts/                                 # Build/utility scripts
├── infra/                                   # Infrastructure configs
├── logs/                                    # Application logs
├── _legacy_dump/                            # Archived deprecated code
│
├── Dockerfile                               # Container image (GPU)
├── docker-compose.yaml                      # Local orchestration
├── docker-compose.gpu.yaml                  # GPU variant
├── start.sh                                 # Container entrypoint
├── CLAUDE.md                                # Project intelligence
└── pytest.ini                               # Test config
```

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  React + Vite (apps/web)                                      │  │
│  │  • Pages: Characters, Training, ImageGen, Dataset             │  │
│  │  • Components: UI kit, Training charts, Panels                │  │
│  │  • Hooks: useSSE for real-time updates                        │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ HTTP + SSE
┌─────────────────────────────▼───────────────────────────────────────┐
│                          API LAYER                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  FastAPI (apps/api)                                           │  │
│  │  • Routes: /characters, /training, /generation, /jobs         │  │
│  │  • Middleware: Correlation IDs, CORS                          │  │
│  │  • Services: Config validation, Job execution                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ Redis Streams
┌─────────────────────────────▼───────────────────────────────────────┐
│                        WORKER LAYER                                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Background Worker (apps/worker)                              │  │
│  │  • Consumes jobs from Redis                                   │  │
│  │  • Loads & invokes plugins                                    │  │
│  │  • Manages GPU lifecycle                                      │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                        PLUGIN LAYER                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ Training Plugin │  │  Image Plugin   │  │   Video Plugin      │  │
│  │ ─────────────── │  │ ─────────────── │  │ ─────────────────── │  │
│  │ • AI-Toolkit    │  │ • ComfyUI       │  │ • (scaffold)        │  │
│  │ • Mock (test)   │  │ • Mock (test)   │  │                     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                        SHARED LAYER                                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  packages/shared                                              │  │
│  │  • config.py: Path resolution, environment modes              │  │
│  │  • types.py: Canonical types (Character, Job, Config)         │  │
│  │  • events.py: SSE event schemas (TrainingProgressEvent)       │  │
│  │  • logging.py: Structured JSON logging                        │  │
│  │  • redis_client.py: Job queue operations                      │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Relationships

| Component | Imports From | Exports To |
|-----------|--------------|------------|
| `apps/api` | `packages/shared` | HTTP responses to `apps/web` |
| `apps/web` | — | HTTP requests to `apps/api` |
| `apps/worker` | `packages/shared`, `packages/plugins/*` | Job results to Redis |
| `packages/shared` | — | Types, config, logging to all |
| `packages/plugins/training` | `packages/shared` | Training capabilities to worker |
| `packages/plugins/image` | `packages/shared` | Generation capabilities to worker |

---

## Environment Modes

| Mode | Activation | Plugins Used | GPU Required |
|------|------------|--------------|--------------|
| `fast-test` | `ISENGARD_MODE=fast-test` | Mock plugins | No |
| `production` | `ISENGARD_MODE=production` | AI-Toolkit + ComfyUI | Yes |

---

## Data Flow Summary

1. **User uploads images** → `apps/web` → `POST /api/characters/{id}/images` → stored in `data/uploads/`
2. **User starts training** → `apps/web` → `POST /api/training` → job queued in Redis
3. **Worker picks up job** → loads `training` plugin → runs AI-Toolkit → emits progress via SSE
4. **Trained LoRA saved** → `data/loras/{char-id}/`
5. **User generates images** → `POST /api/generation` → `image` plugin → ComfyUI → `data/outputs/`
