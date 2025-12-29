/**
 * Test Data Seeding for Isengard E2E
 *
 * Provides deterministic test data that can be seeded before tests
 * and cleaned up after. This ensures tests run against known data.
 *
 * Usage:
 *   const seeder = new TestDataSeeder(page);
 *   await seeder.seedCharacter('alice');
 *   // ... run tests ...
 *   await seeder.cleanup();
 */

import { Page } from '@playwright/test';

// ============================================================
// TEST DATA CONSTANTS
// ============================================================

export const TEST_CHARACTERS = {
  alice: {
    name: 'E2E Alice',
    trigger_word: 'e2e_alice',
    description: 'Test character for E2E - Alice',
  },
  bob: {
    name: 'E2E Bob',
    trigger_word: 'e2e_bob',
    description: 'Test character for E2E - Bob',
  },
  charlie: {
    name: 'E2E Charlie',
    trigger_word: 'e2e_charlie',
    description: 'Test character for E2E - Charlie',
  },
} as const;

export type TestCharacterKey = keyof typeof TEST_CHARACTERS;

export interface SeededCharacter {
  id: string;
  name: string;
  trigger_word: string;
  image_count: number;
}

export interface SeededTrainingJob {
  id: string;
  character_id: string;
  status: string;
}

// ============================================================
// TEST DATA SEEDER CLASS
// ============================================================

export class TestDataSeeder {
  private page: Page;
  private apiUrl: string;
  private createdCharacterIds: string[] = [];
  private createdJobIds: string[] = [];
  private seededCharacters: Map<TestCharacterKey, SeededCharacter> = new Map();

  constructor(page: Page, apiUrl?: string) {
    this.page = page;
    this.apiUrl = apiUrl || process.env.E2E_API_URL || 'http://localhost:8000';
  }

  // --------------------------------------------------------
  // CHARACTER SEEDING
  // --------------------------------------------------------

  /**
   * Seed a predefined test character
   */
  async seedCharacter(key: TestCharacterKey): Promise<SeededCharacter> {
    // Check if already seeded
    const existing = this.seededCharacters.get(key);
    if (existing) {
      return existing;
    }

    const template = TEST_CHARACTERS[key];

    // Check if character already exists (from previous run)
    const existingChar = await this.findCharacterByTrigger(template.trigger_word);
    if (existingChar) {
      this.seededCharacters.set(key, existingChar);
      this.createdCharacterIds.push(existingChar.id);
      return existingChar;
    }

    // Create new character
    const response = await this.page.request.post(`${this.apiUrl}/api/characters`, {
      data: template,
    });

    if (!response.ok()) {
      const error = await response.text();
      throw new Error(`Failed to seed character '${key}': ${error}`);
    }

    const data = await response.json();
    const seeded: SeededCharacter = {
      id: data.id,
      name: data.name,
      trigger_word: data.trigger_word,
      image_count: data.image_count || 0,
    };

    this.seededCharacters.set(key, seeded);
    this.createdCharacterIds.push(data.id);

    return seeded;
  }

  /**
   * Seed all predefined test characters
   */
  async seedAllCharacters(): Promise<Map<TestCharacterKey, SeededCharacter>> {
    for (const key of Object.keys(TEST_CHARACTERS) as TestCharacterKey[]) {
      await this.seedCharacter(key);
    }
    return this.seededCharacters;
  }

  /**
   * Get a seeded character by key
   */
  getCharacter(key: TestCharacterKey): SeededCharacter | undefined {
    return this.seededCharacters.get(key);
  }

  /**
   * Create a custom test character (for one-off tests)
   */
  async createCustomCharacter(name: string, triggerWord?: string): Promise<SeededCharacter> {
    const trigger = triggerWord || `e2e_custom_${Date.now()}`;

    const response = await this.page.request.post(`${this.apiUrl}/api/characters`, {
      data: {
        name,
        trigger_word: trigger,
        description: 'Custom E2E test character',
      },
    });

    if (!response.ok()) {
      const error = await response.text();
      throw new Error(`Failed to create custom character: ${error}`);
    }

    const data = await response.json();
    this.createdCharacterIds.push(data.id);

    return {
      id: data.id,
      name: data.name,
      trigger_word: data.trigger_word,
      image_count: data.image_count || 0,
    };
  }

  // --------------------------------------------------------
  // HELPER METHODS
  // --------------------------------------------------------

  /**
   * Find existing character by trigger word
   */
  private async findCharacterByTrigger(triggerWord: string): Promise<SeededCharacter | null> {
    try {
      const response = await this.page.request.get(`${this.apiUrl}/api/characters`);
      if (!response.ok()) return null;

      const characters = await response.json();
      const found = characters.find((c: any) => c.trigger_word === triggerWord);

      if (found) {
        return {
          id: found.id,
          name: found.name,
          trigger_word: found.trigger_word,
          image_count: found.image_count || 0,
        };
      }
    } catch {
      // Ignore errors
    }
    return null;
  }

  /**
   * Delete a specific character
   */
  async deleteCharacter(id: string): Promise<void> {
    try {
      await this.page.request.delete(`${this.apiUrl}/api/characters/${id}`);
    } catch {
      // Ignore deletion errors
    }
  }

  // --------------------------------------------------------
  // CLEANUP
  // --------------------------------------------------------

  /**
   * Clean up all seeded test data
   */
  async cleanup(): Promise<void> {
    // Delete all created characters
    for (const id of this.createdCharacterIds) {
      await this.deleteCharacter(id);
    }

    // Clear tracking
    this.createdCharacterIds = [];
    this.createdJobIds = [];
    this.seededCharacters.clear();
  }

  /**
   * Clean up only E2E test data (by prefix)
   * Use this to clean up data from failed test runs
   */
  async cleanupAllE2EData(): Promise<{ deleted: number }> {
    let deleted = 0;

    try {
      const response = await this.page.request.get(`${this.apiUrl}/api/characters`);
      if (response.ok()) {
        const characters = await response.json();

        for (const char of characters) {
          // Delete characters with E2E prefixes
          if (
            char.trigger_word?.startsWith('e2e_') ||
            char.name?.startsWith('E2E ')
          ) {
            await this.deleteCharacter(char.id);
            deleted++;
          }
        }
      }
    } catch {
      // Ignore errors during cleanup
    }

    return { deleted };
  }
}

// ============================================================
// STANDALONE CLEANUP FUNCTION
// ============================================================

/**
 * Clean up all E2E test data from the API
 * Can be called from global setup/teardown
 */
export async function cleanupTestData(apiUrl?: string): Promise<void> {
  const url = apiUrl || process.env.E2E_API_URL || 'http://localhost:8000';

  try {
    const response = await fetch(`${url}/api/characters`);
    if (!response.ok) return;

    const characters = await response.json();

    for (const char of characters) {
      if (
        char.trigger_word?.startsWith('e2e_') ||
        char.name?.startsWith('E2E ')
      ) {
        try {
          await fetch(`${url}/api/characters/${char.id}`, { method: 'DELETE' });
        } catch {
          // Ignore individual deletion errors
        }
      }
    }
  } catch {
    // Ignore errors during cleanup
  }
}
