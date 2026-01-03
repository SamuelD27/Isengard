# Part 5: Training UI Restructure - Report

## Summary

This report documents the UI improvements made to the training workflow in the `wt-training-ui` worktree.

## Changes Made

### 1. Base Model Selector (StartTraining.tsx)

**File:** `apps/web/src/pages/StartTraining.tsx`

Added a base model selector dropdown that allows users to choose between FLUX models:

```typescript
const [baseModel, setBaseModel] = useState<'flux-dev' | 'flux-schnell'>('flux-dev')
```

**UI Component:**
- Dropdown selector positioned after character selection
- Two options: "FLUX.1-dev (High Quality)" and "FLUX.1-schnell (Fast)"
- Contextual help text that changes based on selection
- Selected model is passed to the API via the mutation

**Lines changed:** 120, 184-186, 218, 359-376

### 2. SSE Hook with Exponential Backoff (useSSE.ts)

**File:** `apps/web/src/hooks/useSSE.ts`

Completely rewrote the hook to include:

- **Exponential backoff reconnection**: Starts at 1s, doubles on each retry, caps at 30s
- **Retry state tracking**: Exposes `retryCount` and `retryDelay` for UI feedback
- **Countdown display**: Updates retry delay countdown every second
- **Manual reconnect**: Added `reconnect()` function for user-triggered reconnection
- **Custom event types**: Support for listening to custom SSE event types
- **Proper cleanup**: Clears all timers and closes connections on unmount

**New return values:**
```typescript
{
  isConnected: boolean,
  lastMessage: unknown,
  retryCount: number,
  retryDelay: number | null,
  close: () => void,
  reconnect: () => void,
}
```

## Features Already Implemented (No Changes Needed)

### 3. Progress Bar Handling (TrainingLogsPanel.tsx)

**Status:** Already implemented correctly

The component already:
- Defines `ProgressBar` interface with proper types
- Renders active and completed progress bars above log entries
- Uses color coding by progress type (training, download, sample, etc.)
- Shows current/total counts and percentages
- Animates active progress bars with pulse effect

### 4. Sample Images Polling (SampleImagesPanel.tsx)

**Status:** Already implemented correctly

The component already:
- Polls every 5 seconds while training is active (`refetchInterval: isActive ? 5000 : false`)
- Stops polling when training completes
- Uses React Query for automatic cache management

### 5. SSE Reconnection in TrainingDetail (TrainingDetail.tsx)

**Status:** Already implemented correctly

The page already has custom SSE handling with:
- Initial retry delay of 1000ms
- Max retry delay of 30000ms
- Backoff multiplier of 2
- Live countdown display in status bar
- Automatic reconnection on connection loss

## UI Screenshots / Descriptions

### Base Model Selector

Located in the Configuration card, after character selection:

```
┌─────────────────────────────────────────┐
│ Configuration                           │
│ Using Balanced preset                   │
│                                         │
│ Character                               │
│ ┌─────────────────────────────────────┐ │
│ │ Select character...              ▼  │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ Base Model                              │
│ ┌─────────────────────────────────────┐ │
│ │ FLUX.1-dev (High Quality)        ▼  │ │
│ └─────────────────────────────────────┘ │
│ Best quality results, requires more     │
│ training time                           │
│                                         │
│ Training Steps        Resolution        │
│ ┌───────────────┐    ┌───────────────┐  │
│ │ 1000          │    │ 1024px        │  │
│ └───────────────┘    └───────────────┘  │
└─────────────────────────────────────────┘
```

## API Contract Status

No API contract changes needed. The existing `api.startTraining()` function already accepts `baseModel` as a parameter:

```typescript
startTraining: (
  characterId: string,
  config: Partial<TrainingConfig> = {},
  presetName?: string,
  baseModel: string = 'flux-dev'  // Already supported
)
```

The backend `StartTrainingRequest` type already includes `base_model?: string`.

## Files Modified

| File | Changes |
|------|---------|
| `apps/web/src/pages/StartTraining.tsx` | Added baseModel state, selector UI, mutation parameter |
| `apps/web/src/hooks/useSSE.ts` | Complete rewrite with exponential backoff |

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| Base model selector appears on StartTraining page | ✅ Done |
| Selected base model is sent to API | ✅ Done |
| Progress bars update in place (not appended as log lines) | ✅ Already working |
| Sample images panel polls correctly during training | ✅ Already working |
| SSE reconnection works with backoff | ✅ Already working + improved hook |

## Testing Notes

1. **Base Model Selector**: Navigate to `/training/start`, select a character, and verify:
   - Dropdown appears with two options
   - Help text updates based on selection
   - Console logs show selected model when starting training

2. **SSE Reconnection**: Start a training job and simulate network interruption:
   - Status bar shows "Connection lost. Reconnecting in Xs..."
   - Countdown decrements each second
   - Connection re-establishes after delay

3. **Progress Bars**: During training, verify:
   - Progress bars appear in TrainingLogsPanel
   - They update in place, not as new log entries
   - Completed bars fade out and show in "completed" section

4. **Sample Images**: During training, verify:
   - Panel shows loading skeletons initially
   - Images appear as they are generated
   - Polling stops when training completes
