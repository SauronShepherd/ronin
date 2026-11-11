import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';

test('Semantic Studio presents a responsive decision workbench', async ({ page }) => {
  await page.goto('./#semantic');
  await expect(page.locator('.semantic-hero')).toContainText('Make metrics explainable');
  await expect(page.locator('.semantic-workbench')).toContainText('Turn the model into a decision');
  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.locator('#main').evaluate(node => ({ client: node.clientWidth, scroll: node.scrollWidth }));
  expect(widths.scroll).toBe(widths.client);
});

test('Semantic Studio presents metric and join rows before raw evidence', async ({ page }) => {
  await page.route('**/semantic/query', route => route.fulfill({ json: { columns: ['metric', 'value'], rows: [['revenue', 42]], row_count: 1 } }));
  await page.route('**/semantic/join', route => route.fulfill({ json: { columns: ['customer', 'revenue'], rows: [['Ada', 42]], row_count: 1 } }));
  await page.goto('./#semantic');
  await page.getByRole('button', { name: 'Run metric query' }).click();
  await expect(page.locator('#semantic-query-result table')).toContainText('42');
  await expect(page.locator('#semantic-query-result .semantic-raw')).not.toHaveAttribute('open', '');
  await page.getByRole('button', { name: 'Run join' }).click();
  await expect(page.locator('#semantic-join-result table')).toContainText('Ada');
});

test('Semantic Studio follows the active shell workspace and project', async ({ page }) => {
  await page.goto('./#semantic');
  await page.evaluate(() => {
    globalThis.roninStudioContext = { workspace: 'workspace-shell', project: 'project-shell' };
    window.dispatchEvent(new CustomEvent('ronin-context-change', { detail: globalThis.roninStudioContext }));
  });
  await expect(page.locator('#semantic-query-form [name="workspace"]')).toHaveValue('workspace-shell');
  await expect(page.locator('#semantic-query-form [name="project"]')).toHaveValue('project-shell');
  await expect(page.locator('#semantic-bundle-import-form [name="project"]')).toHaveValue('project-shell');
});

test('Semantic Studio exports an integrity-checked archive and previews then imports only the reviewed file and scope', async ({ page }) => {
  const archive = Buffer.from('semantic-bundle-fixture');
  const digest = createHash('sha256').update(archive).digest('hex');
  const calls = [];
  await page.route('**/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push({ method: request.method(), pathname: url.pathname });
    if (request.method() === 'GET' && url.pathname.endsWith('/semantic/bundle')) {
      await route.fulfill({
        json: {
          media_type: 'application/vnd.ronin.bundle+zip',
          digest,
          size_bytes: archive.length,
          content_base64: archive.toString('base64'),
        },
      });
      return;
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/semantic/bundle/plan')) {
      expect(request.postDataJSON().content_base64).toBe(archive.toString('base64'));
      await route.fulfill({
        json: {
          models: [{ id: 'sales' }],
          dashboards: [{ id: 'overview' }],
          inventory: { objects: [] },
          bundle_digest: digest,
          size_bytes: archive.length,
        },
      });
      return;
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/semantic/bundle/import')) {
      expect(request.postDataJSON()).toEqual({
        content_base64: archive.toString('base64'),
        expected_digest: digest,
      });
      await route.fulfill({
        json: { models: [{ id: 'sales' }], dashboards: [{ id: 'overview' }], bundle_digest: digest, size_bytes: archive.length },
      });
      return;
    }
    if (request.method() === 'GET' && url.pathname.endsWith('/semantic/models')) {
      await route.fulfill({ json: { items: [{ id: 'sales' }] } });
      return;
    }
    if (request.method() === 'GET' && url.pathname.endsWith('/semantic/dashboards')) {
      await route.fulfill({ json: { items: [{ id: 'overview' }] } });
      return;
    }
    throw new Error(`Unexpected semantic API request ${request.method()} ${url.pathname}`);
  });

  await page.goto('./#semantic');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download semantic Bundle' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('examples_demo-semantic.roninbundle');
  await expect(page.locator('#semantic-bundle-result')).toContainText(digest);

  const file = page.locator('#semantic-bundle-import-form input[name="bundle"]');
  await file.setInputFiles({ name: 'semantic.roninbundle', mimeType: 'application/zip', buffer: archive });
  const importButton = page.getByRole('button', { name: 'Import reviewed Bundle' });
  await expect(importButton).toBeDisabled();
  await page.getByRole('button', { name: 'Verify and preview' }).click();
  await expect(page.locator('#semantic-bundle-result')).toContainText('sales');
  await expect(page.locator('#semantic-bundle-result')).toContainText('overview');
  await expect(importButton).toBeEnabled();

  await page.locator('#semantic-bundle-import-form [name="project"]').fill('changed-target');
  await importButton.click();
  await expect(importButton).toBeDisabled();
  await expect(page.locator('#semantic-bundle-result')).toContainText('target project changed');
  expect(calls.some(call => call.pathname.endsWith('/semantic/bundle/import'))).toBe(false);

  await page.locator('#semantic-bundle-import-form [name="project"]').fill('examples/demo');
  await page.getByRole('button', { name: 'Verify and preview' }).click();
  await expect(importButton).toBeEnabled();
  await importButton.click();
  await expect(page.locator('#semantic-bundle-result')).toContainText('Imported 1 model(s) and 1 dashboard(s)');
  await expect(page.locator('#semantic-model-result')).toContainText('sales');
  await expect(page.locator('#semantic-dashboard-result')).toContainText('overview');
  expect(calls.map(call => call.method)).toEqual(['GET', 'POST', 'POST', 'POST', 'GET', 'GET']);
});

