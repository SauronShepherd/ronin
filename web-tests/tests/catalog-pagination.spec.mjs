import { test, expect } from '@playwright/test';

test('catalog search follows the server cursor to the next bounded page', async ({ page }) => {
  const requests = [];
  await page.route('**/v1/workspaces/ws-a/catalog/assets**', async route => {
    const url = new URL(route.request().url());
    requests.push(url);
    if (!url.searchParams.has('cursor')) {
      await route.fulfill({
        json: {
          items: [{ id: 'asset-a', name: 'Orders', kind: 'table', tags: [], classifications: [] }],
          next_cursor: 'opaque-next-page',
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        items: [{ id: 'asset-b', name: 'Orders archive', kind: 'table', tags: [], classifications: [] }],
        next_cursor: null,
      },
    });
  });

  await page.goto('./#catalog', { waitUntil: 'load' });
  const form = page.locator('#catalog-search-form');
  await form.getByLabel('Workspace').fill('ws-a');
  await form.getByLabel('Search').fill('orders');
  await form.getByRole('button', { name: 'Search catalog' }).click();
  await expect(page.locator('#catalog-result')).toContainText('Orders');
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page.locator('#catalog-result')).toContainText('Orders archive');
  await expect(page.getByRole('button', { name: 'Next page' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Previous page' }).click();
  await expect(page.locator('#catalog-result')).toContainText('Orders');
  await expect(page.getByRole('button', { name: 'Previous page' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Next page' })).toBeVisible();

  expect(requests).toHaveLength(3);
  expect(requests[0].searchParams.get('q')).toBe('orders');
  expect(requests[0].searchParams.get('limit')).toBe('50');
  expect(requests[0].searchParams.get('include_governance')).toBeNull();
  expect(requests[0].searchParams.get('cursor')).toBeNull();
  expect(requests[1].searchParams.get('cursor')).toBe('opaque-next-page');
  expect(requests[2].searchParams.get('cursor')).toBeNull();
});

test('catalog search keeps the workspace and query recoverable after a lookup error', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/ws-a/catalog/assets**', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { code: 'service_unavailable', message: 'Catalog is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'asset-recovered', name: 'Recovered asset', kind: 'table', tags: [], classifications: [] }], next_cursor: null } });
  });
  await page.goto('./#catalog', { waitUntil: 'load' });
  await page.locator('#catalog-search-form [name="workspace"]').fill('ws-a');
  await page.locator('#catalog-search-form [name="query"]').fill('orders');
  await page.getByRole('button', { name: 'Search catalog' }).click();
  await expect(page.locator('#catalog-result')).toContainText('Catalog is warming up.');
  await page.getByRole('button', { name: 'Retry this search', exact: true }).click();
  await expect(page.locator('#catalog-result')).toContainText('Recovered asset');
  await expect(page.locator('#catalog-search-form [name="workspace"]')).toHaveValue('ws-a');
  await expect(page.locator('#catalog-search-form [name="query"]')).toHaveValue('orders');
  expect(attempts).toBe(2);
});

test('catalog workbench turns governed assets into lineage and glossary review', async ({ page }) => {
  await page.route('**/v1/workspaces/ws-a/catalog/assets**', route => route.fulfill({ json: {
    items: [{ id: 'curated-orders', name: 'Curated orders', kind: 'table', tags: ['gold'], classifications: ['internal'] }],
    next_cursor: null,
  } }));
  await page.route('**/v1/workspaces/ws-a/catalog/lineage/curated-orders/1**', route => route.fulfill({ json: {
    items: [{ source: { asset_id: 'raw-orders', version: 'v2' }, target: { asset_id: 'curated-orders', version: '1' }, operation: 'write', mode: 'observed', execution_ref: 'run-42' }],
    truncated: false,
  } }));
  await page.route('**/v1/workspaces/ws-a/glossary/terms**', async route => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ json: { id: 'customer', version: '1', name: 'Customer', owner: 'data-team' } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'customer', version: '1', name: 'Customer', definition: 'A governed buyer identity.', owner: 'data-team', references: ['catalog:curated-orders'] }] } });
  });

  await page.goto('./#catalog');
  await page.locator('#catalog-search-form [name="workspace"]').fill('ws-a');
  await page.getByRole('button', { name: 'Search catalog' }).click();
  await expect(page.locator('.catalog-table')).toContainText('Curated orders');
  await expect(page.locator('.catalog-pill').filter({ hasText: 'gold' })).toHaveCount(1);
  await page.locator('[data-action="catalog-select-asset"]').last().click();
  await expect(page.locator('#catalog-lineage-form [name="asset_id"]')).toHaveValue('curated-orders');
  await page.locator('#catalog-lineage-form').getByRole('button', { name: 'Inspect lineage' }).click();
  await expect(page.locator('.catalog-lineage-map')).toContainText('raw-orders');
  await expect(page.locator('.catalog-lineage-map')).toContainText('run-42');

  await page.locator('#glossary-form [name="workspace"]').fill('ws-a');
  await page.locator('#glossary-search-form').getByRole('button', { name: 'Load terms' }).click();
  await expect(page.locator('.glossary-table')).toContainText('Customer');
  await expect(page.locator('.glossary-table')).toContainText('data-team');

  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.locator('#main').evaluate(node => ({ client: node.clientWidth, scroll: node.scrollWidth }));
  expect(widths.scroll).toBe(widths.client);
});

