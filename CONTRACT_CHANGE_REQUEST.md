# Contract Change Request: Advanced Generation Toggles

## Requested By: wt-comfyui
## Date: 2026-01-03

## Summary

ControlNet, IP-Adapter, and FaceDetailer toggles were removed from `get_generation_capabilities()` in `apps/api/src/services/job_executor.py`. These features require additional ComfyUI workflow files and model downloads that are not yet implemented.

**Decision:** OPTION B (Remove unsupported toggles) was chosen to keep the API contract clean. The frontend will automatically hide these toggles since they are not present in the capabilities response.

## Current State

| Toggle | Status | Reason |
|--------|--------|--------|
| `use_upscale` | Supported | Workflows exist: `flux-*-upscale.json` with RealESRGAN 2x |
| `use_controlnet` | **Removed** | No workflows, no models |
| `use_ipadapter` | **Removed** | No workflows, no models |
| `use_facedetailer` | **Removed** | No workflows, no models |

## Required Work (Future Sprint)

### 1. ControlNet Support

**Purpose:** Pose/depth guidance for consistent character positioning

**Required Models:**
- ControlNet FLUX models → `$VOLUME_ROOT/models/controlnet/`
- OpenPose/Depth preprocessor models

**Required Workflow Files:**
- `flux-dev-controlnet.json`
- `flux-dev-lora-controlnet.json`
- `flux-dev-lora-controlnet-upscale.json`
- (repeat for flux-schnell variants)

**Code Changes:**
- Add `use_controlnet` back to capabilities
- Add `control_image` input to GenerationConfig
- Update workflow selection logic in `_run_comfyui_generation()`
- Add preprocessor node injection for pose/depth extraction

**Workflow Nodes Required:**
```json
{
  "ControlNetLoader": {"model_name": "flux-controlnet-v1.safetensors"},
  "OpenPosePreprocessor": {"image": ["input_image", 0]},
  "ControlNetApply": {"conditioning": [...], "control_net": [...], "image": [...]}
}
```

### 2. IP-Adapter Support

**Purpose:** Style transfer from reference images

**Required Models:**
- IP-Adapter FLUX models → `$VOLUME_ROOT/models/ipadapter/`
- CLIP Vision models

**Required Workflow Files:**
- `flux-dev-ipadapter.json`
- `flux-dev-lora-ipadapter.json`
- (repeat for flux-schnell and upscale variants)

**Code Changes:**
- Add `use_ipadapter` back to capabilities
- Add `reference_image` input to GenerationConfig
- Add IPAdapterLoader and IPAdapterApply nodes to workflows

### 3. FaceDetailer Support

**Purpose:** Enhanced facial details in generated images

**Required Models:**
- Face detection model (YOLO/mediapipe) → `$VOLUME_ROOT/models/facedetect/`
- Face enhancement model

**Required Workflow Files:**
- Modify upscale workflows to include FaceDetailer node
- Or create separate `flux-*-facedetailer.json` variants

**Code Changes:**
- Add `use_facedetailer` back to capabilities
- Wire to post-processing pipeline after VAEDecode or upscale

## Impact Assessment

### Frontend Impact
- **None** - Frontend dynamically renders toggles based on capabilities response
- When a toggle is not in capabilities, the UI automatically hides it
- No frontend code changes required for removal or future re-addition

### API Contract Impact
- Response from `/api/info` endpoint changed (toggles removed)
- Any client caching old capabilities should refresh
- Breaking change only if clients hardcode toggle expectations

### Testing Impact
- Existing tests should pass (toggles were not wired)
- New tests needed when implementing each feature:
  - Model download verification
  - Workflow file validation
  - End-to-end generation with toggle enabled

## Files Changed in This Sprint

| File | Change |
|------|--------|
| `apps/api/src/services/job_executor.py:148-173` | Removed unsupported toggles from capabilities |
| `apps/api/src/services/job_executor.py:683-690` | Fixed workflow selection to respect `model_variant` |

## Workflow Audit Summary

**Current Workflow Files (8 total):**
```
apps/api/workflows/
├── flux-dev.json                    # Base FLUX dev
├── flux-dev-lora.json               # FLUX dev with LoRA
├── flux-dev-upscale.json            # FLUX dev with RealESRGAN 2x
├── flux-dev-lora-upscale.json       # FLUX dev with LoRA + upscale
├── flux-schnell.json                # Base FLUX schnell
├── flux-schnell-lora.json           # FLUX schnell with LoRA
├── flux-schnell-upscale.json        # FLUX schnell with RealESRGAN 2x
└── flux-schnell-lora-upscale.json   # FLUX schnell with LoRA + upscale
```

**Node Structure (flux-dev-lora.json):**
- `UNETLoader` (node 4): Loads FLUX UNET
- `LoraLoaderModelOnly` (node 14): Applies LoRA to model
- `DualCLIPLoader` (node 11): Loads CLIP text encoders
- `VAELoader` (node 12): Loads VAE for decoding
- `EmptyLatentImage` (node 5): Creates latent at target size
- `CLIPTextEncodeFlux` (node 6): Encodes prompt
- `FluxGuidance` (node 13): Applies guidance scale
- `KSampler` (node 3): Runs diffusion sampling
- `VAEDecode` (node 8): Decodes latent to image
- `SaveImage` (node 9): Saves output

**Upscale Workflow Additions:**
- `UpscaleModelLoader` (node 20): Loads RealESRGAN_x2plus.pth
- `ImageUpscaleWithModel` (node 21): 2x upscale before save

## Priority Recommendation

For future implementation, recommended order:
1. **ControlNet** - Highest user value for consistent character poses
2. **FaceDetailer** - Builds on existing upscale pipeline
3. **IP-Adapter** - Most complex, requires reference image handling

## Sign-off

- [ ] Frontend team acknowledges no action required
- [ ] Backend implementation scheduled for future sprint
- [ ] Model download scripts to be created before implementation
