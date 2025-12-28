/**
 * API Error Types for GUI→API Wiring Audit
 *
 * These errors help detect and diagnose routing/proxy issues where
 * API requests are incorrectly served by a static file server.
 */

/**
 * Error thrown when an API request receives HTML instead of JSON.
 * This indicates a routing/proxy misconfiguration where the static
 * file server is handling /api/* routes instead of the backend.
 */
export class ApiMisrouteError extends Error {
  readonly name = 'ApiMisrouteError'
  readonly isApiMisrouteError = true

  constructor(
    public readonly requestUrl: string,
    public readonly requestMethod: string,
    public readonly responseStatus: number,
    public readonly contentType: string | null,
    public readonly bodyPreview: string,
    public readonly correlationId: string,
    public readonly diagnosticHint: string
  ) {
    super(
      `API request misrouted to static server. ` +
      `${requestMethod} ${requestUrl} returned ${contentType || 'unknown'} instead of JSON. ` +
      `Hint: ${diagnosticHint}`
    )

    // Ensure prototype chain works correctly
    Object.setPrototypeOf(this, ApiMisrouteError.prototype)
  }

  /**
   * Serialize for logging/transmission
   */
  toJSON() {
    return {
      name: this.name,
      message: this.message,
      requestUrl: this.requestUrl,
      requestMethod: this.requestMethod,
      responseStatus: this.responseStatus,
      contentType: this.contentType,
      bodyPreview: this.bodyPreview,
      correlationId: this.correlationId,
      diagnosticHint: this.diagnosticHint,
    }
  }
}

/**
 * Error thrown when response claims to be JSON but fails to parse.
 */
export class ApiJsonParseError extends Error {
  readonly name = 'ApiJsonParseError'
  readonly isApiJsonParseError = true

  constructor(
    public readonly requestUrl: string,
    public readonly requestMethod: string,
    public readonly responseStatus: number,
    public readonly contentType: string | null,
    public readonly bodyPreview: string,
    public readonly correlationId: string,
    public readonly parseError: string
  ) {
    super(
      `API response JSON parse failed. ` +
      `${requestMethod} ${requestUrl} returned status ${responseStatus} with content-type ${contentType || 'unknown'}. ` +
      `Parse error: ${parseError}`
    )
    Object.setPrototypeOf(this, ApiJsonParseError.prototype)
  }

  toJSON() {
    return {
      name: this.name,
      message: this.message,
      requestUrl: this.requestUrl,
      requestMethod: this.requestMethod,
      responseStatus: this.responseStatus,
      contentType: this.contentType,
      bodyPreview: this.bodyPreview,
      correlationId: this.correlationId,
      parseError: this.parseError,
    }
  }
}

/**
 * Detects if a response is likely HTML (static server fallback)
 */
export function isHtmlResponse(contentType: string | null, bodyText: string): boolean {
  // Check content-type header
  if (contentType?.includes('text/html')) {
    return true
  }

  // Check body content patterns (common HTML indicators)
  const trimmed = bodyText.trim().toLowerCase()
  if (
    trimmed.startsWith('<!doctype html') ||
    trimmed.startsWith('<html') ||
    trimmed.startsWith('<!doctype') ||
    // React SPA index.html patterns
    trimmed.includes('<div id="root">') ||
    trimmed.includes('<div id="app">')
  ) {
    return true
  }

  return false
}

/**
 * Generates a diagnostic hint based on the error context
 */
export function getDiagnosticHint(
  url: string,
  _contentType: string | null,
  bodyPreview: string
): string {
  const hints: string[] = []

  // Check for SPA fallback
  if (bodyPreview.includes('<div id="root">')) {
    hints.push('React SPA index.html served instead of API response')
    hints.push('Check that nginx/reverse proxy is configured to forward /api/* to backend')
  }

  // Check for wrong port
  if (url.includes(':3000/api') || url.includes(':5173/api')) {
    hints.push('Request may be hitting frontend dev server instead of API')
    hints.push('Verify Vite proxy or nginx config forwards /api to port 8000')
  }

  // Check for double /api prefix
  if (url.includes('/api/api/')) {
    hints.push('Double /api prefix detected - check API_BASE configuration')
  }

  // Generic fallback hint
  if (hints.length === 0) {
    hints.push('Verify reverse proxy configuration')
    hints.push('Ensure backend is running on expected port')
  }

  return hints.join('. ')
}

/**
 * Sanitize body preview (truncate and remove sensitive data)
 */
export function sanitizeBodyPreview(body: string, maxLength: number = 200): string {
  // Remove potential secrets
  let sanitized = body
    .replace(/Bearer\s+[A-Za-z0-9\-._~+/]+=*/gi, 'Bearer [REDACTED]')
    .replace(/hf_[A-Za-z0-9]+/g, 'hf_[REDACTED]')
    .replace(/sk-[A-Za-z0-9]+/g, 'sk-[REDACTED]')
    .replace(/password["']?\s*[:=]\s*["']?[^"'\s,}]+/gi, 'password=[REDACTED]')

  // Truncate
  if (sanitized.length > maxLength) {
    sanitized = sanitized.slice(0, maxLength) + '...[truncated]'
  }

  return sanitized
}
