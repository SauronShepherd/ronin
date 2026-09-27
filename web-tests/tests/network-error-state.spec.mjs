import { test, expect } from '@playwright/test';

test('runs surface renders a bounded backend error state', async ({ page }) => {
  await page.route('**/v1/jobs**', async route => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'service_unavailable', message: 'backend unavailable' } }),
    });
  });
  await page.goto('./#runs', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#run-result .error')).toBeVisible();
  await expect(page.locator('#run-result')).toContainText('Could not load runs.');
  await expect(page.locator('body')).not.toContainText('undefined');
});
