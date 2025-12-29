# Phase 1 Design: Make Controls Real

**Date:** 2025-12-27
**Status:** Approved
**Author:** Claude Code (Opus 4.5)

---

## Overview

Phase 1 closes the gap between UI controls and backend capabilities. After this phase:
- Backend advertises exactly which parameters it supports (plugin-reported schema)
- Frontend renders controls dynamically from schema
- Unsupported parameters shown in collapsible "Unavailable" section
- End-to-end correlation ID tracing from frontend to worker logs
- Per-job log files with download endpoint
- Upscale toggle working end-to-end

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Capability schema source | Plugin-reported (Option B) | Plugins are self-documenting, schema accurate per-backend |
| Job log bundling | Direct JobLogger (Option B) | Real-time, no collector process, simpler architecture |
| First toggle to implement | Upscale (Option C) | Simplest, immediate quality improvement visible |
| Unsupported params UI | Collapsible section (Option C) | Clean default, full visibility on demand |
| Fast-test mode | Hybrid (Option C) | Full schema mocks, real job log files, actual 2x resize |

---

## 1. Capability Schema System

### Plugin Interface Extension

Each plugin implements `get_capabilities()` returning structured schema:

```python
# packages/plugins/training/src/interface.py
from abc import ABC, abstractmethod
from typing import TypedDict, Literal

class ParameterSchema(TypedDict, total=False):
    type: Literal["int", "float", "enum", "bool", "string"]
    min: float | int
    max: float | int
    step: float  # UI hint
    options: list[str | int | float]
    default: any
    wired: bool
    reason: str | None  # Why unavailable
    description: str | None

class TrainingCapabilities(TypedDict):
    method: str
    backend: str
    parameters: dict[str, ParameterSchema]

class TrainingPlugin(ABC):
    @abstractmethod
    def get_capabilities(self) -> TrainingCapabilities:
        """Return supported parameters with ranges and defaults."""
        pass
```

### AI-Toolkit Implementation

```python
# packages/plugins/training/src/ai_toolkit.py
def get_capabilities(self) -> TrainingCapabilities:
    return {
        "method": "lora",
        "backend": "ai-toolkit",
        "parameters": {
            "steps": {"type": "int", "min": 100, "max": 10000, "default": 1000, "wired": True},
            "learning_rate": {"type": "float", "min": 1e-6, "max": 0.01, "step": 1e-6, "default": 0.0001, "wired": True},
            "lora_rank": {"type": "enum", "options": [4, 8, 16, 32, 64, 128], "default": 16, "wired": True},
            "resolution": {"type": "enum", "options": [512, 768, 1024], "default": 1024, "wired": True},
            "batch_size": {"type": "enum", "options": [1, 2, 4], "default": 1, "wired": True},
            "optimizer": {"type": "enum", "options": ["adamw8bit", "adamw", "prodigy"], "default": "adamw8bit", "wired": True},
            "scheduler": {"type": "enum", "options": ["constant", "cosine", "cosine_with_restarts", "linear"], "default": "cosine", "wired": True},
            "precision": {"type": "enum", "options": ["bf16", "fp16", "fp32"], "default": "bf16", "wired": True},
            # Unwired parameters (shown as unavailable)
            "gradient_accumulation": {"type": "int", "min": 1, "max": 8, "default": 1, "wired": False, "reason": "Not yet implemented in AI-Toolkit adapter"},
            "network_alpha": {"type": "int", "min": 1, "max": 128, "default": 16, "wired": False, "reason": "Planned for Phase 2"},
        }
    }
```

### Image Plugin Capabilities

