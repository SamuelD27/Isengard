/**
 * UELR React Hooks
 *
 * Provides React-specific hooks for UELR integration.
 */

import { useCallback, useRef, useEffect, useState } from 'react';
import { uelr, type InteractionContext } from './sdk';
import type { UELRInteraction, StepStatus } from './types';

/**
 * Hook to create a tracked action handler
 *
 * Usage:
 * ```tsx
 * const handleCreate = useTrackedAction('Create Character', async (ctx) => {
 *   await api.createCharacter(data);
 * }, { category: 'character' });
 *
 * <button onClick={handleCreate}>Create</button>
 * ```
 */
export function useTrackedAction<T extends unknown[]>(
  actionName: string,
  handler: (context: InteractionContext, ...args: T) => Promise<void>,
  options?: { category?: string; page?: string }
): (...args: T) => Promise<void> {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  return useCallback(
    async (...args: T) => {
      const context = uelr.startInteraction(actionName, options);
      try {
        await handlerRef.current(context, ...args);
        await uelr.completeInteraction(context, 'success');
      } catch (error) {
        await uelr.completeInteraction(context, 'error', error);
        throw error;
      }
    },
    [actionName, options?.category, options?.page]
  );
}

/**
 * Hook to create a tracked sync action handler
 *
 * Usage:
 * ```tsx
 * const handleToggle = useTrackedSyncAction('Toggle Advanced', (ctx) => {
 *   setShowAdvanced(!showAdvanced);
 * });
 * ```
 */
export function useTrackedSyncAction<T extends unknown[]>(
  actionName: string,
  handler: (context: InteractionContext, ...args: T) => void,
  options?: { category?: string; page?: string }
): (...args: T) => void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  return useCallback(
    (...args: T) => {
      const context = uelr.startInteraction(actionName, options);
      try {
        handlerRef.current(context, ...args);
        setTimeout(() => uelr.completeInteraction(context, 'success'), 0);
      } catch (error) {
        setTimeout(() => uelr.completeInteraction(context, 'error', error), 0);
        throw error;
      }
    },
    [actionName, options?.category, options?.page]
  );
}

/**
 * Hook to track a mutation (integrates with React Query or similar)
 *
 * Usage:
 * ```tsx
 * const { mutate } = useMutation({ ... });
 * const trackedMutate = useTrackedMutation('Start Training', mutate, { category: 'training' });
 * ```
 */
export function useTrackedMutation<TData, TVariables>(
  actionName: string,
  mutationFn: (variables: TVariables) => Promise<TData>,
  options?: { category?: string; page?: string }
): {
  mutate: (variables: TVariables) => Promise<TData>;
  context: InteractionContext | null;
} {
  const contextRef = useRef<InteractionContext | null>(null);
  const [context, setContext] = useState<InteractionContext | null>(null);

  const mutate = useCallback(
    async (variables: TVariables): Promise<TData> => {
      const ctx = uelr.startInteraction(actionName, options);
      contextRef.current = ctx;
      setContext(ctx);

      try {
        const result = await mutationFn(variables);
        await uelr.completeInteraction(ctx, 'success');
        contextRef.current = null;
        setContext(null);
        return result;
      } catch (error) {
        await uelr.completeInteraction(ctx, 'error', error);
        contextRef.current = null;
        setContext(null);
        throw error;
      }
    },
    [actionName, mutationFn, options?.category, options?.page]
  );

  return { mutate, context };
}

/**
 * Hook to manage a long-running interaction (e.g., for forms, wizards)
 *
 * Usage:
 * ```tsx
 * const { context, complete, cancel, isActive } = useLongInteraction('Fill Form');
 *
 * // When form is submitted
 * await complete('success');
 *
 * // When user cancels
 * await cancel();
 * ```
 */
