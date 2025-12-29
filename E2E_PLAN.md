# E2E Testing Plan for Isengard GUI

## Executive Summary

This document outlines the plan to implement comprehensive E2E (end-to-end) GUI testing for Isengard that:
1. Catches real user-facing bugs (buttons not working, views not updating, race conditions)
2. Runs locally with ONE command before any Docker build/push
3. Produces actionable failure reports with screenshots, videos, traces, and logs
4. Integrates with CI for automated regression testing

## Current State Analysis

### Existing E2E Setup
- **Location**: `/e2e/`
- **Framework**: Playwright v1.40
- **Tests**: 4 spec files (characters, training, gui-api-wiring, uelr)
- **Config**: Basic - only chromium, traces on retry only

### Issues with Current Setup
1. Traces/videos only captured on retry (miss first failures)
2. No page object models (brittle selectors)
3. No deterministic wait strategies (uses `waitForLoadState('networkidle')` which is unreliable)
4. No local stack runner (tests expect services to be running)
5. No visual regression testing
6. No comprehensive failure reports
7. Limited assertion depth (checks visibility, not actual UI state)
8. No edge case coverage (slow API, errors, double-clicks)

## Architecture

```
e2e/
├── playwright.config.ts          # Enhanced config
├── package.json                  # Dependencies
├── tsconfig.json                 # TypeScript config
├── tests/
│   ├── smoke/                    # Quick sanity checks
│   │   └── app-loads.spec.ts
│   ├── flows/                    # User journey tests
│   │   ├── characters.spec.ts
│   │   ├── training.spec.ts
│   │   ├── generation.spec.ts
│   │   └── dataset.spec.ts
│   ├── edge-cases/               # Error handling, race conditions
│   │   ├── slow-api.spec.ts
│   │   ├── api-errors.spec.ts
│   │   └── double-click.spec.ts
│   └── visual/                   # Screenshot comparisons
│       └── baselines.spec.ts
├── pages/                        # Page Object Models
│   ├── base.page.ts
│   ├── characters.page.ts
│   ├── training.page.ts
│   ├── generation.page.ts
│   └── dataset.page.ts
├── fixtures/                     # Test data, setup/teardown
│   ├── test-fixtures.ts
│   ├── api-mock.ts
│   └── seed-data.ts
├── utils/                        # Helpers
│   ├── wait-helpers.ts
│   ├── network-capture.ts
│   ├── log-collector.ts
│   └── report-generator.ts
├── artifacts/                    # Git-ignored test outputs
│   ├── screenshots/
│   ├── videos/
│   ├── traces/
│   └── reports/
└── baselines/                    # Committed visual baselines
    └── desktop/
```

## Configuration Strategy

### Browsers and Viewports
```typescript
projects: [
  { name: 'chromium-desktop', use: { ...devices['Desktop Chrome'] } },
  { name: 'chromium-laptop', use: { viewport: { width: 1366, height: 768 } } },
  { name: 'chromium-mobile', use: { ...devices['iPhone 13'] } },
  { name: 'firefox-desktop', use: { ...devices['Desktop Firefox'] } },
  { name: 'webkit-desktop', use: { ...devices['Desktop Safari'] } },
]
```

### Artifact Collection (Always-On)
```typescript
use: {
  trace: 'on',              // Always capture traces
  screenshot: 'on',          // Screenshot on every test
  video: 'on',               // Record every test
  baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
}
```

### Timeouts
```typescript
timeout: 60000,              // 60s per test
expect: { timeout: 10000 },  // 10s for assertions
actionTimeout: 5000,         // 5s for clicks, fills, etc.
navigationTimeout: 30000,    // 30s for page loads
```

## Page Object Models

