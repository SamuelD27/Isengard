/**
 * Network Capture Utilities
 *
 * Captures and analyzes network traffic during tests for debugging.
 */

import { Page, Response, Request } from '@playwright/test';

export interface ApiCall {
  url: string;
  method: string;
  status: number;
  statusText: string;
  contentType: string | null;
  requestBody: string | null;
  responseBody: string;
  duration: number;
  timestamp: number;
  isApiCall: boolean;
  isError: boolean;
  isHtml: boolean;
}

export interface NetworkCapture {
  calls: ApiCall[];
  errors: ApiCall[];
  start: () => void;
  stop: () => void;
  getApiCalls: () => ApiCall[];
  getErrors: () => ApiCall[];
  getSummary: () => string;
  clear: () => void;
}

/**
 * Create a network capture instance for a page
 */
export function createNetworkCapture(page: Page): NetworkCapture {
  const calls: ApiCall[] = [];
  let isCapturing = false;

  const handleResponse = async (response: Response) => {
    if (!isCapturing) return;

    const request = response.request();
    const url = response.url();
    const timing = request.timing();

    // Only capture API calls and static assets that might fail
    const isApiCall = url.includes('/api/');

    let responseBody = '';
    let requestBody: string | null = null;

    try {
      responseBody = await response.text();
    } catch {}

    try {
      requestBody = request.postData() || null;
    } catch {}

    const contentType = response.headers()['content-type'] || null;
    const isHtml = contentType?.includes('text/html') ||
                   responseBody.trim().startsWith('<!DOCTYPE') ||
                   responseBody.trim().startsWith('<html');

    const call: ApiCall = {
      url: url.replace(/https?:\/\/[^/]+/, ''), // Relative URL
      method: request.method(),
      status: response.status(),
      statusText: response.statusText(),
      contentType,
      requestBody,
      responseBody: responseBody.slice(0, 2000), // Truncate for memory
      duration: timing.responseEnd > 0 ? timing.responseEnd - timing.requestStart : 0,
      timestamp: Date.now(),
      isApiCall,
      isError: response.status() >= 400,
      isHtml: isApiCall && isHtml, // Misrouted API calls
    };

    calls.push(call);
  };

  return {
    calls,

    get errors() {
      return calls.filter((c) => c.isError || c.isHtml);
    },

    start() {
      isCapturing = true;
      page.on('response', handleResponse);
    },

    stop() {
      isCapturing = false;
      page.off('response', handleResponse);
    },

    getApiCalls() {
      return calls.filter((c) => c.isApiCall);
    },

    getErrors() {
      return calls.filter((c) => c.isError);
    },

    getSummary() {
      const apiCalls = calls.filter((c) => c.isApiCall);
      const errors = calls.filter((c) => c.isError);
      const misrouted = calls.filter((c) => c.isHtml && c.isApiCall);

      let summary = `\n=== Network Summary ===\n`;
      summary += `Total API calls: ${apiCalls.length}\n`;
      summary += `Errors (4xx/5xx): ${errors.length}\n`;
      summary += `Misrouted (HTML on API): ${misrouted.length}\n`;

      if (errors.length > 0) {
        summary += `\n--- Errors ---\n`;
        for (const err of errors) {
          summary += `${err.method} ${err.url} -> ${err.status} ${err.statusText}\n`;
          if (err.responseBody) {
            summary += `  Body: ${err.responseBody.slice(0, 200)}...\n`;
          }
        }
      }

      if (misrouted.length > 0) {
        summary += `\n--- Misrouted API Calls (returned HTML) ---\n`;
        for (const mis of misrouted) {
          summary += `${mis.method} ${mis.url} -> got HTML instead of JSON\n`;
        }
      }

      return summary;
    },

    clear() {
      calls.length = 0;
    },
  };
}

/**
 * Assert no API errors occurred
 */
export function assertNoApiErrors(capture: NetworkCapture) {
  const errors = capture.getErrors();
  if (errors.length > 0) {
    const errorDetails = errors
      .map((e) => `${e.method} ${e.url} -> ${e.status}: ${e.responseBody.slice(0, 200)}`)
      .join('\n');
    throw new Error(`API errors occurred:\n${errorDetails}`);
  }
}

/**
 * Assert no misrouted API calls (HTML returned instead of JSON)
 */
export function assertNoMisroutedCalls(capture: NetworkCapture) {
  const misrouted = capture.calls.filter((c) => c.isHtml && c.isApiCall);
  if (misrouted.length > 0) {
    const details = misrouted
      .map((m) => `${m.method} ${m.url} returned HTML instead of JSON`)
      .join('\n');
    throw new Error(`Misrouted API calls:\n${details}`);
  }
}

/**
 * Mock an API endpoint
 */
export async function mockApiEndpoint(
  page: Page,
  urlPattern: string | RegExp,
  options: {
    status?: number;
    body?: object | string;
    delay?: number;
    contentType?: string;
  } = {}
) {
  const {
    status = 200,
    body = {},
    delay = 0,
    contentType = 'application/json',
  } = options;

  await page.route(urlPattern, async (route) => {
    if (delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay));
    }

    const responseBody = typeof body === 'string' ? body : JSON.stringify(body);

    await route.fulfill({
      status,
      contentType,
      body: responseBody,
    });
  });
}

/**
 * Inject latency into API calls
 */
export async function injectApiLatency(page: Page, delayMs: number) {
  await page.route('**/api/**', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.continue();
  });
}

/**
 * Simulate API errors
 */
export async function simulateApiError(
  page: Page,
  urlPattern: string | RegExp,
  options: {
    status?: number;
    message?: string;
    times?: number;
  } = {}
) {
  const { status = 500, message = 'Internal Server Error', times = 1 } = options;
  let errorCount = 0;

  await page.route(urlPattern, async (route) => {
    if (errorCount < times) {
      errorCount++;
      await route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify({ error: message, detail: message }),
      });
    } else {
      await route.continue();
    }
  });
}