```python
# packages/plugins/image/src/comfyui.py
def get_capabilities(self) -> ImageCapabilities:
    return {
        "backend": "comfyui",
        "model_variants": ["flux-dev", "flux-schnell"],
        "toggles": {
            "use_upscale": {"supported": True, "description": "2x upscale with RealESRGAN"},
            "use_facedetailer": {"supported": False, "reason": "Workflow not implemented"},
            "use_ipadapter": {"supported": False, "reason": "Workflow not implemented"},
            "use_controlnet": {"supported": False, "reason": "Workflow not implemented"},
        },
        "parameters": {
            "width": {"type": "int", "min": 512, "max": 2048, "default": 1024, "wired": True},
            "height": {"type": "int", "min": 512, "max": 2048, "default": 1024, "wired": True},
            "steps": {"type": "int", "min": 1, "max": 100, "default": 20, "wired": True},
            "guidance_scale": {"type": "float", "min": 1.0, "max": 20.0, "step": 0.5, "default": 3.5, "wired": True},
            "lora_strength": {"type": "float", "min": 0.0, "max": 2.0, "step": 0.1, "default": 1.0, "wired": True},
        }
    }
```

### API `/info` Enhancement

```python
# apps/api/src/routes/health.py
@router.get("/info")
async def api_info():
    config = get_global_config()
    training_plugin = get_training_plugin()
    image_plugin = get_image_plugin()

    return {
        "name": "Isengard API",
        "version": "0.1.0",
        "mode": config.mode,
        "training": training_plugin.get_capabilities(),
        "image_generation": image_plugin.get_capabilities(),
    }
```

---

## 2. API Validation Against Capabilities

### Config Validator

```python
# apps/api/src/services/config_validator.py
from fastapi import HTTPException

def validate_training_config(config: dict, capabilities: TrainingCapabilities) -> None:
    """Reject unsupported parameters with 400 + backend name + reason."""
    params = capabilities["parameters"]
    backend = capabilities["backend"]

    for key, value in config.items():
        if key not in params:
            continue  # Unknown params ignored (forward compatibility)

        param_schema = params[key]

        # Reject if not wired
        if not param_schema.get("wired", False):
            reason = param_schema.get("reason", "Not supported")
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{key}' not supported by {backend}: {reason}"
            )

        # Validate range
        if "min" in param_schema and value < param_schema["min"]:
            raise HTTPException(400, f"Parameter '{key}' below minimum ({param_schema['min']})")
        if "max" in param_schema and value > param_schema["max"]:
            raise HTTPException(400, f"Parameter '{key}' above maximum ({param_schema['max']})")

        # Validate enum
        if param_schema.get("type") == "enum" and value not in param_schema.get("options", []):
            raise HTTPException(400, f"Parameter '{key}' must be one of {param_schema['options']}")
```

### Integration in Routes

```python
# apps/api/src/routes/training.py
@router.post("/api/training")
async def start_training(request: TrainingRequest):
    plugin = get_training_plugin()
    capabilities = plugin.get_capabilities()
    validate_training_config(request.config.dict(), capabilities)
    # ... proceed with job creation
```

---

## 3. Correlation ID & Job Logger

### Frontend Correlation ID

```typescript
// apps/web/src/lib/api.ts
function generateCorrelationId(): string {
  return `web-${crypto.randomUUID()}`
}

// All API calls include header
const response = await fetch(url, {
  headers: {
    'Content-Type': 'application/json',
    'X-Correlation-ID': generateCorrelationId(),
  },
  ...
})
```

### FastAPI Middleware

```python
# apps/api/src/middleware.py
from contextvars import ContextVar, Token
import uuid

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_correlation_token: ContextVar[Token | None] = ContextVar("correlation_token", default=None)

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    # Extract or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID") or f"api-{uuid.uuid4().hex[:12]}"

    # Set in context with proper reset
    token = _correlation_id.set(correlation_id)
    _correlation_token.set(token)

    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        # Reset to prevent leakage
        _correlation_id.reset(token)
```

### Redis Job Metadata

```python
# packages/shared/src/redis_client.py
def enqueue_job(job_type: str, config: dict, **metadata) -> str:
    job_id = f"{job_type}-{uuid.uuid4().hex[:12]}"
    job_data = {
        "id": job_id,
        "type": job_type,
        "correlation_id": get_correlation_id(),  # From context
        "config": config,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        **metadata,
    }
    # ... store in Redis
```

