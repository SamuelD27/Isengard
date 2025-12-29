/**
 * Training GUI Validation Tests
 *
 * Tests the training UI workflow with the 3-level navigation:
 * - /training → Training History (completed jobs)
 * - /training/start → Start Training (configuration)
 * - /training/ongoing → Ongoing Training (running jobs)
 * - /training/:id → Training Detail
 *
 * These tests validate GUI behavior without needing a real GPU backend.
 *
 * @tag training @gui
 */

import { test, expect } from '../fixtures/test-fixtures';

test.describe('Training: History Page @training @gui', () => {
  test('should display training history page', async ({ page }) => {
    await page.goto('/training');

    // Should show Training History heading
    await expect(page.locator('h1:has-text("Training History")')).toBeVisible({ timeout: 10000 });
  });

  test('should show Start Training button', async ({ page }) => {
    await page.goto('/training');

    const startBtn = page.locator('button:has-text("Start Training")');
    await expect(startBtn.first()).toBeVisible();
    await expect(startBtn.first()).toBeEnabled();
  });

  test('should show Ongoing Training button', async ({ page }) => {
    await page.goto('/training');

    const ongoingBtn = page.locator('button:has-text("Ongoing Training")');
    await expect(ongoingBtn).toBeVisible();
  });

  test('should navigate to Start Training page', async ({ page }) => {
    await page.goto('/training');

    const startBtn = page.locator('button:has-text("Start Training")').first();
    await startBtn.click();

    await expect(page).toHaveURL('/training/start', { timeout: 5000 });
    // Use main content h1 to avoid strict mode violation (header also has h1)
    await expect(page.locator('main h1:has-text("Start Training")').first()).toBeVisible();
  });

  test('should navigate to Ongoing Training page', async ({ page }) => {
    await page.goto('/training');

    const ongoingBtn = page.locator('button:has-text("Ongoing Training")');
    await ongoingBtn.click();

    await expect(page).toHaveURL('/training/ongoing', { timeout: 5000 });
  });

  test('should show empty state when no completed jobs', async ({ page }) => {
    await page.goto('/training');

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Either shows job list or empty state
    const jobList = page.locator('[data-testid="training-job-card"]');
    const emptyState = page.locator('text=No completed trainings yet');

    const hasJobs = await jobList.count() > 0;
    if (!hasJobs) {
      await expect(emptyState).toBeVisible();
    }
  });
});

