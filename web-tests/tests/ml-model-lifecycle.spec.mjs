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
  await page.goto('./#mlstudio', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('#ml-models')).toContainText('model-a');
  await page.locator('[data-feature="ml-card"]').click();
  await expect(page.locator('#ml-output')).toContainText('run-1');
  await page.evaluate(() => { window.prompt = () => 'validated in Studio'; });
  await page.locator('[data-feature="ml-promote"]').click();
  await expect.poll(() => promoted).toBe(true);
});

test('ML Studio registers a successful durable run as a candidate model', async ({ page }) => {
  let registered = false;
  await page.route('**/v1/ml-studio/labs?**', route => route.fulfill({json: {
    items: [{id: 'churn', name: 'Churn', task: 'classification', backend_id: 'local.sklearn'}],
  }}));
  await page.route('**/v1/ml-studio/models?**', route => route.fulfill({json: {
    items: registered ? [{model_id: 'churn', version: 'run-ui', stage: 'candidate'}] : [],
  }}));
  await page.route('**/v1/ml-studio/labs/churn/executions?**', route => route.fulfill({json: {
    run_id: 'run-ui', state: 'queued',
  }}));
  await page.route('**/v1/ml-studio/executions/run-ui?**', route => route.fulfill({json: {
    run_id: 'run-ui', state: 'succeeded', result: {artifact_digest: 'a'.repeat(64)},
  }}));
  await page.route('**/v1/ml-studio/executions/run-ui/register?**', async route => {
    const body = route.request().postDataJSON();
    registered = body.model_id === 'churn' && body.version === 'run-ui';
    await route.fulfill({json: {
      model_id: body.model_id, version: body.version, stage: 'candidate',
    }});
  });
  await page.goto('./#mlstudio', {waitUntil: 'domcontentloaded'});
  await page.locator('[data-feature="ml-run"]').click();
  await expect(page.locator('#ml-register-execution')).toBeVisible();
  await page.locator('#ml-register-execution button[type="submit"]').click();
  await expect.poll(() => registered).toBe(true);
  await expect(page.locator('#ml-register-execution')).toContainText('Registered candidate churn@run-ui');
  await expect(page.locator('#ml-models')).toContainText('churn');
});
