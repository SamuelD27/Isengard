# Vendor Patches

This directory contains patches to apply to vendored upstream code.

## When to Use Patches

Only create patches when:
1. A critical bug fix is needed before upstream accepts it
2. Isengard-specific behavior is required that wouldn't be accepted upstream
3. Security fixes need to be applied immediately

## Patch Naming Convention

```
<vendor>-<issue>-<description>.patch
```

Examples:
- `comfyui-001-localhost-binding.patch`
- `ai-toolkit-002-flux-config-fix.patch`

## Applying Patches

Patches are applied during Docker build. See `Dockerfile` for the patch application step.

```bash
# Manual application (for testing):
cd vendor/comfyui
git apply ../../patches/comfyui-001-example.patch
```

## Creating Patches

```bash
# Make changes in vendor/comfyui
cd vendor/comfyui
# ... edit files ...

# Create patch
git diff > ../../patches/comfyui-001-description.patch

# Or for staged changes
git diff --cached > ../../patches/comfyui-001-description.patch
```

## Current Patches

| Vendor | Patch | Description | Applied Since |
|--------|-------|-------------|---------------|
| (none) | - | No patches currently needed | - |

## Removing Patches

When upstream incorporates a fix, or when updating to a version that includes it:
1. Remove the patch file
2. Update this table
3. Test the build
