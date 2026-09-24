import { test, expect } from '@playwright/test';

test('synthetic studio completes deterministic generation and export journey', async ({ page }) => {
  const calls = [];
  await page.route('**/v1/synthetic-data-studio/catalog/providers**', async (route) => {
    calls.push('providers');
    await route.fulfill({json: {mode: 'offline', external_connections: false, items: [{display_name: 'Local'}]}});
  });
  await page.route('**/v1/synthetic-data-studio/catalog/assets**', async (route) => {
    calls.push('assets');
    await route.fulfill({json: {items: [{id: 'synthetic.customers', name: 'customers'}]}});
  });
  await page.route('**/v1/synthetic-data-studio/runs**', async (route) => {
    calls.push('runs');
    await route.fulfill({json: {items: []}});
  });
  await page.route('**/v1/synthetic-data-studio/formats**', async (route) => {
    calls.push('formats');
    await route.fulfill({json: [{format_id: 'jsonl', status: 'ready'}]});
  });
  await page.route('**/v1/synthetic-data-studio/generate**', async (route) => {
    calls.push('generate');
    const request = route.request();
    expect((await request.postDataJSON()).plan.seed).toBe(42);
    await route.fulfill({json: {
      run_id: 'run-deterministic-42',
      status: 'generated',
      tables: [{name: 'customers', rows: [{id: 1}]}],
    }});
  });
  await page.route('**/v1/synthetic-data-studio/export**', async (route) => {
    calls.push('export');
    const body = await route.request().postDataJSON();
    expect(body).toMatchObject({run_id: 'run-deterministic-42', table: 'customers', format_id: 'jsonl'});
    await route.fulfill({json: {format_id: 'jsonl', content: '{"id":1}\n'}});
  });

  await page.goto('./#synthetic', {waitUntil: 'networkidle'});
  await expect(page.locator('#synthetic-studio-providers')).toContainText('Local');
  await expect(page.locator('#synthetic-studio-assets')).toContainText('customers');

  await page.locator('#synthetic-studio-form button[type="submit"]').click();
  await expect(page.locator('#synthetic-studio-result')).toContainText('run-deterministic-42');
  await expect(page.locator('#synthetic-studio-export')).toBeVisible();

  await page.locator('#synthetic-studio-export-button').click();
  await expect(page.locator('#synthetic-studio-result')).toContainText('jsonl');
  expect(calls).toEqual(expect.arrayContaining(['providers', 'assets', 'runs', 'generate', 'formats', 'export']));
});
