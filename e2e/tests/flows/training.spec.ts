/**
 * Training Flow Tests
 *
 * Full user journey tests for training:
 * - Configure training parameters
 * - Start training job
 * - Observe progress via SSE
 * - View job details
 * - Handle failures gracefully
 *
 * NOTE: These tests are temporarily skipped pending page object updates
 * for the new 3-level training navigation structure.
 * Use training-gui.spec.ts for training validation tests.
 *
 * @tag training @critical
 * @deprecated Use training-gui.spec.ts for training validation
 */

import { test, expect } from '../../fixtures/test-fixtures';
import { createNetworkCapture } from '../../utils/network-capture';

test.describe.skip('Training: Configuration @training', () => {
  test('should display training presets', async ({ page, trainingPage }) => {
    await trainingPage.goto();

    // All three presets should be visible
    await expect(trainingPage.presetQuick).toBeVisible();
    await expect(trainingPage.presetBalanced).toBeVisible();
    await expect(trainingPage.presetQuality).toBeVisible();
  });

  test('should select preset and update config', async ({ page, trainingPage }) => {
    await trainingPage.goto();

    // Select Quick preset
    await trainingPage.selectPreset('quick');

    // Verify steps changed (Quick = 500 steps)
    await expect(trainingPage.stepsInput).toHaveValue('500');
  });

  test('should disable start button without character', async ({ page, trainingPage }) => {
    await trainingPage.goto();

    // Without character selected, button should be disabled
    const isDisabled = await trainingPage.startTrainingBtn.isDisabled();

    // If not disabled, clicking should not trigger API call
    if (!isDisabled) {
      const networkCapture = createNetworkCapture(page);
      networkCapture.start();

      await trainingPage.startTrainingBtn.click();
      await page.waitForTimeout(1000);

      networkCapture.stop();

      // Should not have made a POST to /api/training
      const postCalls = networkCapture.calls.filter(
        (c) => c.method === 'POST' && c.url.includes('/api/training')
      );

      expect(postCalls.length).toBe(0);
    } else {
      expect(isDisabled).toBe(true);
    }
  });

  test('should show character selector with eligible characters', async ({
    page,
    trainingPage,
    createTestCharacter,
  }) => {
    // Create a character with images (via API for speed)
    // Note: In real test, we'd upload images. For now, just verify selector works.

    await trainingPage.goto();

    // Character selector should be visible
    await expect(trainingPage.characterSelect).toBeVisible();
  });
});

test.describe.skip('Training: Start Job Flow @training @critical', () => {
  test.skip('should start training and see job in list', async ({
    page,
    trainingPage,
    createTestCharacter,
  }) => {
    // This test is skipped by default as it requires a character with images
    // Enable when running with seeded data

    const charId = await createTestCharacter('E2E Training Test');

    await trainingPage.goto();
    await trainingPage.selectCharacter('E2E Training Test');
    await trainingPage.selectPreset('quick');

    const result = await trainingPage.startTraining();

    if (result.success && result.jobId) {
      // Job should appear in list
      const appeared = await trainingPage.waitForJobToAppear(result.jobId);
      expect(appeared).toBe(true);

      // Cancel the job to clean up
      await trainingPage.cancelJob(result.jobId);
    } else {
      // If start failed, should show error (character may not have images)
      console.log('Training start failed:', result.error);
    }
  });

  test('should handle start training errors gracefully', async ({
    page,
    trainingPage,
  }) => {
    // Mock the API to return an error
    await page.route('**/api/training', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Character has no training images',
          }),
        });
      } else {
        await route.continue();
      }
    });

    await trainingPage.goto();

    // Force select first character option (may fail validation)
    const select = trainingPage.characterSelect;
    const options = await select.locator('option').all();
    if (options.length > 1) {
      await select.selectOption({ index: 1 });

      const result = await trainingPage.startTraining();

      // Should fail
      expect(result.success).toBe(false);
      expect(result.error).toContain('no training images');
    }

    await page.unroute('**/api/training');
  });
});

