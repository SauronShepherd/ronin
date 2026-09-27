import { test, expect } from '@playwright/test';

test('ML Studio sends the batch-score contract with model identity', async ({ page }) => {
  let requestBody;
  await page.route('**/v1/ml-studio/labs**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/ml-studio/models**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/ml-studio/models/model-a/v1/batch-predict**', async route => {
    requestBody = await route.request().postDataJSON();
    await route.fulfill({json: {batch_id: 'studio-batch-1', predictions: [1]}});
  });
  await page.goto('./#mlstudio', {waitUntil: 'domcontentloaded'});
  const form = page.locator('[data-feature-form="ml-score"]');
  await form.locator('input[name="model_id"]').fill('model-a');
  await form.locator('input[name="version"]').fill('v1');
  await form.locator('input[name="batch_id"]').fill('studio-batch-1');
  await form.locator('textarea[name="rows"]').fill('[{"x":1}]');
  await form.locator('button').click();
  await expect(page.locator('#ml-output')).toContainText('studio-batch-1');
  expect(requestBody).toMatchObject({batch_id: 'studio-batch-1', rows: [{x: 1}]});
});
