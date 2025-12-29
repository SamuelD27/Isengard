/**
 * UELR Storage Module
 *
 * Provides persistent storage for interactions and steps using IndexedDB
 * with localStorage fallback. Handles retention limits and sync queue.
 */

import type { UELRInteraction, UELRStep } from './types';

const DB_NAME = 'uelr_db';
const DB_VERSION = 1;
const STORE_INTERACTIONS = 'interactions';
const STORE_STEPS = 'steps';
const STORE_SYNC_QUEUE = 'sync_queue';

// Retention limits
const MAX_INTERACTIONS = 500;
const MAX_STEPS_PER_INTERACTION = 200;
const RETENTION_DAYS = 7;

type SyncQueueItem = {
  id: string;
  type: 'interaction' | 'steps' | 'complete';
  data: unknown;
  created_at: string;
  retry_count: number;
};

class UELRStorage {
  private db: IDBDatabase | null = null;
  private dbReady: Promise<void>;
  private useLocalStorage = false;

  constructor() {
    this.dbReady = this.initDB();
  }

  private async initDB(): Promise<void> {
    if (typeof indexedDB === 'undefined') {
      console.warn('[UELR] IndexedDB not available, falling back to localStorage');
      this.useLocalStorage = true;
      return;
    }

    return new Promise((resolve) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => {
        console.warn('[UELR] IndexedDB open failed, falling back to localStorage');
        this.useLocalStorage = true;
        resolve();
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Interactions store with indexes
        if (!db.objectStoreNames.contains(STORE_INTERACTIONS)) {
          const interactionStore = db.createObjectStore(STORE_INTERACTIONS, {
            keyPath: 'interaction_id',
          });
          interactionStore.createIndex('started_at', 'started_at', { unique: false });
          interactionStore.createIndex('action_name', 'action_name', { unique: false });
          interactionStore.createIndex('status', 'status', { unique: false });
          interactionStore.createIndex('correlation_id', 'correlation_id', { unique: false });
        }

        // Steps store with indexes
        if (!db.objectStoreNames.contains(STORE_STEPS)) {
          const stepsStore = db.createObjectStore(STORE_STEPS, {
            keyPath: 'step_id',
          });
          stepsStore.createIndex('interaction_id', 'interaction_id', { unique: false });
          stepsStore.createIndex('timestamp', 'timestamp', { unique: false });
        }

        // Sync queue for offline support
        if (!db.objectStoreNames.contains(STORE_SYNC_QUEUE)) {
          const syncStore = db.createObjectStore(STORE_SYNC_QUEUE, {
            keyPath: 'id',
          });
          syncStore.createIndex('created_at', 'created_at', { unique: false });
        }
      };
    });
  }

  async waitForReady(): Promise<void> {
    await this.dbReady;
  }

  // ============ Interaction Methods ============

  async saveInteraction(interaction: UELRInteraction): Promise<void> {
    await this.dbReady;

    if (this.useLocalStorage) {
      const interactions = this.getLocalStorageInteractions();
      const index = interactions.findIndex(
        (i) => i.interaction_id === interaction.interaction_id
      );
      if (index >= 0) {
        interactions[index] = interaction;
      } else {
        interactions.unshift(interaction);
      }
      // Enforce retention
      while (interactions.length > MAX_INTERACTIONS) {
        interactions.pop();
      }
      localStorage.setItem('uelr_interactions', JSON.stringify(interactions));
      return;
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_INTERACTIONS], 'readwrite');
      const store = transaction.objectStore(STORE_INTERACTIONS);
      const request = store.put(interaction);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getInteraction(interactionId: string): Promise<UELRInteraction | null> {
    await this.dbReady;

    if (this.useLocalStorage) {
      const interactions = this.getLocalStorageInteractions();
      return interactions.find((i) => i.interaction_id === interactionId) || null;
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_INTERACTIONS], 'readonly');
      const store = transaction.objectStore(STORE_INTERACTIONS);
      const request = store.get(interactionId);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  async listInteractions(
    limit: number = 50,
    offset: number = 0,
    filters?: {
      action_name?: string;
      status?: string;
      correlation_id?: string;
    }
  ): Promise<{ interactions: UELRInteraction[]; total: number }> {
    await this.dbReady;

    if (this.useLocalStorage) {
      let interactions = this.getLocalStorageInteractions();
      if (filters?.action_name) {
        interactions = interactions.filter((i) =>
          i.action_name.toLowerCase().includes(filters.action_name!.toLowerCase())
        );
      }
      if (filters?.status) {
        interactions = interactions.filter((i) => i.status === filters.status);
      }
      if (filters?.correlation_id) {
        interactions = interactions.filter((i) =>
          i.correlation_id === filters.correlation_id
        );
      }
      return {
        interactions: interactions.slice(offset, offset + limit),
        total: interactions.length,
      };
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_INTERACTIONS], 'readonly');
      const store = transaction.objectStore(STORE_INTERACTIONS);
      const index = store.index('started_at');
      const request = index.openCursor(null, 'prev'); // Newest first

      const results: UELRInteraction[] = [];
      let skipped = 0;
      let total = 0;

      request.onsuccess = () => {
        const cursor = request.result;
        if (cursor) {
          const interaction = cursor.value as UELRInteraction;
          let matches = true;

          if (filters?.action_name) {
            matches =
              matches &&
              interaction.action_name
                .toLowerCase()
                .includes(filters.action_name.toLowerCase());
          }
          if (filters?.status) {
            matches = matches && interaction.status === filters.status;
          }
          if (filters?.correlation_id) {
            matches = matches && interaction.correlation_id === filters.correlation_id;
          }

          if (matches) {
            total++;
            if (skipped < offset) {
              skipped++;
            } else if (results.length < limit) {
              results.push(interaction);
            }
          }

          cursor.continue();
        } else {
          resolve({ interactions: results, total });
        }
      };
      request.onerror = () => reject(request.error);
    });
  }

  // ============ Steps Methods ============

  async saveSteps(steps: UELRStep[]): Promise<void> {
    await this.dbReady;

    if (this.useLocalStorage) {
      const allSteps = this.getLocalStorageSteps();
      for (const step of steps) {
        allSteps.push(step);
      }
      // Simple size limit
      while (allSteps.length > MAX_INTERACTIONS * MAX_STEPS_PER_INTERACTION) {
        allSteps.shift();
      }
      localStorage.setItem('uelr_steps', JSON.stringify(allSteps));
      return;
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_STEPS], 'readwrite');
      const store = transaction.objectStore(STORE_STEPS);

      let completed = 0;
      for (const step of steps) {
        const request = store.put(step);
        request.onsuccess = () => {
          completed++;
          if (completed === steps.length) {
            resolve();
          }
        };
        request.onerror = () => reject(request.error);
      }

      if (steps.length === 0) {
        resolve();
      }
    });
  }

  async getStepsForInteraction(interactionId: string): Promise<UELRStep[]> {
    await this.dbReady;

    if (this.useLocalStorage) {
      const steps = this.getLocalStorageSteps();
      return steps
        .filter((s) => s.interaction_id === interactionId)
        .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_STEPS], 'readonly');
      const store = transaction.objectStore(STORE_STEPS);
      const index = store.index('interaction_id');
      const request = index.getAll(interactionId);
      request.onsuccess = () => {
        const steps = (request.result as UELRStep[]).sort((a, b) =>
          a.timestamp.localeCompare(b.timestamp)
        );
        resolve(steps);
      };
      request.onerror = () => reject(request.error);
    });
  }

  // ============ Sync Queue Methods ============

  async addToSyncQueue(item: Omit<SyncQueueItem, 'id' | 'created_at' | 'retry_count'>): Promise<void> {
    await this.dbReady;

    const queueItem: SyncQueueItem = {
      id: `sync-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      created_at: new Date().toISOString(),
      retry_count: 0,
      ...item,
    };

    if (this.useLocalStorage) {
      const queue = this.getLocalStorageSyncQueue();
      queue.push(queueItem);
      localStorage.setItem('uelr_sync_queue', JSON.stringify(queue));
      return;
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_SYNC_QUEUE], 'readwrite');
      const store = transaction.objectStore(STORE_SYNC_QUEUE);
      const request = store.put(queueItem);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getSyncQueueItems(): Promise<SyncQueueItem[]> {
    await this.dbReady;

    if (this.useLocalStorage) {
      return this.getLocalStorageSyncQueue();
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_SYNC_QUEUE], 'readonly');
      const store = transaction.objectStore(STORE_SYNC_QUEUE);
      const request = store.getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async removeSyncQueueItem(id: string): Promise<void> {
    await this.dbReady;

    if (this.useLocalStorage) {
      const queue = this.getLocalStorageSyncQueue();
      const index = queue.findIndex((item) => item.id === id);
      if (index >= 0) {
        queue.splice(index, 1);
        localStorage.setItem('uelr_sync_queue', JSON.stringify(queue));
      }
      return;
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_SYNC_QUEUE], 'readwrite');
      const store = transaction.objectStore(STORE_SYNC_QUEUE);
      const request = store.delete(id);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async updateSyncQueueRetry(id: string): Promise<void> {
    await this.dbReady;

    if (this.useLocalStorage) {
      const queue = this.getLocalStorageSyncQueue();
      const item = queue.find((item) => item.id === id);
      if (item) {
        item.retry_count++;
        localStorage.setItem('uelr_sync_queue', JSON.stringify(queue));
      }
      return;
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_SYNC_QUEUE], 'readwrite');
      const store = transaction.objectStore(STORE_SYNC_QUEUE);
      const getRequest = store.get(id);
      getRequest.onsuccess = () => {
        const item = getRequest.result;
        if (item) {
          item.retry_count++;
          store.put(item);
        }
        resolve();
      };
      getRequest.onerror = () => reject(getRequest.error);
    });
  }

  // ============ Cleanup Methods ============

  async cleanupOldData(): Promise<void> {
    await this.dbReady;

    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - RETENTION_DAYS);
    const cutoffISO = cutoffDate.toISOString();

    if (this.useLocalStorage) {
      // Clean old interactions
      const interactions = this.getLocalStorageInteractions();
      const validInteractions = interactions.filter(
        (i) => i.started_at >= cutoffISO
      );
      localStorage.setItem('uelr_interactions', JSON.stringify(validInteractions));

      // Clean orphaned steps
      const validIds = new Set(validInteractions.map((i) => i.interaction_id));
      const steps = this.getLocalStorageSteps();
      const validSteps = steps.filter((s) => validIds.has(s.interaction_id));
      localStorage.setItem('uelr_steps', JSON.stringify(validSteps));
      return;
    }

    // IndexedDB cleanup
    const transaction = this.db!.transaction(
      [STORE_INTERACTIONS, STORE_STEPS],
      'readwrite'
    );

    // Get old interaction IDs
    const interactionStore = transaction.objectStore(STORE_INTERACTIONS);
    const stepsStore = transaction.objectStore(STORE_STEPS);

    const oldInteractionIds: string[] = [];
    const index = interactionStore.index('started_at');
    const range = IDBKeyRange.upperBound(cutoffISO);

    await new Promise<void>((resolve) => {
      const request = index.openCursor(range);
      request.onsuccess = () => {
        const cursor = request.result;
        if (cursor) {
          oldInteractionIds.push(cursor.value.interaction_id);
          cursor.delete();
          cursor.continue();
        } else {
          resolve();
        }
      };
    });

    // Delete associated steps
    for (const interactionId of oldInteractionIds) {
      const stepsIndex = stepsStore.index('interaction_id');
      await new Promise<void>((resolve) => {
        const request = stepsIndex.openCursor(IDBKeyRange.only(interactionId));
        request.onsuccess = () => {
          const cursor = request.result;
          if (cursor) {
            cursor.delete();
            cursor.continue();
          } else {
            resolve();
          }
        };
      });
    }

    // Enforce max interactions
    await this.enforceInteractionLimit();
  }

  private async enforceInteractionLimit(): Promise<void> {
    if (this.useLocalStorage) return;

    const { total } = await this.listInteractions(1, 0);
    if (total <= MAX_INTERACTIONS) return;

    const toDelete = total - MAX_INTERACTIONS;

    return new Promise((resolve) => {
      const transaction = this.db!.transaction(
        [STORE_INTERACTIONS, STORE_STEPS],
        'readwrite'
      );
      const interactionStore = transaction.objectStore(STORE_INTERACTIONS);
      const stepsStore = transaction.objectStore(STORE_STEPS);
      const index = interactionStore.index('started_at');

      let deleted = 0;
      const request = index.openCursor(null, 'next'); // Oldest first

      request.onsuccess = () => {
        const cursor = request.result;
        if (cursor && deleted < toDelete) {
          const interactionId = cursor.value.interaction_id;

          // Delete steps
          const stepsIndex = stepsStore.index('interaction_id');
          stepsIndex.openCursor(IDBKeyRange.only(interactionId)).onsuccess = (e) => {
            const stepCursor = (e.target as IDBRequest).result;
            if (stepCursor) {
              stepCursor.delete();
              stepCursor.continue();
            }
          };

          // Delete interaction
          cursor.delete();
          deleted++;
          cursor.continue();
        } else {
          resolve();
        }
      };
    });
  }

  // ============ localStorage Helpers ============

  private getLocalStorageInteractions(): UELRInteraction[] {
    try {
      const data = localStorage.getItem('uelr_interactions');
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  private getLocalStorageSteps(): UELRStep[] {
    try {
      const data = localStorage.getItem('uelr_steps');
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  private getLocalStorageSyncQueue(): SyncQueueItem[] {
    try {
      const data = localStorage.getItem('uelr_sync_queue');
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  // ============ Export for debugging ============

  async exportAll(): Promise<{
    interactions: UELRInteraction[];
    steps: UELRStep[];
  }> {
    await this.dbReady;

    const { interactions } = await this.listInteractions(MAX_INTERACTIONS, 0);

    if (this.useLocalStorage) {
      return {
        interactions,
        steps: this.getLocalStorageSteps(),
      };
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_STEPS], 'readonly');
      const store = transaction.objectStore(STORE_STEPS);
      const request = store.getAll();
      request.onsuccess = () => {
        resolve({
          interactions,
          steps: request.result,
        });
      };
      request.onerror = () => reject(request.error);
    });
  }
}

// Singleton instance
export const uelrStorage = new UELRStorage();