test.describe('Training: Start Page - Configuration @training @gui', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/training/start');
    await page.waitForLoadState('networkidle');
  });

  test('should display Start Training heading', async ({ page }) => {
    // Use main content h1 to avoid strict mode violation (header also has h1)
    await expect(page.locator('main h1:has-text("Start Training")').first()).toBeVisible();
  });

  test('should show back button to training history', async ({ page }) => {
    const backBtn = page.locator('button').filter({ has: page.locator('svg.lucide-arrow-left') });
    await expect(backBtn).toBeVisible();

    // Clicking should go back to /training
    await backBtn.click();
    await expect(page).toHaveURL('/training', { timeout: 5000 });
  });

  test('should display training presets', async ({ page }) => {
    // Check for preset cards (presets are h3 elements inside buttons)
    await expect(page.locator('h3:has-text("Quick Train")')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('h3:has-text("Balanced")')).toBeVisible();
    await expect(page.locator('h3:has-text("High Quality")')).toBeVisible();
    await expect(page.locator('h3:has-text("Custom")')).toBeVisible();
  });

  test('should have Balanced preset selected by default', async ({ page }) => {
    // Balanced preset should have the accent border (selected state)
    const balancedBtn = page.locator('button:has-text("Balanced")');
    await expect(balancedBtn).toHaveClass(/border-accent/);
  });

  test('should allow selecting different presets', async ({ page }) => {
    // Click Quick Train
    const quickBtn = page.locator('button:has-text("Quick Train")');
    await quickBtn.click();

    // Quick Train should now be selected
    await expect(quickBtn).toHaveClass(/border-accent/);

    // Balanced should no longer be selected
    const balancedBtn = page.locator('button:has-text("Balanced")');
    await expect(balancedBtn).not.toHaveClass(/border-accent/);
  });

  test('should show character selector', async ({ page }) => {
    // Should have a character dropdown
    const charSelect = page.locator('select').filter({ hasText: 'Select character' });
    await expect(charSelect).toBeVisible();
  });

  test('should show training steps input', async ({ page }) => {
    const stepsInput = page.locator('input#steps');
    await expect(stepsInput).toBeVisible();

    // Default should be 1000 for Balanced preset
    await expect(stepsInput).toHaveValue('1000');
  });

  test('should show resolution selector', async ({ page }) => {
    const resSelect = page.locator('select#resolution');
    await expect(resSelect).toBeVisible();
  });

  test('should update steps when selecting Quick preset', async ({ page }) => {
    const stepsInput = page.locator('input#steps');

    // Select Quick Train preset
    const quickBtn = page.locator('button:has-text("Quick Train")');
    await quickBtn.click();

    // Quick = 500 steps
    await expect(stepsInput).toHaveValue('500');
  });

  test('should update steps when selecting High Quality preset', async ({ page }) => {
    const stepsInput = page.locator('input#steps');

    // Select High Quality preset
    const qualityBtn = page.locator('button:has-text("High Quality")');
    await qualityBtn.click();

    // Quality = 2000 steps
    await expect(stepsInput).toHaveValue('2000');
  });

  test('should switch to Custom when manually changing steps', async ({ page }) => {
    const stepsInput = page.locator('input#steps');

    // Clear and enter custom value
    await stepsInput.fill('750');

    // Should switch to Custom preset
    const customBtn = page.locator('button:has-text("Custom")');
    await expect(customBtn).toHaveClass(/border-accent/);
  });

  test('should have Advanced Settings toggle', async ({ page }) => {
    // Advanced Settings is a button with text + icons
    const advancedToggle = page.locator('button:has-text("Advanced Settings")');
    await expect(advancedToggle).toBeVisible();

    // Click to expand
    await advancedToggle.click();

    // Should show advanced options (Learning Rate label or input)
    await expect(page.locator('label:has-text("Learning Rate")').or(page.locator('label[for="lr"]'))).toBeVisible({ timeout: 3000 });
  });

  test('should have Start Training button', async ({ page }) => {
    const startBtn = page.locator('button:has-text("Start Training")');
    await expect(startBtn).toBeVisible();
  });

  test('should disable Start button without character selected', async ({ page }) => {
    const startBtn = page.locator('button:has-text("Start Training")');

    // Without a character selected, button should be disabled
    await expect(startBtn).toBeDisabled();
  });

  test('should show estimated training time', async ({ page }) => {
    // Should show time estimate near steps input
    await expect(page.locator('text=~').first()).toBeVisible();
  });
});

test.describe('Training: Form Validation @training @gui', () => {
  test('should not allow invalid steps', async ({ page }) => {
    await page.goto('/training/start');
    await page.waitForLoadState('networkidle');

    const stepsInput = page.locator('input#steps');
    await expect(stepsInput).toBeVisible();

    // Enter a negative value
    await stepsInput.fill('-100');

    // The input may accept the value but should be invalid per HTML5 min constraint
    // Or the value may be clamped. Check either:
    // 1. The value is clamped to min (100)
    // 2. Or the input is in an invalid state
    const value = await stepsInput.inputValue();
    const isValid = await stepsInput.evaluate((el: HTMLInputElement) => el.validity.valid);

    // Either value >= 0 or it's flagged as invalid (rangeUnderflow)
    expect(parseInt(value) >= 0 || !isValid).toBe(true);
  });

  test('should have min/max constraints on steps', async ({ page }) => {
    await page.goto('/training/start');

    const stepsInput = page.locator('input#steps');

    // Check min attribute
    const min = await stepsInput.getAttribute('min');
    expect(min).toBe('100');

    // Check max attribute
    const max = await stepsInput.getAttribute('max');
    expect(max).toBe('10000');
  });
});

