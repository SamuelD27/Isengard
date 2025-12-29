/**
 * Visual Regression Tests
 *
 * Screenshot-based tests for key UI states.
 * Baselines are stored in e2e/baselines/ and committed to git.
 *
 * @tag visual
 */

import { test, expect } from '../../fixtures/test-fixtures';

// Mask dynamic content to avoid false positives
const dynamicMasks = [
  // Timestamps
  '[data-testid="timestamp"]',
  '.timestamp',
  'time',
  // IDs
  '[data-testid="job-id"]',
  '.job-id',
  // Progress bars (constantly changing)
  '[role="progressbar"]',
  '.animate-spin',
  // Random images
  'img[src*="random"]',
];

test.describe('Visual: Characters Page @visual', () => {
  test('should match characters page empty state', async ({
    page,
    charactersPage,
  }) => {
    // Mock empty character list
    await page.route('**/api/characters', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await charactersPage.goto();
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot('characters-empty.png', {
      mask: dynamicMasks.map((s) => page.locator(s)),
      fullPage: true,
    });
  });

  test('should match characters page with items', async ({
    page,
    charactersPage,
  }) => {
    // Mock character list with sample data
    await page.route('**/api/characters', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'char-1',
            name: 'Alice',
            trigger_word: 'alice_char',
            description: 'Test character',
            image_count: 5,
          },
          {
            id: 'char-2',
            name: 'Bob',
            trigger_word: 'bob_char',
            description: 'Another test',
            image_count: 3,
          },
        ]),
      });
    });

    await charactersPage.goto();
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot('characters-with-items.png', {
      mask: dynamicMasks.map((s) => page.locator(s)),
      fullPage: true,
    });
  });

  test('should match character form', async ({ page, charactersPage }) => {
    await page.route('**/api/characters', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await charactersPage.goto();
    await charactersPage.clickNewCharacter();
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('character-form.png', {
      mask: dynamicMasks.map((s) => page.locator(s)),
      fullPage: true,
    });
  });
});

test.describe('Visual: Training Page @visual', () => {
  test('should match training page empty state', async ({
    page,
    trainingPage,
  }) => {
    await page.route('**/api/training/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/characters', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/info', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          name: 'Isengard API',
          version: '1.0.0',
          training: { supported: true },
          image_generation: { supported: true },
        }),
      });
    });

    // Go to training history page (not start)
    await trainingPage.gotoHistory();
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot('training-empty.png', {
      mask: dynamicMasks.map((s) => page.locator(s)),
      fullPage: true,
    });
  });

  test('should match training page with jobs', async ({
    page,
    trainingPage,
  }) => {
    await page.route('**/api/training', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'train-001',
            character_id: 'char-1',
            status: 'completed',
            progress: 100,
            current_step: 1000,
            total_steps: 1000,
            config: { steps: 1000, resolution: 1024, lora_rank: 16 },
            created_at: '2025-01-15T10:00:00Z',
          },
          {
            id: 'train-002',
            character_id: 'char-2',
            status: 'running',
            progress: 45,
            current_step: 450,
            total_steps: 1000,
            config: { steps: 1000, resolution: 1024, lora_rank: 16 },
            created_at: '2025-01-15T11:00:00Z',
          },
        ]),
      });
    });

    await page.route('**/api/characters', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'char-1', name: 'Alice', trigger_word: 'alice', image_count: 5 },
          { id: 'char-2', name: 'Bob', trigger_word: 'bob', image_count: 3 },
        ]),
      });
    });

    await page.route('**/api/info', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          name: 'Isengard API',
          version: '1.0.0',
          training: { supported: true },
          image_generation: { supported: true },
        }),
      });
    });

    // Go to training history page (not start)
    await trainingPage.gotoHistory();
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot('training-with-jobs.png', {
      mask: dynamicMasks.map((s) => page.locator(s)),
      fullPage: true,
    });
  });
});

test.describe('Visual: Generation Page @visual', () => {
  test('should match generation page', async ({ page, generationPage }) => {
    await page.route('**/api/generation', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/characters', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await generationPage.goto();
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot('generation.png', {
      mask: dynamicMasks.map((s) => page.locator(s)),
      fullPage: true,
    });
  });
});

test.describe('Visual: Error States @visual', () => {
  test('should match API error state', async ({ page }) => {
    await page.route('**/api/**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal Server Error' }),
      });
    });

    await page.goto('/characters');
    await page.waitForTimeout(1000);

    await expect(page).toHaveScreenshot('error-state.png', {
      mask: dynamicMasks.map((s) => page.locator(s)),
      fullPage: true,
    });
  });
});
