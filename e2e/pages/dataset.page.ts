/**
 * Dataset Page Object
 *
 * Encapsulates all interactions with the Dataset Manager page.
 */

import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class DatasetPage extends BasePage {
  // Locators
  readonly searchInput: Locator;
  readonly characterFilter: Locator;
  readonly imageGrid: Locator;
  readonly selectAllBtn: Locator;
  readonly deleteSelectedBtn: Locator;
  readonly imageCount: Locator;

  constructor(page: Page) {
    super(page);

    this.searchInput = page.locator('[data-testid="search-input"], input[placeholder*="Search"]');
    this.characterFilter = page.locator('[data-testid="character-filter"], select:near(label:text("Character"))');
    this.imageGrid = page.locator('[data-testid="image-grid"], .image-grid');
    this.selectAllBtn = page.locator('[data-testid="select-all-btn"], button:has-text("Select All")');
    this.deleteSelectedBtn = page.locator('[data-testid="delete-selected-btn"], button:has-text("Delete Selected")');
    this.imageCount = page.locator('[data-testid="image-count"]');
  }

  get url(): string {
    return '/dataset';
  }

  async waitForPageReady(): Promise<void> {
    // Wait for Dataset Manager heading or search input (no image-grid testid in actual UI)
    await expect(
      this.page.locator('h1:has-text("Dataset Manager")').or(this.page.locator('input[placeholder*="Search"]')).first()
    ).toBeVisible({ timeout: 10000 });
    await this.waitForLoadingComplete();
  }

  /**
   * Get all image cards
   */
  getImageCards(): Locator {
    return this.imageGrid.locator('[data-testid="image-card"], .image-card, img');
  }

  /**
   * Get image count
   */
  async getImageCount(): Promise<number> {
    return this.getImageCards().count();
  }

  /**
   * Search for images
   */
  async search(query: string) {
    await this.fillField(this.searchInput, query);
    await this.waitForLoadingComplete();
  }

  /**
   * Filter by character
   */
  async filterByCharacter(characterName: string) {
    if (await this.characterFilter.isVisible()) {
      await this.characterFilter.selectOption({ label: new RegExp(characterName) });
      await this.waitForLoadingComplete();
    }
  }

  /**
   * Select all images
   */
  async selectAll() {
    if (await this.selectAllBtn.isVisible()) {
      await this.selectAllBtn.click();
    }
  }

  /**
   * Delete selected images
   */
  async deleteSelected(): Promise<boolean> {
    if (!(await this.deleteSelectedBtn.isVisible())) {
      return false;
    }

    // Handle confirmation
    this.page.once('dialog', async (dialog) => {
      await dialog.accept();
    });

    await this.deleteSelectedBtn.click();
    await this.waitForLoadingComplete();

    return true;
  }
}
