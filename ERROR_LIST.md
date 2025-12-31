# Isengard - Error List

> All known errors awaiting fix are documented here.

---

## ERR-001: AI-Toolkit Sample Images Not Displayed in GUI

**Status:** Open
**Severity:** High
**Component:** `packages/plugins/training/src/ai_toolkit.py`, `apps/web/src/components/training/SampleImagesPanel.tsx`

### Problem Summary

The `SampleImagesPanel.tsx` component works correctly for the mock plugin but will not work for production AI-Toolkit training.

### Data Flow Analysis

| Component | Expected | Actual (AI-Toolkit) |
|-----------|----------|---------------------|
| **API** (`jobs.py:272-290`) | PNG files at `get_job_samples_dir(job_id)/*.png` with format `step_N.png` | No files exist there |
| **AI-Toolkit** (`ai_toolkit.py:302-313`) | Generates samples in temp folder `output/lora_name/samples/*.jpg` | Generates but in wrong location |
| **Mock Plugin** (`mock_plugin.py:490-501`) | Saves to `get_job_samples_dir(job_id)/step_{step:05d}.png` | Works correctly |

### Root Cause

The AI-Toolkit plugin:
1. **Does not copy** samples from its temp output directory to the job samples directory
2. **Does not report** `sample_path` in `TrainingProgress` callback (see `ai_toolkit.py:660-666`)
3. **Generates JPG** files while API expects **PNG** files

### Fix Required

The AI-Toolkit plugin needs to:
1. Monitor AI-Toolkit's sample output directory during training
2. Copy new samples to `get_job_samples_dir(job_id)` with proper naming
3. Rename to `step_N.png` format (converting if needed)
4. Report `sample_path` in the progress callback

### Files to Modify

- `packages/plugins/training/src/ai_toolkit.py` - Add sample monitoring and copying logic

---
