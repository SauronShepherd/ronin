import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';

const stream = {
  id: 'events/main',
  name: 'Live qualification events',
  source: {
    connection_id: 'live-kafka',
    resource: 'ronin-live-events',
    partitions: [0],
    format: 'json',
  },
  sink: { kind: 'table', target_ref: 'live-qualification-events', mode: 'append' },
  schema: [{ name: 'event', data_type: 'string', nullable: false }],
  runtime: { profile_id: 'local', batch_limit: 10, timeout_seconds: 1 },
};

test('Streaming Studio loads, edits, and saves a persisted stream definition', async ({ page }) => {
  let savedRequest;
  const apiRequests = [];
  const submitEvents = [];
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.route('**/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    apiRequests.push({ method: request.method(), pathname: url.pathname });
    if (request.method() === 'GET' && url.pathname === '/v1/workspaces/workspace-a/streams') {
      await route.fulfill({ json: { items: [stream] } });
      return;
    }
    expect(request.method()).toBe('PUT');
    expect(url.pathname).toBe('/v1/workspaces/workspace-a/streams/events%2Fmain');
    savedRequest = request.postDataJSON();
    await route.fulfill({
      json: { definition: savedRequest.definition, checkpoint_policy: savedRequest.checkpoint_policy },
    });
  });

  await page.goto('./#streaming');
  await page.locator('#stream-definition-form [name="workspace"]').fill('workspace-a');
  await page.getByRole('button', { name: 'Refresh stream list' }).click();
  await expect(page.locator('#stream-list option')).toHaveCount(1);
  await page.locator('#stream-list').selectOption('events/main');

  await expect(page.locator('#stream-definition-form [name="id"]')).toHaveValue('events/main');
  await expect(page.locator('#stream-definition-form [name="name"]')).toHaveValue(stream.name);
  await expect(page.locator('#stream-definition-form [name="connection_id"]')).toHaveValue('live-kafka');
  await expect(page.locator('#stream-definition-form [name="resource"]')).toHaveValue('ronin-live-events');
  expect(await page.locator('#stream-definition-form').evaluate(form => form.checkValidity())).toBe(true);

  await page.locator('#stream-definition-form [name="name"]').fill('Edited events');
  await page.locator('#stream-definition-form [name="checkpoint_policy"]').selectOption('resume');
  await page.locator('#stream-definition-form').evaluate(form => {
    form.addEventListener('submit', () => { window.__streamSubmitEvents = (window.__streamSubmitEvents || 0) + 1; });
  });
  await page.getByRole('button', { name: 'Save stream' }).click();
  await expect.poll(
    () => page.evaluate(() => window.__streamSubmitEvents || 0),
    { message: () => `submit=${apiRequests.length}, errors=${pageErrors.join('; ')}` },
  ).toBe(1);
  expect(savedRequest).toMatchObject({
    checkpoint_policy: 'resume',
    definition: { id: 'events/main', name: 'Edited events' },
  });
  await expect.poll(() => apiRequests.length).toBe(3);
  await expect(page.locator('#stream-definition-result')).toContainText('Edited events');
  expect(apiRequests).toEqual([
    { method: 'GET', pathname: '/v1/workspaces/workspace-a/streams' },
    { method: 'PUT', pathname: '/v1/workspaces/workspace-a/streams/events%2Fmain' },
    { method: 'GET', pathname: '/v1/workspaces/workspace-a/streams' },
  ]);
});

test('Streaming Studio retries a failed health check without losing stream scope', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/ws-a/streams/**/health', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { code: 'stream_unavailable', message: 'Stream health is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { stream_id: 'events/main', status: 'healthy', lag: 0 } });
  });
  await page.goto('./#streaming');
  await page.locator('#stream-health-form [name="workspace"]').fill('ws-a');
  await page.locator('#stream-health-form [name="stream"]').fill('events/main');
  await page.getByRole('button', { name: 'Check health' }).click();
  await expect(page.locator('#stream-health-result')).toContainText('Stream health is warming up.');
  await page.getByRole('button', { name: 'Retry health check', exact: true }).click();
  await expect(page.locator('#stream-health-result .stream-health-summary [data-state="healthy"]')).toHaveAttribute('aria-label', 'Stream health: healthy');
  await expect(page.locator('#stream-health-result')).toContainText('Total lag');
  await expect(page.locator('#stream-health-form [name="stream"]')).toHaveValue('events/main');
  expect(attempts).toBe(2);
});