test('catalog lineage keeps the selected asset revision recoverable after an error', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/ws-a/catalog/lineage/curated-orders/1**', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 502, json: { error: { code: 'lineage_unavailable', message: 'Lineage index is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { items: [{ source: { asset_id: 'raw-orders', version: 'v2' }, target: { asset_id: 'curated-orders', version: '1' }, operation: 'write', mode: 'observed' }] } });
  });
  await page.goto('./#catalog');
  await page.locator('#catalog-search-form [name="workspace"]').fill('ws-a');
  await page.locator('#catalog-lineage-form [name="asset_id"]').fill('curated-orders');
  await page.locator('#catalog-lineage-form [name="version"]').fill('1');
  await page.locator('#catalog-lineage-form [name="direction"]').selectOption('upstream');
  await page.getByRole('button', { name: 'Inspect lineage' }).click();
  await expect(page.locator('#catalog-lineage-result')).toContainText('Lineage index is warming up.');
  await page.getByRole('button', { name: 'Retry lineage', exact: true }).click();
  await expect(page.locator('.catalog-lineage-map')).toContainText('raw-orders');
  await expect(page.locator('#catalog-lineage-form [name="asset_id"]')).toHaveValue('curated-orders');
  await expect(page.locator('#catalog-lineage-form [name="version"]')).toHaveValue('1');
  expect(attempts).toBe(2);
});

test('catalog keeps long asset identities discoverable without widening the table', async ({ page }) => {
  const assetId = 'warehouse.customer_orders.curated.production.v2026_11_11';
  await page.route('**/v1/workspaces/ws-a/catalog/assets**', route => route.fulfill({ json: {
    items: [{ id: assetId, name: 'Customer orders', kind: 'table', tags: [], classifications: [] }],
    next_cursor: null,
  } }));
  await page.goto('./#catalog');
  await page.locator('#catalog-search-form [name="workspace"]').fill('ws-a');
  await page.getByRole('button', { name: 'Search catalog' }).click();
  const identity = page.locator('.catalog-subline').first();
  await expect(identity).toHaveAttribute('title', assetId);
  await expect(page.locator('.catalog-asset-link').first()).toHaveAttribute('aria-label', `Inspect Customer orders (${assetId})`);
  const widths = await page.locator('#main').evaluate(node => ({ client: node.clientWidth, scroll: node.scrollWidth }));
  expect(widths.scroll).toBe(widths.client);
});

test('catalog glossary search preserves workspace and query after an error', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/ws-a/glossary/terms**', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { code: 'glossary_unavailable', message: 'Glossary is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'customer', version: '1', name: 'Customer', definition: 'A governed buyer identity.', owner: 'data-team', references: [] }] } });
  });
  await page.goto('./#catalog');
  await page.locator('#glossary-form [name="workspace"]').fill('ws-a');
  await page.locator('#glossary-search-form [name="query"]').fill('customer');
  await page.getByRole('button', { name: 'Load terms' }).click();
  await expect(page.locator('#glossary-result')).toContainText('Glossary is warming up.');
  await page.getByRole('button', { name: 'Retry glossary search', exact: true }).click();
  await expect(page.locator('.glossary-table')).toContainText('Customer');
  await expect(page.locator('#glossary-form [name="workspace"]')).toHaveValue('ws-a');
  await expect(page.locator('#glossary-search-form [name="query"]')).toHaveValue('customer');
  expect(attempts).toBe(2);
});
