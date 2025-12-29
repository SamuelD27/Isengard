/**
 * UELR Fetch Wrapper
 *
 * Provides a wrapped fetch function that automatically:
 * - Attaches correlation and interaction ID headers
 * - Logs request start/end with timing
 * - Sanitizes logged data
 *
 * Use this instead of raw fetch() to get automatic UELR tracking.
 */

import { uelr, type InteractionContext } from './sdk';

export interface UELRFetchOptions extends RequestInit {
  /** UELR interaction context to attach to this request */
  context?: InteractionContext;

  /** Skip UELR tracking for this request */
  skipTracking?: boolean;

  /** Custom action name for tracking (if no context provided) */
  actionName?: string;
}

/**
 * Fetch wrapper with automatic UELR tracking
 */
export async function uelrFetch(
  input: RequestInfo | URL,
  options: UELRFetchOptions = {}
): Promise<Response> {
  const { context: providedContext, skipTracking, actionName, ...fetchOptions } = options;

  // Determine URL
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  const method = fetchOptions.method || 'GET';

  // Skip tracking if requested
  if (skipTracking) {
    return fetch(input, fetchOptions);
  }

  // Get or create context
  const context = providedContext || uelr.getActiveContext();

  // Attach tracking headers
  const headers = new Headers(fetchOptions.headers);
  if (context) {
    headers.set('X-Correlation-ID', context.correlation_id);
    headers.set('X-Interaction-ID', context.interaction_id);
  } else {
    // Generate correlation ID for standalone requests
    const correlationId = `cor-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    headers.set('X-Correlation-ID', correlationId);
  }

  const modifiedOptions: RequestInit = {
    ...fetchOptions,
    headers,
  };

  // If we have a context, log the request
  if (context) {
    const { startTime } = uelr.logNetworkRequestStart(context, method, url, fetchOptions.body);

    try {
      const response = await fetch(input, modifiedOptions);

      // Try to clone and read response for logging
      let responseBody: unknown;
      try {
        const cloned = response.clone();
        const contentType = response.headers.get('content-type');
        if (contentType?.includes('application/json')) {
          responseBody = await cloned.json();
        }
      } catch {
        // Ignore response parsing errors
      }

      uelr.logNetworkRequestEnd(
        context,
        method,
        url,
        startTime,
        response.status,
        responseBody
      );

      return response;
    } catch (error) {
      uelr.logNetworkRequestEnd(context, method, url, startTime, 0, undefined, error);
      throw error;
    }
  }

  // No context - just make the request with tracking headers
  return fetch(input, modifiedOptions);
}

/**
 * Create an intercepted fetch that attaches to a specific context
 */
export function createContextFetch(
  context: InteractionContext
): (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> {
  return (input, init) => uelrFetch(input, { ...init, context });
}

/**
 * Type-safe JSON fetch with UELR tracking
 */
export async function uelrJsonFetch<T>(
  url: string,
  options: UELRFetchOptions & {
    json?: unknown;
  } = {}
): Promise<{ data: T; response: Response }> {
  const { json, ...fetchOptions } = options;

  const headers = new Headers(fetchOptions.headers);
  if (!headers.has('Content-Type') && json !== undefined) {
    headers.set('Content-Type', 'application/json');
  }
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  const response = await uelrFetch(url, {
    ...fetchOptions,
    headers,
    body: json !== undefined ? JSON.stringify(json) : fetchOptions.body,
  });

  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
    (error as any).response = response;
    (error as any).status = response.status;
    throw error;
  }

  const data = await response.json();
  return { data, response };
}

/**
 * FormData fetch with UELR tracking (for file uploads)
 */
export async function uelrFormFetch<T>(
  url: string,
  formData: FormData,
  options: UELRFetchOptions = {}
): Promise<{ data: T; response: Response }> {
  // Don't set Content-Type - let browser set it with boundary
  const response = await uelrFetch(url, {
    ...options,
    method: options.method || 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
    (error as any).response = response;
    (error as any).status = response.status;
    throw error;
  }

  const data = await response.json();
  return { data, response };
}
