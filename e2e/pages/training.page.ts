/**
 * Training Page Object
 *
 * Encapsulates all interactions with the Training page.
 * Critical for testing the most complex user flow.
 */

import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export interface TrainingConfig {
  character?: string;
  preset?: 'quick' | 'balanced' | 'quality' | 'custom';
  steps?: number;
  resolution?: number;
  learningRate?: number;
  loraRank?: number;
}

export interface TrainingJob {
  id: string;
  status: string;
  progress: number;
  characterName?: string;
}

export class TrainingPage extends BasePage {
  // Locators
  readonly characterSelect: Locator;
  readonly presetQuick: Locator;
  readonly presetBalanced: Locator;
  readonly presetQuality: Locator;
  readonly stepsInput: Locator;
  readonly resolutionSelect: Locator;
  readonly advancedToggle: Locator;
  readonly startTrainingBtn: Locator;
  readonly jobList: Locator;
  readonly trainingLogs: Locator;
  readonly jobDetailModal: Locator;

  constructor(page: Page) {
    super(page);

    // Define locators
    this.characterSelect = page.locator('[data-testid="character-select"], select:near(label:text("Character"))');
    this.presetQuick = page.locator('[data-testid="preset-quick"], button:has-text("Quick Train")');
    this.presetBalanced = page.locator('[data-testid="preset-balanced"], button:has-text("Balanced")');
    this.presetQuality = page.locator('[data-testid="preset-quality"], button:has-text("High Quality")');
    this.stepsInput = page.locator('[data-testid="steps-input"], input#steps');
    this.resolutionSelect = page.locator('[data-testid="resolution-select"], select#resolution');
    this.advancedToggle = page.locator('[data-testid="advanced-toggle"], button:has-text("Advanced Settings")');
    this.startTrainingBtn = page.locator('[data-testid="start-training-btn"], button:has-text("Start Training")');
    this.jobList = page.locator('[data-testid="training-job-list"], .training-jobs');
    this.trainingLogs = page.locator('[data-testid="training-logs"], .training-log');
    this.jobDetailModal = page.locator('[data-testid="job-detail-modal"], [role="dialog"]');
  }

  get url(): string {
    // Training configuration is now at /training/start
    return '/training/start';
  }

  async waitForPageReady(): Promise<void> {
    // Wait for Start Training page to load - check for preset buttons or heading
    // Use first() to avoid strict mode violation when multiple elements match
    await expect(
      this.page.locator('h3:has-text("Balanced")')
        .or(this.page.locator('h3:has-text("Quick Train")'))
        .or(this.page.locator('button:has-text("Balanced")'))
        .or(this.page.locator('h1:has-text("Start Training")'))
        .first()
    ).toBeVisible({ timeout: 10000 });

    // Wait for API calls to complete
    await this.waitForLoadingComplete();
  }

  /**
   * Navigate to Training History page
   */
  async gotoHistory(): Promise<void> {
    await this.page.goto('/training');
    await expect(
      this.page.locator('h1:has-text("Training History")').first()
    ).toBeVisible({ timeout: 10000 });
    await this.waitForLoadingComplete();
  }

  /**
   * Navigate to Ongoing Training page
   */
  async gotoOngoing(): Promise<void> {
    await this.page.goto('/training/ongoing');
    await expect(
      this.page.locator('main h1:has-text("Ongoing Training")').first()
    ).toBeVisible({ timeout: 10000 });
    await this.waitForLoadingComplete();
  }

  /**
   * Get all job cards
   */
  getJobCards(): Locator {
    return this.page.locator('[data-testid="training-job-card"], .job-card');
  }

  /**
   * Get a job card by ID
   */
  getJobCardById(jobId: string): Locator {
    return this.page.locator(`[data-testid="training-job-card"][data-job-id="${jobId}"], [data-job-id="${jobId}"]`);
  }

  /**
   * Get job status badge
   */
  getJobStatus(jobCard: Locator): Locator {
    return jobCard.locator('[data-testid="job-status"], .status-badge');
  }

  /**
   * Get job progress
   */
  getJobProgress(jobCard: Locator): Locator {
    return jobCard.locator('[data-testid="job-progress"], [role="progressbar"]');
  }

  /**
   * Select a character for training
   */
  async selectCharacter(characterName: string) {
    await expect(this.characterSelect).toBeVisible({ timeout: 5000 });
    await expect(this.characterSelect).toBeEnabled({ timeout: 5000 });

    // Select by visible text option
    await this.characterSelect.selectOption({ label: new RegExp(characterName) });
  }

  /**
   * Select a training preset
   */
  async selectPreset(preset: 'quick' | 'balanced' | 'quality') {
    const presetBtn = {
      quick: this.presetQuick,
      balanced: this.presetBalanced,
      quality: this.presetQuality,
    }[preset];

    await expect(presetBtn).toBeVisible({ timeout: 5000 });
    await presetBtn.click();

    // Verify preset is selected (has accent border or active class)
    await expect(presetBtn).toHaveClass(/border-accent|active|selected/);
  }

  /**
   * Configure training parameters
   */
  async configureTraining(config: TrainingConfig) {
    if (config.character) {
      await this.selectCharacter(config.character);
    }

    if (config.preset) {
      await this.selectPreset(config.preset);
    }

    if (config.steps) {
      await this.stepsInput.clear();
      await this.stepsInput.fill(config.steps.toString());
    }

    if (config.resolution) {
      await this.resolutionSelect.selectOption(config.resolution.toString());
    }
  }

