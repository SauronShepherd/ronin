import { test, expect } from '@playwright/test';

test('graph workbench keeps workspace context and reads ontology bound to catalog data', async ({ page }) => {
  await page.route('**/v1/workspaces/team-a/graphs/sales/query', route => route.fulfill({ json: {
    objects: [{ object_type: 'Person', key: [['id', '1']], properties: [['name', 'Ada']] }],
  } }));
  await page.route('**/v1/workspaces/team-a/ontologies/sales/v1', route => route.fulfill({ json: {
    id: 'sales', version: 'v1', name: 'Sales', types: [{ name: 'Person', source: { asset_id: 'customers', version: '1' } }],
  } }));
  await page.route('**/v1/workspaces/team-a/graphs/sales/objects/Person**', route => route.fulfill({ json: {
    items: [{ object_type: 'Person', key: [['id', '1']], properties: [['name', 'Ada']] }],
  } }));
  await page.route('**/v1/workspaces/team-a/graphs/sales/neighbors', route => route.fulfill({ json: {
    items: [{ object_type: 'Order', key: [['id', '10']] }],
  } }));

  await page.goto('./?workspace=team-a&project=project-z#graphs', { waitUntil: 'load' });
  await expect(page.locator('#graph-query-form [name="workspace"]')).toHaveValue('team-a');
  await page.locator('#graph-query-form [name="graph"]').fill('sales');
  await page.getByRole('button', { name: 'Run query' }).click();
  await expect(page.locator('#graph-result')).toContainText('Ada');

  await page.getByRole('button', { name: 'Load schema' }).click();
  await expect(page.locator('#ontology-result')).toContainText('customers');
  await page.getByRole('button', { name: 'List objects' }).click();
  await expect(page.locator('#graph-result')).toContainText('Ada');
  await page.getByRole('button', { name: 'List neighbors' }).click();
  await expect(page.locator('#graph-result')).toContainText('Order');

  await page.locator('.context-change').click();
  await page.locator('#context-form [name="workspace"]').fill('team-b');
  await page.locator('#context-form button[type="submit"]').click();
  await expect(page.locator('#graph-query-form [name="workspace"]')).toHaveValue('team-b');
});

test('graph query keeps the bounded form recoverable after a server error', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/ws-a/graphs/graph-1/query', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { code: 'graph_unavailable', message: 'Graph is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { objects: [{ object_type: 'Person', key: [['id', '1']], properties: [['name', 'Recovered Ada']] }] } });
  });

  await page.goto('./?workspace=ws-a#graphs', { waitUntil: 'load' });
  await page.locator('#graph-query-form [name="query"]').fill("SELECT Person WHERE name = 'Ada' LIMIT 10");
  await page.getByRole('button', { name: 'Run query' }).click();
  await expect(page.locator('#graph-result')).toContainText('Graph is warming up.');
  await expect(page.locator('#graph-query-form [name="workspace"]')).toHaveValue('ws-a');
  await page.getByRole('button', { name: 'Run query' }).click();
  await expect(page.locator('#graph-result')).toContainText('Recovered Ada');
  expect(attempts).toBe(2);
});
