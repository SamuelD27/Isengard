/**
 * Base Page Object
 *
 * Provides common functionality for all page objects:
 * - Navigation
 * - Common waits
 * - Network/console capture
 * - Screenshot helpers
 */

import { Page, Locator, expect } from '@playwright/test';
import { createNetworkCapture, NetworkCapture } from '../utils/network-capture';
import { createLogCollector, LogCollector } from '../utils/log-collector';

export abstract class BasePage {
  protected page: Page;
  protected networkCapture: NetworkCapture;
  protected logCollector: LogCollector;

  constructor(page: Page) {
    this.page = page;
    this.networkCapture = createNetworkCapture(page);
    this.logCollector = createLogCollector(page);
  }

  // Abstract: each page defines its own URL
  abstract get url(): string;

  // Abstract: each page defines how to verify it's loaded
  abstract waitForPageReady(): Promise<void>;

  /**
   * Navigate to this page
   */
  async goto() {
    await this.page.goto(this.url);
    await this.waitForPageReady();
  }

  /**
   * Start capturing network and console
   */
  startCapture() {
    this.networkCapture.start();
    this.logCollector.start();
  }

  /**
   * Stop capturing and return summaries
   */
  stopCapture() {
    this.networkCapture.stop();
    this.logCollector.stop();

    return {
      network: this.networkCapture.getSummary(),
      console: this.logCollector.getSummary(),
      hasNetworkErrors: this.networkCapture.getErrors().length > 0,
      hasConsoleErrors: this.logCollector.hasErrors(),
    };
  }

  /**
   * Wait for an API call to complete
   */
  async waitForApi(
    endpoint: string,
    options: { method?: string; timeout?: number } = {}
  ) {
    const { method = 'GET', timeout = 10000 } = options;

    return this.page.waitForResponse(
      (response) =>
        response.url().includes(endpoint) &&
        response.request().method() === method,
      { timeout }
    );
  }

  /**
   * Wait for navigation to a new URL
   */
  async waitForNavigation(urlPattern: string | RegExp, timeout = 10000) {
    await expect(this.page).toHaveURL(urlPattern, { timeout });
  }

  /**
   * Get a locator by test ID (data-testid attribute)
   */
  getByTestId(testId: string): Locator {
    return this.page.getByTestId(testId);
  }

  /**
   * Click a button and wait for it to be enabled again (for form submissions)
   */
  async clickAndWaitForEnabled(button: Locator, timeout = 10000) {
    await expect(button).toBeEnabled({ timeout: 5000 });
    await button.click();

    // Wait for button to potentially disable (during submit)
    try {
      await expect(button).toBeDisabled({ timeout: 500 });
    } catch {
      // Button may not disable, that's OK
    }

    // Wait for button to be enabled again (after submit)
    await expect(button).toBeEnabled({ timeout });
  }

  /**
   * Fill a form field with retry on failure
   */
  async fillField(locator: Locator, value: string) {
    await expect(locator).toBeVisible({ timeout: 5000 });
    await expect(locator).toBeEnabled({ timeout: 5000 });
    await locator.clear();
    await locator.fill(value);
    await expect(locator).toHaveValue(value);
  }

  /**
   * Select an option from a dropdown
   */
  async selectOption(locator: Locator, value: string) {
    await expect(locator).toBeVisible({ timeout: 5000 });
    await expect(locator).toBeEnabled({ timeout: 5000 });
    await locator.selectOption(value);
  }

  /**
   * Wait for loading to complete
   */
  async waitForLoadingComplete(timeout = 30000) {
    const spinners = this.page.locator(
      '[data-testid="loading"], .animate-spin, [role="progressbar"]'
    );

    // Wait for any spinners to disappear
    const count = await spinners.count();
    if (count > 0) {
      for (let i = 0; i < count; i++) {
        try {
          await spinners.nth(i).waitFor({ state: 'hidden', timeout });
        } catch {
          // Spinner may have already disappeared
        }
      }
    }
  }

  /**
   * Take a screenshot with a descriptive name
   */
  async takeScreenshot(name: string) {
    return this.page.screenshot({
      path: `artifacts/screenshots/${name}-${Date.now()}.png`,
      fullPage: true,
    });
  }

  /**
   * Check if page has any visible errors
   */
  async hasVisibleError(): Promise<boolean> {
    const errorSelectors = [
      '[data-testid="error"]',
      '.error',
      '[role="alert"]',
      '.text-destructive',
      '.text-red-500',
    ];

    for (const selector of errorSelectors) {
      const element = this.page.locator(selector).first();
      if (await element.isVisible()) {
        return true;
      }
    }

    return false;
  }

  /**
   * Get visible error text
   */
  async getVisibleErrorText(): Promise<string | null> {
    const errorSelectors = [
      '[data-testid="error"]',
      '.error',
      '[role="alert"]',
      '.text-destructive',
    ];

    for (const selector of errorSelectors) {
      const element = this.page.locator(selector).first();
      if (await element.isVisible()) {
        return element.textContent();
      }
    }

    return null;
  }

  /**
   * Verify no JavaScript errors in console
   */
  assertNoErrors() {
    const errors = this.logCollector.getErrors();
    if (errors.length > 0) {
      const details = errors.map((e) => e.text).join('\n');
      throw new Error(`JavaScript errors detected:\n${details}`);
    }
  }

  /**
   * Verify no API errors
   */
  assertNoApiErrors() {
    const errors = this.networkCapture.getErrors();
    if (errors.length > 0) {
      const details = errors
        .map((e) => `${e.method} ${e.url} -> ${e.status}`)
        .join('\n');
      throw new Error(`API errors detected:\n${details}`);
    }
  }
}
