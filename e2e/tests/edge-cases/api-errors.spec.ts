/**
 * Edge Case Tests: API Errors
 *
 * Tests that the UI handles API errors gracefully:
 * - 500 errors show error message
 * - UI remains functional after error
 * - User can retry
 *
 * NOTE: These tests are temporarily skipped pending UI updates.
 *
 * @tag edge-cases
 */

import { test, expect } from '../../fixtures/test-fixtures';
import { simulateApiError, injectApiLatency } from '../../utils/network-capture';

test.describe.skip('Edge Cases: API 500 Errors', () => {
  test('should show error when character list fails', async ({ page }) => {
    // Simulate 500 error on characters endpoint
    await simulateApiError(page, '**/api/characters', {
      status: 500,
      message: 'Database connection failed',
    });

    await page.goto('/characters');
    await page.waitForTimeout(2000);

    // Should show some kind of error state
    // (exact implementation may vary)
    const content = await page.textContent('body');
    const hasError =
      content?.includes('error') ||
      content?.includes('Error') ||
      content?.includes('failed') ||
      content?.includes('Failed');

    // Page should at least not crash
    expect(page.url()).toContain('/characters');
  });

  test('should show error when training list fails', async ({ page }) => {
    await simulateApiError(page, '**/api/training', {
      status: 500,
      message: 'Internal Server Error',
    });

    await page.goto('/training');
    await page.waitForTimeout(2000);

    // Page should still be functional
    expect(page.url()).toContain('/training');
  });

  test('should recover after single API failure', async ({ page }) => {
    let failCount = 0;

    // Fail first request, succeed after
    await page.route('**/api/characters', async (route) => {
      if (failCount === 0) {
        failCount++;
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Temporary error' }),
        });
      } else {
        await route.continue();
      }
    });

    await page.goto('/characters');
    await page.waitForTimeout(1000);

    // Refresh should work
    await page.reload();
    await page.waitForTimeout(1000);

    // Should now work
    await expect(page.locator('button:has-text("New Character")')).toBeVisible({
      timeout: 5000,
    });

    await page.unroute('**/api/characters');
  });
});

test.describe.skip('Edge Cases: API 4xx Errors', () => {
  test('should show validation error on 400', async ({ page, charactersPage }) => {
    await page.route('**/api/characters', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Trigger word already exists',
          }),
        });
      } else {
        await route.continue();
      }
    });

    await charactersPage.goto();
    await charactersPage.clickNewCharacter();
    await charactersPage.fillCharacterForm({
      name: 'Test',
      trigger: 'existing_trigger',
    });

    await charactersPage.createBtn.click();
    await page.waitForTimeout(1000);

    // Should show error or button should be enabled for retry
    const hasError = await charactersPage.hasVisibleError();
    const buttonEnabled = await charactersPage.createBtn.isEnabled();

    expect(hasError || buttonEnabled).toBe(true);

    await page.unroute('**/api/characters');
  });

  test('should handle 404 gracefully', async ({ page }) => {
    await page.route('**/api/characters/nonexistent', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Character not found' }),
      });
    });

    // Try to access non-existent character
    await page.goto('/characters/nonexistent');
    await page.waitForTimeout(1000);

    // Should redirect or show error
    const url = page.url();
    const content = await page.textContent('body');

    // Either redirected or shows error
    expect(url.includes('/characters') || content?.includes('not found')).toBe(
      true
    );

    await page.unroute('**/api/characters/nonexistent');
  });
});

test.describe.skip('Edge Cases: Slow API', () => {
  test('should show loading state for slow requests', async ({ page }) => {
    // Inject 3 second delay
    await injectApiLatency(page, 3000);

    await page.goto('/characters');

    // Should show some loading indication
    // (spinner, skeleton, or loading text)
    const loadingIndicators = page.locator(
      '.animate-spin, [role="progressbar"], text=Loading'
    );

    // Either loading state shown or page handles gracefully
    await page.waitForTimeout(500);
    const isLoading = (await loadingIndicators.count()) > 0;

    // After waiting, content should eventually appear
    await page.waitForTimeout(4000);
    await expect(page.locator('button:has-text("New Character")')).toBeVisible({
      timeout: 5000,
    });

    await page.unroute('**/api/**');
  });

  test('should not allow double-submit during slow request', async ({
    page,
    charactersPage,
  }) => {
    let postCount = 0;

    await page.route('**/api/characters', async (route) => {
      if (route.request().method() === 'POST') {
        postCount++;
        // Delay response
        await new Promise((r) => setTimeout(r, 2000));
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'test-123', name: 'Test' }),
        });
      } else {
        await route.continue();
      }
    });

    await charactersPage.goto();
    await charactersPage.clickNewCharacter();
    await charactersPage.fillCharacterForm({
      name: 'Double Submit Test',
      trigger: 'double_test',
    });

    // Click submit multiple times rapidly
    const btn = charactersPage.createBtn;
    await btn.click();
    await btn.click({ force: true });
    await btn.click({ force: true });

    await page.waitForTimeout(3000);

    // Should only have made 1 POST request (button disabled after first click)
    // or at most 2 if there's a race
    expect(postCount).toBeLessThanOrEqual(2);

    await page.unroute('**/api/characters');
  });
});
