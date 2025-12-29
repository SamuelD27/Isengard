import { test, expect } from '@playwright/test';

/**
 * UELR (User End Log Register) E2E Tests
 *
 * Tests the end-to-end interaction logging system, verifying that:
 * - Click events generate interaction IDs
 * - Correlation IDs are propagated in headers
 * - Interactions appear in the Logs UI
 * - Backend steps are linked to frontend interactions
 *
 * NOTE: These tests are skipped until the UELR backend is implemented.
 * The UELR system requires:
 * - /api/uelr/interactions endpoint
 * - /logs UI page
 * - Frontend interaction tracking
 */

test.describe.skip('UELR Click-to-Trace', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to characters page (a page with clickable actions)
    await page.goto('/characters');
    await page.waitForLoadState('networkidle');
  });

  test('should attach X-Correlation-ID and X-Interaction-ID headers to API requests', async ({ page }) => {
    const headers: { correlationId: string | null; interactionId: string | null }[] = [];

    // Monitor API requests
    page.on('request', (request) => {
      if (request.url().includes('/api/characters') && request.method() === 'POST') {
        headers.push({
          correlationId: request.headers()['x-correlation-id'] || null,
          interactionId: request.headers()['x-interaction-id'] || null,
        });
      }
    });

    // Click new character button
    await page.click('button:has-text("New Character")');

    // Fill in form
    const uniqueName = `UELR Test ${Date.now()}`;
    await page.fill('input#name', uniqueName);
    await page.fill('input#trigger', `uelr_${Date.now()}`);

    // Click create button
    await page.click('button:has-text("Create Character")');

    // Wait for API call
    await page.waitForResponse(
      (response) =>
        response.url().includes('/api/characters') &&
        response.request().method() === 'POST'
    );

    // Verify headers were attached
    expect(headers.length).toBeGreaterThan(0);
    const createRequest = headers[headers.length - 1];
    expect(createRequest.correlationId).not.toBeNull();
    expect(createRequest.correlationId).toBeTruthy();
  });

  test('should receive X-Correlation-ID in API responses', async ({ page }) => {
    const responses: { correlationId: string | null }[] = [];

    page.on('response', (response) => {
      if (response.url().includes('/api/') && response.status() < 400) {
        responses.push({
          correlationId: response.headers()['x-correlation-id'] || null,
        });
      }
    });

    // Trigger API calls by loading page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Verify responses have correlation ID
    expect(responses.length).toBeGreaterThan(0);
    for (const res of responses) {
      expect(res.correlationId).not.toBeNull();
    }
  });
});

test.describe.skip('UELR Logs UI', () => {
  test('should display the Logs page', async ({ page }) => {
    await page.goto('/logs');
    await page.waitForLoadState('networkidle');

    // Check page elements
    await expect(page.locator('text=Interaction Logs')).toBeVisible();
    await expect(page.locator('text=Recent Interactions')).toBeVisible();
  });

  test('should show interactions in the list', async ({ page }) => {
    // First, perform an action to generate an interaction
    await page.goto('/characters');
    await page.waitForLoadState('networkidle');

    // Click a button to generate an interaction
    await page.click('button:has-text("New Character")');
    await page.waitForTimeout(500); // Wait for interaction to be recorded

    // Navigate to logs
    await page.goto('/logs');
    await page.waitForLoadState('networkidle');

    // Wait for interactions to load (with timeout)
    await page.waitForTimeout(1000);

    // The logs page should show either interactions or a message about no interactions
    const pageContent = await page.content();
    const hasInteractions =
      pageContent.includes('interaction') ||
      pageContent.includes('No interactions recorded');
    expect(hasInteractions).toBe(true);
  });

  test('should have search and filter functionality', async ({ page }) => {
    await page.goto('/logs');
    await page.waitForLoadState('networkidle');

    // Check for search input
    await expect(page.locator('input[placeholder*="Search"]')).toBeVisible();

    // Check for status filter
    await expect(page.locator('button:has-text("All Status")')).toBeVisible();
  });

  test('should have download bundle functionality on interaction details', async ({ page }) => {
    // First, perform an action to generate an interaction
    await page.goto('/characters');
    await page.waitForLoadState('networkidle');
    await page.click('button:has-text("New Character")');
    await page.waitForTimeout(500);

    // Navigate to logs
    await page.goto('/logs');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // If there are interactions, click on one and check for download button
    const interactionItems = page.locator('[class*="cursor-pointer"]').first();
    if (await interactionItems.isVisible()) {
      await interactionItems.click();
      await page.waitForTimeout(500);

      // Check for Download Bundle button in detail panel
      await expect(page.locator('button:has-text("Download Bundle")')).toBeVisible();
    }
  });
});

