# ComfyUI Workflows

This directory contains workflow JSON files for image generation with various module combinations.

## Workflow Naming Convention

Workflows are named by their enabled modules, sorted alphabetically and joined with underscores:

| Modules Enabled | Workflow File |
|-----------------|---------------|
| None (base FLUX + LoRA) | `base.json` |
| ControlNet only | `controlnet.json` |
| IPAdapter only | `ipadapter.json` |
| FaceDetailer only | `facedetailer.json` |
| Upscale only | `upscale.json` |
| ControlNet + IPAdapter | `controlnet_ipadapter.json` |
| ControlNet + FaceDetailer | `controlnet_facedetailer.json` |
| ControlNet + Upscale | `controlnet_upscale.json` |
| IPAdapter + FaceDetailer | `facedetailer_ipadapter.json` |
| IPAdapter + Upscale | `ipadapter_upscale.json` |
| FaceDetailer + Upscale | `facedetailer_upscale.json` |
| ControlNet + IPAdapter + FaceDetailer | `controlnet_facedetailer_ipadapter.json` |
| ControlNet + IPAdapter + Upscale | `controlnet_ipadapter_upscale.json` |
| ControlNet + FaceDetailer + Upscale | `controlnet_facedetailer_upscale.json` |
| IPAdapter + FaceDetailer + Upscale | `facedetailer_ipadapter_upscale.json` |
| All modules | `controlnet_facedetailer_ipadapter_upscale.json` |

## Placeholder Variables

Each workflow JSON uses placeholders that get substituted at runtime:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{PROMPT}}` | Positive prompt text | "photo of ohwx woman in paris" |
| `{{NEGATIVE_PROMPT}}` | Negative prompt text | "blurry, low quality" |
| `{{LORA_PATH}}` | Path to LoRA safetensors file | "/workspace/isengard/models/loras/emma.safetensors" |
| `{{WIDTH}}` | Image width | 1024 |
| `{{HEIGHT}}` | Image height | 1024 |
| `{{STEPS}}` | Sampling steps | 30 |
| `{{CFG}}` | CFG scale | 7.5 |
| `{{SEED}}` | Random seed | 12345 |
| `{{CONTROLNET_IMAGE}}` | ControlNet input image path | "/path/to/pose.png" |
| `{{CONTROLNET_STRENGTH}}` | ControlNet strength | 0.8 |
| `{{IPADAPTER_IMAGE}}` | IPAdapter reference image path | "/path/to/face.png" |
| `{{IPADAPTER_STRENGTH}}` | IPAdapter strength | 0.6 |

## Creating Workflows

1. Design workflow in ComfyUI web interface
2. Export as API format JSON (not PNG workflow)
3. Replace hardcoded values with placeholders above
4. Save with appropriate filename based on modules used

## Module Descriptions

### ControlNet
Guides image generation using structural input (pose, edges, depth).
- Input: Reference image (pose skeleton, canny edges, etc.)
- Use case: Match specific poses or compositions

### IPAdapter
Transfers facial features or style from a reference image.
- Input: Reference face/style image
- Use case: Consistent character identity across generations

### FaceDetailer
Post-processes faces to improve detail and quality.
- Input: Generated image (automatic)
- Use case: Fix common face artifacts

### Upscale
Increases image resolution using AI upscaling.
- Input: Generated image (automatic)
- Use case: Higher resolution final outputs
