/**
 * Custom Failure Reporter
 *
 * Generates detailed failure reports with all debugging information.
 */

import type { Reporter, TestCase, TestResult, FullResult } from '@playwright/test/reporter';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface FailureDetails {
  test: string;
  file: string;
  duration: number;
  status: 'passed' | 'failed' | 'timedOut' | 'skipped';
  error?: {
    message: string;
    stack: string;
  };
  artifacts: {
    screenshot?: string;
    video?: string;
    trace?: string;
  };
  retry: number;
  annotations: string[];
}

class FailureReporter implements Reporter {
  private failures: FailureDetails[] = [];
  private outputDir: string;
  private e2eRoot: string;

  constructor(options: { outputFolder?: string } = {}) {
    // Resolve e2e root directory
    this.e2eRoot = path.resolve(__dirname, '..');
    this.outputDir = options.outputFolder
      ? path.resolve(this.e2eRoot, options.outputFolder)
      : path.join(this.e2eRoot, 'artifacts/reports');
  }

  onBegin() {
    // Ensure output directory exists at start
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }
  }

  onTestEnd(test: TestCase, result: TestResult) {
    if (result.status === 'failed' || result.status === 'timedOut') {
      const failure: FailureDetails = {
        test: test.title,
        file: test.location.file,
        duration: result.duration,
        status: result.status,
        retry: result.retry,
        annotations: test.annotations.map((a) => `${a.type}: ${a.description}`),
        artifacts: {},
      };

      // Extract error details
      if (result.error) {
        failure.error = {
          message: result.error.message || 'Unknown error',
          stack: result.error.stack || '',
        };
      }

      // Find artifacts from attachments
      for (const attachment of result.attachments) {
        if (attachment.name === 'screenshot' && attachment.path) {
          failure.artifacts.screenshot = attachment.path;
        }
        if (attachment.name === 'video' && attachment.path) {
          failure.artifacts.video = attachment.path;
        }
        if (attachment.name === 'trace' && attachment.path) {
          failure.artifacts.trace = attachment.path;
        }
      }

      this.failures.push(failure);
    }
  }

  onEnd(result: FullResult) {
    // Ensure output directory exists
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }

    // Always write JSON report (even if empty, for CI to check)
    const jsonPath = path.join(this.outputDir, 'failures.json');
    fs.writeFileSync(jsonPath, JSON.stringify(this.failures, null, 2));

    if (this.failures.length === 0) {
      // Write a success marker
      const successPath = path.join(this.outputDir, 'SUCCESS.txt');
      fs.writeFileSync(successPath, `All tests passed at ${new Date().toISOString()}\n`);
      return;
    }

    // Write human-readable report
    const textPath = path.join(this.outputDir, 'FAILURE_REPORT.txt');
    const report = this.generateTextReport(result);
    fs.writeFileSync(textPath, report);

    console.log(`\n[FailureReporter] Wrote failure report to: ${textPath}`);
    console.log(`[FailureReporter] Found ${this.failures.length} failure(s)\n`);
  }

  private generateTextReport(result: FullResult): string {
    const lines: string[] = [];

    lines.push('');
    lines.push('='.repeat(70));
    lines.push('                    E2E TEST FAILURE REPORT');
    lines.push('='.repeat(70));
    lines.push('');
    lines.push(`Run completed: ${new Date().toISOString()}`);
    lines.push(`Duration: ${Math.round(result.duration / 1000)}s`);
    lines.push(`Status: ${result.status}`);
    lines.push('');

    lines.push('-'.repeat(70));
    lines.push('SUMMARY');
    lines.push('-'.repeat(70));
    lines.push(`Total failures: ${this.failures.length}`);
    lines.push('');

    for (let i = 0; i < this.failures.length; i++) {
      const failure = this.failures[i];
      lines.push('-'.repeat(70));
      lines.push(`FAILURE ${i + 1}: ${failure.test}`);
      lines.push('-'.repeat(70));
      lines.push(`File: ${failure.file}`);
      lines.push(`Duration: ${failure.duration}ms`);
      lines.push(`Retry: ${failure.retry}`);
      lines.push('');

      if (failure.error) {
        lines.push('ERROR:');
        lines.push(failure.error.message);
        lines.push('');
        if (failure.error.stack) {
          lines.push('STACK TRACE:');
          // Show first 20 lines of stack
          const stackLines = failure.error.stack.split('\n').slice(0, 20);
          lines.push(...stackLines);
          lines.push('');
        }
      }

      lines.push('ARTIFACTS:');
      if (failure.artifacts.screenshot) {
        lines.push(`  Screenshot: ${failure.artifacts.screenshot}`);
      } else {
        lines.push(`  Screenshot: (not captured)`);
      }
      if (failure.artifacts.video) {
        lines.push(`  Video: ${failure.artifacts.video}`);
      } else {
        lines.push(`  Video: (not captured)`);
      }
      if (failure.artifacts.trace) {
        lines.push(`  Trace: npx playwright show-trace ${failure.artifacts.trace}`);
      } else {
        lines.push(`  Trace: (not captured)`);
      }
      lines.push('');
    }

    lines.push('='.repeat(70));
    lines.push('END OF FAILURE REPORT');
    lines.push('='.repeat(70));
    lines.push('');
    lines.push('To view the full HTML report: npx playwright show-report');
    lines.push('To view a trace: npx playwright show-trace <path-to-trace.zip>');
    lines.push('');

    return lines.join('\n');
  }
}

export default FailureReporter;
