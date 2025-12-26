# Isengard Implementation Plan

**Generated:** 2025-12-26
**Version:** 2.0
**Last Updated:** 2025-12-26

---

## Executive Summary

Isengard is a GUI-first platform for training identity LoRAs and generating AI images. This document outlines the implementation milestones, from current scaffold to production-ready deployment.

### Non-Negotiables (Encoded)

These rules are absolute and override any convenience shortcuts:

1. **GUI-first, refined UX** - Every feature usable through web interface
2. **Plugin architecture** - Training/image/video backends swappable behind stable interfaces
3. **Storage correctness** - Heavy artifacts on RunPod volume; local uses dockerignored folders
4. **Observability first** - Structured JSON logs + correlation IDs from day 1; no "add later"
5. **No "give up" fixes** - Fix root causes; no disabling features to pass tests
6. **LoRA only** - DoRA/full fine-tune explicitly out of scope
7. **Video scaffold-only** - Interface defined, clearly marked "In Development"
8. **Safe ComfyUI upgrades** - Pin with upgrade strategy, not fragile exact versions

---

## Milestones Overview

| Milestone | Focus | Key Deliverables |
|-----------|-------|------------------|
| **M0** | Foundation Complete | Scaffold, Docker, basic wiring |
| **M1** | End-to-End Fast-Test | Full workflow with mocks |
| **M2** | Redis Integration | Job queue with Streams, persistence |
| **M3** | Training Integration | AI-Toolkit + real LoRA training |
| **M3.5** | Synthetic Expansion | Dataset generation for training |
| **M4** | ComfyUI Integration | Real image generation |
| **M5** | Production Hardening | Security, monitoring, deployment |
| **M6** | Video Scaffold | Interface for future video gen |

---

## Storage Contract

> **This section is authoritative for all path decisions.**

### Environment Variable: `VOLUME_ROOT`

| Environment | Default Value | Description |
|-------------|---------------|-------------|
| Local Dev | `./data` | Gitignored, dockerignored |
| RunPod | `/runpod-volume/isengard` | Persistent network volume |
| Workspace | `/workspace/isengard` | Alternative volume mount |

**Resolution Order:**
1. Explicit `VOLUME_ROOT` env var
2. `/runpod-volume/isengard` if `/runpod-volume` exists
3. `/workspace/isengard` if `/workspace` exists
4. `./data` (local fallback)

### Directory Structure

```
$VOLUME_ROOT/
├── characters/           # Character metadata JSON files
│   └── {char_id}.json
├── uploads/              # Raw training images (user-provided)
│   └── {char_id}/
│       └── *.{jpg,png,webp}
├── datasets/             # Curated training datasets (processed)
│   └── {char_id}/
│       ├── images/
│       └── metadata.json
├── synthetic/            # Generated synthetic images for augmentation
│   └── {char_id}/
│       ├── images/
│       ├── rejected/     # Images that failed quality gates
│       └── manifest.json
├── loras/                # Trained LoRA models
│   └── {char_id}/
│       ├── {version}.safetensors
│       └── training_config.json
├── outputs/              # Generated images (final outputs)
│   └── {job_id}/
│       └── *.{png,jpg}
├── comfyui/              # ComfyUI workspace (production only)
│   ├── models/
│   ├── custom_nodes/
│   └── workflows/
└── cache/                # Ephemeral cache (can be cleared)
    └── embeddings/
```

### Rules

1. **No writes outside `VOLUME_ROOT`** except:
   - `./logs/` (observability, separate mount)
   - `./tmp/` (ephemeral, gitignored, cleared on restart)

2. **All paths derived from config module:**
   ```python
   config = get_global_config()
   uploads = config.volume_root / "uploads" / character_id
   ```

3. **Docker mounts must be consistent:**
   ```yaml
   # All containers share the same volume root
   volumes:
     - ${VOLUME_ROOT:-./data}:/data
     - ./logs:/logs
   ```

---

## Queue Architecture (Redis Streams)

> **Decision: Use Redis Streams with Consumer Groups**

Redis Streams provide better semantics than Lists (BLPOP) for job queues:
- Message acknowledgment (XACK)
- Consumer groups for parallel workers
- Pending entry list for retry handling
- Message IDs for ordering

### Stream Names

| Stream | Purpose |
|--------|---------|
| `isengard:jobs:training` | Training job submissions |
| `isengard:jobs:generation` | Image generation submissions |
| `isengard:progress:{job_id}` | Progress updates (ephemeral) |