test.describe.skip('Training: Job History @training', () => {
  test('should display training job history', async ({ page, trainingPage }) => {
    await trainingPage.goto();

    // Should have job list section
    await expect(page.locator('text=Training History')).toBeVisible({ timeout: 10000 });
  });

  test('should fetch jobs from API', async ({ page, trainingPage }) => {
    const networkCapture = createNetworkCapture(page);
    networkCapture.start();

    await trainingPage.goto();
    await page.waitForTimeout(1000);

    networkCapture.stop();

    // Should have called GET /api/training
    const getCalls = networkCapture.calls.filter(
      (c) => c.method === 'GET' && c.url.includes('/api/training')
    );

    expect(getCalls.length).toBeGreaterThan(0);

    // Should be JSON
    for (const call of getCalls) {
      expect(call.isHtml).toBe(false);
      expect(call.isJson).toBe(true);
    }
  });

  test.skip('should show job progress for running jobs', async ({
    page,
    trainingPage,
  }) => {
    // This test requires a running job
    // Skip unless we have seeded data

    await trainingPage.goto();

    const jobCards = trainingPage.getJobCards();
    const count = await jobCards.count();

    if (count > 0) {
      const firstJob = jobCards.first();
      const status = await trainingPage.getJobStatus(firstJob).textContent();

      if (status === 'running' || status === 'queued') {
        // Should show progress bar
        const progress = trainingPage.getJobProgress(firstJob);
        await expect(progress).toBeVisible();
      }
    }
  });
});

test.describe.skip('Training: SSE Streaming @training', () => {
  test.skip('should receive SSE updates for running job', async ({
    page,
    trainingPage,
  }) => {
    // This test requires actually starting a training job
    // and waiting for SSE updates

    await trainingPage.goto();

    // Check if there's a running job
    const jobCards = trainingPage.getJobCards();
    const count = await jobCards.count();

    for (let i = 0; i < count; i++) {
      const card = jobCards.nth(i);
      const status = await trainingPage.getJobStatus(card).textContent();

      if (status === 'running') {
        // Wait for logs to appear
        const logsAppeared = await trainingPage.waitForLogs(15000);
        expect(logsAppeared).toBe(true);

        const logsText = await trainingPage.getLogsText();
        expect(logsText.length).toBeGreaterThan(0);
        break;
      }
    }
  });
});

test.describe.skip('Training: Job Details Modal @training', () => {
  test.skip('should open and close job details', async ({
    page,
    trainingPage,
  }) => {
    await trainingPage.goto();

    const jobCards = trainingPage.getJobCards();
    const count = await jobCards.count();

    if (count > 0) {
      // Get first job ID
      const firstCard = jobCards.first();
      const jobId = await firstCard.getAttribute('data-job-id');

      if (jobId) {
        await trainingPage.openJobDetails(jobId);
        await expect(trainingPage.jobDetailModal).toBeVisible();

        await trainingPage.closeJobDetails();
        await expect(trainingPage.jobDetailModal).toBeHidden();
      }
    }
  });
});

test.describe.skip('Training: API Wiring @training', () => {
  test('API calls should return JSON, not HTML', async ({
    page,
    trainingPage,
  }) => {
    const networkCapture = createNetworkCapture(page);
    networkCapture.start();

    await trainingPage.goto();
    await page.waitForTimeout(2000);

    networkCapture.stop();

    // Check for misrouted calls
    const apiCalls = networkCapture.calls.filter((c) => c.isApiCall);
    const misrouted = apiCalls.filter((c) => c.isHtml);

    if (misrouted.length > 0) {
      console.log(
        'Misrouted API calls:',
        misrouted.map((m) => `${m.method} ${m.url}`)
      );
    }

    expect(misrouted.length).toBe(0);
  });

  test('should handle network errors gracefully', async ({
    page,
    trainingPage,
  }) => {
    // Simulate network failure
    await page.route('**/api/training', async (route) => {
      await route.abort('connectionfailed');
    });

    // Page should still load without crashing
    await page.goto('/training');
    await page.waitForTimeout(2000);

    // Should show error or fallback state
    const pageContent = await page.textContent('body');
    expect(pageContent).toBeDefined();

    await page.unroute('**/api/training');
  });
});
