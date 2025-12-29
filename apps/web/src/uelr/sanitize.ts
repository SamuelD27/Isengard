/**
 * UELR Sanitization Module
 *
 * Handles redaction of sensitive data before logging or transmission.
 */

import { SENSITIVE_FIELDS, REDACTION_PATTERNS } from './types';

/**
 * Check if a key is a sensitive field (case-insensitive)
 */
function isSensitiveKey(key: string): boolean {
  const lowerKey = key.toLowerCase();
  return SENSITIVE_FIELDS.some((field) => lowerKey.includes(field));
}

/**
 * Redact sensitive patterns from a string value
 */
export function redactString(value: string): string {
  let result = value;
  for (const { pattern, replacement } of REDACTION_PATTERNS) {
    // Create a new RegExp to reset lastIndex for global patterns
    const regex = new RegExp(pattern.source, pattern.flags);
    result = result.replace(regex, replacement);
  }
  return result;
}

/**
 * Recursively sanitize an object, redacting sensitive fields and patterns
 */
export function sanitize<T>(data: T, maxDepth: number = 10): T {
  return sanitizeRecursive(data, 0, maxDepth, new WeakSet());
}

function sanitizeRecursive<T>(
  data: T,
  depth: number,
  maxDepth: number,
  seen: WeakSet<object>
): T {
  // Prevent infinite recursion
  if (depth > maxDepth) {
    return '[MAX_DEPTH_EXCEEDED]' as unknown as T;
  }

  // Handle null/undefined
  if (data === null || data === undefined) {
    return data;
  }

  // Handle strings - apply pattern redaction
  if (typeof data === 'string') {
    return redactString(data) as unknown as T;
  }

  // Handle primitives
  if (typeof data !== 'object') {
    return data;
  }

  // Handle circular references
  if (seen.has(data)) {
    return '[CIRCULAR_REFERENCE]' as unknown as T;
  }
  seen.add(data);

  // Handle arrays
  if (Array.isArray(data)) {
    return data.map((item) =>
      sanitizeRecursive(item, depth + 1, maxDepth, seen)
    ) as unknown as T;
  }

  // Handle objects
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
    // Redact sensitive keys entirely
    if (isSensitiveKey(key)) {
      result[key] = '***REDACTED***';
    } else {
      result[key] = sanitizeRecursive(value, depth + 1, maxDepth, seen);
    }
  }

  return result as T;
}

/**
 * Sanitize HTTP headers, preserving only safe headers
 */
export function sanitizeHeaders(
  headers: Record<string, string> | Headers
): Record<string, string> {
  const result: Record<string, string> = {};

  // Safe headers to preserve
  const safeHeaders = [
    'content-type',
    'content-length',
    'accept',
    'accept-language',
    'cache-control',
    'x-correlation-id',
    'x-interaction-id',
    'x-request-id',
  ];

  const entries =
    headers instanceof Headers
      ? Array.from(headers.entries())
      : Object.entries(headers);

  for (const [key, value] of entries) {
    const lowerKey = key.toLowerCase();
    if (safeHeaders.includes(lowerKey)) {
      result[key] = redactString(value);
    } else if (isSensitiveKey(key)) {
      result[key] = '***REDACTED***';
    } else {
      // Include but redact value patterns
      result[key] = redactString(value);
    }
  }

  return result;
}

/**
 * Sanitize request/response body for logging
 * Truncates large bodies and redacts sensitive data
 */
export function sanitizeBody(
  body: unknown,
  maxLength: number = 10000
): unknown {
  if (body === null || body === undefined) {
    return body;
  }

  // Handle strings (e.g., raw text bodies)
  if (typeof body === 'string') {
    const sanitized = redactString(body);
    if (sanitized.length > maxLength) {
      return sanitized.slice(0, maxLength) + `... [TRUNCATED: ${sanitized.length - maxLength} chars]`;
    }
    return sanitized;
  }

  // Handle objects
  if (typeof body === 'object') {
    const sanitized = sanitize(body);
    const serialized = JSON.stringify(sanitized);
    if (serialized.length > maxLength) {
      return {
        _truncated: true,
        _original_size: serialized.length,
        _preview: serialized.slice(0, maxLength) + '...',
      };
    }
    return sanitized;
  }

  return body;
}

/**
 * Create a safe error object for logging
 */
export function sanitizeError(error: unknown): {
  type: string;
  message: string;
  stack?: string;
} {
  if (error instanceof Error) {
    return {
      type: error.name,
      message: redactString(error.message),
      stack: error.stack ? redactString(error.stack.split('\n').slice(0, 5).join('\n')) : undefined,
    };
  }

  if (typeof error === 'string') {
    return {
      type: 'Error',
      message: redactString(error),
    };
  }

  return {
    type: 'UnknownError',
    message: redactString(String(error)),
  };
}
