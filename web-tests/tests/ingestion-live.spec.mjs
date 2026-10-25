import { test, expect } from '@playwright/test';

const apiBase = process.env.RONIN_LIVE_API_URL;
const apiToken = process.env.RONIN_LIVE_API_TOKEN;
const workspace = process.env.RONIN_LIVE_WORKSPACE;
const pgPort = process.env.RONIN_LIVE_PG_PORT;
const liveReady = Boolean(apiBase && apiToken && workspace && pgPort);

async function configureDatabaseConnection(request) {
  const response = await request.post(
    `${apiBase}/v1/workspaces/${encodeURIComponent(workspace)}/connections`,
    {
      headers: { Authorization: `Bearer ${apiToken}` },
      data: {
        id: 'pg-live-e2e',
        name: 'Live PostgreSQL browser test',
        connector_id: 'postgresql',
        options: {
          host: '127.0.0.1',
          port: pgPort,
          database: 'ronin_test',
          schema: 'public',
          connect_timeout: '5',
        },
        secret_refs: {
          user: 'secret://env/RONIN_PG_TEST_USER',
          password: 'secret://env/RONIN_PG_TEST_PASSWORD',
        },
      },
    },
  );
  expect([200, 201]).toContain(response.status());
}

async function connectStudio(page, token = apiToken) {
  const proxied = [];
  await page.route('**/v1/**', async route => {
    const request = route.request();
    const requestUrl = new URL(request.url());
    const upstreamUrl = new URL(`${requestUrl.pathname}${requestUrl.search}`, `${apiBase}/`).toString();
    const requestHeaders = await request.allHeaders();
    const authorizationHeader = Object.entries(requestHeaders)
      .find(([name]) => name.toLowerCase() === 'authorization')?.[1];
    const headers = new Headers();
    for (const name of ['accept', 'authorization', 'content-type']) {
      const value = Object.entries(requestHeaders)
        .find(([headerName]) => headerName.toLowerCase() === name)?.[1];
      if (value) headers.set(name, value);
    }
    const method = request.method();
    const upstream = await fetch(upstreamUrl, {
      method,
      headers,
      body: ['GET', 'HEAD'].includes(method) ? undefined : await request.postDataBuffer(),
      signal: AbortSignal.timeout(10_000),
    });
    const status = upstream.status;
    const body = await upstream.text();
    const authorizationValue = authorizationHeader?.replace(/^Bearer\s+/i, '');
    proxied.push({
      path: requestUrl.pathname,
      status,
      authorizationKind: authorizationValue === token ? 'expected' : authorizationValue === apiToken ? 'configured' : authorizationValue === 'job-token' ? 'playwright-default' : authorizationValue ? 'other' : 'missing',
    });
    await route.fulfill({ status, contentType: 'application/json', body });
  });
  await page.goto('./#home');
  await page.locator('#api-url').fill('');
  await page.locator('#api-token').fill(token);
  await page.getByRole('button', { name: 'Connect' }).click();
  await expect(page.locator('#toast')).toContainText('Connection saved');
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBe(token);
  await page.goto('./#ingestion');
  return proxied;
}

test('Ingestion Studio discovers real PostgreSQL pages through the live API', async ({ page, request }) => {
  test.setTimeout(60_000);
  test.skip(!liveReady, 'Set RONIN_LIVE_* variables and start the composed API with seeded PostgreSQL tables.');
  await configureDatabaseConnection(request);
  const proxied = await connectStudio(page);
  await expect.poll(() => proxied.some(call => call.path.endsWith('/v1/platform/connectors'))).toBe(true);
  expect(proxied.find(call => call.path.endsWith('/v1/platform/connectors'))).toMatchObject({
    status: 200,
    authorizationKind: 'expected',
  });
  await page.locator('#ingestion-workspace').fill(workspace);
  await page.locator('[name="connection_ref"]').fill('pg-live-e2e');
  await page.locator('[name="connector_id"]').fill('postgresql');
  await page.locator('[name="page_size"]').fill('1');

  await page.getByRole('button', { name: 'Discover assets' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText('Page 1 loaded');
  expect(proxied.find(call => call.path.endsWith('/v1/platform/connectors/discover'))).toMatchObject({
    status: 200,
    authorizationKind: 'expected',
  });
  await expect(page.locator('#ingestion-discovery-status')).toContainText('more pages available');
  await expect(page.locator('#ingestion-discovery-result')).toContainText('ui_page_accounts');
  await page.getByRole('button', { name: 'Load next page' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText('Page 2 loaded');
  await expect(page.locator('#ingestion-discovery-result')).toContainText('ui_page_orders');

  await page.locator('#ingestion-definition').fill(JSON.stringify({
    id: 'live-preview',
    connector_id: 'postgresql',
    connection_ref: 'pg-live-e2e',
    asset_ref: 'pg-live-e2e::public.ui_page_accounts',
    destination_ref: 'artifact://live-preview',
    checkpoint_identity: 'live-preview',
    mode: 'snapshot',
  }));
  await page.getByRole('button', { name: 'Preview source' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('a@example.test');
  await page.getByRole('button', { name: 'Plan sync' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('snapshot');
  await page.getByRole('button', { name: 'Checkpoint health' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('live-preview');
});

test('Ingestion Studio displays a live API authorization error', async ({ page }) => {
  test.setTimeout(60_000);
  test.skip(!liveReady, 'Set RONIN_LIVE_* variables and start the composed API.');
  const proxied = await connectStudio(page, 'deliberately-invalid-token');
  await expect.poll(() => proxied.some(call => call.path.endsWith('/v1/platform/connectors'))).toBe(true);
  expect(proxied.find(call => call.path.endsWith('/v1/platform/connectors'))).toMatchObject({
    status: 401,
    authorizationKind: 'expected',
  });
  await expect(page.locator('#ingestion-capabilities')).toContainText('valid authorization required');
  await page.locator('#ingestion-workspace').fill(workspace);
  await page.locator('[name="connection_ref"]').fill('pg-live-e2e');
  await page.locator('[name="connector_id"]').fill('postgresql');
  await page.getByRole('button', { name: 'Discover assets' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText('Discovery failed:');
  expect(proxied.find(call => call.path.endsWith('/v1/platform/connectors/discover'))).toMatchObject({
    status: 401,
    authorizationKind: 'expected',
  });
  await expect(page.locator('#ingestion-discovery-status')).toContainText('valid authorization required');
});
