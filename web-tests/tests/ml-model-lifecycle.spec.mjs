import { test, expect } from '@playwright/test';

test('ML Studio exposes model card and promotion actions', async ({ page }) => {
  let promoted = false;
  await page.route('**/v1/ml-studio/labs**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/ml-studio/models?**', route => route.fulfill({json: {
    items: [{model_id: 'model-a', version: 'v1', stage: 'candidate'}],
  }}));
  await page.route('**/v1/ml-studio/models/model-a/v1/card**', route => route.fulfill({json: {
    model_id: 'model-a', version: 'v1', provenance: {run_id: 'run-1'}, quality: {accuracy: 0.9},
  }}));
  await page.route('**/v1/ml-studio/models/model-a/v1/promote**', async route => {
    promoted = (await route.request().postDataJSON()).reason === 'validated in Studio';
    await route.fulfill({json: {model_id: 'model-a', version: 'v1', stage: 'champion'}});
  });
  await page.goto('./#mlstudio', {waitUntil: 'networkidle'});
  await expect(page.locator('#ml-models')).toContainText('model-a');
  await page.locator('[data-feature="ml-card"]').click();
  await expect(page.locator('#ml-output')).toContainText('run-1');
  await page.evaluate(() => { window.prompt = () => 'validated in Studio'; });
  await page.locator('[data-feature="ml-promote"]').click();
  await expect.poll(() => promoted).toBe(true);
});
