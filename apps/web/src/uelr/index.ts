/**
 * UELR - User End Log Register
 *
 * End-to-end interaction logging system for Isengard.
 *
 * Quick Start:
 *
 * ```typescript
 * import { uelr } from '@/uelr';
 *
 * // Start an interaction
 * const context = uelr.startInteraction('Create Character', { category: 'character' });
 *
 * // Log steps
 * uelr.logStep(context, { type: 'UI_STATE_CHANGE', ... });
 *
 * // Complete interaction
 * await uelr.completeInteraction(context, 'success');
 *
 * // Or use wrapAction for automatic tracking
 * const handleClick = uelr.wrapAction('Create Character', async (ctx) => {
 *   // Your async code here
 * });
 * ```
 */

// Core SDK
export { uelr, type InteractionContext } from './sdk';

// Fetch wrappers
export {
  uelrFetch,
  uelrJsonFetch,
  uelrFormFetch,
  createContextFetch,
  type UELRFetchOptions,
} from './fetch';

// Types
export type {
  UELRInteraction,
  UELRStep,
  StepType,
  StepComponent,
  StepStatus,
  CreateInteractionRequest,
  AppendStepsRequest,
  CompleteInteractionRequest,
  ListInteractionsResponse,
  InteractionFilter,
  BundleRequest,
} from './types';

// Sanitization utilities
export { sanitize, sanitizeBody, sanitizeHeaders, sanitizeError, redactString } from './sanitize';

// Storage (for advanced use)
export { uelrStorage } from './storage';

// React hooks
export {
  useTrackedAction,
  useTrackedSyncAction,
  useTrackedMutation,
  useLongInteraction,
  useInteractionHistory,
  useInteractionDetails,
} from './hooks';
