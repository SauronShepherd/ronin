import { test, expect } from '@playwright/test';

const liveUrl = process.env.RONIN_STUDIO_E2E_URL;
const token = process.env.RONIN_STUDIO_E2E_TOKEN;

test('live Runs connects without submitting a connection and retains the project filter', async ({ page }) => {
  test.skip(!liveUrl || !token, 'requires a running Ronin API and RONIN_STUDIO_E2E_TOKEN');

  const apiOrigin = new URL(liveUrl).origin;
  const connectionRequests = [];
  const pageErrors = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.endsWith('/connections')) connectionRequests.push(request.url());
  });
  page.on('pageerror', error => pageErrors.push(error.message));

  await page.goto(new URL('/studio/#runs', apiOrigin).toString(), { waitUntil: 'domcontentloaded' });
  await page.locator('#api-url').fill(apiOrigin);
  await page.locator('#api-token').fill(token);
  await page.getByRole('button', { name: 'Connect' }).click();
  await page.locator('#run-project').fill('examples/demo');

  const listResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname === '/v1/jobs' && url.searchParams.get('project') === 'examples/demo';
  });
  await page.locator('[data-action="refresh-runs"]').click();

  const response = await listResponse;
  expect(response.status()).toBe(200);
  await expect(page.locator('#run-project')).toHaveValue('examples/demo');
  await expect(page.locator('#view table tbody tr').first()).toBeVisible();
  expect(connectionRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});
