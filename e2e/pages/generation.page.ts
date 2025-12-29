/**
 * Generation Page Object
 *
 * Encapsulates all interactions with the Image Generation page.
 */

import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export interface GenerationConfig {
  prompt: string;
  negativePrompt?: string;
  aspectRatio?: string;
  quality?: 'draft' | 'standard' | 'high';
  lora?: string;
  loraStrength?: number;
  useControlnet?: boolean;
  useIpadapter?: boolean;
  useFacedetailer?: boolean;
  useUpscale?: boolean;
}

export class GenerationPage extends BasePage {
  // Locators
  readonly promptInput: Locator;
  readonly negativePromptInput: Locator;
  readonly aspectRatioSelect: Locator;
  readonly qualitySelect: Locator;
  readonly loraSelect: Locator;
  readonly loraStrengthSlider: Locator;
  readonly generateBtn: Locator;
  readonly outputGallery: Locator;
  readonly jobQueue: Locator;

  constructor(page: Page) {
    super(page);

    this.promptInput = page.locator('[data-testid="prompt-input"], textarea[placeholder*="prompt"], #prompt');
    this.negativePromptInput = page.locator('[data-testid="negative-prompt-input"], textarea[placeholder*="negative"]');
    this.aspectRatioSelect = page.locator('[data-testid="aspect-ratio-select"]');
    this.qualitySelect = page.locator('[data-testid="quality-select"]');
    this.loraSelect = page.locator('[data-testid="lora-select"]');
    this.loraStrengthSlider = page.locator('[data-testid="lora-strength-slider"]');
    this.generateBtn = page.locator('[data-testid="generate-btn"], button:has-text("Generate")');
    this.outputGallery = page.locator('[data-testid="output-gallery"], .output-gallery');
    this.jobQueue = page.locator('[data-testid="job-queue"], .generation-jobs');
  }

  get url(): string {
    return '/generate';
  }

  async waitForPageReady(): Promise<void> {
    await expect(this.promptInput).toBeVisible({ timeout: 10000 });
    await this.waitForLoadingComplete();
  }

  /**
   * Fill in the prompt
   */
  async enterPrompt(prompt: string) {
    await expect(this.promptInput).toBeVisible();
    await this.promptInput.clear();
    await this.promptInput.fill(prompt);
  }

  /**
   * Fill in the negative prompt
   */
  async enterNegativePrompt(prompt: string) {
    if (await this.negativePromptInput.isVisible()) {
      await this.negativePromptInput.clear();
      await this.negativePromptInput.fill(prompt);
    }
  }

  /**
   * Select aspect ratio
   */
  async selectAspectRatio(ratio: string) {
    const ratioBtn = this.page.locator(`[data-testid="aspect-${ratio}"], button:has-text("${ratio}")`);
    if (await ratioBtn.isVisible()) {
      await ratioBtn.click();
    }
  }

  /**
   * Select a LoRA
   */
  async selectLora(loraName: string) {
    if (await this.loraSelect.isVisible()) {
      await this.loraSelect.selectOption({ label: new RegExp(loraName) });
    }
  }

  /**
   * Configure and start generation
   */
  async configureGeneration(config: GenerationConfig) {
    await this.enterPrompt(config.prompt);

    if (config.negativePrompt) {
      await this.enterNegativePrompt(config.negativePrompt);
    }

    if (config.aspectRatio) {
      await this.selectAspectRatio(config.aspectRatio);
    }

    if (config.lora) {
      await this.selectLora(config.lora);
    }
  }

  /**
   * Click generate and wait for response
   */
  async generate(): Promise<{ success: boolean; jobId?: string; error?: string }> {
    await expect(this.generateBtn).toBeEnabled({ timeout: 5000 });

    const responsePromise = this.waitForApi('/api/generation', { method: 'POST', timeout: 15000 });

    await this.generateBtn.click();

    try {
      const response = await responsePromise;
      const status = response.status();

      if (status === 200 || status === 201 || status === 202) {
        const data = await response.json();
        return { success: true, jobId: data.id || data.job_id };
      }

      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || `HTTP ${status}`,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * Wait for output to appear in gallery
   */
  async waitForOutput(timeout = 60000): Promise<boolean> {
    try {
      await expect(this.outputGallery.locator('img')).toBeVisible({ timeout });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Get number of images in gallery
   */
  async getOutputCount(): Promise<number> {
    return this.outputGallery.locator('img').count();
  }
}