### JobLogger Class

```python
# packages/shared/src/logging.py
import json
import portalocker
from pathlib import Path
from datetime import datetime, timezone

class JobLogger:
    """Logger that writes to both service log and job-specific JSONL file."""

    def __init__(self, job_id: str, service: str = "worker"):
        self.job_id = job_id
        self.service = service
        self._service_logger = get_logger(f"{service}.job.{job_id}")

        # Job log path from config (single source of truth)
        config = get_global_config()
        self.job_log_path = config.volume_root / "logs" / "jobs" / f"{job_id}.jsonl"
        self.job_log_path.parent.mkdir(parents=True, exist_ok=True)

    def _build_record(self, level: str, msg: str, event: str | None, fields: dict) -> dict:
        return {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": level,
            "service": self.service,
            "job_id": self.job_id,
            "correlation_id": get_correlation_id(),
            "event": event,
            "msg": msg,
            "fields": fields if fields else None,
        }

    def _append_to_job_log(self, record: dict) -> None:
        """Append record to job log file with file lock."""
        line = json.dumps({k: v for k, v in record.items() if v is not None}, default=str)
        with portalocker.Lock(self.job_log_path, "a", timeout=5) as f:
            f.write(line + "\n")

    def info(self, msg: str, *, event: str | None = None, **fields):
        record = self._build_record("INFO", msg, event, fields)
        self._service_logger.info(msg, extra={"event": event, **fields})
        self._append_to_job_log(record)

    def error(self, msg: str, *, event: str | None = None, **fields):
        record = self._build_record("ERROR", msg, event, fields)
        self._service_logger.error(msg, extra={"event": event, **fields})
        self._append_to_job_log(record)

    def warning(self, msg: str, *, event: str | None = None, **fields):
        record = self._build_record("WARNING", msg, event, fields)
        self._service_logger.warning(msg, extra={"event": event, **fields})
        self._append_to_job_log(record)
```

### Worker Context Restoration

```python
# apps/worker/src/job_processor.py
async def process_job(job_data: dict):
    job_id = job_data["id"]
    correlation_id = job_data.get("correlation_id")

    # Restore correlation context
    token = set_correlation_id(correlation_id)

    try:
        # Create job logger
        job_logger = JobLogger(job_id)
        job_logger.info("Job started", event="job.start", job_type=job_data["type"])

        # Pass logger to plugin (optional parameter)
        if job_data["type"] == "training":
            await training_plugin.train(config, logger=job_logger)
        elif job_data["type"] == "generation":
            await image_plugin.generate(config, logger=job_logger)

        job_logger.info("Job completed", event="job.complete")
    finally:
        reset_correlation_id(token)
```

### VOLUME_ROOT Configuration

```python
# packages/shared/src/config.py
@dataclass
class GlobalConfig:
    volume_root: Path = field(default_factory=lambda: Path(
        os.environ.get("VOLUME_ROOT", "/runpod-volume/isengard")
    ))
    # ... other fields

# Single source of truth - all components use config.volume_root
```

---

## 4. Log Download Endpoint

```python
# apps/api/src/routes/logs.py
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from packages.shared.src.config import get_global_config

router = APIRouter()

@router.get("/api/jobs/{job_id}/logs")
async def download_job_logs(job_id: str):
    """Download the JSONL log file for a specific job."""
    # Validate job_id format to prevent path traversal
    if not re.match(r'^[a-zA-Z0-9_-]+$', job_id):
        raise HTTPException(400, "Invalid job ID format")

    config = get_global_config()
    log_path = config.volume_root / "logs" / "jobs" / f"{job_id}.jsonl"

    if not log_path.exists():
        raise HTTPException(404, "Log file not found")

    return FileResponse(
        log_path,
        media_type="application/x-ndjson",
        filename=f"{job_id}.jsonl"
    )
```