### Base Page
```typescript
export class BasePage {
  constructor(protected page: Page) {}

  // Standard waits
  async waitForPageReady() {
    await this.page.waitForLoadState('domcontentloaded');
    await this.page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
  }

  // API response capture
  async waitForApiResponse(endpoint: string, method = 'GET') {
    return this.page.waitForResponse(
      r => r.url().includes(endpoint) && r.request().method() === method
    );
  }

  // Network error detection
  async captureNetworkErrors(): Promise<NetworkError[]> { ... }

  // Console error detection
  async captureConsoleErrors(): Promise<ConsoleMessage[]> { ... }
}
```

### Page-Specific Models
Each page model provides:
1. **Locators** - Using `data-testid` attributes
2. **Actions** - High-level user operations
3. **Assertions** - State validation methods
4. **Waits** - Page-specific ready conditions

## Test Categories

### 1. Smoke Tests (< 30 seconds)
- App loads without JS errors
- Navigation works
- API health check passes
- Key pages render

### 2. Flow Tests (User Journeys)
**Characters Flow**:
- Create character with form validation
- Upload images
- View character details
- Delete character with confirmation

**Training Flow** (Critical):
- Select character
- Configure training preset
- Start training
- Verify job appears in queue
- Observe progress updates via SSE
- View job details
- Check logs appear
- Handle completion/failure states

**Generation Flow**:
- Configure generation settings
- Start generation
- Observe progress
- View output gallery

### 3. Edge Case Tests
- **Slow API**: Inject 5s latency, verify UI shows loading state, no double-submits
- **API Errors**: Return 500, verify error displayed and recoverable
- **Double Click**: Rapid clicks on submit, verify only one action
- **Network Loss**: Simulate disconnect, verify reconnection handling
- **Viewport Resize**: Critical controls remain accessible

### 4. Visual Regression Tests
Baseline screenshots for:
- Characters list (empty, populated)
- Training page (idle, running, completed)
- Training detail modal
- Generation page
- Error states

## Wait Strategy (Deterministic)

**NEVER use**:
```typescript
await page.waitForTimeout(1000);  // Arbitrary sleep
await page.waitForLoadState('networkidle');  // Unreliable
```

**ALWAYS use**:
```typescript
// Wait for specific element
await expect(page.getByTestId('character-card')).toBeVisible();

// Wait for specific count
await expect(page.getByTestId('job-list').locator('.job-card')).toHaveCount(1);

// Wait for specific text
await expect(page.getByTestId('job-status')).toHaveText('running');

// Wait for API response
const response = await page.waitForResponse(r => r.url().includes('/api/training'));
expect(response.status()).toBe(201);

// Wait for navigation
await expect(page).toHaveURL('/training/job-123');
```

## UI Instrumentation (data-testid)

### Required Test IDs
```html
<!-- App -->
<div data-testid="app-ready">

<!-- Characters -->
<button data-testid="new-character-btn">
<form data-testid="character-form">
<input data-testid="character-name-input">
<input data-testid="character-trigger-input">
<button data-testid="create-character-btn">
<div data-testid="character-card" data-character-id="...">
<button data-testid="delete-character-btn">

<!-- Training -->
<select data-testid="character-select">
<button data-testid="preset-quick">
<button data-testid="preset-balanced">
<button data-testid="preset-quality">
<button data-testid="start-training-btn">
<div data-testid="training-job-card" data-job-id="...">
<span data-testid="job-status">
<div data-testid="job-progress">
<div data-testid="training-logs">

<!-- Generation -->
<button data-testid="generate-btn">
<div data-testid="output-gallery">
```

## Local Stack Runner

### Script: `scripts/e2e-run.sh`
```bash
#!/bin/bash
set -e

# 1. Start services (docker-compose or direct)
# 2. Wait for health checks
# 3. Run Playwright tests
# 4. Collect artifacts
# 5. Generate report
# 6. Cleanup
```

### Commands
```bash
# Full E2E run
./scripts/e2e-run.sh

# Smoke tests only
./scripts/e2e-run.sh --smoke

# Headed mode (debug)
./scripts/e2e-run.sh --headed

# Specific test file
./scripts/e2e-run.sh --file flows/training.spec.ts

# Update baselines
./scripts/e2e-run.sh --update-snapshots
```

