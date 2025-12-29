/**
 * Global Teardown for E2E Tests
 *
 * Runs once after all tests:
 * 1. Generate summary report
 * 2. Clean up test data
 */

import { FullConfig } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { cleanupTestData } from './test-data.js';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const API_URL = process.env.E2E_API_URL || 'http://localhost:8000';

async function globalTeardown(config: FullConfig) {
  console.log('\n=== E2E Global Teardown ===\n');

  // Clean up test characters using the centralized cleanup function
  console.log('Cleaning up test data...');
  try {
    await cleanupTestData(API_URL);
  } catch (error) {
    console.log('  Cleanup skipped (API not available)');
  }

  // Generate summary from test results
  const e2eRoot = path.resolve(__dirname, '..');
  const reportPath = path.join(e2eRoot, 'artifacts/reports/test-results.json');

  if (fs.existsSync(reportPath)) {
    try {
      const report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
      const stats = report.stats || {};

      console.log('\n=== Test Summary ===');
      console.log(`Total:    ${stats.expected || 0}`);
      console.log(`Passed:   ${stats.expected - (stats.unexpected || 0) - (stats.flaky || 0)}`);
      console.log(`Failed:   ${stats.unexpected || 0}`);
      console.log(`Flaky:    ${stats.flaky || 0}`);
      console.log(`Skipped:  ${stats.skipped || 0}`);
      console.log(`Duration: ${Math.round((stats.duration || 0) / 1000)}s`);
    } catch (error) {
      console.log('Could not parse test results');
    }
  }

  // List artifact locations
  console.log('\n=== Artifact Locations ===');
  const artifactRoot = path.join(e2eRoot, 'artifacts');

  const listDir = (dir: string, label: string) => {
    const fullPath = path.join(artifactRoot, dir);
    if (fs.existsSync(fullPath)) {
      const files = fs.readdirSync(fullPath);
      if (files.length > 0 && files[0] !== '.DS_Store') {
        console.log(`${label}: ${fullPath} (${files.length} items)`);
      }
    }
  };

  listDir('test-results', 'Test Results');
  listDir('screenshots', 'Screenshots');
  listDir('reports', 'Reports');

  console.log('\n=== Teardown Complete ===\n');
}

export default globalTeardown;
