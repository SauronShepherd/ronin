import { test, expect } from '@playwright/test';

test('Synthetic Studio exposes validation and cancellable async generation', async ({ page }) => {
  const calls = [];
  await page.route('**/v1/synthetic-data-studio/catalog/providers**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/synthetic-data-studio/catalog/assets**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/synthetic-data-studio/runs**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/synthetic-data-studio/validate**', async route => {
    calls.push('validate');
    await route.fulfill({json: {status: 'validated', evidenceId: 'evidence-1'}});
  });
  await page.route('**/v1/synthetic-data-studio/generate/async**', async route => {
    calls.push('async');
    await route.fulfill({json: {job_id: 'job-1', run_id: 'run-1', status: 'queued'}});
  });
  await page.route('**/v1/synthetic-data-studio/jobs/job-1/cancel**', async route => {
    calls.push('cancel');
    await route.fulfill({json: {job_id: 'job-1', status: 'cancelled'}});
  });
  await page.goto('./#synthetic', {waitUntil: 'domcontentloaded'});
  await page.locator('[data-sds-validate]').click();
  await expect(page.locator('#synthetic-studio-result')).toContainText('evidence-1');
  await page.locator('[data-sds-async]').click();
  await page.locator('[data-sds-cancel]').click();
  await expect(page.locator('#synthetic-studio-result')).toContainText('cancelled');
  expect(calls).toEqual(['validate', 'async', 'cancel']);
});