### Job Message Schema

```json
{
  "id": "train-abc123",
  "type": "training",
  "correlation_id": "req-xyz789",
  "created_at": "2025-12-26T10:30:00Z",
  "payload": {
    "character_id": "char-001",
    "config": {
      "method": "lora",
      "steps": 1500,
      "learning_rate": 0.0001,
      "lora_rank": 16
    }
  }
}
```

### Progress Event Schema

```json
{
  "job_id": "train-abc123",
  "correlation_id": "req-xyz789",
  "timestamp": "2025-12-26T10:35:00Z",
  "status": "running",
  "progress": 45.5,
  "current_step": 682,
  "total_steps": 1500,
  "message": "Training step 682/1500",
  "preview_url": null
}
```

### Idempotency Strategy

- Job ID is server-generated (UUID7 for time-ordering)
- API generates job ID on POST, returns it to client immediately
- Before XADD, check if idempotency key exists in `isengard:jobs:idempotency` hash (if provided)
- Worker uses XREADGROUP with consumer name for exactly-once processing
- **Future enhancement:** Accept `Idempotency-Key` header for client-driven deduplication

### Retry Policy

| Attempt | Delay | Action |
|---------|-------|--------|
| 1 | 0s | Immediate |
| 2 | 30s | After first failure |
| 3 | 2m | After second failure |
| 4+ | N/A | Move to dead-letter, alert |

---

## Observability Requirements

> **Phase 1 Mandatory - No "add later"**

### Structured Logging

All services emit JSON logs with these fields:

```json
{
  "timestamp": "2025-12-26T10:30:00.000Z",
  "level": "INFO",
  "service": "api|worker|web",
  "correlation_id": "req-abc123",
  "logger": "api.routes.training",
  "message": "Training job started",
  "context": {
    "job_id": "train-xyz",
    "character_id": "char-001"
  }
}
```

### Correlation ID Propagation

```
Frontend                  Backend API              Worker                ComfyUI
   │                          │                       │                     │
   │ X-Correlation-ID: abc123 │                       │                     │
   ├─────────────────────────►│                       │                     │
   │                          │ job.correlation_id    │                     │
   │                          ├──────────────────────►│                     │
   │                          │                       │ prompt.metadata.cid │
   │                          │                       ├────────────────────►│
   │   SSE: {correlation_id}  │                       │                     │
   │◄─────────────────────────┤◄──────────────────────┤                     │
```

### Log File Layout

```
./logs/
├── api/
│   ├── 2025-12-26.log
│   └── 2025-12-26.log.gz  # Rotated after 7 days
├── worker/
│   └── 2025-12-26.log
└── web/
    └── 2025-12-26.log
```

### Retention Policy

- Keep 30 days of logs
- Compress after 7 days
- Delete after 30 days
- In production: ship to external aggregator (phase 2)

### Redaction Rules

| Pattern | Replacement | Example |
|---------|-------------|---------|
| `hf_[A-Za-z0-9]+` | `hf_***REDACTED***` | HuggingFace tokens |
| `sk-[A-Za-z0-9]+` | `sk-***REDACTED***` | API keys |
| `ghp_[A-Za-z0-9]+` | `ghp_***REDACTED***` | GitHub tokens |
| `rpa_[A-Za-z0-9]+` | `rpa_***REDACTED***` | RunPod keys |
| `/Users/*/`, `/home/*/` | `/[HOME]/` | Local paths |
| `token=...`, `password=...` | `***` | URL params |

### Acceptance Criteria (Enforced M1+)

- [ ] All log lines are valid JSON
- [ ] correlation_id present on every request-scoped log
- [ ] SSE events include job_id and correlation_id
- [ ] No secrets in logs (test with grep patterns)
- [ ] Logs persist to ./logs/{service}/ directory
- [ ] Log rotation configured

---

## M0: Foundation Complete (COMPLETE)

### Scope
- Repository structure and architecture
- Docker Compose local development
- Basic API endpoints (stubbed)
- Frontend UI skeleton
- Observability plumbing

### Acceptance Criteria
- [x] `docker-compose up` starts all services
- [x] Frontend loads at http://localhost:3000
- [x] API responds at http://localhost:8000/health
- [x] Structured JSON logging works
- [x] Correlation IDs propagate through stack
- [x] All 4 UI pages render (Characters, Training, Image Gen, Video)