### Frontend Download Button

```typescript
// apps/web/src/pages/Training.tsx (in TrainingJobCard)
<Button variant="ghost" size="sm" asChild>
  <a
    href={`${API_BASE}/api/jobs/${job.id}/logs`}
    download={`${job.id}.jsonl`}
  >
    <Download className="h-4 w-4 mr-1" />
    Logs
  </a>
</Button>
```

---

## 5. Upscale Workflow

### Workflow Selection Logic

```python
# packages/plugins/image/src/comfyui.py
def _select_workflow(self, config: GenerationConfig, lora_path: Path | None) -> str:
    # Step 1: Base model (user-configurable)
    base = config.model_variant or "flux-dev"  # "flux-dev" or "flux-schnell"

    # Step 2: Add LoRA suffix if provided
    if lora_path:
        base = f"{base}-lora"

    # Step 3: Add upscale suffix if enabled AND no LoRA
    # (LoRA+upscale deferred - upscale ignored when LoRA present)
    if config.use_upscale and not lora_path:
        base = f"{base}-upscale"

    return base
```

### Workflow Files (Phase 1)

- `flux-dev-upscale.json` — FLUX dev + 2x RealESRGAN upscale
- `flux-schnell-upscale.json` — FLUX schnell + 2x RealESRGAN upscale

LoRA + upscale combinations deferred to avoid variant explosion.

### Upscale Workflow Structure

```
[FLUX Pipeline] → VAEDecode → [Image] → UpscaleModelLoader → ImageUpscaleWithModel → SaveImage
                                              ↓
                              models/upscale_models/RealESRGAN_x2plus.pth
```

### Model Download (start.sh)

```bash
# Download upscale model to ComfyUI's expected location
UPSCALE_MODEL_PATH="/comfyui/models/upscale_models/RealESRGAN_x2plus.pth"
if [ ! -f "$UPSCALE_MODEL_PATH" ]; then
    echo "Downloading RealESRGAN_x2plus.pth..."
    wget -q -O "$UPSCALE_MODEL_PATH" \
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"
fi
```

### Fast-Test Mock (Actual 2x Resize)

```python
# packages/plugins/image/src/mock_plugin.py
from PIL import Image

async def generate(self, config, output_dir, lora_path=None, count=1, progress_callback=None, logger=None):
    output_paths = []

    for i in range(count):
        # Create base placeholder
        img = Image.new("RGB", (config.width, config.height), color=(64, 64, 80))

        # Actually resize if upscale enabled
        if config.use_upscale:
            img = img.resize(
                (config.width * 2, config.height * 2),
                Image.Resampling.LANCZOS
            )

        output_path = output_dir / f"mock_{uuid.uuid4().hex[:8]}.png"
        img.save(output_path)
        output_paths.append(output_path)

    return GenerationResult(success=True, output_paths=output_paths)
```

---

## 6. Frontend Dynamic Rendering

### Fetch Capabilities

```typescript
// apps/web/src/lib/api.ts
export const api = {
  getInfo: async (): Promise<ApiInfo> => {
    const response = await fetch(`${API_BASE}/api/info`)
    return response.json()
  },
  // ... other methods
}

interface ParameterSchema {
  type: 'int' | 'float' | 'enum' | 'bool' | 'string'
  min?: number
  max?: number
  step?: number
  options?: (string | number)[]
  default: any
  wired: boolean
  reason?: string
  description?: string
}

interface TrainingCapabilities {
  backend: string
  method: string
  parameters: Record<string, ParameterSchema>
}
```

### Initialize Form State from Schema

```typescript
// apps/web/src/pages/Training.tsx
const { data: capabilities } = useQuery({
  queryKey: ['capabilities'],
  queryFn: api.getInfo,
  staleTime: 5 * 60 * 1000,
})

// Initialize config from schema defaults ONCE
useEffect(() => {
  if (capabilities?.training?.parameters) {
    const defaults: Record<string, any> = {}
    for (const [key, param] of Object.entries(capabilities.training.parameters)) {
      defaults[key] = param.default
    }
    setConfig(prev => ({ ...defaults, ...prev }))
  }
}, [capabilities])
```

