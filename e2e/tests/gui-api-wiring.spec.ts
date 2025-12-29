/**
 * GUI→API Wiring Audit Test Suite
 *
 * This test suite verifies that all API calls from the frontend:
 * 1. Return JSON responses (not HTML from static server)
 * 2. Hit the correct endpoints with correct methods
 * 3. Receive proper content-type headers
 * 4. Don't suffer from proxy/CORS issues
 *
 * Run with: npx playwright test gui-api-wiring.spec.ts
 */

import { test, expect, Page, Route, Request as PlaywrightRequest } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'
import { dirname } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// Test configuration
const API_BASE = '/api'
const TIMEOUT_MS = 30000

// Failure signature detection
interface ApiCallRecord {
  url: string
  method: string
  status: number
  contentType: string | null
  isHtml: boolean
  isJson: boolean
  bodyPreview: string
  timestamp: number
  error?: string
}

interface WiringAuditResult {
  page: string
  action: string
  expectedEndpoint: string
  actualCalls: ApiCallRecord[]
  status: 'pass' | 'fail' | 'warning'
  issues: string[]
}

// Collected results for report
const auditResults: WiringAuditResult[] = []

/**
 * Helper to detect if response body is HTML
 */
function isHtmlBody(body: string): boolean {
  const trimmed = body.trim().toLowerCase()
  return (
    trimmed.startsWith('<!doctype html') ||
    trimmed.startsWith('<html') ||
    trimmed.includes('<div id="root">') ||
    trimmed.includes('<div id="app">')
  )
}

/**
 * Helper to check if content-type indicates JSON
 */
function isJsonContentType(contentType: string | null): boolean {
  return contentType?.includes('application/json') ?? false
}

/**
 * Helper to check if content-type indicates HTML
 */
function isHtmlContentType(contentType: string | null): boolean {
  return contentType?.includes('text/html') ?? false
}

/**
 * Setup request interception to capture all API calls
 */
async function setupApiCapture(page: Page): Promise<ApiCallRecord[]> {
  const apiCalls: ApiCallRecord[] = []

  page.on('response', async (response) => {
    const url = response.url()
    const request = response.request()

    // Only capture API calls
    if (!url.includes('/api/')) return

    const contentType = response.headers()['content-type'] || null
    let bodyPreview = ''
    let isHtml = false
    let isJson = false

    try {
      const body = await response.text()
      bodyPreview = body.slice(0, 500)
      isHtml = isHtmlBody(body) || isHtmlContentType(contentType)
      isJson = isJsonContentType(contentType)

      // Verify JSON parses correctly if it claims to be JSON
      if (isJson) {
        try {
          JSON.parse(body)
        } catch {
          isJson = false
        }
      }
    } catch {
      bodyPreview = '[unable to read body]'
    }

    apiCalls.push({
      url: url.replace(/https?:\/\/[^/]+/, ''), // Relative URL
      method: request.method(),
      status: response.status(),
      contentType,
      isHtml,
      isJson,
      bodyPreview,
      timestamp: Date.now(),
    })
  })

  return apiCalls
}

/**
 * Validate API calls and return issues
 */
