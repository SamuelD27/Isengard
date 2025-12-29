/**
 * Global Setup for E2E Tests
 *
 * Runs once before all tests:
 * 1. Verify services are healthy
 * 2. Clean up test data from previous runs
 * 3. Create necessary directories
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
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000';

async function globalSetup(config: FullConfig) {
  console.log('\n=== E2E Global Setup ===\n');

  // Create artifact directories (relative to e2e/ root)
  const e2eRoot = path.resolve(__dirname, '..');
  const artifactDirs = [
    'artifacts/screenshots',
    'artifacts/videos',
    'artifacts/traces',
    'artifacts/reports',
    'artifacts/har',
    'artifacts/test-results',
  ];

  for (const dir of artifactDirs) {
    const fullPath = path.join(e2eRoot, dir);
    if (!fs.existsSync(fullPath)) {
      fs.mkdirSync(fullPath, { recursive: true });
      console.log(`Created directory: ${dir}`);
    }
  }

  console.log(`Artifact root: ${path.join(e2eRoot, 'artifacts')}`);

  // Verify API health
  console.log(`\nChecking API health at ${API_URL}/health...`);
  try {
    const response = await fetch(`${API_URL}/health`);
    if (!response.ok) {
      console.error(`API health check failed: ${response.status}`);
      console.error('Make sure the API server is running with: docker-compose up api');
      process.exit(1);
    }
    const data = await response.json();
    console.log(`API healthy: ${JSON.stringify(data)}`);
  } catch (error) {
    console.error(`API not reachable: ${error}`);
    console.error('Make sure to start services with: ./scripts/e2e-run.sh');
    // Don't exit - let the test runner handle missing services
  }

  // Verify frontend
  console.log(`Checking frontend at ${BASE_URL}...`);
  try {
    const response = await fetch(BASE_URL);
    if (!response.ok) {
      console.error(`Frontend check failed: ${response.status}`);
    } else {
      console.log('Frontend reachable');
    }
  } catch (error) {
    console.error(`Frontend not reachable: ${error}`);
  }

  // Clean up test characters from previous runs using centralized cleanup
  console.log('\nCleaning up test data...');
  try {
    await cleanupTestData(API_URL);
  } catch (error) {
    console.log('  Cleanup skipped (API not available)');
  }

  console.log('\n=== Setup Complete ===\n');
}

export default globalSetup;
