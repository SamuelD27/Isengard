/**
 * Test Fixtures for Isengard E2E
 *
 * Provides reusable setup/teardown and utilities for tests:
 * - Page object instances
 * - Network error capture
 * - Console log capture
 * - Test data seeding
 * - API mocking capabilities
 */

import { test as base, expect, Page, BrowserContext, Response, ConsoleMessage, Request } from '@playwright/test';
import { CharactersPage } from '../pages/characters.page';
import { TrainingPage } from '../pages/training.page';
import { GenerationPage } from '../pages/generation.page';
import { DatasetPage } from '../pages/dataset.page';
import { TestDataSeeder, TEST_CHARACTERS, TestCharacterKey, SeededCharacter } from './test-data';
import fs from 'fs';
import path from 'path';

// Types for network/console capture
interface NetworkError {
  url: string;
  method: string;
  status: number;
  statusText: string;
  body: string;
  timestamp: number;
}

interface ConsoleError {
  type: string;
  text: string;
  location: string;
  timestamp: number;
}

interface TestContext {
  networkErrors: NetworkError[];
  consoleErrors: ConsoleError[];
  apiCalls: { url: string; method: string; status: number; duration: number }[];
}

// Extended test fixtures
export const test = base.extend<{
  // Page objects
  charactersPage: CharactersPage;
  trainingPage: TrainingPage;
  generationPage: GenerationPage;
  datasetPage: DatasetPage;

  // Test context
  testContext: TestContext;

  // Test data seeder
  testDataSeeder: TestDataSeeder;

  // Helpers
  captureNetworkErrors: () => void;
  captureConsoleErrors: () => void;
  waitForApiReady: () => Promise<void>;
  createTestCharacter: (name?: string) => Promise<string>;
  deleteTestCharacter: (id: string) => Promise<void>;
  seedCharacter: (key: TestCharacterKey) => Promise<SeededCharacter>;
}>({
  // Page Object fixtures
  charactersPage: async ({ page }, use) => {
    const charactersPage = new CharactersPage(page);
    await use(charactersPage);
  },

  trainingPage: async ({ page }, use) => {
    const trainingPage = new TrainingPage(page);
    await use(trainingPage);
  },

  generationPage: async ({ page }, use) => {
    const generationPage = new GenerationPage(page);
    await use(generationPage);
  },

  datasetPage: async ({ page }, use) => {
    const datasetPage = new DatasetPage(page);
    await use(datasetPage);
  },

  // Test context for collecting errors
  testContext: async ({ page }, use) => {
    const context: TestContext = {
      networkErrors: [],
      consoleErrors: [],
      apiCalls: [],
    };

    // Capture failed requests
    page.on('response', async (response: Response) => {
      const url = response.url();
      if (!url.includes('/api/')) return;

      const request = response.request();
      const timing = request.timing();

      context.apiCalls.push({
        url,
        method: request.method(),
        status: response.status(),
        duration: timing.responseEnd - timing.requestStart,
      });

      if (response.status() >= 400) {
        let body = '';
        try {
          body = await response.text();
        } catch {}

        context.networkErrors.push({
          url,
          method: request.method(),
          status: response.status(),
          statusText: response.statusText(),
          body: body.slice(0, 500),
          timestamp: Date.now(),
        });
      }
    });

    // Capture console errors
    page.on('console', (msg: ConsoleMessage) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        context.consoleErrors.push({
          type: msg.type(),
          text: msg.text(),
          location: msg.location()?.url || '',
          timestamp: Date.now(),
        });
      }
    });

    // Capture page errors
    page.on('pageerror', (error) => {
      context.consoleErrors.push({
        type: 'pageerror',
        text: error.message,
        location: error.stack || '',
        timestamp: Date.now(),
      });
    });

    await use(context);
  },

  // Helper: Wait for API to be ready
  waitForApiReady: async ({ page }, use) => {
    const waitForApiReady = async () => {
      const apiUrl = process.env.E2E_API_URL || 'http://localhost:8000';
      let attempts = 0;
      const maxAttempts = 30;

      while (attempts < maxAttempts) {
        try {
          const response = await page.request.get(`${apiUrl}/health`);
          if (response.ok()) {
            return;
          }
        } catch {}
        await page.waitForTimeout(1000);
        attempts++;
      }

      throw new Error('API not ready after 30 seconds');
    };

    await use(waitForApiReady);
  },

  // Helper: Create a test character
  createTestCharacter: async ({ page }, use) => {
    const createdIds: string[] = [];

    const createTestCharacter = async (name?: string): Promise<string> => {
      const apiUrl = process.env.E2E_API_URL || 'http://localhost:8000';
      const charName = name || `E2E Test ${Date.now()}`;
      const triggerWord = `e2e_test_${Date.now()}`;

      const response = await page.request.post(`${apiUrl}/api/characters`, {
        data: {
          name: charName,
          trigger_word: triggerWord,
          description: 'Created by E2E tests',
        },
      });

      if (!response.ok()) {
        throw new Error(`Failed to create character: ${await response.text()}`);
      }

      const data = await response.json();
      createdIds.push(data.id);
      return data.id;
    };

    await use(createTestCharacter);

    // Cleanup: delete all created characters
    const apiUrl = process.env.E2E_API_URL || 'http://localhost:8000';
    for (const id of createdIds) {
      try {
        await fetch(`${apiUrl}/api/characters/${id}`, { method: 'DELETE' });
      } catch {}
    }
  },

  // Helper: Delete a test character
  deleteTestCharacter: async ({ page }, use) => {
    const deleteTestCharacter = async (id: string) => {
      const apiUrl = process.env.E2E_API_URL || 'http://localhost:8000';
      await page.request.delete(`${apiUrl}/api/characters/${id}`);
    };

    await use(deleteTestCharacter);
  },

  // Test data seeder fixture
  testDataSeeder: async ({ page }, use) => {
    const seeder = new TestDataSeeder(page);
    await use(seeder);
    // Cleanup after test
    await seeder.cleanup();
  },

  // Convenience fixture: seed a predefined character
  seedCharacter: async ({ page }, use) => {
    const seeder = new TestDataSeeder(page);

    const seedCharacter = async (key: TestCharacterKey): Promise<SeededCharacter> => {
      return seeder.seedCharacter(key);
    };

    await use(seedCharacter);

    // Cleanup after test
    await seeder.cleanup();
  },
});

// Re-export expect for convenience
export { expect };

// Re-export test data utilities
export { TestDataSeeder, TEST_CHARACTERS, cleanupTestData } from './test-data';
export type { TestCharacterKey, SeededCharacter } from './test-data';

// Test tags for filtering
export const tags = {
  smoke: '@smoke',
  critical: '@critical',
  slow: '@slow',
  visual: '@visual',
  training: '@training',
  characters: '@characters',
  generation: '@generation',
};