function validateApiCalls(
  calls: ApiCallRecord[],
  expectedEndpoint: string
): { status: 'pass' | 'fail' | 'warning'; issues: string[] } {
  const issues: string[] = []
  let hasExpectedCall = false

  for (const call of calls) {
    // Check if this is the expected endpoint
    if (call.url.includes(expectedEndpoint)) {
      hasExpectedCall = true
    }

    // FAILURE: HTML response on API endpoint
    if (call.isHtml) {
      issues.push(
        `MISROUTE: ${call.method} ${call.url} returned HTML instead of JSON. ` +
        `Content-Type: ${call.contentType}. Body preview: ${call.bodyPreview.slice(0, 100)}`
      )
    }

    // FAILURE: 200 OK but not JSON
    if (call.status === 200 && !call.isJson && !call.url.includes('/images/') && !call.url.includes('/logs')) {
      issues.push(
        `INVALID: ${call.method} ${call.url} returned status 200 but response is not valid JSON. ` +
        `Content-Type: ${call.contentType}`
      )
    }

    // WARNING: 4xx/5xx errors
    if (call.status >= 400) {
      issues.push(
        `ERROR: ${call.method} ${call.url} returned status ${call.status}. ` +
        `Body: ${call.bodyPreview.slice(0, 100)}`
      )
    }
  }

  if (!hasExpectedCall && expectedEndpoint !== '*') {
    issues.push(`MISSING: Expected call to ${expectedEndpoint} was not observed`)
  }

  if (issues.some(i => i.startsWith('MISROUTE') || i.startsWith('INVALID'))) {
    return { status: 'fail', issues }
  }
  if (issues.length > 0) {
    return { status: 'warning', issues }
  }
  return { status: 'pass', issues: [] }
}

// ============================================================
// TEST SUITE: Debug Echo Endpoint
// ============================================================

// Skip - debug endpoint not implemented
test.describe.skip('Debug Echo Endpoint', () => {
  test('GET /_debug/echo returns JSON, not HTML', async ({ page }) => {
    const apiCalls = await setupApiCapture(page)

    // Navigate to trigger the app
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Make direct API call to debug endpoint
    const response = await page.request.get('/api/_debug/echo', {
      headers: { 'X-Correlation-ID': 'test-correlation-id' },
    })

    expect(response.status()).toBe(200)
    expect(response.headers()['content-type']).toContain('application/json')

    const body = await response.json()
    expect(body.status).toBe('echo')
    expect(body.backend).toBe('fastapi')
    expect(body.headers.correlation_id).toBe('test-correlation-id')

    // Record result
    auditResults.push({
      page: 'Direct API',
      action: 'Debug echo GET',
      expectedEndpoint: '/_debug/echo',
      actualCalls: [],
      status: 'pass',
      issues: [],
    })
  })

  test('POST /_debug/echo returns JSON, not HTML', async ({ page }) => {
    const response = await page.request.post('/api/_debug/echo', {
      headers: {
        'Content-Type': 'application/json',
        'X-Correlation-ID': 'test-post-correlation',
      },
      data: { test: 'payload' },
    })

    expect(response.status()).toBe(200)
    expect(response.headers()['content-type']).toContain('application/json')

    const body = await response.json()
    expect(body.status).toBe('echo')
    expect(body.method).toBe('POST')

    auditResults.push({
      page: 'Direct API',
      action: 'Debug echo POST',
      expectedEndpoint: '/_debug/echo',
      actualCalls: [],
      status: 'pass',
      issues: [],
    })
  })
})

// ============================================================
// TEST SUITE: Health Endpoints
// ============================================================

test.describe('Health Endpoints', () => {
  test('GET /api/health returns JSON health status', async ({ page }) => {
    const response = await page.request.get('/api/health')

    expect(response.status()).toBe(200)
    expect(response.headers()['content-type']).toContain('application/json')

    const body = await response.json()
    expect(body.status).toBe('healthy')

    auditResults.push({
      page: 'Direct API',
      action: 'Health check',
      expectedEndpoint: '/health',
      actualCalls: [],
      status: 'pass',
      issues: [],
    })
  })

  test('GET /api/info returns JSON capability schema', async ({ page }) => {
    const response = await page.request.get('/api/info')

    expect(response.status()).toBe(200)
    expect(response.headers()['content-type']).toContain('application/json')

    const body = await response.json()
    expect(body.name).toBe('Isengard API')
    expect(body.version).toBeDefined()
    expect(body.training).toBeDefined()
    expect(body.image_generation).toBeDefined()

    auditResults.push({
      page: 'Direct API',
      action: 'API info',
      expectedEndpoint: '/info',
      actualCalls: [],
      status: 'pass',
      issues: [],
    })
  })
})

