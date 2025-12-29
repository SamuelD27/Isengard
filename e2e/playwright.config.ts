import { defineConfig, devices } from '@playwright/test';
import path from 'path';

/**
 * Isengard E2E Test Configuration
 *
 * Production-grade configuration with:
 * - Multi-browser support (Chromium, Firefox, WebKit)
 * - Multiple viewports (desktop, laptop, mobile)
 * - Always-on artifact collection (traces, screenshots, videos)
 * - Proper timeouts and wait strategies
 * - CI/local environment support
 *
 * Commands:
 *   npm test                    # Run all tests headless
 *   npm run test:headed         # Run with visible browser
 *   npm run test:ui             # Interactive UI mode
 *   npm run test:smoke          # Quick smoke tests only
 *   npm run test:debug          # Debug mode with inspector
 *   npm run report              # Open HTML report
 *   npm run trace               # Open last trace file
 */

const isCI = !!process.env.CI;
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:3000';
const apiURL = process.env.E2E_API_URL || 'http://localhost:8000';

export default defineConfig({
  testDir: './tests',

  // Test organization
  fullyParallel: false, // Sequential for reliability
  forbidOnly: isCI,
  retries: isCI ? 2 : 1,
  workers: isCI ? 1 : 2,

  // Timeouts
  timeout: 60000,           // 60s per test
  expect: {
    timeout: 10000,         // 10s for assertions
  },

  // Reporter configuration
  reporter: [
    ['html', {
      outputFolder: 'playwright-report',
      open: 'never',
    }],
    ['list'],
    ['json', {
      outputFile: 'artifacts/reports/test-results.json',
    }],
    // Custom failure reporter
    ['./utils/failure-reporter.ts'],
  ],

  // Global settings
  use: {
    baseURL,

    // Always capture artifacts for debugging
    trace: 'on',
    screenshot: 'on',
    video: 'on',

    // Network capture
    // Capture HAR for network analysis

    // Timeouts
    actionTimeout: 5000,
    navigationTimeout: 30000,

    // Browser settings
    headless: !process.env.HEADED,
    launchOptions: {
      slowMo: process.env.SLOW_MO ? parseInt(process.env.SLOW_MO) : 0,
    },

    // Extra HTTP headers
    extraHTTPHeaders: {
      'X-E2E-Test': 'true',
    },

    // Ignore HTTPS errors in dev
    ignoreHTTPSErrors: true,
  },

  // Output directory for test artifacts
  outputDir: 'artifacts/test-results',

  // Browser projects
  // Note: Firefox and WebKit require: npx playwright install firefox webkit
  projects: [
    // Primary: Desktop Chrome (1920x1080)
    {
      name: 'chromium-desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
      testMatch: /.*\.spec\.ts/,
    },

    // Laptop viewport (1366x768)
    {
      name: 'chromium-laptop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1366, height: 768 },
      },
      testMatch: /.*\.spec\.ts/,
      testIgnore: /visual/,  // Skip visual tests for alternate viewports
    },

    // Mobile viewport using Chromium (not WebKit/iPhone)
    {
      name: 'chromium-mobile',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },  // iPhone 14 Pro dimensions
        isMobile: true,
        hasTouch: true,
      },
      testMatch: '**/smoke/*.spec.ts',  // Only smoke tests on mobile
    },

    // Firefox (optional - only if installed)
    // Run with: npx playwright test --project=firefox-desktop
    // {
    //   name: 'firefox-desktop',
    //   use: {
    //     ...devices['Desktop Firefox'],
    //     viewport: { width: 1920, height: 1080 },
    //   },
    //   testMatch: '**/smoke/*.spec.ts',
    // },

    // WebKit/Safari (optional - only if installed)
    // Run with: npx playwright test --project=webkit-desktop
    // {
    //   name: 'webkit-desktop',
    //   use: {
    //     ...devices['Desktop Safari'],
    //     viewport: { width: 1920, height: 1080 },
    //   },
    //   testMatch: '**/smoke/*.spec.ts',
    // },
  ],

  // Web server management
  webServer: process.env.E2E_SKIP_SERVER ? undefined : [
    // API server health check
    {
      command: 'echo "API server should be running"',
      url: `${apiURL}/health`,
      reuseExistingServer: true,
      timeout: 30000,
    },
    // Frontend dev server (if not already running)
    {
      command: 'cd ../apps/web && npm run dev -- --host --port 3000',
      url: baseURL,
      reuseExistingServer: true,
      timeout: 60000,
      env: {
        VITE_API_URL: apiURL,
      },
    },
  ],

  // Global setup/teardown
  globalSetup: './fixtures/global-setup.ts',
  globalTeardown: './fixtures/global-teardown.ts',

  // Snapshot settings for visual testing
  snapshotPathTemplate: '{testDir}/baselines/{projectName}/{testFilePath}/{arg}{ext}',
  expect: {
    timeout: 10000,
    toMatchSnapshot: {
      maxDiffPixels: 100,
      maxDiffPixelRatio: 0.01,
    },
  },
});
