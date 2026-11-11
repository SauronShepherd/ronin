import { test, expect } from '@playwright/test';

test('FinOps workbench inherits context and keeps measure selection explicit', async ({ page }) => {
  await page.route('**/v1/workspaces/team-a/finops/budgets', async route => {
    await route.fulfill({ json: { items: [{ id: 'monthly', state: 'active' }] } });
  });
  await page.goto('./?workspace=team-a&project=project-z#finops');
  await expect(page.locator('#finops-form [name="workspace"]')).toHaveValue('team-a');
  await expect(page.locator('.workspace-hero')).toContainText('runtime spend');
  await page.getByRole('button', { name: 'Load budgets' }).click();
  await expect(page.locator('#finops-result')).toContainText('monthly');
});

test('FinOps workbench retries the last bounded request', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/default/finops/budgets', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { message: 'Ledger is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'monthly', state: 'active' }] } });
  });
  await page.goto('./#finops');
  await page.getByRole('button', { name: 'Load budgets' }).click();
  await expect(page.locator('#finops-result')).toContainText('FinOps operation failed');
  await page.getByRole('button', { name: 'Retry this request' }).click();
  await expect(page.locator('#finops-result')).toContainText('monthly');
  expect(attempts).toBe(2);
});