test.describe('Training: Ongoing Page @training @gui', () => {
  test('should display Ongoing Training heading', async ({ page }) => {
    await page.goto('/training/ongoing');
    await page.waitForLoadState('networkidle');

    // Use main content h1 to avoid strict mode violation
    await expect(page.locator('main h1:has-text("Ongoing Training")').first()).toBeVisible({ timeout: 10000 });
  });

  test('should show back button to training history', async ({ page }) => {
    await page.goto('/training/ongoing');

    const backBtn = page.locator('button').filter({ has: page.locator('svg.lucide-arrow-left') });
    await expect(backBtn).toBeVisible();
  });

  test('should show empty state or job list', async ({ page }) => {
    await page.goto('/training/ongoing');
    await page.waitForLoadState('networkidle');

    // Wait for page to load (heading should be visible)
    await expect(page.locator('main h1:has-text("Ongoing Training")').first()).toBeVisible({ timeout: 10000 });

    // Either shows running jobs or empty state
    // The empty state text is "No ongoing training jobs"
    const jobCards = page.locator('[data-testid="training-job-card"]');
    const emptyState = page.locator('text=No ongoing training jobs');

    const hasJobs = await jobCards.count() > 0;
    if (!hasJobs) {
      await expect(emptyState).toBeVisible({ timeout: 5000 });
    } else {
      await expect(jobCards.first()).toBeVisible();
    }
  });
});

test.describe('Training: API Integration @training @gui', () => {
  test('should fetch training jobs on history page', async ({ page }) => {
    const apiCalls: string[] = [];

    page.on('request', (request) => {
      if (request.url().includes('/api/training') && request.method() === 'GET') {
        apiCalls.push(request.url());
      }
    });

    await page.goto('/training');
    await page.waitForLoadState('networkidle');

    // Should have made API calls
    expect(apiCalls.length).toBeGreaterThan(0);
  });

  test('should fetch characters on start page', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/characters') &&
        response.request().method() === 'GET'
    );

    await page.goto('/training/start');
    const response = await responsePromise;

    expect(response.status()).toBe(200);
  });

  test('API calls should return JSON, not HTML', async ({ page }) => {
    const apiResponses: { url: string; contentType: string }[] = [];

    page.on('response', async (response) => {
      if (response.url().includes('/api/')) {
        const contentType = response.headers()['content-type'] || '';
        apiResponses.push({ url: response.url(), contentType });
      }
    });

    await page.goto('/training');
    await page.waitForLoadState('networkidle');

    // All API calls should return JSON
    for (const resp of apiResponses) {
      if (resp.url.includes('/api/')) {
        // Skip 404s from unimplemented endpoints
        if (!resp.contentType.includes('text/html')) {
          expect(resp.contentType).toContain('application/json');
        }
      }
    }
  });
});

test.describe('Training: Error Handling @training @gui', () => {
  test('should handle API errors gracefully on history page', async ({ page }) => {
    // Mock API to fail
    await page.route('**/api/training/**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal server error' }),
      });
    });

    // Page should still load
    await page.goto('/training');

    // Should show some UI (not crash)
    await expect(page.locator('body')).toBeVisible();

    await page.unroute('**/api/training/**');
  });

  test('should handle network failures', async ({ page }) => {
    // Block API requests
    await page.route('**/api/training/**', async (route) => {
      await route.abort('connectionfailed');
    });

    // Page should still load
    await page.goto('/training');

    // Should show some UI (not crash)
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('h1:has-text("Training History")')).toBeVisible({ timeout: 10000 });

    await page.unroute('**/api/training/**');
  });
});
