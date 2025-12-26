/**
 * Isengard Frontend Logger
 *
 * Structured logging for the web frontend with:
 * - Batched server submission
 * - Local console output in development
 * - Correlation ID propagation
 * - UI event tracking
 */

import { generateCorrelationId } from './utils'

type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'

interface LogEntry {
  timestamp: string
  level: LogLevel
  message: string
  event?: string
  context?: Record<string, unknown>
}

interface LoggerConfig {
  /** Minimum level to log */
  minLevel: LogLevel
  /** Whether to log to console */
  consoleOutput: boolean
  /** Whether to send logs to server */
  serverOutput: boolean
  /** Batch size before sending to server */
  batchSize: number
  /** Max time (ms) before flushing batch */
  flushInterval: number
  /** Server endpoint for log submission */
  serverEndpoint: string
}

const LOG_LEVELS: Record<LogLevel, number> = {
  DEBUG: 0,
  INFO: 1,
  WARNING: 2,
  ERROR: 3,
}

const DEFAULT_CONFIG: LoggerConfig = {
  minLevel: import.meta.env.DEV ? 'DEBUG' : 'INFO',
  consoleOutput: import.meta.env.DEV,
  serverOutput: true,
  batchSize: 10,
  flushInterval: 5000,
  serverEndpoint: '/api/client-logs',
}

class Logger {
  private config: LoggerConfig
  private buffer: LogEntry[] = []
  private flushTimer: ReturnType<typeof setTimeout> | null = null
  private correlationId: string | null = null

