import { test, expect } from '@playwright/test';

test('Quality Studio presents an evidence-first decision workbench', async ({ page }) => {
  await page.route('**/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'GET' && url.pathname.endsWith('/quality/state/asset-a/v1')) {
      await route.fulfill({
        json: {
          latest_status: 'passed',
          latest_run_id: 'quality-run-7',
          run_count: 2,
          latest_run: {
            execution_ref: 'pipeline-7',
            status: 'passed',
            results: [{ rule_id: 'row-count', status: 'passed', message: 'Rows are present.' }],
          },
          history: [{ run_id: 'quality-run-7', asset: { asset_id: 'asset-a', version: 'v1' }, status: 'passed' }],
        },
      });
      return;
    }
    if (request.method() === 'GET' && url.pathname.endsWith('/quality/contracts/asset-a/v1')) {
      await route.fulfill({ json: { asset: { asset_id: 'asset-a', version: 'v1' }, rules: [] } });
      return;
    }
    if (request.method() === 'PUT' && url.pathname.endsWith('/quality/contracts/asset-a/v1')) {
      await route.fulfill({ json: request.postDataJSON() });
      return;
    }
    throw new Error(`Unexpected quality request ${request.method()} ${url.pathname}`);
  });

  await page.goto('./#quality', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.quality-hero')).toContainText('Make data quality a decision');
  await expect(page.locator('.quality-playbook li')).toHaveCount(3);
  await expect(page.locator('#quality-controls')).toContainText('Contract JSON');
  await expect(page.locator('#quality-controls')).toContainText('Dry-run rows');

  await page.locator('#quality-workspace').fill('ws-a');
  await page.locator('#quality-asset').fill('asset-a');
  await page.locator('#quality-version').fill('v1');
  await page.getByRole('button', { name: 'Load state', exact: true }).click();
  await expect(page.locator('#quality-result')).toContainText('quality-run-7');
  await expect(page.locator('#quality-result')).toContainText('Rows are present.');
  await expect(page.locator('#quality-mode')).toContainText('passed');

  await page.getByRole('button', { name: 'Load contract', exact: true }).click();
  await expect(page.locator('#quality-contract')).toHaveValue(/asset-a/);
  await page.locator('#quality-contract').fill(JSON.stringify({ asset: { asset_id: 'asset-a', version: 'v1' }, rules: [{ id: 'row-count' }] }));
  await page.getByRole('button', { name: 'Save contract', exact: true }).click();
  await expect(page.locator('#quality-result')).toContainText('row-count');

  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.locator('#main').evaluate(node => ({ client: node.clientWidth, scroll: node.scrollWidth }));
  expect(widths.scroll).toBe(widths.client);
});