### Validation Commands
```bash
docker-compose up -d
curl http://localhost:8000/health
curl http://localhost:8000/info
docker-compose logs api | head -20
```

---

## M1: End-to-End Fast-Test (COMPLETE)

### Scope
- Complete character CRUD with file upload
- Mock training job execution (in-process, not queued)
- Mock image generation
- SSE progress streaming
- Job status persistence (in-memory)

### Acceptance Criteria
- [x] Can create a character via UI
- [x] Can upload training images via UI
- [x] Can start mock training job
- [x] Progress updates stream via SSE to frontend
- [x] Mock LoRA file created in `$VOLUME_ROOT/loras/{char_id}/`
- [x] Can generate mock images using trained "LoRA"
- [x] UI shows real-time progress bars
- [x] All log lines include correlation_id

### Validation Report
See `reports/m1_log_validation.md` for full validation report.

### Tests Required
```python
# tests/test_workflow.py
async def test_full_workflow_fast_test():
    # Create character
    char = await client.post("/api/characters", json={
        "name": "TestChar",
        "trigger_word": "ohwx person"
    })
    assert char.status_code == 201

    # Upload images
    files = [("files", ("test.jpg", b"...", "image/jpeg"))]
    upload = await client.post(f"/api/characters/{char.json()['id']}/images", files=files)
    assert upload.status_code == 201

    # Start training
    job = await client.post("/api/training", json={
        "character_id": char.json()["id"],
        "config": {"steps": 10}  # Fast for testing
    })
    assert job.status_code == 201

    # Wait for completion via polling
    job_id = job.json()["id"]
    for _ in range(30):
        status = await client.get(f"/api/training/{job_id}")
        if status.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    assert status.json()["status"] == "completed"
    assert status.json()["output_path"] is not None
```

### Validation Commands
```bash
docker-compose exec api pytest tests/
./scripts/test_workflow.sh
```

---

## M2: Redis Integration (COMPLETE)

### Scope
- Replace in-memory storage with Redis
- Implement job queue with Redis Streams
- Consumer groups for worker scaling
- Progress events via Redis Streams (replayable)
- Character/job persistence

### Acceptance Criteria
- [x] Jobs survive API restart (Redis persistence)
- [x] Worker consumes from Redis Streams (XREADGROUP)
- [x] Progress updates via Redis Streams (`isengard:progress:{job_id}`)
- [x] SSE endpoint reads progress from Redis stream
- [x] Multiple workers can run in parallel (consumer group with unique names)
- [x] Job history queryable from Redis (list_jobs)
- [x] Feature flag `USE_REDIS` for M1 compatibility (default: false)

### Implementation Notes
- `packages/shared/src/redis_client.py` - Core Redis operations
- `apps/worker/src/job_processor.py` - Consumer group implementation
- Routes updated with dual-mode support (in-memory for M1, Redis for M2)
- 6 Redis integration tests passing (`tests/test_redis_integration.py`)
- M1 tests still pass (13 tests, backward compatible)

### Technical Implementation

```python
# API: Submit job
async def submit_training_job(request):
    job_id = generate_uuid7()

    # Idempotency check
    if await redis.hexists("isengard:jobs:index", job_id):
        return await get_job_status(job_id)

    # Add to stream
    await redis.xadd("isengard:jobs:training", {
        "id": job_id,
        "payload": json.dumps(request.dict()),
        "correlation_id": get_correlation_id(),
    })

    # Index for lookup
    await redis.hset("isengard:jobs:index", job_id, "pending")

    return {"id": job_id, "status": "queued"}

# Worker: Consume jobs
async def consume_jobs():
    while True:
        messages = await redis.xreadgroup(
            groupname="workers",
            consumername=f"worker-{os.getpid()}",
            streams={"isengard:jobs:training": ">"},
            count=1,
            block=5000,
        )
        for stream, entries in messages:
            for entry_id, data in entries:
                await process_job(data)
                await redis.xack("isengard:jobs:training", "workers", entry_id)
```

### Validation Commands
```bash
docker-compose down -v
docker-compose up -d

# Submit job
curl -X POST http://localhost:8000/api/training -H "Content-Type: application/json" \
  -d '{"character_id": "char-001", "config": {"steps": 100}}'

# Restart API, verify job state persists
docker-compose restart api
curl http://localhost:8000/api/training/{job_id}
```

---

