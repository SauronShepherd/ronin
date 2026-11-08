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
