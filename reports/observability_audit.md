# Isengard Observability Audit

**Generated:** 2025-12-26
**Auditor:** Claude Code (Opus 4.5)
**Status:** Pre-implementation audit

---

## Current Logging State

### Services Identified

| Service | Location | Language | Logging Status |
|---------|----------|----------|----------------|
| API | `apps/api/` | Python | Partial |
| Worker | `apps/worker/` | Python | Partial |
| Web | `apps/web/` | TypeScript | None |

### Existing Infrastructure

#### Shared Logging Module (`packages/shared/src/logging.py`)

**Implemented:**
- ✅ `StructuredFormatter` - JSON output format
- ✅ `ContextAdapter` - Context field support
- ✅ Correlation ID via `ContextVar`
- ✅ `redact_sensitive()` - Secret/path redaction
- ✅ Per-day log files (`YYYY-MM-DD.log`)
- ✅ Stdout + file output
- ✅ `configure_logging()` for service startup

**Missing:**
- ❌ Log rotation between runs (archive system)
- ❌ `latest/` vs `archive/YYYYMMDD_HHMMSS/` structure
- ❌ Subprocess stdout/stderr capture
- ❌ Log schema specification document
- ❌ Validation/verification utilities

#### API Middleware (`apps/api/src/middleware.py`)

**Implemented:**
- ✅ `CorrelationIDMiddleware` - generates/extracts X-Correlation-ID
- ✅ Request start/end logging
- ✅ Response status logging

**Missing:**
- ❌ Request body logging (sanitized)
- ❌ Response time measurement
- ❌ Exception stack trace logging (middleware-level)

#### Frontend (`apps/web/src/lib/api.ts`)

**Implemented:**
- ✅ `generateCorrelationId()` exists
- ✅ Correlation ID header on requests

**Missing:**
- ❌ Client-side logging infrastructure
- ❌ UI event logging
- ❌ Error boundary logging
- ❌ Log persistence to server

---

## Current Log Directory Structure

```
logs/
└── .gitkeep  (50 bytes - placeholder only)
```

**Problem:** No actual logs present. No service subdirectories created.

---

## Inconsistencies Between Services

### 1. Log Level Handling
- API uses `config.log_level` (configurable)
- Worker may not be initializing logging consistently
- Frontend has no logging at all

### 2. Correlation ID Propagation
- Frontend generates but doesn't log locally
- API extracts and logs
- Worker receives but subprocess output is not captured

### 3. Log File Paths
- Config says logs go to `./logs/{service}/`
- But directory structure not created automatically on startup
- No archive rotation implemented

### 4. Error Handling Gaps
- Exceptions logged but stack traces may be truncated
- Subprocess failures not captured to dedicated files
- Client-side errors not sent to server

---

## Required Fixes (Prioritized)

### P0: Critical (Must have for debugging)

1. **Log rotation system**
   - Archive existing logs on each run
   - Maintain `latest/` vs `archive/` separation
   - Clear session boundaries

2. **Directory auto-creation**
   - Ensure `logs/api/latest/`, `logs/worker/latest/` exist
   - Create archive directories on rotation

3. **Subprocess capture**
   - Route job stdout/stderr to `logs/worker/subprocess/{job_id}.*`

### P1: Important (For production readiness)

4. **Frontend logging**
   - Client-side structured logger
   - POST to `/api/client-logs` endpoint
   - Local file persistence in dev

5. **Log schema specification**
   - Document required fields
   - Create validation utility

6. **Exception enhancement**
   - Full stack traces in JSON
   - Request context preservation

### P2: Nice to have

7. **Metrics endpoint**
   - Log counts by level
   - Error rate tracking

8. **Log aggregation hooks**
   - Ship to external service (future)

---

## Immediate Action Plan

1. Create `packages/shared/observability/` directory
2. Add `LOGGING_SPEC.md` with schema definition
3. Enhance logging module with rotation
4. Add `scripts/rotate_logs.py`
5. Update CLAUDE.md with logging doctrine
6. Add verification scripts
7. Validate M1 using logs

---

*This audit identifies gaps that must be fixed before M1 validation.*
