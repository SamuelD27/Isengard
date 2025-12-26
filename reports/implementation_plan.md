# Isengard Implementation Plan

**Generated:** 2024-12-26
**Version:** 1.0

---

## Executive Summary

Isengard is a GUI-first platform for training identity LoRAs and generating AI images. This document outlines the implementation milestones, from current scaffold to production-ready deployment.

---

## Milestones Overview

| Milestone | Focus | Key Deliverables |
|-----------|-------|------------------|
| **M0** | Foundation Complete | Scaffold, Docker, basic wiring |
| **M1** | End-to-End Fast-Test | Full workflow with mocks |
| **M2** | Redis Integration | Real job queue, persistence |
| **M3** | Training Integration | AI-Toolkit + real LoRA training |
| **M4** | ComfyUI Integration | Real image generation |
| **M5** | Production Hardening | Security, monitoring, deployment |
| **M6** | Video Scaffold | Interface for future video gen |

---

## M0: Foundation Complete (CURRENT)

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
# Start services
docker-compose up -d

# Check health
curl http://localhost:8000/health
curl http://localhost:8000/info

# View logs
docker-compose logs api | head -20
```

### Fast-Test vs Production
- **Fast-Test:** All services run, mock plugins return placeholder data
- **Production:** N/A for M0

---

## M1: End-to-End Fast-Test

### Scope
- Complete character CRUD with file upload
- Mock training job execution
- Mock image generation
- SSE progress streaming
- Job status persistence (in-memory)

### Acceptance Criteria
- [ ] Can create a character
- [ ] Can upload training images
- [ ] Can start mock training job
- [ ] Progress updates stream via SSE
- [ ] Mock LoRA file created in data/models/
- [ ] Can generate mock images using trained "LoRA"
- [ ] UI shows real-time progress

### Tests Required
```python
# tests/test_workflow.py
def test_full_workflow_fast_test():
    # Create character
    char = client.post("/api/characters", json={...})

    # Upload images
    client.post(f"/api/characters/{char.id}/images", files=[...])

    # Start training
    job = client.post("/api/training", json={"character_id": char.id})

    # Poll until complete
    while job.status != "completed":
        job = client.get(f"/api/training/{job.id}")
        time.sleep(1)

    # Generate image
    gen = client.post("/api/generation", json={
        "config": {"prompt": "...", "lora_id": char.id}
    })

    assert gen.status == "completed"
    assert len(gen.output_paths) > 0
```

### Validation Commands
```bash
# Run integration tests
docker-compose exec api pytest tests/

# Manual workflow test
./scripts/test_workflow.sh
```

### Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| SSE connection drops | Implement reconnection logic in frontend |
| File upload size limits | Configure multipart limits in FastAPI |

---

## M2: Redis Integration

### Scope
- Replace in-memory job storage with Redis
- Implement job queue (BLPOP pattern)
- Pub/sub for progress updates
- Character storage persistence

### Acceptance Criteria
- [ ] Jobs survive API restart
- [ ] Worker processes jobs from Redis queue
- [ ] Progress updates via Redis pub/sub
- [ ] Multiple workers can run in parallel
- [ ] Job history persisted

### Technical Decisions
- Use Redis Streams for job queue (better than lists for acknowledgment)
- Use pub/sub for progress broadcasting
- Store job state as Redis hashes

### Validation Commands
```bash
# Start with clean Redis
docker-compose down -v
docker-compose up -d

# Submit job, restart API, verify job continues
curl -X POST http://localhost:8000/api/training -d '...'
docker-compose restart api
curl http://localhost:8000/api/training/{job_id}
```

---

## M3: Training Integration

### Scope
- Integrate AI-Toolkit for real LoRA training
- Model download scripts
- Training configuration validation
- Progress parsing from AI-Toolkit logs

### Acceptance Criteria
- [ ] AI-Toolkit installed in worker container
- [ ] FLUX.1-dev model downloadable
- [ ] Training produces valid .safetensors file
- [ ] Progress updates parsed correctly
- [ ] Training can be cancelled
- [ ] Trained LoRA usable in generation

### Prerequisites
- GPU-enabled Docker host (RTX 3090/A5000+)
- FLUX.1-dev model access
- AI-Toolkit integration tested standalone

### Technical Approach
1. Create AI-Toolkit config generator from our TrainingConfig
2. Launch training as subprocess
3. Parse stdout for progress updates
4. Handle signals for cancellation
5. Validate output file format

### Tests Required
```python
def test_real_training_produces_lora():
    # Requires GPU, run in CI with GPU runner
    config = TrainingConfig(steps=100)  # Short for testing
    result = await plugin.train(config, images_dir, output_path, "ohwx")
    assert result.success
    assert output_path.exists()
    assert output_path.stat().st_size > 1000  # Not placeholder
```

### Validation Commands
```bash
# Production mode with GPU
ISENGARD_MODE=production docker-compose up worker

# Monitor training
docker-compose logs -f worker

