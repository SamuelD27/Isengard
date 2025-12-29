/**
 * Visual Regression Tests
 *
 * Captures baseline screenshots for key pages and compares against future runs.
 * Uses Playwright's built-in snapshot comparison with configurable thresholds.
 *
 * Commands:
 *   npx playwright test tests/visual --project=chromium-desktop
 *   npx playwright test tests/visual --update-snapshots    # Update baselines
 *
 * Baseline images are stored in: e2e/tests/baselines/{projectName}/
 *
 * @tag visual
 */

import { test, expect } from '../../fixtures/test-fixtures';

// Helper to wait for page to stabilize before screenshot
async function waitForStableUI(page: import('@playwright/test').Page) {
  // Wait for network idle
  await page.waitForLoadState('networkidle');
  // Wait for animations to settle
  await page.waitForTimeout(500);
  // Wait for fonts to load
  await page.evaluate(() => document.fonts.ready);
}

test.describe('Visual Regression: Core Pages @visual', () => {
  test.beforeEach(async ({ page }) => {
    // Set a consistent viewport for visual tests
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  test('Characters page - empty state', async ({ page }) => {
    await page.goto('/characters');
    await waitForStableUI(page);

    // Mask dynamic content (timestamps, etc.)
    await expect(page).toHaveScreenshot('characters-page.png', {
      mask: [
        page.locator('[data-testid="timestamp"]'),
        page.locator('.animate-pulse'), // Loading skeletons
      ],
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Training History page', async ({ page }) => {
    await page.goto('/training');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('training-history.png', {
      mask: [
        page.locator('[data-testid="timestamp"]'),
        page.locator('.animate-pulse'),
      ],
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Start Training page', async ({ page }) => {
    await page.goto('/training/start');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('training-start.png', {
      mask: [
        page.locator('[data-testid="timestamp"]'),
        page.locator('.animate-pulse'),
      ],
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Ongoing Training page', async ({ page }) => {
    await page.goto('/training/ongoing');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('training-ongoing.png', {
      mask: [
        page.locator('[data-testid="timestamp"]'),
        page.locator('.animate-pulse'),
      ],
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Generation page', async ({ page }) => {
    await page.goto('/generate');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('generation-page.png', {
      mask: [
        page.locator('[data-testid="timestamp"]'),
        page.locator('.animate-pulse'),
      ],
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Dataset page', async ({ page }) => {
    await page.goto('/dataset');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('dataset-page.png', {
      mask: [
        page.locator('[data-testid="timestamp"]'),
        page.locator('.animate-pulse'),
      ],
      maxDiffPixelRatio: 0.02,
    });
  });
});

test.describe('Visual Regression: Training Presets @visual', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/training/start');
    await waitForStableUI(page);
  });

  test('Quick Train preset selected', async ({ page }) => {
    await page.locator('button:has-text("Quick Train")').click();
    await page.waitForTimeout(300); // Wait for selection animation

    // Full page screenshot showing preset selection state
    await expect(page).toHaveScreenshot('preset-quick-selected.png', {
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Balanced preset selected', async ({ page }) => {
    // Balanced is selected by default, just verify
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('preset-balanced-selected.png', {
      maxDiffPixelRatio: 0.02,
    });
  });

  test('High Quality preset selected', async ({ page }) => {
    await page.locator('button:has-text("High Quality")').click();
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('preset-quality-selected.png', {
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Advanced Settings expanded', async ({ page }) => {
    await page.locator('button:has-text("Advanced Settings")').click();
    await page.waitForTimeout(300);

    // Screenshot the page with advanced settings expanded
    await expect(page).toHaveScreenshot('advanced-settings-expanded.png', {
      mask: [
        page.locator('[data-testid="timestamp"]'),
      ],
      maxDiffPixelRatio: 0.02,
    });
  });
});

test.describe('Visual Regression: Component States @visual', () => {
  test('Empty state - no characters', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });

    // Mock empty API response
    await page.route('**/api/characters', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/characters');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('empty-state-characters.png', {
      maxDiffPixelRatio: 0.02,
    });

    await page.unroute('**/api/characters');
  });

  test('Empty state - no training jobs', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });

    // Mock empty API response
    await page.route('**/api/training/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/training');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('empty-state-training.png', {
      maxDiffPixelRatio: 0.02,
    });

    await page.unroute('**/api/training/**');
  });

  test('Error state - API failure', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });

    // Mock API error
    await page.route('**/api/characters', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal server error' }),
      });
    });

    await page.goto('/characters');
    await waitForStableUI(page);

    // Just verify the page renders (error state may vary)
    await expect(page.locator('body')).toBeVisible();

    await page.unroute('**/api/characters');
  });
});

test.describe('Visual Regression: Responsive @visual', () => {
  test('Training page - laptop viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto('/training/start');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('training-laptop.png', {
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Training page - tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/training/start');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('training-tablet.png', {
      maxDiffPixelRatio: 0.02,
    });
  });

  test('Training page - mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/training/start');
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot('training-mobile.png', {
      maxDiffPixelRatio: 0.02,
    });
  });
});