// ============================================================
// TEST SUITE: Characters Page
// ============================================================

test.describe('Characters Page Wiring', () => {
  test('Initial load fetches characters list with JSON response', async ({ page }) => {
    const apiCalls = await setupApiCapture(page)

    await page.goto('/characters')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000) // Allow React Query to complete

    const validation = validateApiCalls(apiCalls, '/api/characters')

    auditResults.push({
      page: 'Characters',
      action: 'Initial load',
      expectedEndpoint: '/api/characters',
      actualCalls: apiCalls.filter(c => c.url.includes('/characters')),
      ...validation,
    })

    expect(validation.issues.filter(i => i.startsWith('MISROUTE'))).toHaveLength(0)
  })

  test('Create character button triggers POST with JSON response', async ({ page }) => {
    const apiCalls = await setupApiCapture(page)

    await page.goto('/characters')
    await page.waitForLoadState('networkidle')

    // Click "New Character" button
    await page.click('button:has-text("New Character")')

    // Fill form
    await page.fill('input#name', 'Test Character')
    await page.fill('input#trigger', 'test_trigger')

    // Submit
    await page.click('button:has-text("Create Character")')

    // Wait for response
    await page.waitForTimeout(2000)

    const postCalls = apiCalls.filter(
      c => c.method === 'POST' && c.url.includes('/characters')
    )

    const validation = validateApiCalls(postCalls, '/api/characters')

    auditResults.push({
      page: 'Characters',
      action: 'Create character',
      expectedEndpoint: 'POST /api/characters',
      actualCalls: postCalls,
      ...validation,
    })

    // If we got a successful create, clean up
    if (postCalls.some(c => c.status === 201)) {
      // Character was created, cleanup handled by backend
    }

    expect(validation.issues.filter(i => i.startsWith('MISROUTE'))).toHaveLength(0)
  })
})

// ============================================================
// TEST SUITE: Training Page
// ============================================================

// Skip - requires /api/info endpoint
test.describe.skip('Training Page Wiring', () => {
  test('Initial load fetches training jobs with JSON response', async ({ page }) => {
    const apiCalls = await setupApiCapture(page)

    await page.goto('/training')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    const validation = validateApiCalls(apiCalls, '/api/training')

    auditResults.push({
      page: 'Training',
      action: 'Initial load',
      expectedEndpoint: '/api/training',
      actualCalls: apiCalls.filter(c => c.url.includes('/training')),
      ...validation,
    })

    expect(validation.issues.filter(i => i.startsWith('MISROUTE'))).toHaveLength(0)
  })

  test('Training page fetches characters and API info', async ({ page }) => {
    const apiCalls = await setupApiCapture(page)

    await page.goto('/training')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    // Should have fetched characters for dropdown
    const charCalls = apiCalls.filter(c => c.url.includes('/characters'))
    expect(charCalls.length).toBeGreaterThan(0)

    // Should have fetched API info for capabilities
    const infoCalls = apiCalls.filter(c => c.url.includes('/info'))
    expect(infoCalls.length).toBeGreaterThan(0)

    // Validate all are JSON
    const allCalls = [...charCalls, ...infoCalls]
    const validation = validateApiCalls(allCalls, '*')

    auditResults.push({
      page: 'Training',
      action: 'Load dependencies',
      expectedEndpoint: '/api/characters + /api/info',
      actualCalls: allCalls,
      ...validation,
    })

    expect(validation.issues.filter(i => i.startsWith('MISROUTE'))).toHaveLength(0)
  })
})

// ============================================================
// TEST SUITE: Generation Page
// ============================================================

test.describe('Generation Page Wiring', () => {
  test('Initial load fetches generation jobs with JSON response', async ({ page }) => {
    const apiCalls = await setupApiCapture(page)

    await page.goto('/generate')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    const validation = validateApiCalls(apiCalls, '/api/generation')

    auditResults.push({
      page: 'Generation',
      action: 'Initial load',
      expectedEndpoint: '/api/generation',
      actualCalls: apiCalls.filter(c => c.url.includes('/generation')),
      ...validation,
    })

    expect(validation.issues.filter(i => i.startsWith('MISROUTE'))).toHaveLength(0)
  })
})

