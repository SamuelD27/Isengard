/**
 * Character Flow Tests
 *
 * Full user journey tests for character management:
 * - Create character with validation
 * - View character details
 * - Delete character with confirmation
 *
 * NOTE: These tests are temporarily skipped pending page object updates.
 * Use smoke tests for basic character validation.
 *
 * @tag characters @critical
 */

import { test, expect } from '../../fixtures/test-fixtures';
import { createNetworkCapture } from '../../utils/network-capture';

test.describe.skip('Characters: Create Flow @characters @critical', () => {
  test('should create a character successfully', async ({ page, charactersPage }) => {
    const networkCapture = createNetworkCapture(page);
    networkCapture.start();

    await charactersPage.goto();

    const uniqueName = `E2E Test ${Date.now()}`;
    const triggerWord = `e2e_test_${Date.now()}`;

    const result = await charactersPage.createCharacter({
      name: uniqueName,
      trigger: triggerWord,
      description: 'Created by E2E test suite',
    });

    networkCapture.stop();

    // Verify success
    expect(result.success).toBe(true);
    expect(result.characterId).toBeDefined();

    // Verify character appears in grid
    const exists = await charactersPage.verifyCharacterExists(uniqueName);
    expect(exists).toBe(true);

    // Verify no API errors
    const errors = networkCapture.getErrors();
    expect(errors.length).toBe(0);

    // Cleanup
    await charactersPage.deleteCharacter(uniqueName);
  });

  test('should validate required fields', async ({ page, charactersPage }) => {
    await charactersPage.goto();
    await charactersPage.clickNewCharacter();

    // Try to submit with empty name
    const createBtn = charactersPage.createBtn;

    // Button should be disabled or form should prevent submission
    // This depends on implementation - check both scenarios
    const isDisabled = await createBtn.isDisabled();
    if (isDisabled) {
      expect(isDisabled).toBe(true);
    } else {
      // If button is enabled, clicking should show validation error
      await createBtn.click();
      const hasError = await charactersPage.hasVisibleError();
      // Either button is disabled or error is shown
      expect(hasError || isDisabled).toBe(true);
    }

    await charactersPage.closeFormIfOpen();
  });

  test('should handle duplicate trigger word gracefully', async ({
    page,
    charactersPage,
    createTestCharacter,
  }) => {
    // Create first character via API
    const charId = await createTestCharacter('E2E Duplicate Test');

    await charactersPage.goto();

    // Try to create another with same trigger
    await charactersPage.clickNewCharacter();
    await charactersPage.fillCharacterForm({
      name: 'E2E Duplicate Test 2',
      trigger: 'e2e_duplicate_test', // Same trigger
    });

    // Submit - should either fail or succeed with different trigger
    const result = await charactersPage.submitCharacterForm();

    // Either fails with error or succeeds (backend generates unique trigger)
    // Both are acceptable behaviors
    if (!result.success) {
      const hasError = await charactersPage.hasVisibleError();
      expect(hasError).toBe(true);
    }

    await charactersPage.closeFormIfOpen();
  });
});

test.describe.skip('Characters: View Details Flow @characters', () => {
  test('should view character details', async ({
    page,
    charactersPage,
    createTestCharacter,
  }) => {
    const charId = await createTestCharacter('E2E View Test');

    await charactersPage.goto();

    // Click on character to view details
    await charactersPage.viewCharacterDetails('E2E View Test');

    // Should show detail view with images section
    await expect(page.locator('text=Reference Images')).toBeVisible();
  });
});

test.describe.skip('Characters: Delete Flow @characters', () => {
  test('should delete character with confirmation', async ({
    page,
    charactersPage,
  }) => {
    // Create a character to delete
    await charactersPage.goto();

    const uniqueName = `E2E Delete Test ${Date.now()}`;
    await charactersPage.createCharacter({
      name: uniqueName,
      trigger: `e2e_delete_${Date.now()}`,
    });

    // Verify it exists
    const existsBefore = await charactersPage.verifyCharacterExists(uniqueName);
    expect(existsBefore).toBe(true);

    // Delete it
    const deleteResult = await charactersPage.deleteCharacter(uniqueName);
    expect(deleteResult.success).toBe(true);

    // Verify it's gone
    const existsAfter = await charactersPage.verifyCharacterNotExists(uniqueName);
    expect(existsAfter).toBe(true);
  });

  test('should handle delete cancellation', async ({ page, charactersPage }) => {
    // Create a character
    await charactersPage.goto();

    const uniqueName = `E2E Cancel Delete ${Date.now()}`;
    await charactersPage.createCharacter({
      name: uniqueName,
      trigger: `e2e_cancel_${Date.now()}`,
    });

    // Start delete but cancel
    const card = charactersPage.getCharacterCardByName(uniqueName);
    await card.hover();

    const deleteBtn = card.locator('[data-testid="delete-character-btn"], button:has(svg.lucide-trash-2)');

    // Handle dialog by dismissing
    page.once('dialog', async (dialog) => {
      await dialog.dismiss();
    });

    await deleteBtn.click();

    // Character should still exist
    await page.waitForTimeout(500);
    const stillExists = await charactersPage.verifyCharacterExists(uniqueName);
    expect(stillExists).toBe(true);

    // Cleanup
    await charactersPage.deleteCharacter(uniqueName);
  });
});

test.describe.skip('Characters: API Wiring @characters', () => {
  test('should have correlation ID in all requests', async ({ page, charactersPage }) => {
    const correlationIds: string[] = [];

    page.on('request', (request) => {
      if (request.url().includes('/api/')) {
        const correlationId = request.headers()['x-correlation-id'];
        if (correlationId) {
          correlationIds.push(correlationId);
        }
      }
    });

    await charactersPage.goto();
    await page.waitForTimeout(1000);

    // Should have at least one API call with correlation ID
    expect(correlationIds.length).toBeGreaterThan(0);

    // All should have the expected format
    for (const id of correlationIds) {
      expect(id).toMatch(/^fe-/);
    }
  });

  test('should handle API errors gracefully', async ({ page, charactersPage }) => {
    // Simulate API error
    await page.route('**/api/characters', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal Server Error' }),
        });
      } else {
        await route.continue();
      }
    });

    await charactersPage.goto();
    await charactersPage.clickNewCharacter();
    await charactersPage.fillCharacterForm({
      name: 'Error Test',
      trigger: 'error_test',
    });

    await charactersPage.createBtn.click();
    await page.waitForTimeout(1000);

    // Should show error or handle gracefully
    const hasError = await charactersPage.hasVisibleError();
    // Either error is shown or button becomes enabled again
    const buttonEnabled = await charactersPage.createBtn.isEnabled();

    expect(hasError || buttonEnabled).toBe(true);

    await page.unroute('**/api/characters');
    await charactersPage.closeFormIfOpen();
  });
});
