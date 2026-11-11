import { test, expect } from '@playwright/test';

test('Alerts workbench inherits the active workspace and keeps actions grouped', async ({ page }) => {
  await page.route('**/v1/workspaces/team-a/alerts/rules', async route => {
    await route.fulfill({ json: { items: [{ id: 'orders-late', state: 'firing', severity: 'high', metric: 'latency' }] } });
  });
  await page.goto('./?workspace=team-a&project=project-z#alerts');
  await expect(page.locator('#alerts-form [name="workspace"]')).toHaveValue('team-a');
  await expect(page.locator('.alerts-hero')).toContainText('governed decision');
  await page.getByRole('button', { name: 'List rules' }).click();
  await expect(page.locator('#alerts-result')).toContainText('orders-late');
});

test('Alerts workbench retries the last operation without losing scope', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/default/alerts/instances', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { message: 'Alert index is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'orders-late', state: 'firing' }] } });
  });
  await page.goto('./#alerts');
  await page.getByRole('button', { name: 'List states' }).click();
  await expect(page.locator('#alerts-result')).toContainText('Alert operation failed');
  await page.getByRole('button', { name: 'Retry this operation' }).click();
  await expect(page.locator('#alerts-result')).toContainText('orders-late');
  expect(attempts).toBe(2);
});