test.describe.skip('UELR Backend Integration', () => {
  test('should create UELR interaction via API', async ({ request }) => {
    const interactionId = `int-test-${Date.now()}`;
    const correlationId = `cor-test-${Date.now()}`;

    // Create interaction
    const createResponse = await request.post('/api/uelr/interactions', {
      data: {
        interaction_id: interactionId,
        correlation_id: correlationId,
        action_name: 'E2E Test Action',
        action_category: 'test',
        page: '/test',
      },
    });

    expect(createResponse.status()).toBe(201);

    const interaction = await createResponse.json();
    expect(interaction.interaction_id).toBe(interactionId);
    expect(interaction.correlation_id).toBe(correlationId);
    expect(interaction.action_name).toBe('E2E Test Action');
    expect(interaction.status).toBe('pending');
  });

  test('should append steps to interaction', async ({ request }) => {
    const interactionId = `int-step-${Date.now()}`;
    const correlationId = `cor-step-${Date.now()}`;

    // Create interaction first
    await request.post('/api/uelr/interactions', {
      data: {
        interaction_id: interactionId,
        correlation_id: correlationId,
        action_name: 'Step Test Action',
      },
    });

    // Append steps
    const stepsResponse = await request.post(
      `/api/uelr/interactions/${interactionId}/steps`,
      {
        data: {
          interaction_id: interactionId,
          steps: [
            {
              step_id: `step-1-${Date.now()}`,
              correlation_id: correlationId,
              type: 'UI_ACTION_START',
              component: 'frontend',
              timestamp: new Date().toISOString(),
              message: 'Test step 1',
              status: 'success',
            },
            {
              step_id: `step-2-${Date.now()}`,
              correlation_id: correlationId,
              type: 'NETWORK_REQUEST_START',
              component: 'frontend',
              timestamp: new Date().toISOString(),
              message: 'Test step 2',
              status: 'pending',
            },
          ],
        },
      }
    );

    expect(stepsResponse.status()).toBe(200);
    const result = await stepsResponse.json();
    expect(result.appended).toBe(2);
  });

  test('should complete interaction', async ({ request }) => {
    const interactionId = `int-complete-${Date.now()}`;
    const correlationId = `cor-complete-${Date.now()}`;

    // Create interaction
    await request.post('/api/uelr/interactions', {
      data: {
        interaction_id: interactionId,
        correlation_id: correlationId,
        action_name: 'Complete Test Action',
      },
    });

    // Complete interaction
    const completeResponse = await request.put(
      `/api/uelr/interactions/${interactionId}/complete`,
      {
        data: {
          interaction_id: interactionId,
          status: 'success',
        },
      }
    );

    expect(completeResponse.status()).toBe(200);

    const interaction = await completeResponse.json();
    expect(interaction.status).toBe('success');
    expect(interaction.ended_at).toBeTruthy();
    expect(interaction.duration_ms).toBeGreaterThanOrEqual(0);
  });

  test('should get interaction with steps', async ({ request }) => {
    const interactionId = `int-get-${Date.now()}`;
    const correlationId = `cor-get-${Date.now()}`;

    // Create interaction
    await request.post('/api/uelr/interactions', {
      data: {
        interaction_id: interactionId,
        correlation_id: correlationId,
        action_name: 'Get Test Action',
      },
    });

    // Add a step
    await request.post(`/api/uelr/interactions/${interactionId}/steps`, {
      data: {
        interaction_id: interactionId,
        steps: [
          {
            step_id: `step-get-${Date.now()}`,
            correlation_id: correlationId,
            type: 'UI_ACTION_START',
            component: 'frontend',
            timestamp: new Date().toISOString(),
            message: 'Get test step',
            status: 'success',
          },
        ],
      },
    });

    // Get interaction
    const getResponse = await request.get(`/api/uelr/interactions/${interactionId}`);

    expect(getResponse.status()).toBe(200);

    const interaction = await getResponse.json();
    expect(interaction.interaction_id).toBe(interactionId);
    expect(interaction.steps).toBeDefined();
    expect(interaction.steps.length).toBe(1);
    expect(interaction.steps[0].message).toBe('Get test step');
  });

  test('should list interactions', async ({ request }) => {
    const listResponse = await request.get('/api/uelr/interactions?limit=10');

    expect(listResponse.status()).toBe(200);

    const result = await listResponse.json();
    expect(result.interactions).toBeDefined();
    expect(Array.isArray(result.interactions)).toBe(true);
    expect(typeof result.total).toBe('number');
    expect(typeof result.has_more).toBe('boolean');
  });

  test('should redact sensitive data in steps', async ({ request }) => {
    const interactionId = `int-redact-${Date.now()}`;
    const correlationId = `cor-redact-${Date.now()}`;

    // Create interaction
    await request.post('/api/uelr/interactions', {
      data: {
        interaction_id: interactionId,
        correlation_id: correlationId,
        action_name: 'Redaction Test',
      },
    });

    // Add step with sensitive data
    await request.post(`/api/uelr/interactions/${interactionId}/steps`, {
      data: {
        interaction_id: interactionId,
        steps: [
          {
            step_id: `step-redact-${Date.now()}`,
            correlation_id: correlationId,
            type: 'NETWORK_REQUEST_END',
            component: 'frontend',
            timestamp: new Date().toISOString(),
            message: 'Request with secrets',
            status: 'success',
            details: {
              url: '/api/test',
              authorization: 'Bearer super_secret_token',
              password: 'my_password',
              api_key: 'sk-secret123',
            },
          },
        ],
      },
    });

    // Get interaction and verify redaction
    const getResponse = await request.get(`/api/uelr/interactions/${interactionId}`);
    const interaction = await getResponse.json();

    expect(interaction.steps.length).toBe(1);
    const step = interaction.steps[0];
    expect(step.details.authorization).toBe('***REDACTED***');
    expect(step.details.password).toBe('***REDACTED***');
    expect(step.details.api_key).toBe('***REDACTED***');
    expect(step.details.url).toBe('/api/test'); // URL should not be redacted
  });
});

test.describe.skip('UELR Navigation Integration', () => {
  test('should show Logs link in navigation', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check for Logs link in sidebar
    await expect(page.locator('a[href="/logs"]')).toBeVisible();
    await expect(page.locator('text=Logs')).toBeVisible();
  });

  test('should navigate to Logs page from sidebar', async ({ page }) => {
    await page.goto('/characters');
    await page.waitForLoadState('networkidle');

    // Click Logs link
    await page.click('a[href="/logs"]');
    await page.waitForLoadState('networkidle');

    // Verify we're on the logs page
    expect(page.url()).toContain('/logs');
    await expect(page.locator('text=Interaction Logs')).toBeVisible();
  });
});