## M3: Training Integration (IMPLEMENTED)

### Scope
- Integrate AI-Toolkit for real LoRA training
- Model download scripts
- Training configuration validation
- Progress parsing from AI-Toolkit logs

### Acceptance Criteria
- [x] AI-Toolkit installed in worker container (Dockerfile.gpu)
- [x] FLUX.1-dev model downloadable via script (scripts/download_models.py)
- [x] Training produces valid .safetensors file (AI-Toolkit output)
- [x] Progress updates parsed from stdout (regex patterns for step/loss)
- [x] Training can be cancelled (SIGTERM handling)
- [ ] Trained LoRA loadable in generation (M4: ComfyUI Integration)

### Prerequisites
- GPU-enabled Docker host (RTX 3090/A5000+ with 24GB VRAM)
- FLUX.1-dev model access (HuggingFace)
- AI-Toolkit tested standalone

### Implementation Notes
- `packages/plugins/training/src/ai_toolkit.py` - Full AI-Toolkit integration
- `scripts/download_models.py` - Model download utility
- `apps/worker/Dockerfile.gpu` - GPU-enabled worker container
- `docker-compose.gpu.yaml` - Production compose with GPU support

### Technical Approach
1. Create AI-Toolkit config YAML generator from TrainingConfig ✓
2. Launch training via subprocess ✓
3. Parse stdout regex for progress (step, loss) ✓
4. Handle SIGTERM for cancellation ✓
5. Validate output .safetensors format ✓

### Validation Commands
```bash
# Download models first
HF_TOKEN=xxx python scripts/download_models.py --check-gpu

# Start GPU worker
docker-compose -f docker-compose.gpu.yaml up worker

# Monitor logs
docker-compose -f docker-compose.gpu.yaml logs -f worker

# Check outputs
ls -la data/loras/
```

---

## M3.5: Synthetic Expansion Pipeline

> **NEW MILESTONE - Required for quality training**

### Scope
Generate synthetic training images from 1-few reference photos to expand dataset before training.

### Inputs
- 1-10 reference images of subject
- Trigger word
- Optional: proto-LoRA (from quick initial training)

### Pipeline Steps

1. **Prompt Template Generation**
   - Base prompts: `{trigger_word} in {setting}, {lighting}, {pose}`
   - Settings: studio, outdoor, office, cafe, etc.
   - Lighting: natural, studio, golden hour, etc.
   - Poses: headshot, portrait, full body, etc.

2. **Controlled Generation**
   - Use ControlNet/IP-Adapter for pose/composition control
   - Vary focal length, angle, expression
   - Deterministic seed ranges for reproducibility

3. **Quality Filtering**
   - Face detection (must detect exactly 1 face)
   - Face embedding similarity to reference (threshold: 0.7)
   - Sharpness/blur detection
   - Aesthetic score (optional)

4. **Output Curation**
   - Passed images → `$VOLUME_ROOT/synthetic/{char_id}/images/`
   - Failed images → `$VOLUME_ROOT/synthetic/{char_id}/rejected/`
   - Manifest with generation params and filter scores

### Acceptance Criteria
- [ ] API endpoint: `POST /api/characters/{id}/synthetic`
- [ ] UI toggle: "Generate synthetic dataset" with count slider
- [ ] Preview grid of synthetic images before training
- [ ] Filter stats: generated/passed/rejected counts
- [ ] Deterministic dry-run mode (fixed seeds, no randomness)
- [ ] Unit tests for face similarity filter
- [ ] Integration test: 5 input → 50+ output images

### Configuration

```python
class SyntheticConfig(BaseModel):
    target_count: int = 50          # Images to generate
    similarity_threshold: float = 0.7
    min_sharpness: float = 0.3
    prompt_templates: list[str] = [...]
    use_controlnet: bool = True
    seed_start: int = 42            # For reproducibility
```

### Validation Commands
```bash
# Dry-run mode (deterministic)
curl -X POST http://localhost:8000/api/characters/char-001/synthetic \
  -d '{"target_count": 10, "dry_run": true}'

# Verify outputs
ls data/synthetic/char-001/images/
cat data/synthetic/char-001/manifest.json
```

---

## M4: ComfyUI Integration

### Scope
- ComfyUI API integration
- Workflow management system
- LoRA loading in workflows
- Image retrieval and storage

