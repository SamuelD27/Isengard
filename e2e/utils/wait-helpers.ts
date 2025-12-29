/**
 * Wait Helpers for Deterministic E2E Tests
 *
 * NEVER use arbitrary timeouts or networkidle.
 * ALWAYS wait for specific, observable conditions.
 */

import { Page, Locator, expect } from '@playwright/test';

/**
 * Wait for an element to be visible and enabled (clickable)
 */
export async function waitForClickable(locator: Locator, timeout = 10000) {
  await expect(locator).toBeVisible({ timeout });
  await expect(locator).toBeEnabled({ timeout });
}

/**
 * Wait for an element to be visible and have specific text
 */
export async function waitForText(locator: Locator, text: string | RegExp, timeout = 10000) {
  await expect(locator).toBeVisible({ timeout });
  await expect(locator).toHaveText(text, { timeout });
}

/**
 * Wait for a specific number of elements
 */
export async function waitForCount(locator: Locator, count: number, timeout = 10000) {
  await expect(locator).toHaveCount(count, { timeout });
}

/**
 * Wait for an element to disappear
 */
export async function waitForHidden(locator: Locator, timeout = 10000) {
  await expect(locator).toBeHidden({ timeout });
}

/**
 * Wait for an API response with specific status
 */
export async function waitForApiResponse(
  page: Page,
  urlPattern: string | RegExp,
  options: {
    method?: string;
    status?: number;
    timeout?: number;
  } = {}
) {
  const { method = 'GET', status, timeout = 10000 } = options;

  const response = await page.waitForResponse(
    (response) => {
      const url = response.url();
      const urlMatches = typeof urlPattern === 'string'
        ? url.includes(urlPattern)
        : urlPattern.test(url);
      const methodMatches = response.request().method() === method;
      const statusMatches = status === undefined || response.status() === status;
      return urlMatches && methodMatches && statusMatches;
    },
    { timeout }
  );

  return response;
}

/**
 * Wait for navigation to a specific URL
 */
export async function waitForNavigation(page: Page, urlPattern: string | RegExp, timeout = 10000) {
  await expect(page).toHaveURL(urlPattern, { timeout });
}

/**
 * Wait for loading spinner to disappear
 */
export async function waitForLoadingComplete(page: Page, timeout = 30000) {
  const spinner = page.locator('[data-testid="loading-spinner"], .animate-spin, [role="progressbar"]');

  // First wait for spinner to appear (it should show on slow ops)
  try {
    await spinner.first().waitFor({ state: 'visible', timeout: 1000 });
  } catch {
    // Spinner may not appear for fast operations, that's OK
    return;
  }

  // Then wait for it to disappear
  await spinner.first().waitFor({ state: 'hidden', timeout });
}

/**
 * Wait for a form to be ready (all fields visible and enabled)
 */
export async function waitForFormReady(form: Locator, timeout = 10000) {
  await expect(form).toBeVisible({ timeout });

  // Wait for inputs to be enabled
  const inputs = form.locator('input:visible, select:visible, textarea:visible');
  const count = await inputs.count();

  for (let i = 0; i < count; i++) {
    const input = inputs.nth(i);
    // Skip disabled-by-design fields
    const isDisabledByDesign = await input.getAttribute('data-disabled');
    if (isDisabledByDesign !== 'true') {
      await expect(input).toBeEnabled({ timeout });
    }
  }
}

/**
 * Wait for a toast notification
 */
export async function waitForToast(
  page: Page,
  options: {
    type?: 'success' | 'error' | 'warning' | 'info';
    text?: string | RegExp;
    timeout?: number;
  } = {}
) {
  const { type, text, timeout = 5000 } = options;

  let selector = '[role="alert"], [data-testid="toast"]';
  if (type) {
    selector += `, .toast-${type}`;
  }

  const toast = page.locator(selector).first();
  await expect(toast).toBeVisible({ timeout });

  if (text) {
    await expect(toast).toHaveText(text, { timeout });
  }

  return toast;
}

/**
 * Wait for SSE connection to be established
 */
export async function waitForSSEConnection(page: Page, timeout = 5000) {
  return new Promise<void>((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error('SSE connection timeout'));
    }, timeout);

    // Listen for EventSource messages
    page.on('console', (msg) => {
      if (msg.text().includes('SSE') || msg.text().includes('EventSource')) {
        clearTimeout(timeoutId);
        resolve();
      }
    });

    // Also check for SSE-related network activity
    page.on('request', (request) => {
      if (request.url().includes('/stream')) {
        clearTimeout(timeoutId);
        resolve();
      }
    });
  });
}

/**
 * Retry an action until it succeeds
 */
export async function retryUntilSuccess<T>(
  action: () => Promise<T>,
  options: {
    maxAttempts?: number;
    delay?: number;
    timeout?: number;
  } = {}
): Promise<T> {
  const { maxAttempts = 5, delay = 500, timeout = 30000 } = options;
  const startTime = Date.now();

  let lastError: Error | undefined;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    if (Date.now() - startTime > timeout) {
      throw new Error(`Timeout after ${timeout}ms: ${lastError?.message || 'unknown error'}`);
    }

    try {
      return await action();
    } catch (error) {
      lastError = error as Error;
      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError || new Error('Action failed after max attempts');
}