  constructor(config: Partial<LoggerConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
    this.startFlushTimer()

    // Flush on page unload
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => this.flush())
      window.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
          this.flush()
        }
      })
    }
  }

  /**
   * Set the correlation ID for all subsequent logs
   */
  setCorrelationId(id: string): void {
    this.correlationId = id
  }

  /**
   * Get current correlation ID or generate one
   */
  getCorrelationId(): string {
    if (!this.correlationId) {
      this.correlationId = generateCorrelationId()
    }
    return this.correlationId
  }

  /**
   * Log at DEBUG level
   */
  debug(message: string, context?: Record<string, unknown>): void {
    this.log('DEBUG', message, undefined, context)
  }

  /**
   * Log at INFO level
   */
  info(message: string, context?: Record<string, unknown>): void {
    this.log('INFO', message, undefined, context)
  }

  /**
   * Log at WARNING level
   */
  warn(message: string, context?: Record<string, unknown>): void {
    this.log('WARNING', message, undefined, context)
  }

  /**
   * Log at ERROR level
   */
  error(message: string, error?: Error, context?: Record<string, unknown>): void {
    const errorContext = error
      ? {
          ...context,
          error_name: error.name,
          error_message: error.message,
          error_stack: error.stack?.substring(0, 500),
        }
      : context
    this.log('ERROR', message, undefined, errorContext)
  }

  /**
   * Log a UI event
   */
  event(eventType: string, message: string, context?: Record<string, unknown>): void {
    this.log('INFO', message, eventType, context)
  }

  /**
   * Log page view
   */
  pageView(path: string, context?: Record<string, unknown>): void {
    this.event('ui.page.view', `Page view: ${path}`, { path, ...context })
  }

  /**
   * Log button click
   */
  buttonClick(buttonName: string, context?: Record<string, unknown>): void {
    this.event('ui.button.click', `Button clicked: ${buttonName}`, {
      button: buttonName,
      ...context,
    })
  }

  /**
   * Log form submission
   */
  formSubmit(formName: string, context?: Record<string, unknown>): void {
    this.event('ui.form.submit', `Form submitted: ${formName}`, {
      form: formName,
      ...context,
    })
  }

  /**
   * Log API request
   */
  apiRequest(method: string, endpoint: string, context?: Record<string, unknown>): void {
    this.event('ui.api.request', `API request: ${method} ${endpoint}`, {
      method,
      endpoint,
      ...context,
    })
  }

  /**
   * Log API response
   */
  apiResponse(
    method: string,
    endpoint: string,
    status: number,
    durationMs: number,
    context?: Record<string, unknown>
  ): void {
    this.event('ui.api.response', `API response: ${method} ${endpoint} ${status}`, {
      method,
      endpoint,
      status,
      duration_ms: durationMs,
      ...context,
    })
  }

  /**
   * Log SSE connection
   */
  sseConnect(endpoint: string, context?: Record<string, unknown>): void {
    this.event('ui.sse.connect', `SSE connected: ${endpoint}`, {
      endpoint,
      ...context,
    })
  }

  /**
   * Log SSE message
   */
  sseMessage(endpoint: string, eventType: string, context?: Record<string, unknown>): void {
    this.event('ui.sse.message', `SSE message: ${eventType}`, {
      endpoint,
      event_type: eventType,
      ...context,
    })
  }

  /**
   * Log SSE error
   */
  sseError(endpoint: string, error: string, context?: Record<string, unknown>): void {
    this.event('ui.sse.error', `SSE error: ${error}`, {
      endpoint,
      error,
      ...context,
    })
  }

  /**
   * Log error boundary catch
   */
  errorBoundary(
    error: Error,
    componentStack: string,
    context?: Record<string, unknown>
  ): void {
    this.event('ui.error.boundary', `Error boundary triggered: ${error.message}`, {
      error_name: error.name,
      error_message: error.message,
      error_stack: error.stack?.substring(0, 500),
      component_stack: componentStack.substring(0, 500),
      ...context,
    })
  }

  private log(
    level: LogLevel,
    message: string,
    event?: string,
    context?: Record<string, unknown>
  ): void {
    if (LOG_LEVELS[level] < LOG_LEVELS[this.config.minLevel]) {
      return
    }

    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      event,
      context: {
        correlation_id: this.getCorrelationId(),
        ...context,
      },
    }

    // Console output in development
    if (this.config.consoleOutput) {
      const consoleMethod =
        level === 'ERROR'
          ? console.error
          : level === 'WARNING'
          ? console.warn
          : level === 'DEBUG'
          ? console.debug
          : console.log

      consoleMethod(
        `[${entry.timestamp}] ${level}${event ? ` [${event}]` : ''}: ${message}`,
        context || ''
      )
    }

    // Add to buffer for server submission
    if (this.config.serverOutput) {
      this.buffer.push(entry)

      if (this.buffer.length >= this.config.batchSize) {
        this.flush()
      }
    }
  }

  private startFlushTimer(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer)
    }
    this.flushTimer = setInterval(() => this.flush(), this.config.flushInterval)
  }

  /**
   * Send buffered logs to server
   */
  async flush(): Promise<void> {
    if (this.buffer.length === 0) {
      return
    }

    const entries = [...this.buffer]
    this.buffer = []

    try {
      const response = await fetch(this.config.serverEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Correlation-ID': this.getCorrelationId(),
        },
        body: JSON.stringify({ entries }),
      })

      if (!response.ok) {
        // Re-add to buffer on failure (with limit to prevent memory issues)
        if (this.buffer.length < 100) {
          this.buffer.unshift(...entries)
        }
        console.error('[Logger] Failed to send logs to server:', response.status)
      }
    } catch (error) {
      // Re-add to buffer on network error
      if (this.buffer.length < 100) {
        this.buffer.unshift(...entries)
      }
      console.error('[Logger] Network error sending logs:', error)
    }
  }

  /**
   * Update logger configuration
   */
  configure(config: Partial<LoggerConfig>): void {
    this.config = { ...this.config, ...config }
    this.startFlushTimer()
  }
}

// Export singleton instance
export const logger = new Logger()

// Export class for testing or custom instances
export { Logger, type LoggerConfig, type LogEntry, type LogLevel }