### Acceptance Criteria
- [ ] ComfyUI server runs in Docker
- [ ] Workflow templates validate (JSON schema)
- [ ] LoRA injection works
- [ ] Generated images saved to `$VOLUME_ROOT/outputs/`
- [ ] Progress updates from ComfyUI WebSocket
- [ ] Multiple concurrent generations supported

### ComfyUI Versioning Policy

> **Source of Truth:** ComfyUI and custom node pins live in `sota/registry.yml`; this section describes policy, not the canonical pin.

**Known-Good Version:** `v0.2.7` (or latest stable at implementation time)

| Component | Pin Strategy | Upgrade Procedure |
|-----------|--------------|-------------------|
| ComfyUI core | Git tag in Dockerfile | Test workflows → update tag → test again |
| Custom nodes | requirements.txt in repo | Individual node updates with testing |
| Workflow JSON | Schema version field | Migration script if schema changes |

**Compatibility Matrix:**

| ComfyUI Version | FLUX Support | SDXL Support | Known Issues |
|-----------------|--------------|--------------|--------------|
| v0.2.7 | Yes | Yes | None |
| v0.2.6 | Yes | Yes | Minor LoRA loading bug |
| < v0.2.5 | Partial | Yes | Missing FLUX nodes |

**Upgrade Checklist:**
1. [ ] Run workflow validation tests against new version
2. [ ] Test LoRA loading with sample model
3. [ ] Verify WebSocket progress events
4. [ ] Update Dockerfile tag
5. [ ] Update compatibility matrix in docs

### Workflow Templates Required
- `flux-dev-lora.json` - FLUX.1-dev with LoRA support
- `sdxl-lora.json` - SDXL with LoRA support
- `flux-schnell.json` - Fast generation without LoRA

### Workflow Validation Test
```python
def test_workflow_json_valid():
    """Validate workflow structure without GPU execution."""
    workflow = load_workflow("flux-dev-lora.json")

    # Required nodes exist
    assert "KSampler" in [n["class_type"] for n in workflow["nodes"]]
    assert "LoraLoader" in [n["class_type"] for n in workflow["nodes"]]

    # Injection points defined
    assert "PROMPT_INJECT" in str(workflow)
    assert "LORA_INJECT" in str(workflow)
```

---

## M5: Production Hardening

### Scope
- Security review and fixes
- Rate limiting
- Monitoring and alerting
- RunPod deployment configuration

### Acceptance Criteria
- [ ] No secrets in logs (verified by grep test)
- [ ] Path traversal prevented (tested)
- [ ] Rate limiting on upload endpoints
- [ ] Health checks pass in orchestration
- [ ] Deployment guide for RunPod complete
- [ ] Backup/restore procedure documented

### Security Checklist
- [ ] File upload validation (type, size, dimensions)
- [ ] Path sanitization for all file operations
- [ ] Redis password in production
- [ ] CORS restricted to known origins
- [ ] No debug endpoints in production mode
- [ ] Input validation on all API endpoints

### RunPod Configuration

```yaml
# runpod-template.yaml
name: isengard
image: ghcr.io/samueld27/isengard-worker:latest
gpu_type: RTX_4090
volume_mount: /runpod-volume
volume_size: 100GB  # Models + outputs
env:
  ISENGARD_MODE: production
  VOLUME_ROOT: /runpod-volume/isengard
  REDIS_URL: redis://redis:6379
  LOG_LEVEL: INFO
```

---

## M6: Video Scaffold

### Scope
- Video generation interface (no implementation)
- UI shows "In Development" clearly
- API rejects requests gracefully

### Acceptance Criteria
- [ ] VideoPlugin interface defined (already done)
- [ ] Video page shows "In Development" banner
- [ ] `POST /api/video/*` returns 501 Not Implemented
- [ ] Architecture supports future video addition
- [ ] Capabilities matrix shows video=scaffold_only

### Technical Notes
- Video interface follows same pattern as image plugin
- Consider for future: Hunyuan Video, CogVideoX, Mochi
- Will require significant GPU resources (48GB+ VRAM)

---

## SOTA Registry

> **Single source of truth for model selection/pinning**

### Location
`sota/registry.yml`

### Schema