### Preset Application with Note

```typescript
const handlePresetChange = (preset: PresetKey) => {
  const presetConfig = PRESETS[preset].config
  const skipped: string[] = []
  const applied: Record<string, any> = {}

  for (const [key, value] of Object.entries(presetConfig)) {
    const param = trainingParams[key]
    if (param?.wired) {
      applied[key] = value
    } else {
      skipped.push(key)
    }
  }

  setConfig(prev => ({ ...prev, ...applied }))
  setPresetNote(skipped.length > 0
    ? `${skipped.length} preset params not supported by current trainer`
    : null)
}
```

### DynamicControl Component

```typescript
// apps/web/src/components/DynamicControl.tsx
function DynamicControl({ name, schema, value, onChange, disabled }) {
  const isNumericEnum = schema.type === 'enum' && typeof schema.options?.[0] === 'number'

  if (schema.type === 'enum') {
    return (
      <select
        disabled={disabled}
        value={value}
        onChange={(e) => {
          const val = isNumericEnum ? Number(e.target.value) : e.target.value
          onChange(val)
        }}
      >
        {schema.options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
      </select>
    )
  }

  if (schema.type === 'int' || schema.type === 'float') {
    const step = schema.step ?? (schema.type === 'int' ? 1 : undefined)
    return (
      <Input
        type="number"
        min={schema.min}
        max={schema.max}
        step={step}
        disabled={disabled}
        value={value}
        onChange={(e) => {
          const val = schema.type === 'int'
            ? parseInt(e.target.value)
            : parseFloat(e.target.value)
          onChange(isNaN(val) ? schema.default : val)
        }}
      />
    )
  }

  // ... bool, string types
}
```

### Collapsible Unavailable Section

```typescript
const wiredParams = Object.entries(trainingParams).filter(([_, p]) => p.wired)
const unwiredParams = Object.entries(trainingParams).filter(([_, p]) => !p.wired)

{unwiredParams.length > 0 && (
  <Collapsible>
    <CollapsibleTrigger className="text-sm text-muted-foreground">
      {unwiredParams.length} parameters not available
    </CollapsibleTrigger>
    <CollapsibleContent className="space-y-3 pt-3">
      {unwiredParams.map(([key, param]) => (
        <div key={key} className="opacity-60">
          <Label>{formatParamName(key)}</Label>
          <DynamicControl name={key} schema={param} value={param.default} disabled />
          {param.reason && (
            <p className="text-xs text-muted-foreground mt-1">{param.reason}</p>
          )}
        </div>
      ))}
    </CollapsibleContent>
  </Collapsible>
)}
```

---

## 7. Tests

### Schema Contract Test

```python
# tests/test_capabilities.py
def test_info_returns_capability_schema(client):
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()

    assert "training" in data
    assert "backend" in data["training"]
    params = data["training"]["parameters"]

    # Validate schema invariants
    valid_types = {"int", "float", "enum", "bool", "string"}
    for name, param in params.items():
        assert param["type"] in valid_types
        assert "default" in param
        assert "wired" in param

        if param["type"] == "enum":
            assert "options" in param and len(param["options"]) > 0

        if "min" in param and "max" in param:
            assert param["min"] <= param["default"] <= param["max"]
```

### Correlation ID Test

