# UELR - User End Log Register

UELR is a first-class, end-to-end interaction logging system that enables complete traceability from user clicks in the GUI through to backend processing and worker jobs.

## Overview

When a user clicks any button in Isengard, UELR:

1. Creates an **Interaction** with a unique `interaction_id`
2. Generates a **Correlation ID** that travels through all API calls
3. Logs each step of the process (UI events, network requests, backend processing, jobs)
4. Persists everything to disk for later analysis
5. Provides a Logs UI to view interaction traces

## Key Concepts

### Interaction ID vs Correlation ID

- **`interaction_id`**: Unique ID for a single user action (e.g., one button click). Starts with `int-`.
- **`correlation_id`**: Unique ID for tracing a request through the system. Starts with `cor-`.

Both are generated on the frontend and propagated through HTTP headers:
- `X-Correlation-ID`: Always present in API requests
- `X-Interaction-ID`: Present when a tracked interaction is active

### Steps

Each interaction contains multiple **steps** representing discrete events:

| Step Type | Component | Description |
|-----------|-----------|-------------|
| `UI_ACTION_START` | frontend | User initiated action |
| `UI_ACTION_END` | frontend | Action completed |
| `NETWORK_REQUEST_START` | frontend | HTTP request initiated |
| `NETWORK_REQUEST_END` | frontend | HTTP response received |
| `SSE_CONNECT` | frontend | SSE connection opened |
| `SSE_MESSAGE` | frontend | SSE message received |
| `BACKEND_ROUTE_START` | backend | Route handler started |
| `BACKEND_ROUTE_END` | backend | Route handler completed |
| `JOB_ENQUEUE` | backend | Job queued |
| `JOB_START` | worker | Job execution started |
| `JOB_PROGRESS` | worker | Job progress update |
| `JOB_END` | worker | Job completed |
| `PLUGIN_CALL` | plugin | Plugin method called |
| `COMFYUI_REQUEST` | comfyui | ComfyUI API request |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Frontend (React)                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      UELR SDK                                 │   │
│  │  startInteraction() → logStep() → completeInteraction()      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              IndexedDB + Sync Queue                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ X-Correlation-ID, X-Interaction-ID
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Backend API (FastAPI)                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              CorrelationIDMiddleware                          │   │
│  │  Extracts/generates correlation ID, sets in context           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              UELR Routes (/api/uelr/*)                        │   │
│  │  POST /interactions, POST /steps, GET /bundle                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              JSONL Persistence                                │   │
│  │  logs/uelr/interactions/{id}.jsonl                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Log Locations

### Local Development

```
logs/
├── api/
│   └── latest/
│       └── api.log              # JSON structured logs
├── worker/
│   └── latest/
│       └── worker.log
└── uelr/
    ├── interactions/
    │   ├── int-abc123.jsonl     # Interaction + steps
    │   └── int-def456.jsonl
    └── index/
        └── interactions.jsonl   # Quick lookup index
```

### RunPod / Production

Set `UELR_LOG_DIR` environment variable to persist to network volume:

```bash
export UELR_LOG_DIR=/runpod-volume/isengard/logs/uelr
```

## Frontend Usage

### Basic Usage

```typescript
import { uelr } from '@/uelr';

// Start tracking an interaction
const context = uelr.startInteraction('Create Character', {
  category: 'character'
});

try {
  // Your async code here
  await api.createCharacter(data);
  await uelr.completeInteraction(context, 'success');
} catch (error) {
  await uelr.completeInteraction(context, 'error', error);
}
```

### Using wrapAction

```typescript
const handleClick = uelr.wrapAction('Create Character', async (ctx) => {
  await api.createCharacter(data);
}, { category: 'character' });

// Use in button
<button onClick={handleClick}>Create</button>
```

### Using React Hooks

```typescript
import { useTrackedAction } from '@/uelr';

function MyComponent() {
  const handleCreate = useTrackedAction(
    'Create Character',
    async (ctx, formData: FormData) => {
      await api.createCharacter(formData);
    },
    { category: 'character' }
  );

  return <button onClick={() => handleCreate(data)}>Create</button>;
}
```

## API Endpoints

### Create Interaction

```http
POST /api/uelr/interactions
Content-Type: application/json

{
  "interaction_id": "int-abc123",
  "correlation_id": "cor-xyz789",
  "action_name": "Create Character",
  "action_category": "character",
  "page": "/characters"
}
```

### Append Steps

```http
POST /api/uelr/interactions/{interaction_id}/steps
Content-Type: application/json

{
  "interaction_id": "int-abc123",
  "steps": [
    {
      "step_id": "step-1",
      "correlation_id": "cor-xyz789",
      "type": "NETWORK_REQUEST_START",
      "component": "frontend",
      "timestamp": "2025-01-15T10:30:00.000Z",
      "message": "POST /api/characters",
      "status": "pending",
      "details": {
        "method": "POST",
        "url": "/api/characters"
      }
    }
  ]
}
```

### Complete Interaction

```http
PUT /api/uelr/interactions/{interaction_id}/complete
Content-Type: application/json

{
  "interaction_id": "int-abc123",
  "status": "success"
}
```

### Get Interaction with Steps

```http
GET /api/uelr/interactions/{interaction_id}
```

### List Interactions

```http
GET /api/uelr/interactions?limit=50&offset=0&status=error&action_name=Create
```

### Download Bundle

```http
GET /api/uelr/interactions/{interaction_id}/bundle
```

Returns a ZIP file containing:
- `interaction.json` - Full interaction with steps
- `backend_logs.jsonl` - Backend logs filtered by correlation_id
- `worker_logs.jsonl` - Worker logs filtered by correlation_id

## Logs UI

Access the Logs page at `/logs` to:

1. **View Recent Interactions**: Left panel shows a list of recent interactions with:
   - Action name
   - Status (success/error/pending)
   - Timestamp and duration
   - Error count

2. **Inspect Timeline**: Click an interaction to see:
   - Complete timeline of steps
   - Expandable details for each step
   - Component icons (Frontend/Backend/Worker)
   - Timing information

3. **Download Bundle**: Click "Download Bundle" to get a ZIP with all related logs

4. **Filter/Search**: Use the search bar and status filter to find specific interactions

## Redaction

UELR automatically redacts sensitive data before logging:

### Redacted Patterns
- Hugging Face tokens: `hf_*` → `hf_***REDACTED***`
- OpenAI keys: `sk-*` → `sk-***REDACTED***`
- GitHub tokens: `ghp_*` → `ghp_***REDACTED***`
- RunPod keys: `rpa_*` → `rpa_***REDACTED***`
- Bearer tokens: `Bearer *` → `Bearer ***REDACTED***`
- URL tokens: `token=*` → `token=***`
- Passwords: `password=*` → `password=***`
- User paths: `/Users/john/` → `/[HOME]/`

### Redacted Keys
These field names have their values completely redacted:
- `authorization`
- `cookie`, `set-cookie`
- `api_key`, `apikey`, `x-api-key`
- `token`
- `password`, `secret`, `credential`

## Error Handling

When an action fails, a toast notification appears with:
- Error message
- Truncated correlation ID
- "Open Logs" button to deep-link to the interaction

```typescript
import { useToast } from '@/components/ui/toast';

function MyComponent() {
  const { showError } = useToast();

  const handleClick = async () => {
    const context = uelr.startInteraction('My Action');
    try {
      await doSomething();
    } catch (error) {
      await uelr.completeInteraction(context, 'error', error);
      showError(
        'Action Failed',
        error.message,
        context.correlation_id,
        context.interaction_id
      );
    }
  };
}
```

## Extracting Logs for Debugging

### Using the UI

1. Navigate to `/logs`
2. Find the relevant interaction
3. Click "Download Bundle"
4. Share the ZIP file for debugging

### Using the CLI

```bash
# Get all logs for a correlation ID
grep "cor-abc123" logs/api/latest/api.log | jq .

# Get UELR interaction
cat logs/uelr/interactions/int-xyz789.jsonl | jq .

# Download bundle via curl
curl -o bundle.zip http://localhost:8000/api/uelr/interactions/int-xyz789/bundle
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `UELR_LOG_DIR` | Directory for UELR logs | `./logs/uelr` |

### Retention

- **Frontend**: 500 interactions max, 7 days retention
- **Backend**: 1000 interactions max, 30 days retention

Cleanup runs automatically or via:

```http
POST /api/uelr/cleanup?retention_days=30
```

## Testing

### Unit Tests

```bash
# Backend redaction tests
pytest tests/test_uelr_redaction.py -v

# Frontend sanitization tests
cd apps/web && npm test -- src/uelr/sanitize.test.ts
```

### E2E Tests

```bash
# Run UELR-specific E2E tests
cd e2e && npx playwright test tests/uelr.spec.ts
```

## Tracked Actions (Click-to-Trace Guarantee)

These actions are fully instrumented:

| Action | Category | Steps |
|--------|----------|-------|
| Create Character | character | UI_START → NETWORK → BACKEND → UI_END |
| Upload Images | character | UI_START → NETWORK → BACKEND → UI_END |
| Delete Character | character | UI_START → NETWORK → BACKEND → UI_END |
| Start Training | training | UI_START → NETWORK → BACKEND → JOB_ENQUEUE → JOB_START → JOB_PROGRESS → JOB_END → UI_END |
| Cancel Training | training | UI_START → NETWORK → BACKEND → UI_END |
| Generate Image | generation | UI_START → NETWORK → BACKEND → JOB_ENQUEUE → JOB_START → JOB_PROGRESS → JOB_END → UI_END |
| Navigation | navigation | UI_START → UI_END |
| Form Submit | form | UI_START → NETWORK → BACKEND → UI_END |

## Troubleshooting

### Interactions not appearing in Logs UI

1. Check browser console for errors
2. Verify IndexedDB is enabled (some browsers disable in private mode)
3. Check backend logs for UELR API errors

### Correlation IDs not matching

1. Ensure middleware is registered in FastAPI app
2. Check that headers are being passed through proxies

### Bundle download fails

1. Check disk space on server
2. Verify log directory permissions
3. Check for very large interactions (may timeout)
