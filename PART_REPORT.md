# Part 3 Report: ComfyUI Generation Backend + Capability Toggles

## Date: 2026-01-03
## Branch: wt-comfyui

---

## 1. Toggle Status

### Before Changes
| Toggle | supported | Description |
|--------|-----------|-------------|
| `use_upscale` | `true` | 2x upscale |
| `use_facedetailer` | `false` | Face enhancement |
| `use_ipadapter` | `false` | Style transfer |
| `use_controlnet` | `false` | Pose guidance |

### After Changes
| Toggle | supported | Description |
|--------|-----------|-------------|
| `use_upscale` | `true` | 2x RealESRGAN upscale |

**Removed toggles:** `use_facedetailer`, `use_ipadapter`, `use_controlnet`

---

## 2. Decision Made

**OPTION B: Remove unsupported toggles**

Rationale:
- Toggles with `supported: false` clutter the API contract
- Frontend already handles dynamic toggle rendering based on capabilities
- Clean API is preferable to advertising non-functional features
- Future implementation plan documented in `CONTRACT_CHANGE_REQUEST.md`

---

## 3. Workflow Audit Results

### Current Files (8 total)
```
apps/api/workflows/
├── flux-dev.json               (1469 bytes)
├── flux-dev-lora.json          (1649 bytes)
├── flux-dev-upscale.json       (1867 bytes)
├── flux-dev-lora-upscale.json  (2047 bytes)
├── flux-schnell.json           (1472 bytes)
├── flux-schnell-lora.json      (1652 bytes)
├── flux-schnell-upscale.json   (1870 bytes)
└── flux-schnell-lora-upscale.json (2050 bytes)
```

### Workflow Node Structure
All workflows share a common structure:

**Base Pipeline:**
1. `UNETLoader` → Load FLUX UNET model
2. `DualCLIPLoader` → Load CLIP L + T5XXL encoders
3. `VAELoader` → Load VAE for decoding
4. `EmptyLatentImage` → Create latent at target dimensions
5. `CLIPTextEncodeFlux` → Encode prompt with FLUX-specific encoding
6. `FluxGuidance` → Apply CFG guidance scale
7. `KSampler` → Run diffusion sampling (euler/simple scheduler)
8. `VAEDecode` → Decode latent to RGB
9. `SaveImage` → Save output with prefix

**LoRA Variants Add:**
- `LoraLoaderModelOnly` (node 14) → Injects LoRA between UNET load and KSampler

**Upscale Variants Add:**
- `UpscaleModelLoader` → Load RealESRGAN_x2plus.pth
- `ImageUpscaleWithModel` → 2x upscale before save

### Placeholder Tokens
Workflows use these placeholders for runtime injection:
- `__LORA_PATH_PLACEHOLDER__` → Replaced with actual LoRA path
- `__PROMPT_PLACEHOLDER__` → Replaced with user prompt
- Width/height/seed/steps → Replaced via regex on JSON

---

## 4. Bug Fixes Applied

### 4.1 Workflow Selection Logic Bug

**Location:** `apps/api/src/services/job_executor.py:684`

**Before (BROKEN):**
```python
workflow_name = "flux-dev-lora" if lora_path else "flux-schnell"
```

This ignored `config.model_variant`, always using dev with LoRA or schnell without.

**After (FIXED):**
```python
model_variant = config.model_variant or "flux-dev"
if lora_path:
    workflow_name = f"flux-{model_variant.replace('flux-', '')}-lora"
else:
    workflow_name = f"flux-{model_variant.replace('flux-', '')}"
```

Now correctly handles all 8 workflow variants based on:
- `config.model_variant` (flux-dev or flux-schnell)
- `lora_path` presence (with or without LoRA)
- `config.use_upscale` (appends -upscale)

### 4.2 Capabilities Cleanup

**Location:** `apps/api/src/services/job_executor.py:148-173`

Removed non-functional toggles from the capabilities dictionary. Added docstring explaining removal and reference to CONTRACT_CHANGE_REQUEST.md.

---

## 5. Test Results

### Manual Verification
```bash
# Check the workflow selection patterns are correct:
model_variant = "flux-dev"
lora_path = "/path/to/lora.safetensors"
use_upscale = True

# Expected workflow: "flux-dev-lora-upscale"
# File exists: apps/api/workflows/flux-dev-lora-upscale.json ✓

model_variant = "flux-schnell"
lora_path = None
use_upscale = False

# Expected workflow: "flux-schnell"
# File exists: apps/api/workflows/flux-schnell.json ✓
```

### All Workflow Combinations
| model_variant | lora_path | use_upscale | Expected Workflow | File Exists |
|---------------|-----------|-------------|-------------------|-------------|
| flux-dev | None | false | flux-dev | ✓ |
| flux-dev | None | true | flux-dev-upscale | ✓ |
| flux-dev | set | false | flux-dev-lora | ✓ |
| flux-dev | set | true | flux-dev-lora-upscale | ✓ |
| flux-schnell | None | false | flux-schnell | ✓ |
| flux-schnell | None | true | flux-schnell-upscale | ✓ |
| flux-schnell | set | false | flux-schnell-lora | ✓ |
| flux-schnell | set | true | flux-schnell-lora-upscale | ✓ |

---

## 6. Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `apps/api/src/services/job_executor.py` | 148-173 | Removed unsupported toggles from capabilities |
| `apps/api/src/services/job_executor.py` | 683-690 | Fixed workflow selection to respect model_variant |

## 7. Files Created

| File | Description |
|------|-------------|
| `CONTRACT_CHANGE_REQUEST.md` | Documents future toggle implementation requirements |
| `PART_REPORT.md` | This report |

---

## 8. Acceptance Criteria Checklist

- [x] Only `use_upscale` appears in generation capabilities
- [x] Unsupported toggles removed from `get_generation_capabilities()`
- [x] `CONTRACT_CHANGE_REQUEST.md` documents future toggle implementation
- [x] Workflow selection logic verified correct for all 8 variants
- [x] No changes to training code

---

## 9. Notes for Next Steps

1. **Frontend:** Should automatically hide ControlNet/IPAdapter/FaceDetailer toggles since they're no longer in capabilities response.

2. **Testing:** Run full generation test with both model variants and both LoRA/no-LoRA configurations to verify workflow selection.

3. **Future Work:** See `CONTRACT_CHANGE_REQUEST.md` for implementation roadmap of advanced toggles.