```python
# tests/test_correlation.py
def test_correlation_id_echoed_in_response(client):
    correlation_id = "test-corr-12345"
    response = client.post(
        "/api/training",
        headers={"X-Correlation-ID": correlation_id},
        json={"character_id": "test", "config": {...}}
    )
    assert response.headers.get("X-Correlation-ID") == correlation_id

def test_correlation_id_in_redis_job(client, redis_client):
    correlation_id = "test-corr-67890"
    response = client.post(
        "/api/training",
        headers={"X-Correlation-ID": correlation_id},
        json={...}
    )
    job_id = response.json()["id"]
    job_data = redis_client.get_job(job_id)
    assert job_data["correlation_id"] == correlation_id

def test_correlation_id_in_job_log_file(tmp_path, monkeypatch):
    # Monkeypatch VOLUME_ROOT
    monkeypatch.setenv("VOLUME_ROOT", str(tmp_path))

    job_id = "test-job-001"
    correlation_id = "corr-abc123"

    token = set_correlation_id(correlation_id)
    try:
        logger = JobLogger(job_id)
        logger.info("Test message", event="test.event")
    finally:
        reset_correlation_id(token)

    log_path = tmp_path / "logs" / "jobs" / f"{job_id}.jsonl"
    with open(log_path) as f:
        record = json.loads(f.readline())
        assert record["correlation_id"] == correlation_id
        assert record["job_id"] == job_id
```

### Workflow Tests

```python
# tests/test_workflow.py
def test_upscale_workflows_exist():
    workflows_dir = Path("packages/plugins/image/workflows")
    assert (workflows_dir / "flux-dev-upscale.json").exists()
    assert (workflows_dir / "flux-schnell-upscale.json").exists()

def test_upscale_workflow_structure():
    with open("packages/plugins/image/workflows/flux-dev-upscale.json") as f:
        workflow = json.load(f)

    # Find upscale nodes by class_type
    node_types = {node.get("class_type") for node in workflow.values() if isinstance(node, dict)}
    assert "UpscaleModelLoader" in node_types
    assert "ImageUpscaleWithModel" in node_types

    # Verify upscale node is connected (not orphaned)
    # ... structural validation

def test_workflow_selection_deterministic():
    plugin = ComfyUIPlugin()

    # No LoRA, upscale enabled
    config = GenerationConfig(prompt="test", use_upscale=True, model_variant="flux-dev")
    assert plugin._select_workflow(config, lora_path=None) == "flux-dev-upscale"

    # With LoRA, upscale enabled (upscale ignored - deterministic)
    config = GenerationConfig(prompt="test", use_upscale=True, model_variant="flux-dev")
    assert plugin._select_workflow(config, lora_path=Path("/lora.safetensors")) == "flux-dev-lora"
```

### Observability Smoke Test

```python
# scripts/obs_smoke_test.py
import pytest
import os

@pytest.mark.skipif(
    os.environ.get("SMOKE_TEST_ENABLED") != "1",
    reason="Smoke tests require running services"
)
def test_correlation_propagation():
    correlation_id = f"smoke-{uuid.uuid4().hex[:8]}"

    response = requests.post(
        f"{API_URL}/api/generation",
        headers={"X-Correlation-ID": correlation_id},
        json={...}
    )
    job_id = response.json()["id"]
    wait_for_job(job_id)

    logs_response = requests.get(f"{API_URL}/api/jobs/{job_id}/logs")
    assert logs_response.status_code == 200

    for line in logs_response.text.strip().split("\n"):
        record = json.loads(line)
        assert record.get("correlation_id") == correlation_id

@pytest.mark.skipif(...)
def test_job_log_download():
    # ... run job, download logs
    assert logs_response.headers["content-type"] == "application/x-ndjson"
```

---

## 8. Implementation Checklist

