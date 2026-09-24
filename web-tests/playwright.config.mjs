import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.RONIN_STUDIO_E2E_URL || 'http://127.0.0.1:8099/web/';
const slowMo = Number(process.env.RONIN_UI_SLOW_MO_MS || 0);
const token = process.env.RONIN_STUDIO_E2E_TOKEN || 'job-token';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : 2,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    headless: !process.env.PWDEBUG,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    launchOptions: { slowMo },
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.RONIN_STUDIO_E2E_URL
    ? undefined
    : {
        command: 'python -m http.server 8099 --directory ..',
        url: 'http://127.0.0.1:8099/web/',
        reuseExistingServer: false,
        timeout: 30_000,
      },
});