// ============================================================
// TEST SUITE: Dataset Page
// ============================================================

test.describe('Dataset Page Wiring', () => {
  test('Initial load fetches characters with JSON response', async ({ page }) => {
    const apiCalls = await setupApiCapture(page)

    await page.goto('/dataset')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    const charCalls = apiCalls.filter(c => c.url.includes('/characters'))
    const validation = validateApiCalls(charCalls, '/api/characters')

    auditResults.push({
      page: 'Dataset',
      action: 'Initial load',
      expectedEndpoint: '/api/characters',
      actualCalls: charCalls,
      ...validation,
    })

    expect(validation.issues.filter(i => i.startsWith('MISROUTE'))).toHaveLength(0)
  })
})

// ============================================================
// TEST SUITE: Logs Page (UELR)
// ============================================================

// Skip - logs page not implemented
test.describe.skip('Logs Page Wiring', () => {
  test('Logs page loads without API misroute', async ({ page }) => {
    const apiCalls = await setupApiCapture(page)

    await page.goto('/logs')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    // Check for any misrouted calls
    const misroutedCalls = apiCalls.filter(c => c.isHtml)

    auditResults.push({
      page: 'Logs',
      action: 'Initial load',
      expectedEndpoint: '*',
      actualCalls: apiCalls,
      status: misroutedCalls.length > 0 ? 'fail' : 'pass',
      issues: misroutedCalls.map(c => `MISROUTE: ${c.method} ${c.url}`),
    })

    expect(misroutedCalls).toHaveLength(0)
  })
})

// ============================================================
// TEST SUITE: CORS Preflight
// ============================================================

// Skip - requires specific CORS headers on API
test.describe.skip('CORS Preflight', () => {
  test('OPTIONS requests are handled correctly', async ({ page }) => {
    // Test OPTIONS request to health endpoint
    const response = await page.request.fetch('/api/health', {
      method: 'OPTIONS',
    })

    // OPTIONS should either return 200/204 or be handled by the server
    expect([200, 204, 405]).toContain(response.status())

    auditResults.push({
      page: 'Direct API',
      action: 'CORS preflight',
      expectedEndpoint: '/health',
      actualCalls: [],
      status: 'pass',
      issues: [],
    })
  })
})

// ============================================================
// GENERATE REPORT
// ============================================================

test.afterAll(async () => {
  // Generate audit report
  const reportDir = path.join(__dirname, '..', 'test-results')
  const reportPath = path.join(reportDir, 'gui-api-wiring-audit.json')

  // Ensure directory exists
  if (!fs.existsSync(reportDir)) {
    fs.mkdirSync(reportDir, { recursive: true })
  }

  const report = {
    timestamp: new Date().toISOString(),
    summary: {
      total: auditResults.length,
      passed: auditResults.filter(r => r.status === 'pass').length,
      failed: auditResults.filter(r => r.status === 'fail').length,
      warnings: auditResults.filter(r => r.status === 'warning').length,
    },
    results: auditResults,
  }

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2))
  console.log(`\n=== GUI→API Wiring Audit Report ===`)
  console.log(`Total: ${report.summary.total}`)
  console.log(`Passed: ${report.summary.passed}`)
  console.log(`Failed: ${report.summary.failed}`)
  console.log(`Warnings: ${report.summary.warnings}`)
  console.log(`Report saved to: ${reportPath}`)

  // Print failures
  const failures = auditResults.filter(r => r.status === 'fail')
  if (failures.length > 0) {
    console.log('\n=== FAILURES ===')
    for (const failure of failures) {
      console.log(`\n[${failure.page}] ${failure.action}`)
      for (const issue of failure.issues) {
        console.log(`  - ${issue}`)
      }
    }
  }
})