```yaml
version: "1.0"
models:
  - id: flux-dev
    name: FLUX.1-dev
    source: black-forest-labs/FLUX.1-dev
    license: FLUX.1-dev Non-Commercial License
    version: "1.0"
    sha256: abc123...
    purpose: Base model for LoRA training
    fast_test_alternative: null  # No alternative, skip in fast-test
    compatibility:
      min_vram_gb: 24
      supported_training: [lora]
      notes: "Requires HuggingFace access token"

  - id: flux-schnell
    name: FLUX.1-schnell
    source: black-forest-labs/FLUX.1-schnell
    license: Apache 2.0
    version: "1.0"
    sha256: def456...
    purpose: Fast inference (4 steps)
    fast_test_alternative: null
    compatibility:
      min_vram_gb: 16
      supported_training: []
      notes: "Distilled, not for training"

  - id: insightface-buffalo
    name: InsightFace Buffalo_L
    source: deepinsight/insightface
    license: MIT
    version: "buffalo_l"
    sha256: ...
    purpose: Face embedding for synthetic filtering
    fast_test_alternative: null
    compatibility:
      min_vram_gb: 2
      notes: "CPU fallback available"
```

### Validation Script

```bash
# scripts/validate_registry.py
python scripts/validate_registry.py sota/registry.yml

# Checks:
# - YAML syntax valid
# - All required fields present
# - SHA256 format valid
# - No duplicate IDs
# - License field not empty
```

### Milestone: Add to M2
- [ ] Create `sota/registry.yml` with initial models
- [ ] Add `scripts/validate_registry.py`
- [ ] CI check for registry validation
- [ ] Download script reads from registry

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| AI-Toolkit breaking changes | Medium | High | Pin version in registry, integration tests |
| ComfyUI node incompatibility | Medium | Medium | Version matrix, workflow validation tests |
| GPU memory exhaustion | High | Medium | Config validation, VRAM checks before start |
| Training quality issues | Medium | High | Synthetic expansion, parameter presets |
| Long training times | High | Low | Progress updates, background processing |
| Storage filling up | Medium | High | Quota enforcement, cleanup policies |
| Face similarity failures | Medium | Medium | Adjustable threshold, manual override |

---

## Spike Tasks

### Spike 1: AI-Toolkit Integration (Pre-M3)
- [ ] Install AI-Toolkit in isolated environment
- [ ] Train single LoRA manually with 10 images
- [ ] Document exact config YAML format
- [ ] Identify progress regex pattern in stdout
- [ ] Test SIGTERM cancellation behavior
- [ ] Measure VRAM usage at different ranks

### Spike 2: ComfyUI Workflow Management (Pre-M4)
- [ ] Set up ComfyUI server locally
- [ ] Export workflow as API JSON
- [ ] Identify injection points for prompt/LoRA
- [ ] Test parameter substitution
- [ ] Measure generation times (FLUX vs SDXL)

### Spike 3: Face Embedding Pipeline (Pre-M3.5)
- [ ] Set up InsightFace
- [ ] Test similarity scoring on known pairs
- [ ] Determine optimal threshold (0.6-0.8 range)
- [ ] Benchmark CPU vs GPU performance

### Spike 4: RunPod Deployment (Pre-M5)
- [ ] Create minimal pod template
- [ ] Test volume persistence across restarts
- [ ] Measure cold start times
- [ ] Test GPU allocation and VRAM access

---

## Definition of Done

For each milestone to be considered complete:

1. **All acceptance criteria met**
2. **Tests passing** (unit + integration)
3. **Documentation updated** (README, CLAUDE.md if needed)
4. **No new warnings** in lint/build
5. **Works in both fast-test and production modes** (where applicable)
6. **Logs structured correctly** with correlation IDs
7. **Observability acceptance criteria pass**
8. **Code committed to main branch**

---

## Scope Boundaries

### In Scope (Current Release)
- Character management
- LoRA training (AI-Toolkit)
- Synthetic dataset expansion
- Image generation (ComfyUI)
- Web UI for all above
- Fast-test mode for development
- RunPod deployment support

### Scaffold Only (Future)
- Video generation (interface defined, no implementation)

### Out of Scope
- DoRA training
- Full model fine-tuning
- Multi-user / authentication
- Public API access
- Mobile apps

---

## Appendix: Migration Notes

### BLPOP → Streams Migration

The original code had BLPOP comments but this plan specifies Streams. When implementing M2:

1. Remove BLPOP TODO comments from `job_processor.py`
2. Implement XREADGROUP consumer pattern
3. Add consumer group creation on startup
4. Update tests to verify Stream semantics

---

*This plan should be reviewed and updated as implementation progresses.*