test('Streaming Studio verifies, reviews, imports, and exports a portable Bundle', async ({ page }) => {
  const archive = Buffer.from('ronin-stream-bundle-fixture');
  const digest = createHash('sha256').update(archive).digest('hex');
  const exportArchive = Buffer.from('abc');
  const exportDigest = createHash('sha256').update(exportArchive).digest('hex');
  let importRequest;
  const requests = [];
  await page.route('**/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push({ method: request.method(), pathname: url.pathname });
    if (request.method() === 'GET' && url.pathname.endsWith('/streams')) {
      await route.fulfill({ json: { items: [stream] } });
      return;
    }
    if (request.method() === 'GET' && url.pathname.endsWith('/streams/bundle')) {
      await route.fulfill({
        json: {
          media_type: 'application/vnd.ronin.bundle+zip',
          digest: exportDigest,
          size_bytes: exportArchive.length,
          content_base64: exportArchive.toString('base64'),
        },
      });
      return;
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/streams/bundle/plan')) {
      expect(request.postDataJSON().content_base64).toBe(archive.toString('base64'));
      await route.fulfill({
        json: {
          items: [stream],
          unresolved_bindings: [
            { kind: 'connection', source_ref: 'connection:source-kafka', suggested_target_ref: null },
            { kind: 'runtime', source_ref: 'runtime-profile:local', suggested_target_ref: null },
            { kind: 'storage', source_ref: 'storage-target:orders', suggested_target_ref: null },
          ],
          bundle_digest: digest,
          size_bytes: archive.length,
        },
      });
      return;
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/streams/bundle/import')) {
      importRequest = request.postDataJSON();
      await route.fulfill({
        json: {
          items: [stream],
          checkpoint_policies: importRequest.checkpoint_policies,
          runtime_bindings: { 'events/main': 'ronin-stream-test' },
          bundle_digest: digest,
          size_bytes: archive.length,
        },
      });
      return;
    }
    throw new Error(`Unexpected request ${request.method()} ${url.pathname}`);
  });

  await page.goto('./#streaming');
  await page.locator('#stream-definition-form [name="workspace"]').fill('workspace-a');
  await page.locator('#stream-bundle-import-form [name="workspace"]').fill('workspace-a');
  await page.locator('#stream-bundle-import-form [name="bundle"]').setInputFiles({
    name: 'streams.roninbundle',
    mimeType: 'application/zip',
    buffer: archive,
  });
  await page.getByRole('button', { name: 'Verify and preview Bundle' }).click();
  await expect(page.locator('#stream-bundle-import-review')).toContainText('Verified 1 stream definition');
  const commit = page.getByRole('button', { name: 'Import reviewed Bundle' });
  await expect(commit).toBeDisabled();
  await page.locator('[data-binding-source="connection:source-kafka"]').fill('connection:target-kafka');
  await page.locator('[data-binding-source="storage-target:orders"]').fill('storage-target:orders-copy');
  await page.locator('[data-checkpoint-stream="events/main"]').selectOption('reset');
  await expect(commit).toBeEnabled();
  await commit.click();
  await expect(page.locator('#stream-bundle-result')).toContainText('Imported 1 stream definition');
  expect(importRequest).toMatchObject({
    expected_digest: digest,
    binding_remaps: {
      'connection:source-kafka': 'connection:target-kafka',
      'runtime-profile:local': 'runtime-profile:local',
      'storage-target:orders': 'storage-target:orders-copy',
    },
    checkpoint_policies: { 'events/main': 'reset' },
  });

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download stream Bundle' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('workspace-a-streams.roninbundle');
  expect(requests).toContainEqual({ method: 'POST', pathname: '/v1/workspaces/workspace-a/streams/bundle/plan' });
  expect(requests).toContainEqual({ method: 'POST', pathname: '/v1/workspaces/workspace-a/streams/bundle/import' });
  expect(requests).toContainEqual({ method: 'GET', pathname: '/v1/workspaces/workspace-a/streams/bundle' });
});