export function useLongInteraction(
  actionName: string,
  options?: { category?: string; autoStart?: boolean }
): {
  context: InteractionContext | null;
  start: () => InteractionContext;
  complete: (status: 'success' | 'error', error?: unknown) => Promise<void>;
  cancel: () => Promise<void>;
  isActive: boolean;
} {
  const [context, setContext] = useState<InteractionContext | null>(null);

  const start = useCallback(() => {
    if (context) {
      // Already active - complete the old one first
      uelr.completeInteraction(context, 'cancelled');
    }
    const ctx = uelr.startInteraction(actionName, options);
    setContext(ctx);
    return ctx;
  }, [actionName, options?.category, context]);

  const complete = useCallback(
    async (status: 'success' | 'error', error?: unknown) => {
      if (context) {
        await uelr.completeInteraction(context, status, error);
        setContext(null);
      }
    },
    [context]
  );

  const cancel = useCallback(async () => {
    if (context) {
      await uelr.completeInteraction(context, 'cancelled');
      setContext(null);
    }
  }, [context]);

  // Auto-start if requested
  useEffect(() => {
    if (options?.autoStart && !context) {
      start();
    }
  }, [options?.autoStart]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (context) {
        uelr.completeInteraction(context, 'cancelled');
      }
    };
  }, []);

  return {
    context,
    start,
    complete,
    cancel,
    isActive: context !== null,
  };
}

/**
 * Hook to fetch and display interaction history
 *
 * Usage:
 * ```tsx
 * const { interactions, loading, refetch, loadMore, hasMore } = useInteractionHistory({
 *   limit: 20,
 *   filters: { status: 'error' }
 * });
 * ```
 */
export function useInteractionHistory(options?: {
  limit?: number;
  filters?: { action_name?: string; status?: StepStatus; correlation_id?: string };
  autoRefresh?: boolean;
  refreshInterval?: number;
}): {
  interactions: UELRInteraction[];
  total: number;
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
  loadMore: () => Promise<void>;
  hasMore: boolean;
} {
  const [interactions, setInteractions] = useState<UELRInteraction[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = options?.limit || 50;

  const fetch = useCallback(
    async (reset: boolean = false) => {
      setLoading(true);
      setError(null);
      try {
        const newOffset = reset ? 0 : offset;
        const result = await uelr.listInteractions(limit, newOffset, options?.filters);
        if (reset) {
          setInteractions(result.interactions);
          setOffset(limit);
        } else {
          setInteractions((prev) => [...prev, ...result.interactions]);
          setOffset((prev) => prev + limit);
        }
        setTotal(result.total);
      } catch (e) {
        setError(e as Error);
      } finally {
        setLoading(false);
      }
    },
    [limit, offset, options?.filters]
  );

  // Initial fetch
  useEffect(() => {
    fetch(true);
  }, [options?.filters?.action_name, options?.filters?.status, options?.filters?.correlation_id]);

  // Auto-refresh
  useEffect(() => {
    if (options?.autoRefresh) {
      const interval = setInterval(
        () => fetch(true),
        options.refreshInterval || 5000
      );
      return () => clearInterval(interval);
    }
  }, [options?.autoRefresh, options?.refreshInterval, fetch]);

  return {
    interactions,
    total,
    loading,
    error,
    refetch: () => fetch(true),
    loadMore: () => fetch(false),
    hasMore: interactions.length < total,
  };
}

/**
 * Hook to get a single interaction with its steps
 *
 * Usage:
 * ```tsx
 * const { interaction, steps, loading, refetch } = useInteractionDetails(interactionId);
 * ```
 */
export function useInteractionDetails(interactionId: string | null): {
  interaction: UELRInteraction | null;
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
} {
  const [interaction, setInteraction] = useState<UELRInteraction | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetch = useCallback(async () => {
    if (!interactionId) {
      setInteraction(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await uelr.getInteraction(interactionId);
      setInteraction(result);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [interactionId]);

  useEffect(() => {
    fetch();
  }, [interactionId]);

  return {
    interaction,
    loading,
    error,
    refetch: fetch,
  };
}
