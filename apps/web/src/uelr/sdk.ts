/**
 * UELR SDK - Core Module
 *
 * Provides the main API for tracking user interactions end-to-end.
 *
 * Usage:
 *   const interaction = uelr.startInteraction('Create Character', { category: 'character' });
 *   try {
 *     // ... do work
 *     await uelr.completeInteraction(interaction, 'success');
 *   } catch (error) {
 *     await uelr.completeInteraction(interaction, 'error', error);
 *   }
 *
 * Or use the wrapper:
 *   const handleClick = uelr.wrapAction('Create Character', async () => {
 *     // ... do work
 *   });
 */

import type {
  UELRInteraction,
  UELRStep,
  StepStatus,
  CreateInteractionRequest,
  AppendStepsRequest,
  CompleteInteractionRequest,
} from './types';
import { uelrStorage } from './storage';
import { sanitize, sanitizeBody, sanitizeError } from './sanitize';

// Generate unique IDs
function generateId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

// Batching configuration
const BATCH_INTERVAL_MS = 250;
const MAX_BATCH_SIZE = 50;
const SYNC_RETRY_INTERVAL_MS = 30000;
const MAX_RETRY_COUNT = 5;

interface InteractionContext {
  interaction_id: string;
  correlation_id: string;
  action_name: string;
  started_at: Date;
  steps: UELRStep[];
  step_count: number;
  error_count: number;
}

class UELRSDK {
  private activeInteractions: Map<string, InteractionContext> = new Map();
  private stepBatch: UELRStep[] = [];
  private batchTimer: ReturnType<typeof setTimeout> | null = null;
  private syncTimerRef: ReturnType<typeof setInterval> | null = null;
  private apiBaseUrl: string = '/api';
  private isOnline: boolean = true;

  constructor() {
    // Initialize storage and start sync
    this.init();
  }

  private async init() {
    await uelrStorage.waitForReady();

    // Monitor online status
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => {
        this.isOnline = true;
        this.processSyncQueue();
      });
      window.addEventListener('offline', () => {
        this.isOnline = false;
      });

      // Clean up old data periodically
      uelrStorage.cleanupOldData();
      setInterval(() => uelrStorage.cleanupOldData(), 60 * 60 * 1000); // Every hour

