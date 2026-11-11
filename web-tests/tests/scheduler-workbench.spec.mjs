import { test, expect } from '@playwright/test';

test('Scheduler Studio groups durable operations and keeps their scope visible', async ({ page }) => {
  await page.route('**/v1/workspaces/default/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'GET' && url.pathname.endsWith('/workflows')) {
      await route.fulfill({ json: { items: [{ id: 'main', name: 'Main workflow' }] } });
      return;
    }
    if (request.method() === 'GET' && url.pathname.endsWith('/event-triggers')) {
      await route.fulfill({ json: { items: [] } });
      return;
    }
    if (request.method() === 'GET' && url.pathname.endsWith('/schedules')) {
      await route.fulfill({ json: { items: [{ id: 'daily', workflow_id: 'main', cron: '0 0 * * *', enabled: true }] } });
      return;
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/workflows/main/runs')) {
      await route.fulfill({ json: { id: 'run-42', state: 'queued', workflow_id: 'main' } });
      return;
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/backfills/preview')) {
      await route.fulfill({ json: { items: [{ scheduled_at: '2026-01-01T00:00:00Z' }] } });
      return;
    }
    throw new Error(`Unexpected scheduler request ${request.method()} ${url.pathname}`);
  });

  await page.goto('./#workflows');
  await expect(page.locator('.scheduler-hero')).toContainText('durable workflow operations');
  await expect(page.locator('[data-action-group="observe"]')).toContainText('List schedules');
  await expect(page.locator('[data-action-group="recover"]')).toContainText('Preview backfill');

  await page.getByRole('button', { name: 'List schedules' }).click();
  await expect(page.locator('#scheduler-result')).toContainText('daily');
  await page.getByRole('button', { name: 'Run workflow' }).click();
  await expect(page.locator('#scheduler-result')).toContainText('run-42');
  await page.getByRole('button', { name: 'Preview backfill' }).click();
  await expect(page.locator('#scheduler-result')).toContainText('scheduled_at');

  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.locator('#main').evaluate(node => ({ client: node.clientWidth, scroll: node.scrollWidth }));
  expect(widths.scroll).toBe(widths.client);
});

test('Scheduler Studio retries a failed observation without losing its scope', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/default/schedules', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { code: 'scheduler_unavailable', message: 'Scheduler is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'daily', workflow_id: 'main' }] } });
  });
  await page.goto('./#workflows');
  await page.locator('#scheduler-form [name="workspace"]').fill('default');
  await page.locator('#scheduler-form [name="schedule_id"]').fill('daily');
  await page.getByRole('button', { name: 'List schedules' }).click();
  await expect(page.locator('#scheduler-result')).toContainText('Scheduler is warming up.');
  await page.getByRole('button', { name: 'Retry this observation', exact: true }).click();
  await expect(page.locator('#scheduler-result')).toContainText('daily');
  await expect(page.locator('#scheduler-form [name="schedule_id"]')).toHaveValue('daily');
  expect(attempts).toBe(2);
});

test('Scheduler Studio retries event delivery observation after a transient error', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/default/event-deliveries?limit=100', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { code: 'delivery_unavailable', message: 'Delivery index is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'delivery-1', state: 'delivered' }] } });
  });
  await page.goto('./#workflows');
  await page.getByRole('button', { name: 'Inspect event deliveries' }).click();
  await expect(page.locator('#scheduler-result')).toContainText('Delivery index is warming up.');
  await page.getByRole('button', { name: 'Retry this observation', exact: true }).click();
  await expect(page.locator('#scheduler-result')).toContainText('delivery-1');
  expect(attempts).toBe(2);
});

test('Scheduler Studio inherits the active shell workspace', async ({ page }) => {
  const requests = [];
  await page.route('**/v1/workspaces/team-a/schedules', async route => {
    requests.push(route.request().url());
    await route.fulfill({ json: { items: [] } });
  });
  await page.goto('./?workspace=team-a&project=project-z#workflows');
  await expect(page.locator('#scheduler-form [name="workspace"]')).toHaveValue('team-a');
  await page.getByRole('button', { name: 'List schedules' }).click();
  await expect(page.locator('#scheduler-result')).toContainText('items');
  expect(requests).toHaveLength(1);
});
