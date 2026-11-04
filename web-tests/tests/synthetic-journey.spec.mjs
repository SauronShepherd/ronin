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

  await page.goto('./#synthetic', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('#synthetic-studio-providers')).toContainText('Local');
  await expect(page.locator('#synthetic-studio-assets')).toContainText('customers');

  await page.locator('#synthetic-studio-form button[type="submit"]').click();
  await expect(page.locator('#synthetic-studio-result')).toContainText('run-deterministic-42');
  await expect(page.locator('#synthetic-studio-export')).toBeVisible();

  await page.locator('#synthetic-studio-export-button').click();
  await expect(page.locator('#synthetic-studio-result')).toContainText('jsonl');
  expect(calls).toEqual(expect.arrayContaining(['providers', 'assets', 'runs', 'generate', 'formats', 'export']));
});

test('synthetic generation remains actionable while the initial catalog request is pending', async ({ page }) => {
  let markProvidersStarted;
  let releaseProviders;
  const providersStarted = new Promise(resolve => { markProvidersStarted = resolve; });
  const heldProviders = new Promise(resolve => { releaseProviders = resolve; });
  await page.route('**/v1/synthetic-data-studio/catalog/providers**', async route => {
    markProvidersStarted();
    await heldProviders;
    await route.fulfill({json: {mode: 'offline', external_connections: false, items: []}});
  });
  await page.route('**/v1/synthetic-data-studio/catalog/assets**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/synthetic-data-studio/runs**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/synthetic-data-studio/generate**', route => route.fulfill({json: {
    run_id: 'run-before-catalog',
    status: 'generated',
    tables: [{name: 'customers', rows: [{id: 1}]}],
  }}));
  await page.route('**/v1/synthetic-data-studio/formats**', route => route.fulfill({json: [
    {format_id: 'jsonl', status: 'ready'},
  ]}));

  await page.goto('./#synthetic', {waitUntil: 'load'});
  await providersStarted;
  try {
    const generationResponse = page.waitForResponse(response =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/v1/synthetic-data-studio/generate',
    );
    await page.locator('#synthetic-studio-form button[type="submit"]').click();
    expect((await generationResponse).status()).toBe(200);
    await expect(page.locator('#synthetic-studio-result')).toContainText('run-before-catalog');
  } finally {
    releaseProviders();
  }
});
