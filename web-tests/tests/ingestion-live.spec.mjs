import { test, expect } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import { connectLiveStudio, flushLiveTraffic, installLiveApiProxy } from './live-support.mjs';

const apiBase = process.env.RONIN_LIVE_API_URL;
const apiToken = process.env.RONIN_LIVE_API_TOKEN;
const workspace = process.env.RONIN_LIVE_WORKSPACE;
const pgPort = process.env.RONIN_LIVE_PG_PORT;
const pgDatabase = process.env.RONIN_LIVE_PG_DATABASE || 'ronin_test';
const liveReady = Boolean(apiBase && apiToken && workspace && pgPort);
const liveWorkerReady = liveReady && process.env.RONIN_LIVE_WORKER_ENABLED === '1';
const liveDatabaseMutationReady = liveWorkerReady && Boolean(process.env.RONIN_LIVE_PYTHON);

async function configureDatabaseConnection(request, {
  connectionId = 'pg-live-e2e',
  incremental = false,
} = {}) {
  const response = await request.post(
    `${apiBase}/v1/workspaces/${encodeURIComponent(workspace)}/connections`,
    {
      headers: { Authorization: `Bearer ${apiToken}` },
      data: {
        id: connectionId,
        name: 'Live PostgreSQL browser test',
        connector_id: 'postgresql',
        options: {
          host: '127.0.0.1',
          port: pgPort,
          database: pgDatabase,
          schema: 'public',
          connect_timeout: '5',
          ...(incremental ? {
            incremental_column: 'updated_at',
            tie_breaker_columns: 'id',
          } : {}),
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

function insertIncrementalAccount() {
  const python = process.env.RONIN_LIVE_PYTHON;
  if (!python) throw new Error('RONIN_LIVE_PYTHON is required for the live incremental fixture.');
  const script = [
    'import os',
    'import psycopg',
    "with psycopg.connect(host='127.0.0.1', port=int(os.environ['RONIN_LIVE_PG_PORT']), dbname=os.environ['RONIN_LIVE_PG_DATABASE'], user=os.environ['RONIN_PG_TEST_USER'], password=os.environ['RONIN_PG_TEST_PASSWORD']) as connection:",
    "    connection.execute('INSERT INTO public.ui_page_accounts (id, email, updated_at) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, updated_at = EXCLUDED.updated_at', (2, 'b@example.test', '2026-01-02T00:00:00Z'))",
  ].join('\n');
  const result = spawnSync(python, ['-c', script], {
    encoding: 'utf8',
    env: process.env,
    timeout: 15_000,
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    throw new Error(`Could not add the live incremental PostgreSQL row: ${result.stderr || result.error}`);
  }
}

async function submitLiveSync(page, definition) {
  await page.locator('#ingestion-definition').fill(JSON.stringify(definition));
  const submitResponse = page.waitForResponse(response =>
    response.request().method() === 'POST' &&
    new URL(response.url()).pathname === '/v1/platform/connectors/syncs',
  );
  await page.getByRole('button', { name: 'Run durable sync' }).click();
  const response = await submitResponse;
  expect(response.status(), await response.text()).toBe(201);
  const job = await response.json();
  expect(job.id).toBeTruthy();
  await expect(page.locator('#ingestion-sync-status')).toContainText('succeeded', { timeout: 90_000 });
  const receipt = JSON.parse((await page.locator('#ingestion-sync-evidence').textContent()) || '{}');
  expect(receipt.evidence.items).toEqual(expect.arrayContaining([
    expect.objectContaining({
      role: 'scheduler-result',
      availability: 'available',
      digest_algorithm: 'sha256',
      digest: expect.stringMatching(/^[0-9a-f]{64}$/),
    }),
  ]));
  return job;
}

async function readCheckpointHealth(page, identity) {
  await page.locator('#ingestion-definition').fill(JSON.stringify({
    id: 'checkpoint-health-inspection',
    connector_id: 'postgresql',
    connection_ref: 'pg-live-incremental-e2e',
    asset_ref: 'pg-live-incremental-e2e::public.ui_page_accounts',
    destination_ref: 'artifact://live-ingestion/incremental/accounts',
    checkpoint_identity: identity,
    mode: 'incremental',
  }));
  const healthResponse = page.waitForResponse(response =>
    response.request().method() === 'POST' &&
    new URL(response.url()).pathname === '/v1/platform/connectors/checkpoint-health',
  );
  await page.getByRole('button', { name: 'Checkpoint health' }).click();
  const response = await healthResponse;
  expect(response.status(), await response.text()).toBe(200);
  const payload = await response.json();
  const output = page.locator('#ingestion-preview-result');
  await expect(output).toContainText(identity);
  return payload;
}

async function ensureProject(request) {
  const projectsUrl = `${apiBase}/v1/workspaces/${encodeURIComponent(workspace)}/projects`;
  const headers = { Authorization: `Bearer ${apiToken}` };
  const listed = await request.get(projectsUrl, { headers });
  expect(listed.status(), await listed.text()).toBe(200);
  const items = (await listed.json()).items || [];
  if (items.some(item => item.project?.id === 'examples/demo')) return;

  const created = await request.post(projectsUrl, {
    headers: { ...headers, 'Idempotency-Key': `live-ingestion-${workspace}-examples-demo` },
    data: {
      schema: 'ronin.project/v1',
      project: {
        id: 'examples/demo',
        name: 'Ronin Live Qualification Fixture',
        repositories: [{
          adapter_id: 'git',
          alias: 'code',
          default_ref: 'main',
          role: 'primary',
          subdirectory: null,
          sync_policy: 'manual',
          uri: 'https://git.example.test/ronin/live.git',
        }],
        execution: {
          requirements: [],
          resolution: 'strict',
          runtime: { adapter_id: 'python', profile_id: '3.11' },
        },
      },
    },
  });
  expect([200, 201], await created.text()).toContain(created.status());
}

async function connectStudio(page, token = apiToken) {
  const proxied = installLiveApiProxy(page, token);
  await connectLiveStudio(page, token);
  await page.goto('./#ingestion');
  return proxied;
}

test('Ingestion Studio discovers real PostgreSQL pages through the live API', async ({ page, request }) => {
  test.setTimeout(120_000);
  test.skip(!liveWorkerReady, 'Run the full live qualification with its real Docker worker and seeded PostgreSQL tables.');
  await ensureProject(request);
  await configureDatabaseConnection(request);
  const proxied = await connectStudio(page);
  await expect.poll(() => proxied.some(call => call.path.endsWith('/v1/platform/connectors'))).toBe(true);
  expect(proxied.find(call => call.path.endsWith('/v1/platform/connectors'))).toMatchObject({
    status: 200,
    authorizationKind: 'expected',
  });
  await page.locator('#ingestion-workspace').fill(workspace);
  await page.locator('#ingestion-project').fill('examples/demo');
  await page.locator('[name="connection_ref"]').fill('pg-live-e2e');
  await page.locator('[name="connector_id"]').fill('postgresql');
  await page.locator('[name="page_size"]').fill('1');

  await page.getByRole('button', { name: 'Discover assets' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText(
    'Page 1 loaded',
    { timeout: 16_000 },
  );
  expect(proxied.find(call => call.path.endsWith('/v1/platform/connectors/discover'))).toMatchObject({
    status: 200,
    authorizationKind: 'expected',
  });
  await expect(page.locator('#ingestion-discovery-status')).toContainText('more pages available');
  await expect(page.locator('#ingestion-discovery-result')).toContainText('ui_page_accounts');
  await page.getByRole('button', { name: 'Load next page' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText(
    'Page 2 loaded',
    { timeout: 16_000 },
  );
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

  const syncDefinition = {
    id: `live-postgres-sync-${Date.now()}`,
    connector_id: 'postgresql',
    connection_ref: 'pg-live-e2e',
    asset_ref: 'pg-live-e2e::public.ui_page_accounts',
    destination_ref: 'artifact://live-ingestion/accounts',
    checkpoint_identity: `live-postgres-checkpoint-${Date.now()}`,
    mode: 'snapshot',
    source_revision_ref: { asset_id: 'live-ingestion-source', version: 'source-v1' },
    destination_asset_id: 'live-ingestion-target',
  };
  await page.locator('#ingestion-definition').fill(JSON.stringify(syncDefinition));
  const syncSubmit = page.waitForResponse(response =>
    response.request().method() === 'POST' &&
    new URL(response.url()).pathname === '/v1/platform/connectors/syncs',
  );
  await page.getByRole('button', { name: 'Run durable sync' }).click();
  const submitted = await syncSubmit;
  expect(submitted.status(), await submitted.text()).toBe(201);
  const job = await submitted.json();
  expect(job.id).toBeTruthy();
  await expect(page.locator('#ingestion-sync-status')).toContainText('succeeded', { timeout: 90_000 });
  const syncEvidence = JSON.parse((await page.locator('#ingestion-sync-evidence').textContent()) || '{}');
  expect(syncEvidence.evidence.items).toEqual(expect.arrayContaining([
    expect.objectContaining({
      role: 'scheduler-result',
      availability: 'available',
      digest_algorithm: 'sha256',
      digest: expect.stringMatching(/^[0-9a-f]{64}$/),
    }),
  ]));
  await expect(page.locator('#ingestion-sync-lineage')).toContainText('live-ingestion-target');
  expect(proxied.some(call => call.path.endsWith(`/syncs/${encodeURIComponent(job.id)}/status`) && call.status === 200)).toBe(true);

  await page.getByRole('button', { name: 'Checkpoint health' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText(syncDefinition.checkpoint_identity);
  await expect(page.locator('#ingestion-preview-result')).toContainText('"present": true');
  await flushLiveTraffic();
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

test('Ingestion Studio bootstraps and advances a PostgreSQL watermark without replay duplication', async ({ page, request }) => {
  test.setTimeout(180_000);
  test.skip(!liveDatabaseMutationReady, 'Run full live qualification with its hash-locked Python runtime, Docker worker and PostgreSQL fixture.');
  await ensureProject(request);
  await configureDatabaseConnection(request, {
    connectionId: 'pg-live-incremental-e2e',
    incremental: true,
  });
  const calls = await connectStudio(page);
  await page.locator('#ingestion-workspace').fill(workspace);
  await page.locator('#ingestion-project').fill('examples/demo');
  const checkpointIdentity = `live-postgres-watermark-${Date.now()}`;
  const definition = {
    id: `live-postgres-watermark-sync-${Date.now()}`,
    connector_id: 'postgresql',
    connection_ref: 'pg-live-incremental-e2e',
    asset_ref: 'pg-live-incremental-e2e::public.ui_page_accounts',
    destination_ref: 'artifact://live-ingestion/incremental/accounts',
    checkpoint_identity: checkpointIdentity,
    mode: 'snapshot',
    source_revision_ref: { asset_id: 'live-ingestion-incremental-source', version: 'source-v1' },
    destination_asset_id: 'live-ingestion-incremental-target',
  };

  await submitLiveSync(page, definition);
  await expect(page.locator('#ingestion-sync-lineage')).toContainText('live-ingestion-incremental-target');
  const initial = await readCheckpointHealth(page, checkpointIdentity);
  expect(initial.present).toBe(true);
  expect(initial.output_committed).toBe(true);
  expect(initial.checkpoint_digest).toMatch(/^[0-9a-f]{64}$/);
  const initialDigest = initial.checkpoint_digest;

  insertIncrementalAccount();
  const incrementalDefinition = { ...definition, mode: 'incremental' };
  await page.locator('#ingestion-definition').fill(JSON.stringify(incrementalDefinition));
  await page.getByRole('button', { name: 'Preview source' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('b@example.test');
  await submitLiveSync(page, { ...incrementalDefinition, id: `${definition.id}-after-source-change` });
  await expect(page.locator('#ingestion-sync-lineage')).toContainText('live-ingestion-incremental-target');
  const advanced = await readCheckpointHealth(page, checkpointIdentity);
  expect(advanced.present).toBe(true);
  expect(advanced.output_committed).toBe(true);
  expect(advanced.checkpoint_digest).toMatch(/^[0-9a-f]{64}$/);
  expect(advanced.checkpoint_digest).not.toBe(initialDigest);

  await submitLiveSync(page, { ...incrementalDefinition, id: `${definition.id}-replay` });
  const replayed = await readCheckpointHealth(page, checkpointIdentity);
  expect(replayed.checkpoint_digest).toBe(advanced.checkpoint_digest);
  expect(replayed.output_committed).toBe(true);
  expect(calls.some(call => call.path.endsWith('/v1/platform/connectors')) &&
    calls.every(call => call.authorization === 'present')).toBe(true);
  expect(calls.some(call => call.status >= 500 || call.status === 0)).toBe(false);
  await flushLiveTraffic();
});
