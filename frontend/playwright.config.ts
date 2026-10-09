import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './browser-tests',
  timeout: 120_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  outputDir: '../.context/browser-results',
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5179', locale: 'fr-FR', viewport: { width: 1440, height: 1100 }, headless: true, screenshot: 'only-on-failure' },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5179 --strictPort',
    url: 'http://127.0.0.1:5179',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
