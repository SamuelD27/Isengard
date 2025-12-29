/**
 * Log Collector for E2E Tests
 *
 * Captures browser console logs and page errors for debugging.
 */

import { Page, ConsoleMessage } from '@playwright/test';

export interface LogEntry {
  type: 'log' | 'info' | 'warn' | 'error' | 'debug' | 'trace' | 'pageerror';
  text: string;
  url: string;
  line: number;
  column: number;
  timestamp: number;
}

export interface LogCollector {
  logs: LogEntry[];
  errors: LogEntry[];
  start: () => void;
  stop: () => void;
  getErrors: () => LogEntry[];
  getWarnings: () => LogEntry[];
  getAllLogs: () => LogEntry[];
  getSummary: () => string;
  clear: () => void;
  hasErrors: () => boolean;
  hasWarnings: () => boolean;
}

/**
 * Create a log collector for a page
 */
export function createLogCollector(page: Page): LogCollector {
  const logs: LogEntry[] = [];
  let isCollecting = false;

  const handleConsole = (msg: ConsoleMessage) => {
    if (!isCollecting) return;

    const location = msg.location();
    const entry: LogEntry = {
      type: msg.type() as LogEntry['type'],
      text: msg.text(),
      url: location.url,
      line: location.lineNumber,
      column: location.columnNumber,
      timestamp: Date.now(),
    };

    logs.push(entry);
  };

  const handlePageError = (error: Error) => {
    if (!isCollecting) return;

    logs.push({
      type: 'pageerror',
      text: error.message + (error.stack ? `\n${error.stack}` : ''),
      url: '',
      line: 0,
      column: 0,
      timestamp: Date.now(),
    });
  };

  return {
    logs,

    get errors() {
      return logs.filter((l) => l.type === 'error' || l.type === 'pageerror');
    },

    start() {
      isCollecting = true;
      page.on('console', handleConsole);
      page.on('pageerror', handlePageError);
    },

    stop() {
      isCollecting = false;
      page.off('console', handleConsole);
      page.off('pageerror', handlePageError);
    },

    getErrors() {
      return logs.filter((l) => l.type === 'error' || l.type === 'pageerror');
    },

    getWarnings() {
      return logs.filter((l) => l.type === 'warn');
    },

    getAllLogs() {
      return [...logs];
    },

    getSummary() {
      const errors = logs.filter((l) => l.type === 'error' || l.type === 'pageerror');
      const warnings = logs.filter((l) => l.type === 'warn');

      let summary = `\n=== Console Log Summary ===\n`;
      summary += `Total logs: ${logs.length}\n`;
      summary += `Errors: ${errors.length}\n`;
      summary += `Warnings: ${warnings.length}\n`;

      if (errors.length > 0) {
        summary += `\n--- Errors ---\n`;
        for (const err of errors) {
          summary += `[${err.type}] ${err.text}\n`;
          if (err.url) {
            summary += `  at ${err.url}:${err.line}:${err.column}\n`;
          }
        }
      }

      if (warnings.length > 0) {
        summary += `\n--- Warnings ---\n`;
        for (const warn of warnings) {
          summary += `[warn] ${warn.text.slice(0, 200)}\n`;
        }
      }

      return summary;
    },

    clear() {
      logs.length = 0;
    },

    hasErrors() {
      return logs.some((l) => l.type === 'error' || l.type === 'pageerror');
    },

    hasWarnings() {
      return logs.some((l) => l.type === 'warn');
    },
  };
}

/**
 * Assert no console errors occurred
 */
export function assertNoConsoleErrors(collector: LogCollector, options: {
  ignorePatterns?: RegExp[];
} = {}) {
  const { ignorePatterns = [] } = options;

  const errors = collector.getErrors().filter((err) => {
    // Filter out known/expected errors
    return !ignorePatterns.some((pattern) => pattern.test(err.text));
  });

  if (errors.length > 0) {
    const errorDetails = errors
      .map((e) => `[${e.type}] ${e.text}`)
      .join('\n');
    throw new Error(`Console errors occurred:\n${errorDetails}`);
  }
}

/**
 * Common patterns to ignore in error checking
 */
export const IGNORED_ERROR_PATTERNS = [
  // React development warnings
  /Warning: ReactDOM\.render is no longer supported/,
  /Warning: Each child in a list should have a unique/,

  // Network errors that are expected in tests
  /Failed to fetch/,
  /NetworkError/,

  // Browser extension noise
  /chrome-extension/,

  // ResizeObserver (common false positive)
  /ResizeObserver loop/,
];
