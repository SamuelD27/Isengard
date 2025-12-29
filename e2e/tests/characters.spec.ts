import { test, expect } from '@playwright/test';

/**
 * Character Management E2E Tests (LEGACY)
 *
 * Tests the full GUI flow for creating, viewing, and managing characters.
 *
 * NOTE: These tests are temporarily skipped pending selector updates.
 * Use flows/characters.spec.ts or smoke tests for character validation.
 *
 * @deprecated Update selectors to match current UI
 */

test.describe.skip('Character Management', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to characters page
    await page.goto('/characters');
    // Wait for page to load
    await page.waitForLoadState('networkidle');
  });

  test('should display characters page', async ({ page }) => {
    // Check page title/heading exists
    await expect(page.locator('text=New Character')).toBeVisible();
  });

  test('should open create character form', async ({ page }) => {
    // Click new character button
    await page.click('button:has-text("New Character")');

    // Wait for form to appear
    await expect(page.locator('text=Character Details')).toBeVisible();

    // Check form fields exist
    await expect(page.locator('input#name')).toBeVisible();
    await expect(page.locator('input#trigger')).toBeVisible();
  });

  test('should create a character', async ({ page }) => {
    // Click new character button
    await page.click('button:has-text("New Character")');

    // Fill in form
    const uniqueName = `Test Character ${Date.now()}`;
    const triggerWord = `testchar_${Date.now()}`;

    await page.fill('input#name', uniqueName);
    await page.fill('input#trigger', triggerWord);
    await page.fill('textarea#description', 'E2E test character');

    // Intercept the API call
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/characters') &&
        response.request().method() === 'POST'
    );

    // Click create button
    await page.click('button:has-text("Create Character")');

    // Wait for API response
    const response = await responsePromise;
    expect(response.status()).toBe(201);

    // Verify character appears in list
    await expect(page.locator(`text=${uniqueName}`)).toBeVisible({ timeout: 5000 });
  });

  test('should display character details', async ({ page }) => {
    // First create a character
    await page.click('button:has-text("New Character")');
    const uniqueName = `Detail Test ${Date.now()}`;
    await page.fill('input#name', uniqueName);
    await page.fill('input#trigger', `trigger_${Date.now()}`);

    const createResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/characters') &&
        response.request().method() === 'POST'
    );
    await page.click('button:has-text("Create Character")');
    await createResponse;

    // Wait for redirect back to list
    await page.waitForLoadState('networkidle');

    // Click on character card to view details
    await page.click(`text=${uniqueName}`);

    // Verify detail view shows
    await expect(page.locator('text=Reference Images')).toBeVisible({ timeout: 5000 });
  });

  test('should handle character deletion', async ({ page }) => {
    // First create a character
    await page.click('button:has-text("New Character")');
    const uniqueName = `Delete Test ${Date.now()}`;
    await page.fill('input#name', uniqueName);
    await page.fill('input#trigger', `trigger_${Date.now()}`);

    await page.click('button:has-text("Create Character")');
    await page.waitForLoadState('networkidle');

    // Find and click delete button on the card
    const card = page.locator(`text=${uniqueName}`).locator('..');
    await card.hover();

    // Handle confirmation dialog
    page.on('dialog', async (dialog) => {
      expect(dialog.type()).toBe('confirm');
      await dialog.accept();
    });

    // Click delete icon button
    await card.locator('button:has(svg.lucide-trash-2)').click();

    // Verify character is removed
    await expect(page.locator(`text=${uniqueName}`)).not.toBeVisible({ timeout: 5000 });
  });
});

test.describe('API Integration', () => {
  test('should have correlation ID in all requests', async ({ page }) => {
    const requests: { url: string; correlationId: string | null }[] = [];

    // Monitor all API requests
    page.on('request', (request) => {
      if (request.url().includes('/api/')) {
        requests.push({
          url: request.url(),
          correlationId: request.headers()['x-correlation-id'] || null,
        });
      }
    });

    await page.goto('/characters');
    await page.waitForLoadState('networkidle');

    // Verify at least one API call was made
    expect(requests.length).toBeGreaterThan(0);

    // Verify all requests have correlation ID
    for (const req of requests) {
      expect(req.correlationId).not.toBeNull();
      expect(req.correlationId).toMatch(/^fe-/);
    }
  });

  test('should receive correlation ID in responses', async ({ page }) => {
    const responses: { url: string; correlationId: string | null }[] = [];

    page.on('response', (response) => {
      if (response.url().includes('/api/')) {
        responses.push({
          url: response.url(),
          correlationId: response.headers()['x-correlation-id'] || null,
        });
      }
    });

    await page.goto('/characters');
    await page.waitForLoadState('networkidle');

    expect(responses.length).toBeGreaterThan(0);

    for (const res of responses) {
      expect(res.correlationId).not.toBeNull();
    }
  });
});
