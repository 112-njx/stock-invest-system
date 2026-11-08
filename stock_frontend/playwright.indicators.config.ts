import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

export default defineConfig({
  testDir: './tests/indicator-acceptance',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 30_000 },
  outputDir: '../.artifacts/indicators/browser-results',
  reporter: [['line'], ['json', { outputFile: '../.artifacts/indicators/browser-results.json' }]],
  use: {
    baseURL: process.env.INDICATOR_TEST_URL || 'http://127.0.0.1:8081',
    viewport: { width: 1600, height: 1000 },
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'off',
    launchOptions: {
      ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: resolve(process.env.PLAYWRIGHT_EXECUTABLE_PATH) }
        : process.platform === 'win32' ? { channel: 'msedge' } : {}),
    },
  },
})
