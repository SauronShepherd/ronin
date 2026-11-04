import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

const baseURL = process.env.RONIN_STUDIO_E2E_URL || 'http://127.0.0.1:8099/web/';
const slowMo = Number(process.env.RONIN_UI_SLOW_MO_MS || 0);
const outputDir = path.resolve(process.env.PLAYWRIGHT_OUTPUT_DIR || 'test-results');
const htmlOutputDir = path.resolve(process.env.PLAYWRIGHT_HTML_OUTPUT_DIR || `${outputDir}-html`);
const isWithin = (parent, candidate) => {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
};
if (isWithin(outputDir, htmlOutputDir) || isWithin(htmlOutputDir, outputDir)) {
  throw new Error('Playwright HTML report and test artifact directories must not overlap.');
}
const reporters = [
  // Stream each completed case so long browser runs show progress in the
  // terminal. HTML and optional JUnit reports still retain full evidence.
  ['line'],
  [
    'html',
    {
      outputFolder: htmlOutputDir,
      open: 'never',
    },
  ],
];
if (process.env.PLAYWRIGHT_JUNIT_OUTPUT_FILE) {
  reporters.push([
    'junit',
    { outputFile: path.resolve(process.env.PLAYWRIGHT_JUNIT_OUTPUT_FILE) },
  ]);
}

export default defineConfig({
  testDir: './tests',
  // Include browser/page fixture startup in the budget on slower local hosts.
  timeout: 60_000,
  fullyParallel: true,
  forbidOnly: true,
  retries: Number(process.env.PLAYWRIGHT_RETRIES || 0),
  // Live product qualification overrides this to one worker because journeys
  // mutate shared seeded state. Static tests may opt into more workers.
  workers: Number(process.env.PLAYWRIGHT_WORKERS || 2),
  outputDir,
  reporter: reporters,
  use: {
    baseURL,
    headless: !process.env.PWDEBUG,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    launchOptions: { slowMo },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.RONIN_STUDIO_E2E_URL
    ? undefined
    : {
        command: 'python static_server.py',
        url: 'http://127.0.0.1:8099/web/',
        // Always start a fresh static server so stale processes cannot mask a bad build.
        reuseExistingServer: false,
        timeout: 30_000,
      },
});
