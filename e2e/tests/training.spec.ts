import { test, expect } from '@playwright/test';

/**
 * Training E2E Tests (LEGACY)
 *
 * NOTE: This file is deprecated. Use training-gui.spec.ts instead.
 * These tests use the old page structure before the 3-level navigation was added.
 *
 * The new structure is:
 * - /training → Training History (completed jobs)
 * - /training/start → Start Training (configuration)
 * - /training/ongoing → Ongoing Training (running jobs)
 *
 * @deprecated Use training-gui.spec.ts instead
 */

test.describe.skip('Training Page (Legacy)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/training');
    await page.waitForLoadState('networkidle');
  });

  test('should display training page', async ({ page }) => {
    // Check for training page elements
    await expect(page.locator('text=Training')).toBeVisible();
  });

  test('should show character selector', async ({ page }) => {
    // Training page should have a character selection dropdown
    await expect(page.locator('text=Select Character').or(page.locator('[data-testid="character-select"]'))).toBeVisible({ timeout: 5000 });
  });

  test('should show training presets', async ({ page }) => {
    // Check for preset options (Quick, Balanced, High Quality)
    await expect(
      page.locator('text=Quick').or(page.locator('text=Balanced')).or(page.locator('text=High Quality'))
    ).toBeVisible({ timeout: 5000 });
  });

  test('should disable start button without character', async ({ page }) => {
    // Start button should be disabled if no character is selected
    const startButton = page.locator('button:has-text("Start Training")');
    if (await startButton.isVisible()) {
      await expect(startButton).toBeDisabled();
    }
  });

  test('should show training job history', async ({ page }) => {
    // Check for job history section
    await expect(
      page.locator('text=Job History').or(page.locator('text=Recent Jobs'))
    ).toBeVisible({ timeout: 5000 });
  });
});

test.describe.skip('Training API Integration (Legacy)', () => {
  test('should fetch training jobs from API', async ({ page }) => {
    let apiCalled = false;

    page.on('request', (request) => {
      if (request.url().includes('/api/training') && request.method() === 'GET') {
        apiCalled = true;
      }
    });

    await page.goto('/training');
    await page.waitForLoadState('networkidle');

    expect(apiCalled).toBe(true);
  });

  test('should handle training job list response', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/training') &&
        response.request().method() === 'GET'
    );

    await page.goto('/training');
    const response = await responsePromise;

    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
  });
});
