import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.RESPONSIVE_TEST_URL || 'http://127.0.0.1:4184'

export default defineConfig({
  testDir: './tests/responsive',
  outputDir: '../.artifacts/responsive',
  workers: 2,
  timeout: 45_000,
  expect: { timeout: 12_000 },
  reporter: 'line',
  use: { baseURL, screenshot: 'only-on-failure', actionTimeout: 8000 },
  projects: [
    ...[320, 360, 390, 430].map(width => ({
      name: `phone-${width}`,
      use: {
        ...devices['Pixel 7'],
        viewport: { width, height: 844 },
        defaultBrowserType: 'chromium' as const,
      },
    })),
    { name: 'phone-landscape', use: {
      ...devices['Pixel 7 landscape'],
      viewport: { width: 844, height: 390 },
      defaultBrowserType: 'chromium',
    } },
    { name: 'tablet', use: { viewport: { width: 768, height: 900 }, hasTouch: true } },
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
  ],
  webServer: process.env.RESPONSIVE_TEST_URL ? undefined : {
    command: 'npm run preview -- --host 127.0.0.1 --port 4184 --strictPort',
    url: baseURL,
  },
})