test('Semantic Studio refuses digest-mismatched exports and clears stale reviews when the file changes', async ({ page }) => {
  const archive = Buffer.from('safe');
  const digest = createHash('sha256').update(archive).digest('hex');
  await page.route('**/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'GET' && url.pathname.endsWith('/semantic/bundle')) {
      await route.fulfill({ json: { media_type: 'application/vnd.ronin.bundle+zip', digest: '0'.repeat(64), size_bytes: archive.length, content_base64: archive.toString('base64') } });
      return;
    }
    if (url.pathname.endsWith('/semantic/bundle/plan')) {
      await route.fulfill({ json: { models: [], dashboards: [], bundle_digest: digest, size_bytes: archive.length } });
      return;
    }
    throw new Error(`Unexpected request ${request.method()} ${url.pathname}`);
  });
  await page.goto('./#semantic');
  await page.getByRole('button', { name: 'Download semantic Bundle' }).click();
  await expect(page.locator('#semantic-bundle-result')).toContainText('digest or size does not match');

  const file = page.locator('#semantic-bundle-import-form input[name="bundle"]');
  await file.setInputFiles({ name: 'semantic.roninbundle', mimeType: 'application/zip', buffer: archive });
  await page.getByRole('button', { name: 'Verify and preview' }).click();
  const importButton = page.getByRole('button', { name: 'Import reviewed Bundle' });
  await expect(importButton).toBeEnabled();
  await file.setInputFiles({ name: 'changed.roninbundle', mimeType: 'application/zip', buffer: Buffer.from('changed') });
  await expect(importButton).toBeDisabled();
  await expect(page.locator('#semantic-bundle-result')).toContainText('selected file changed');

  const oversized = Buffer.alloc(700 * 1024 + 1, 97);
  await file.setInputFiles({ name: 'large.roninbundle', mimeType: 'application/zip', buffer: oversized });
  await page.getByRole('button', { name: 'Verify and preview' }).click();
  await expect(page.locator('#semantic-bundle-result')).toContainText('700 KiB file limit');
});

test('Semantic Studio ships a valid dashboard example and persists it through the API', async ({ page }) => {
  let savedDashboard;
  await page.route('**/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'PUT' && url.pathname.endsWith('/semantic/dashboards/sales_dashboard')) {
      savedDashboard = request.postDataJSON();
      await route.fulfill({ json: savedDashboard });
      return;
    }
    throw new Error(`Unexpected semantic API request ${request.method()} ${url.pathname}`);
  });

  await page.goto('./#semantic');
  const definition = page.locator('#semantic-dashboard-form [name="definition"]');
  const example = JSON.parse(await definition.inputValue());
  expect(example).toMatchObject({
    id: 'sales_dashboard',
    name: 'Sales',
    tiles: [{ id: 'orders', chart: 'number', query: { model_id: 'sales', measures: ['orders'] } }],
  });
  await expect.poll(() => page.locator('#semantic-dashboard-form').evaluate(form => form.checkValidity())).toBe(true);
  await page.getByRole('button', { name: 'Save dashboard' }).click();
  await expect(page.locator('#semantic-dashboard-result')).toContainText('sales_dashboard');
  expect(savedDashboard).toEqual(example);
});
