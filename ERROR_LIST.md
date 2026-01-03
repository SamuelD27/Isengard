# Isengard - Error List

> All known errors awaiting fix are documented here.

---

## ERR-001: AI-Toolkit Sample Images Not Displayed in GUI

**Status:** ✅ RESOLVED
**Severity:** High
**Component:** `apps/api/src/services/job_executor.py`
**Date Resolved:** 2026-01-03

### Problem Summary

The `SampleImagesPanel.tsx` component works correctly for the mock plugin but will not work for production AI-Toolkit training.

### Data Flow Analysis

| Component | Expected | Actual (AI-Toolkit) |
|-----------|----------|---------------------|
| **API** (`jobs.py:272-290`) | PNG files at `get_job_samples_dir(job_id)/*.png` with format `step_N.png` | No files exist there |
| **AI-Toolkit** (`ai_toolkit.py:302-313`) | Generates samples in temp folder `output/lora_name/samples/*.jpg` | Generates but in wrong location |
| **Mock Plugin** (`mock_plugin.py:490-501`) | Saves to `get_job_samples_dir(job_id)/step_{step:05d}.png` | Works correctly |

### Root Cause

The AI-Toolkit training function in `_run_aitoolkit_training()`:
1. **Did not copy** samples from its temp output directory to the job samples directory
2. **Did not report** `sample_path` in `TrainingProgress` callback
3. **Generated JPG** files while API expects **PNG** files

### Fix Applied

Modified `apps/api/src/services/job_executor.py` function `_run_aitoolkit_training()` (lines 421-647):

1. **Added sample monitoring during training loop:**
   - Monitors `{output_dir}/{job_name}/samples/` directory every 2 seconds
   - Uses regex pattern `.*__(\d+)_(\d+)\.(jpg|jpeg|png|webp)$` to parse AI-Toolkit sample filenames
   - Tracks already-copied samples to avoid duplicates

2. **Added sample copying to job samples directory:**
   - Copies samples to `get_job_samples_dir(job_id)` with naming `step_{step:05d}_{idx}.png`
   - Includes final check after training completes to catch any remaining samples

3. **Reports sample_path in progress callback:**
   - Sets `sample_path` in `TrainingProgress` when new samples are detected
   - Clears after reporting to avoid duplicate notifications

4. **Returns samples in TrainingResult:**
   - `TrainingResult.samples` now populated with all copied sample paths

### Files Modified

- `apps/api/src/services/job_executor.py` - Lines 421-647 (`_run_aitoolkit_training` function)

---
