/**
 * Characters Page Object
 *
 * Encapsulates all interactions with the Characters page.
 */

import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class CharactersPage extends BasePage {
  // Locators
  readonly newCharacterBtn: Locator;
  readonly characterForm: Locator;
  readonly nameInput: Locator;
  readonly triggerInput: Locator;
  readonly descriptionInput: Locator;
  readonly createBtn: Locator;
  readonly cancelBtn: Locator;
  readonly characterGrid: Locator;

  constructor(page: Page) {
    super(page);

    // Define locators using test IDs and fallbacks
    this.newCharacterBtn = page.locator('[data-testid="new-character-btn"], button:has-text("New Character")');
    this.characterForm = page.locator('[data-testid="character-form"], form');
    this.nameInput = page.locator('[data-testid="character-name-input"], input#name');
    this.triggerInput = page.locator('[data-testid="character-trigger-input"], input#trigger');
    this.descriptionInput = page.locator('[data-testid="character-description-input"], textarea#description');
    this.createBtn = page.locator('[data-testid="create-character-btn"], button:has-text("Create Character")');
    this.cancelBtn = page.locator('[data-testid="cancel-btn"], button:has-text("Cancel")');
    this.characterGrid = page.locator('[data-testid="character-grid"], .grid');
  }

  get url(): string {
    return '/characters';
  }

  async waitForPageReady(): Promise<void> {
    // Wait for the page header or new character button to be visible
    await expect(this.newCharacterBtn).toBeVisible({ timeout: 10000 });
    await this.waitForLoadingComplete();
  }

  /**
   * Get all character cards
   */
  getCharacterCards(): Locator {
    return this.page.locator('[data-testid="character-card"], .character-card');
  }

  /**
   * Get a character card by name
   */
  getCharacterCardByName(name: string): Locator {
    return this.page.locator(`[data-testid="character-card"]:has-text("${name}"), .character-card:has-text("${name}")`);
  }

  /**
   * Get character count
   */
  async getCharacterCount(): Promise<number> {
    return this.getCharacterCards().count();
  }

  /**
   * Click New Character button
   */
  async clickNewCharacter() {
    await expect(this.newCharacterBtn).toBeEnabled({ timeout: 5000 });
    await this.newCharacterBtn.click();
    await expect(this.characterForm).toBeVisible({ timeout: 5000 });
  }

  /**
   * Fill character form
   */
  async fillCharacterForm(options: {
    name: string;
    trigger?: string;
    description?: string;
  }) {
    const { name, trigger, description } = options;

    await this.fillField(this.nameInput, name);

    if (trigger) {
      await this.fillField(this.triggerInput, trigger);
    }

    if (description) {
      await expect(this.descriptionInput).toBeVisible();
      await this.descriptionInput.fill(description);
    }
  }

  /**
   * Submit character form and wait for response
   */
  async submitCharacterForm(): Promise<{ success: boolean; status: number; characterId?: string }> {
    const responsePromise = this.waitForApi('/api/characters', { method: 'POST', timeout: 15000 });

    await this.clickAndWaitForEnabled(this.createBtn);

    try {
      const response = await responsePromise;
      const status = response.status();

      if (status === 201) {
        const data = await response.json();
        return { success: true, status, characterId: data.id };
      }

      return { success: false, status };
    } catch (error) {
      return { success: false, status: 0 };
    }
  }

  /**
   * Create a character with full flow
   */
  async createCharacter(options: {
    name: string;
    trigger?: string;
    description?: string;
  }): Promise<{ success: boolean; characterId?: string }> {
    await this.clickNewCharacter();
    await this.fillCharacterForm(options);

    const result = await this.submitCharacterForm();

    if (result.success) {
      // Wait for character to appear in grid
      await expect(this.getCharacterCardByName(options.name)).toBeVisible({ timeout: 5000 });
    }

    return result;
  }

  /**
   * Click on a character card to view details
   */
  async viewCharacterDetails(name: string) {
    const card = this.getCharacterCardByName(name);
    await expect(card).toBeVisible({ timeout: 5000 });
    await card.click();

    // Wait for detail view or modal
    await expect(this.page.locator('[data-testid="character-detail"], text=Reference Images')).toBeVisible({ timeout: 5000 });
  }

  /**
   * Delete a character
   */
  async deleteCharacter(name: string): Promise<{ success: boolean }> {
    const card = this.getCharacterCardByName(name);
    await expect(card).toBeVisible({ timeout: 5000 });

    // Hover to reveal delete button
    await card.hover();

    // Find and click delete button
    const deleteBtn = card.locator('[data-testid="delete-character-btn"], button:has(svg.lucide-trash-2)');

    // Handle confirmation dialog
    this.page.once('dialog', async (dialog) => {
      await dialog.accept();
    });

    const responsePromise = this.waitForApi('/api/characters/', { method: 'DELETE', timeout: 10000 });
    await deleteBtn.click();

    try {
      const response = await responsePromise;
      const success = response.status() === 200 || response.status() === 204;

      if (success) {
        // Wait for character to disappear
        await expect(card).toBeHidden({ timeout: 5000 });
      }

      return { success };
    } catch {
      return { success: false };
    }
  }

  /**
   * Verify character exists in grid
   */
  async verifyCharacterExists(name: string): Promise<boolean> {
    try {
      await expect(this.getCharacterCardByName(name)).toBeVisible({ timeout: 3000 });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Verify character does NOT exist in grid
   */
  async verifyCharacterNotExists(name: string): Promise<boolean> {
    try {
      await expect(this.getCharacterCardByName(name)).toBeHidden({ timeout: 3000 });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Close the form/modal if open
   */
  async closeFormIfOpen() {
    if (await this.cancelBtn.isVisible()) {
      await this.cancelBtn.click();
      await expect(this.characterForm).toBeHidden({ timeout: 3000 });
    }
  }
}