      // Start sync queue processing
      this.startSyncProcessor();
    }
  }

  // ============ Core API ============

  /**
   * Start a new interaction. Returns context to use for subsequent steps.
   */
  startInteraction(
    actionName: string,
    meta?: {
      category?: string;
      page?: string;
      correlationId?: string;
    }
  ): InteractionContext {
    const interaction_id = generateId('int');
    const correlation_id = meta?.correlationId || generateId('cor');
    const started_at = new Date();

    const context: InteractionContext = {
      interaction_id,
      correlation_id,
      action_name: actionName,
      started_at,
      steps: [],
      step_count: 0,
      error_count: 0,
    };

    this.activeInteractions.set(interaction_id, context);

    // Log the start step
    this.logStep(context, {
      type: 'UI_ACTION_START',
      component: 'frontend',
      message: `Started: ${actionName}`,
      status: 'pending',
      details: {
        page: meta?.page || (typeof window !== 'undefined' ? window.location.pathname : undefined),
        category: meta?.category,
      },
    });

    // Create interaction record
    const interaction: UELRInteraction = {
      interaction_id,
      correlation_id,
      action_name: actionName,
      action_category: meta?.category,
      started_at: started_at.toISOString(),
      status: 'pending',
      page: meta?.page || (typeof window !== 'undefined' ? window.location.pathname : undefined),
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
      step_count: 1,
      error_count: 0,
    };

    // Save locally
    uelrStorage.saveInteraction(interaction);

    // Queue for backend sync
    this.queueForSync({
      type: 'interaction',
      data: {
        interaction_id,
        correlation_id,
        action_name: actionName,
        action_category: meta?.category,
        page: interaction.page,
        user_agent: interaction.user_agent,
      } as CreateInteractionRequest,
    });

    return context;
  }

  /**
   * Log a step within an interaction
   */
  logStep(
    context: InteractionContext,
    step: Omit<UELRStep, 'step_id' | 'interaction_id' | 'correlation_id' | 'timestamp'>
  ): UELRStep {
    const fullStep: UELRStep = {
      step_id: generateId('step'),
      interaction_id: context.interaction_id,
      correlation_id: context.correlation_id,
      timestamp: new Date().toISOString(),
      ...step,
      details: step.details ? sanitize(step.details) : undefined,
    };

    context.steps.push(fullStep);
    context.step_count++;
    if (step.status === 'error') {
      context.error_count++;
    }

    // Add to batch
    this.addToBatch(fullStep);

    return fullStep;
  }

  /**
   * Complete an interaction
   */
  async completeInteraction(
    context: InteractionContext,
    status: 'success' | 'error' | 'cancelled',
    error?: unknown
  ): Promise<void> {
    const ended_at = new Date();
    const duration_ms = ended_at.getTime() - context.started_at.getTime();

    // Log end step
    this.logStep(context, {
      type: 'UI_ACTION_END',
      component: 'frontend',
      message: `Completed: ${context.action_name} (${status})`,
      status,
      duration_ms,
      details: error
        ? { error: sanitizeError(error) }
        : undefined,
    });

    // Flush any pending steps
    await this.flushBatch();

    // Update interaction
    const interaction = await uelrStorage.getInteraction(context.interaction_id);
    if (interaction) {
      interaction.ended_at = ended_at.toISOString();
      interaction.duration_ms = duration_ms;
      interaction.status = status;
      interaction.step_count = context.step_count;
      interaction.error_count = context.error_count;
      if (error) {
        const sanitizedError = sanitizeError(error);
        interaction.error_summary = sanitizedError.message;
      }
      await uelrStorage.saveInteraction(interaction);
    }

    // Queue completion for backend
    this.queueForSync({
      type: 'complete',
      data: {
        interaction_id: context.interaction_id,
        status,
        error_summary: error ? sanitizeError(error).message : undefined,
      } as CompleteInteractionRequest,
    });

    // Remove from active
    this.activeInteractions.delete(context.interaction_id);
  }

  /**
   * Wrap an async action with automatic interaction tracking
   */
  wrapAction<T>(
    actionName: string,
    fn: (context: InteractionContext) => Promise<T>,
    meta?: { category?: string; page?: string }
  ): () => Promise<T> {
    return async () => {
      const context = this.startInteraction(actionName, meta);
      try {
        const result = await fn(context);
        await this.completeInteraction(context, 'success');
        return result;
      } catch (error) {
        await this.completeInteraction(context, 'error', error);
        throw error;
      }
    };
  }

  /**
   * Wrap a sync action with automatic interaction tracking
   */
  wrapSyncAction<T>(
    actionName: string,
    fn: (context: InteractionContext) => T,
    meta?: { category?: string; page?: string }
  ): () => T {
    return () => {
      const context = this.startInteraction(actionName, meta);
      try {
        const result = fn(context);
        // Use setTimeout to allow sync completion
        setTimeout(() => this.completeInteraction(context, 'success'), 0);
        return result;
      } catch (error) {
        setTimeout(() => this.completeInteraction(context, 'error', error), 0);
        throw error;
      }
    };
  }

  // ============ Network Tracking ============

  /**
   * Create headers to attach to outgoing requests
   */
  getTrackingHeaders(context?: InteractionContext): Record<string, string> {
    if (!context) {
      // No active interaction, generate correlation ID for standalone request
      return {
        'X-Correlation-ID': generateId('cor'),
      };
    }
    return {
      'X-Correlation-ID': context.correlation_id,
      'X-Interaction-ID': context.interaction_id,
    };
  }

  /**
   * Log the start of a network request
   */
  logNetworkRequestStart(
    context: InteractionContext,
    method: string,
    url: string,
    body?: unknown
  ): { startTime: number; step: UELRStep } {
    const startTime = performance.now();
    const step = this.logStep(context, {
      type: 'NETWORK_REQUEST_START',
      component: 'frontend',
      message: `${method} ${url}`,
      status: 'pending',
      details: {
        method,
        url,
        request_size: body ? JSON.stringify(body).length : 0,
      },
    });
    return { startTime, step };
  }

  /**
   * Log the end of a network request
   */
  logNetworkRequestEnd(
    context: InteractionContext,
    method: string,
    url: string,
    startTime: number,
    statusCode: number,
    responseBody?: unknown,
    error?: unknown
  ): UELRStep {
    const duration_ms = performance.now() - startTime;
    const isSuccess = statusCode >= 200 && statusCode < 400;

    return this.logStep(context, {
      type: 'NETWORK_REQUEST_END',
      component: 'frontend',
      message: `${method} ${url} -> ${statusCode}`,
      status: error ? 'error' : isSuccess ? 'success' : 'error',
      duration_ms,
      details: {
        method,
        url,
        status_code: statusCode,
        response_size: responseBody ? JSON.stringify(responseBody).length : 0,
        ...(error ? { error: sanitizeError(error) } : {}),
      },
    });
  }

  /**
   * Log SSE connection events
   */
  logSSEConnect(context: InteractionContext, url: string): UELRStep {
    return this.logStep(context, {
      type: 'SSE_CONNECT',
      component: 'frontend',
      message: `SSE connected: ${url}`,
      status: 'success',
      details: { url },
    });
  }

  logSSEMessage(context: InteractionContext, eventType: string, data?: unknown): UELRStep {
    return this.logStep(context, {
      type: 'SSE_MESSAGE',
      component: 'frontend',
      message: `SSE message: ${eventType}`,
      status: 'success',
      details: {
        event_type: eventType,
        data: data ? sanitizeBody(data, 1000) : undefined,
      },
    });
  }

  logSSEClose(context: InteractionContext, url: string): UELRStep {
    return this.logStep(context, {
      type: 'SSE_CLOSE',
      component: 'frontend',
      message: `SSE closed: ${url}`,
      status: 'success',
      details: { url },
    });
  }

  logSSEError(context: InteractionContext, url: string, error: unknown): UELRStep {
    return this.logStep(context, {
      type: 'SSE_ERROR',
      component: 'frontend',
      message: `SSE error: ${url}`,
      status: 'error',
      details: {
        url,
        error: sanitizeError(error),
      },
    });
  }

  // ============ State Change Tracking ============

  logStateChange(
    context: InteractionContext,
    stateName: string,
    oldValue: unknown,
    newValue: unknown
  ): UELRStep {
    return this.logStep(context, {
      type: 'UI_STATE_CHANGE',
      component: 'frontend',
      message: `State changed: ${stateName}`,
      status: 'success',
      details: {
        state_name: stateName,
        old_value: sanitizeBody(oldValue, 500),
        new_value: sanitizeBody(newValue, 500),
      },
    });
  }

  // ============ Batching ============

  private addToBatch(step: UELRStep): void {
    this.stepBatch.push(step);

    // Save to local storage immediately
    uelrStorage.saveSteps([step]);

    // Schedule batch send
    if (!this.batchTimer) {
      this.batchTimer = setTimeout(() => this.flushBatch(), BATCH_INTERVAL_MS);
    }

    // Force flush if batch is full
    if (this.stepBatch.length >= MAX_BATCH_SIZE) {
      this.flushBatch();
    }
  }

  private async flushBatch(): Promise<void> {
    if (this.batchTimer) {
      clearTimeout(this.batchTimer);
      this.batchTimer = null;
    }

    if (this.stepBatch.length === 0) return;

    const steps = [...this.stepBatch];
    this.stepBatch = [];

    // Group steps by interaction
    const byInteraction = new Map<string, UELRStep[]>();
    for (const step of steps) {
      const existing = byInteraction.get(step.interaction_id) || [];
      existing.push(step);
      byInteraction.set(step.interaction_id, existing);
    }

    // Queue each batch for sync
    for (const [interactionId, interactionSteps] of byInteraction) {
      this.queueForSync({
        type: 'steps',
        data: {
          interaction_id: interactionId,
          steps: interactionSteps.map(({ interaction_id, ...rest }) => rest),
        } as AppendStepsRequest,
      });
    }
  }

  // ============ Backend Sync ============

  private queueForSync(item: { type: 'interaction' | 'steps' | 'complete'; data: unknown }): void {
    uelrStorage.addToSyncQueue(item);
    // Attempt immediate sync if online
    if (this.isOnline) {
      this.processSyncQueue();
    }
  }

  private startSyncProcessor(): void {
    this.syncTimerRef = setInterval(() => {
      if (this.isOnline) {
        this.processSyncQueue();
      }
    }, SYNC_RETRY_INTERVAL_MS);
  }

  /**
   * Cleanup method to stop background processing
   */
  destroy(): void {
    if (this.syncTimerRef) {
      clearInterval(this.syncTimerRef);
      this.syncTimerRef = null;
    }
    if (this.batchTimer) {
      clearTimeout(this.batchTimer);
      this.batchTimer = null;
    }
  }

  private async processSyncQueue(): Promise<void> {
    const items = await uelrStorage.getSyncQueueItems();

    for (const item of items) {
      if (item.retry_count >= MAX_RETRY_COUNT) {
        // Give up after max retries
        await uelrStorage.removeSyncQueueItem(item.id);
        continue;
      }

      try {
        let endpoint: string;
        let method: 'POST' | 'PUT' = 'POST';
        let body: unknown = item.data;

        switch (item.type) {
          case 'interaction':
            endpoint = `${this.apiBaseUrl}/uelr/interactions`;
            break;
          case 'steps':
            endpoint = `${this.apiBaseUrl}/uelr/interactions/${(item.data as AppendStepsRequest).interaction_id}/steps`;
            break;
          case 'complete':
            endpoint = `${this.apiBaseUrl}/uelr/interactions/${(item.data as CompleteInteractionRequest).interaction_id}/complete`;
            method = 'PUT';
            break;
          default:
            continue;
        }

        const response = await fetch(endpoint, {
          method,
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        });

        if (response.ok || response.status === 409) {
          // Success or already exists - remove from queue
          await uelrStorage.removeSyncQueueItem(item.id);
        } else if (response.status >= 500) {
          // Server error - retry later
          await uelrStorage.updateSyncQueueRetry(item.id);
        } else {
          // Client error - don't retry
          await uelrStorage.removeSyncQueueItem(item.id);
        }
      } catch {
        // Network error - retry later
        await uelrStorage.updateSyncQueueRetry(item.id);
      }
    }
  }

  // ============ Query API ============

  /**
   * Get an interaction by ID (from local storage)
   */
  async getInteraction(interactionId: string): Promise<UELRInteraction | null> {
    const interaction = await uelrStorage.getInteraction(interactionId);
    if (interaction) {
      interaction.steps = await uelrStorage.getStepsForInteraction(interactionId);
    }
    return interaction;
  }

  /**
   * List recent interactions (from local storage)
   */
  async listInteractions(
    limit: number = 50,
    offset: number = 0,
    filters?: { action_name?: string; status?: StepStatus; correlation_id?: string }
  ): Promise<{ interactions: UELRInteraction[]; total: number }> {
    return uelrStorage.listInteractions(limit, offset, filters);
  }

  /**
   * Get the current active interaction context (if any)
   */
  getActiveContext(): InteractionContext | undefined {
    // Return the most recent active interaction
    const contexts = Array.from(this.activeInteractions.values());
    return contexts[contexts.length - 1];
  }

  /**
   * Get or create an active context
   */
  getOrCreateContext(actionName: string, meta?: { category?: string }): InteractionContext {
    const active = this.getActiveContext();
    if (active) return active;
    return this.startInteraction(actionName, meta);
  }

  // ============ Export ============

  async exportInteraction(interactionId: string): Promise<string> {
    const interaction = await this.getInteraction(interactionId);
    if (!interaction) {
      throw new Error(`Interaction ${interactionId} not found`);
    }
    return JSON.stringify(interaction, null, 2);
  }

  async exportAll(): Promise<string> {
    const data = await uelrStorage.exportAll();
    return JSON.stringify(data, null, 2);
  }
}

// Singleton instance
export const uelr = new UELRSDK();

// Export for advanced use cases
export type { InteractionContext };