| Category | File | Action |
|----------|------|--------|
| **Capability Schema** | | |
| | `packages/plugins/training/src/interface.py` | Add `get_capabilities()` abstract method |
| | `packages/plugins/training/src/ai_toolkit.py` | Implement `get_capabilities()` |
| | `packages/plugins/training/src/mock_plugin.py` | Implement `get_capabilities()` |
| | `packages/plugins/image/src/interface.py` | Add `get_capabilities()` abstract method |
| | `packages/plugins/image/src/comfyui.py` | Implement `get_capabilities()` |
| | `packages/plugins/image/src/mock_plugin.py` | Implement `get_capabilities()` |
| | `apps/api/src/routes/health.py` | Enhance `/info` to return full schema |
| **API Validation** | | |
| | `apps/api/src/services/config_validator.py` | New file - validate against capabilities |
| | `apps/api/src/routes/training.py` | Integrate validator |
| | `apps/api/src/routes/generation.py` | Integrate validator |
| **Correlation & JobLogger** | | |
| | `apps/web/src/lib/api.ts` | Generate correlation ID via `crypto.randomUUID()` |
| | `apps/api/src/middleware.py` | Add correlation middleware with contextvars set/reset |
| | `packages/shared/src/logging.py` | Add `JobLogger` class with portalocker |
| | `packages/shared/src/redis_client.py` | Store correlation_id in job metadata |
| | `apps/worker/src/job_processor.py` | Restore context, create JobLogger |
| **Log Download** | | |
| | `apps/api/src/routes/logs.py` | New file with `/api/jobs/{job_id}/logs` endpoint |
| | `apps/api/src/main.py` | Register logs router |
| | `apps/web/src/pages/Training.tsx` | Add download logs button |
| | `apps/web/src/pages/ImageGen.tsx` | Add download logs button |
| **Upscale Workflow** | | |
| | `packages/plugins/image/workflows/flux-dev-upscale.json` | New workflow |
| | `packages/plugins/image/workflows/flux-schnell-upscale.json` | New workflow |
| | `packages/plugins/image/src/comfyui.py` | Fix workflow selection logic |
| | `packages/plugins/image/src/mock_plugin.py` | Actual 2x CPU resize |
| | `start.sh` | Download RealESRGAN_x2plus.pth |
| **Frontend Dynamic Rendering** | | |
| | `apps/web/src/lib/api.ts` | Add `getInfo()`, capability types |
| | `apps/web/src/pages/Training.tsx` | Schema-driven rendering, preset notes |
| | `apps/web/src/components/DynamicControl.tsx` | New component |
| | `apps/web/src/components/ui/collapsible.tsx` | New component |
| **Tests** | | |
| | `tests/test_capabilities.py` | New file |
| | `tests/test_correlation.py` | New file |
| | `tests/test_job_logger.py` | New file |
| | `tests/test_workflow.py` | Extend with upscale tests |
| | `scripts/obs_smoke_test.py` | Add correlation + log download tests |

---

## 9. Verification Commands

```bash
# Local (fast-test mode)
ISENGARD_MODE=fast-test pytest tests/ -v
curl http://localhost:8000/api/info | jq .

# RunPod (production mode)
ssh root@<pod-ip> -p <port> -i ~/.ssh/id_ed25519 \
  "cd /app && pytest tests/ -v"

ssh root@<pod-ip> -p <port> -i ~/.ssh/id_ed25519 \
  "curl http://localhost:8000/api/info | jq ."

ssh root@<pod-ip> -p <port> -i ~/.ssh/id_ed25519 \
  "ls -la /runpod-volume/isengard/logs/jobs/"
```

---

## 10. Definition of Done

- [ ] `GET /api/info` returns capability schema with parameter details
- [ ] API rejects unsupported parameters with 400 + backend name + reason
- [ ] Training page renders controls from schema (not hardcoded)
- [ ] Unavailable parameters shown in collapsible section with reasons
- [ ] Presets show note when params skipped
- [ ] Correlation ID flows from frontend to worker logs (header → Redis → JSONL)
- [ ] Job log files created at `VOLUME_ROOT/logs/jobs/{job_id}.jsonl`
- [ ] "Download Logs" button works in Training and ImageGen pages
- [ ] Upscale toggle produces 2x larger output image when enabled (no LoRA)
- [ ] All tests pass in fast-test mode
- [ ] Smoke tests pass with services running

---

*Document approved: 2025-12-27*