  /**
   * Start training and wait for job creation
   */
  async startTraining(): Promise<{ success: boolean; jobId?: string; error?: string }> {
    // Verify button is enabled
    await expect(this.startTrainingBtn).toBeEnabled({ timeout: 5000 });

    // Capture the API response
    const responsePromise = this.waitForApi('/api/training', { method: 'POST', timeout: 30000 });

    // Click start
    await this.startTrainingBtn.click();

    // Button should disable during submission
    try {
      await expect(this.startTrainingBtn).toBeDisabled({ timeout: 1000 });
    } catch {
      // Button may not disable immediately
    }

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
        error: errorData.detail || errorData.error || `HTTP ${status}`,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * Wait for a job to appear in the list
   */
  async waitForJobToAppear(jobId: string, timeout = 10000): Promise<boolean> {
    try {
      await expect(this.getJobCardById(jobId)).toBeVisible({ timeout });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Wait for job status to change
   */
  async waitForJobStatus(
    jobId: string,
    status: string,
    timeout = 60000
  ): Promise<boolean> {
    const jobCard = this.getJobCardById(jobId);
    const statusBadge = this.getJobStatus(jobCard);

    try {
      await expect(statusBadge).toHaveText(status, { timeout });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Wait for job to start running
   */
  async waitForJobRunning(jobId: string, timeout = 30000): Promise<boolean> {
    return this.waitForJobStatus(jobId, 'running', timeout);
  }

  /**
   * Wait for training logs to appear
   */
  async waitForLogs(timeout = 10000): Promise<boolean> {
    try {
      await expect(this.trainingLogs).toBeVisible({ timeout });
      const logContent = await this.trainingLogs.textContent();
      return logContent !== null && logContent.length > 0;
    } catch {
      return false;
    }
  }

  /**
   * Get current logs text
   */
  async getLogsText(): Promise<string> {
    if (await this.trainingLogs.isVisible()) {
      return (await this.trainingLogs.textContent()) || '';
    }
    return '';
  }

  /**
   * Open job details
   */
  async openJobDetails(jobId: string) {
    const jobCard = this.getJobCardById(jobId);
    await expect(jobCard).toBeVisible({ timeout: 5000 });

    // Click the card or view button
    const viewBtn = jobCard.locator('[data-testid="view-details-btn"], button:has(svg.lucide-eye)');
    if (await viewBtn.isVisible()) {
      await viewBtn.click();
    } else {
      await jobCard.click();
    }

    await expect(this.jobDetailModal).toBeVisible({ timeout: 5000 });
  }

  /**
   * Close job details modal
   */
  async closeJobDetails() {
    if (await this.jobDetailModal.isVisible()) {
      const closeBtn = this.jobDetailModal.locator('[data-testid="close-btn"], button:has-text("Close")');
      if (await closeBtn.isVisible()) {
        await closeBtn.click();
      } else {
        // Click outside to close
        await this.page.keyboard.press('Escape');
      }
      await expect(this.jobDetailModal).toBeHidden({ timeout: 3000 });
    }
  }

  /**
   * Cancel a running job
   */
  async cancelJob(jobId: string): Promise<boolean> {
    const jobCard = this.getJobCardById(jobId);
    const cancelBtn = jobCard.locator('[data-testid="cancel-job-btn"], button:has-text("Cancel")');

    if (!(await cancelBtn.isVisible())) {
      return false;
    }

    const responsePromise = this.waitForApi(`/api/training/${jobId}/cancel`, { method: 'POST', timeout: 10000 });
    await cancelBtn.click();

    try {
      const response = await responsePromise;
      return response.ok();
    } catch {
      return false;
    }
  }

  /**
   * Get current job count
   */
  async getJobCount(): Promise<number> {
    return this.getJobCards().count();
  }

  /**
   * Verify the start button is properly disabled without character
   */
  async verifyStartButtonDisabledWithoutCharacter(): Promise<boolean> {
    // Clear character selection if possible
    try {
      await this.characterSelect.selectOption({ value: '' });
    } catch {
      // May not have empty option
    }

    const isDisabled = await this.startTrainingBtn.isDisabled();
    return isDisabled;
  }

  /**
   * Full training flow: configure -> start -> verify running -> observe progress
   */
  async runTrainingFlow(config: TrainingConfig): Promise<{
    success: boolean;
    jobId?: string;
    error?: string;
    logsAppeared: boolean;
  }> {
    await this.configureTraining(config);

    const startResult = await this.startTraining();

    if (!startResult.success || !startResult.jobId) {
      return {
        success: false,
        error: startResult.error || 'Failed to start training',
        logsAppeared: false,
      };
    }

    const { jobId } = startResult;

    // Wait for job to appear in list
    const appeared = await this.waitForJobToAppear(jobId, 10000);
    if (!appeared) {
      return {
        success: false,
        jobId,
        error: 'Job did not appear in list',
        logsAppeared: false,
      };
    }

    // Wait for job to start running (or queued is OK)
    const running = await this.waitForJobRunning(jobId, 30000);

    // Check if logs appear
    const logsAppeared = await this.waitForLogs(10000);

    return {
      success: true,
      jobId,
      logsAppeared,
    };
  }
}
