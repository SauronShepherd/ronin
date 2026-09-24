import { test, expect } from '@playwright/test';

test('hash navigation supports deep links and browser back/forward', async ({ page }) => {
  await page.goto('./#runs', { waitUntil: 'networkidle' });
  await expect(page.locator('#breadcrumb')).toHaveText('Runs');
  await expect(page.locator('#view')).toBeVisible();

  await page.locator('a[href="#workspaces"]').click();
  await expect(page).toHaveURL(/#workspaces$/);
  await expect(page.locator('#breadcrumb')).toHaveText('Workspaces');

  await page.goBack();
  await expect(page).toHaveURL(/#runs$/);
  await expect(page.locator('#breadcrumb')).toHaveText('Runs');

  await page.goForward();
  await expect(page).toHaveURL(/#workspaces$/);
  await expect(page.locator('#breadcrumb')).toHaveText('Workspaces');
});

test('unknown deep links fail closed to an explicit empty surface', async ({ page }) => {
  await page.goto('./#not-a-route', { waitUntil: 'networkidle' });
  await expect(page.locator('#breadcrumb')).toHaveText('Studio');
  await expect(page.locator('#view')).toContainText('not connected to a published backend');
  await expect(page.locator('body')).not.toContainText('undefined');
});