# Verify output
ls -la data/models/
```

### Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| AI-Toolkit API changes | Pin version, add integration tests |
| OOM during training | Validate config before starting, add memory limits |
| Training hangs | Add timeout, health checks |

---

## M4: ComfyUI Integration

### Scope
- ComfyUI API integration
- Workflow management system
- LoRA loading in workflows
- Image retrieval and storage

### Acceptance Criteria
- [ ] ComfyUI server runs in Docker
- [ ] Workflow templates load correctly
- [ ] LoRA injection works
- [ ] Generated images saved to output directory
- [ ] Progress updates from ComfyUI
- [ ] Multiple concurrent generations supported

### Technical Approach
1. Store workflow JSON templates in `/workflows/`
2. Inject parameters (prompt, size, seed, LoRA) into workflow
3. POST to `/prompt` endpoint
4. Poll `/history` for completion
5. Download images from ComfyUI output

### Workflow Templates Required
- `flux-dev-lora.json` - FLUX.1-dev with LoRA support
- `sdxl-lora.json` - SDXL with LoRA support
- `flux-schnell.json` - Fast generation without LoRA

### Validation Commands
```bash
# Start ComfyUI
docker-compose up comfyui

# Test generation
curl -X POST http://localhost:8000/api/generation \
  -d '{"config": {"prompt": "a photo of ohwx woman"}}'

# Check output
ls data/outputs/
```

---

## M5: Production Hardening

### Scope
- Security review and fixes
- Rate limiting
- Authentication (optional)
- Monitoring and alerting
- RunPod deployment configuration

### Acceptance Criteria
- [ ] No secrets in logs
- [ ] Path traversal prevented
- [ ] Rate limiting on endpoints
- [ ] Health checks for orchestration
- [ ] Deployment guide for RunPod

### Security Checklist
- [ ] File upload validation (type, size)
- [ ] Path sanitization for file operations
- [ ] Redis password in production
- [ ] CORS properly configured
- [ ] No debug endpoints in production

### Monitoring
- [ ] Log aggregation configured
- [ ] Error alerting set up
- [ ] Resource usage tracked
- [ ] Job queue depth monitored

### RunPod Configuration
```yaml
# Example pod configuration
template:
  name: isengard
  image: isengard/worker:latest
  gpu_type: RTX_4090
  volume_mount: /runpod-volume
  env:
    ISENGARD_MODE: production
    DATA_DIR: /runpod-volume/data
```

---

## M6: Video Scaffold

### Scope
- Define video generation interface
- UI placeholder (already done)
- Prepare for future video model integration

### Acceptance Criteria
- [ ] VideoPlugin interface defined
- [ ] Video page shows "In Development"
- [ ] API rejects video requests gracefully
- [ ] Architecture supports video addition

### Technical Notes
- Video interface follows same pattern as image plugin
- Consider: Hunyuan Video, CogVideoX, Mochi
- Will require significant GPU resources

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| AI-Toolkit breaking changes | Medium | High | Pin versions, integration tests |
| ComfyUI node incompatibility | Medium | Medium | Use stable node names, test workflows |
| GPU memory exhaustion | High | Medium | Config validation, resource limits |
| Training quality issues | Medium | High | Provide parameter guidelines, presets |
| Long training times | High | Low | Progress updates, background processing |
| Storage filling up | Medium | High | Quota enforcement, cleanup policies |

---

## Spike Tasks

Before implementing production features, complete these investigations:

### Spike 1: AI-Toolkit Integration (Pre-M3)
- [ ] Install AI-Toolkit in isolated environment
- [ ] Train single LoRA manually
- [ ] Document exact config format
- [ ] Identify progress parsing method
- [ ] Test cancellation

### Spike 2: ComfyUI Workflow Management (Pre-M4)
- [ ] Set up ComfyUI server
- [ ] Export workflow as API JSON
- [ ] Inject LoRA into workflow
- [ ] Test parameter substitution
- [ ] Measure generation times

### Spike 3: RunPod Deployment (Pre-M5)
- [ ] Create minimal pod template
- [ ] Test volume persistence
- [ ] Measure startup times
- [ ] Test GPU allocation

---

## Definition of Done

For each milestone to be considered complete:

1. **All acceptance criteria met**
2. **Tests passing** (unit + integration)
3. **Documentation updated** (README, CLAUDE.md)
4. **No new warnings** in lint/build
5. **Works in both fast-test and production modes** (where applicable)
6. **Logs structured correctly** with correlation IDs
7. **Code reviewed** (if team > 1)

---

## Scope Boundaries

### In Scope (Current Release)
- Character management
- LoRA training (AI-Toolkit)
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

## Next Steps

1. **Complete M1** - End-to-end fast-test workflow
2. **Run Spike 1** - AI-Toolkit integration research
3. **Complete M2** - Redis integration
4. **Run Spike 2** - ComfyUI workflow research
5. **Continue M3-M5** based on learnings

---

*This plan should be reviewed and updated as implementation progresses.*