## Failure Report Format

### Per-Test Failure Report
```json
{
  "test": "Training Flow > should start training and observe progress",
  "file": "flows/training.spec.ts:45",
  "duration": 12340,
  "status": "failed",
  "error": {
    "message": "Expected element [data-testid='job-status'] to have text 'running', but got 'queued'",
    "selector": "[data-testid='job-status']",
    "expected": "running",
    "actual": "queued",
    "screenshot": "artifacts/screenshots/training-flow-failed-1.png",
    "trace": "artifacts/traces/training-flow-trace.zip"
  },
  "network": {
    "failedRequests": [],
    "status4xx5xx": [
      { "url": "/api/training", "status": 500, "body": "..." }
    ]
  },
  "console": {
    "errors": ["Uncaught TypeError: Cannot read property 'id' of undefined"],
    "warnings": []
  },
  "artifacts": {
    "video": "artifacts/videos/training-flow.webm",
    "screenshot": "artifacts/screenshots/training-flow-failed-1.png",
    "trace": "artifacts/traces/training-flow-trace.zip",
    "harLog": "artifacts/har/training-flow.har"
  }
}
```

### Summary Report
```
═══════════════════════════════════════════════════════════════
                    E2E TEST REPORT - Isengard
═══════════════════════════════════════════════════════════════

Run: 2025-01-15 14:32:00
Duration: 2m 34s
Browser: chromium-desktop

SUMMARY
───────
Total:  24
Passed: 22
Failed:  2
Skipped: 0

FAILURES
────────
1. [flows/training.spec.ts:45] Training Flow > should start training
   Error: Expected job status 'running', got 'queued'
   Screenshot: artifacts/screenshots/training-flow-1.png
   Trace: playwright show-trace artifacts/traces/training-flow.zip

2. [edge-cases/slow-api.spec.ts:23] Slow API > should show loading state
   Error: Timeout waiting for loading spinner
   Screenshot: artifacts/screenshots/slow-api-1.png

NETWORK ISSUES
──────────────
- POST /api/training returned 500 (2 times)
- GET /api/characters/123/images returned 404 (1 time)

CONSOLE ERRORS
──────────────
- TypeError: Cannot read property 'id' of undefined (training.tsx:234)

═══════════════════════════════════════════════════════════════
Full HTML report: playwright-report/index.html
═══════════════════════════════════════════════════════════════
```

## CI Integration

### GitHub Actions Workflow
```yaml
name: E2E Tests
on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - name: Install dependencies
        run: cd e2e && npm ci
      - name: Install Playwright
        run: cd e2e && npx playwright install --with-deps
      - name: Start services
        run: docker-compose up -d
      - name: Wait for services
        run: ./scripts/wait-for-services.sh
      - name: Run E2E tests
        run: cd e2e && npm test
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: e2e-artifacts
          path: e2e/artifacts/
```

## Implementation Sequence

### Phase 1: Foundation (Day 1)
1. Enhance playwright.config.ts
2. Create page object models structure
3. Create utility helpers
4. Add critical data-testid attributes to UI

### Phase 2: Core Tests (Day 2)
5. Implement smoke tests
6. Implement character flow tests
7. Implement training flow tests (critical path)

### Phase 3: Robustness (Day 3)
8. Implement edge case tests
9. Add visual regression baselines
10. Create failure report generator

### Phase 4: Integration (Day 4)
11. Create local stack runner script
12. Add GitHub Actions workflow
13. Document usage in README

## Success Criteria

1. **One Command**: `./scripts/e2e-run.sh` boots stack, runs tests, produces report
2. **Reliable**: Tests pass consistently (no flaky tests)
3. **Actionable**: Failures include screenshots, traces, network logs
4. **Fast**: Smoke suite < 30s, full suite < 5min
5. **Real Bugs**: Suite catches the actual user-facing issues (buttons not working, views not updating)

## Maintenance

- Review and update baselines quarterly
- Add tests for any new features
- Update page objects when UI changes
- Review flaky test logs weekly
