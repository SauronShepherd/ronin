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
  let promoted = false;
  let executionBody;
  await page.route('**/v1/ml-studio/labs?**', route => route.fulfill({json: {
    items: [{id: 'churn', name: 'Churn', task: 'classification', backend_id: 'local.sklearn', features: [{column: 'segment', role: 'categorical'}]}],
  }}));
  await page.route('**/v1/ml-studio/models?**', route => route.fulfill({json: {
    items: registered ? [{model_id: 'churn', version: 'run-ui', stage: promoted ? 'champion' : 'candidate'}] : [],
  }}));
  await page.route('**/v1/ml-studio/labs/churn/executions?**', async route => {
    executionBody = route.request().postDataJSON();
    await route.fulfill({json: {run_id: 'run-ui', state: 'queued'}});
  });
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
  await page.route('**/v1/ml-studio/models/churn/run-ui/promote**', async route => {
    promoted = (await route.request().postDataJSON()).reason === 'validated run';
    await route.fulfill({json: {model_id: 'churn', version: 'run-ui', stage: 'champion'}});
  });
  await page.goto('./#mlstudio', {waitUntil: 'domcontentloaded'});
  await page.locator('[data-ml-algorithm="churn"]').selectOption('random_forest_classifier');
  await page.locator('[data-ml-preprocessor="churn"]').selectOption('one_hot');
  await page.locator('[data-feature="ml-run"]').click();
  await expect.poll(() => executionBody?.algorithm).toBe('random_forest_classifier');
  await expect.poll(() => executionBody?.preprocessor).toBe('one_hot');
  await expect.poll(() => executionBody?.rows?.[0]?.segment).toBe('category-0');
  await expect(page.locator('#ml-register-execution')).toBeVisible();
  await page.locator('#ml-register-execution button[type="submit"]').click();
  await expect.poll(() => registered).toBe(true);
  await expect(page.locator('#ml-register-execution')).toContainText('Registered candidate churn@run-ui');
  await expect(page.locator('#ml-models')).toContainText('churn');
  await page.evaluate(() => { window.prompt = () => 'validated run'; });
  await page.locator('#ml-register-execution [data-feature="ml-promote"]').click();
  await expect.poll(() => promoted).toBe(true);
  await expect(page.locator('#ml-models')).toContainText('champion');
});

test('ML Studio retries a failed durable run from a selected stage', async ({ page }) => {
  let retryBody;
  let registered = false;
  await page.route('**/v1/ml-studio/labs?**', route => route.fulfill({json: {
    items: [{id: 'churn', name: 'Churn', task: 'classification', backend_id: 'local.sklearn'}],
  }}));
  await page.route('**/v1/ml-studio/models?**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/ml-studio/labs/churn/executions?**', route => route.fulfill({json: {
    run_id: 'failed-ui', state: 'queued',
  }}));
  await page.route('**/v1/ml-studio/executions/failed-ui?**', route => route.fulfill({json: {
    run_id: 'failed-ui', state: 'failed', error: 'train failed transiently',
  }}));
  await page.route('**/v1/ml-studio/executions/failed-ui/retry?**', async route => {
    retryBody = route.request().postDataJSON();
    await route.fulfill({json: {
      run_id: retryBody.run_id, state: 'queued',
      retry_of_run_id: 'failed-ui', retry_from_stage: retryBody.from_stage,
    }});
  });
  await page.route('**/v1/ml-studio/executions/failed-ui-retry?**', route => route.fulfill({json: {
    run_id: 'failed-ui-retry', state: 'succeeded', result: {artifact_digest: 'b'.repeat(64)},
  }}));
  await page.route('**/v1/ml-studio/executions/failed-ui-retry/register?**', async route => {
    registered = true;
    await route.fulfill({json: {model_id: 'churn', version: 'failed-ui-retry', stage: 'candidate'}});
  });
  await page.goto('./#mlstudio', {waitUntil: 'domcontentloaded'});
  await page.locator('[data-feature="ml-run"]').click();
  await expect(page.locator('#ml-retry-execution')).toBeVisible();
  await page.locator('#ml-retry-execution [name="retry_run_id"]').fill('failed-ui-retry');
  await page.locator('#ml-retry-execution [name="from_stage"]').selectOption('evaluate');
  await page.locator('#ml-retry-execution button[type="submit"]').click();
  await expect.poll(() => retryBody).toEqual({run_id: 'failed-ui-retry', from_stage: 'evaluate'});
  await expect(page.locator('#ml-register-execution')).toBeVisible();
  await page.locator('#ml-register-execution button[type="submit"]').click();
  await expect.poll(() => registered).toBe(true);
});

test('ML Studio downloads a verified artifact in bounded chunks', async ({ page }) => {
  const requests = [];
  await page.route('**/v1/ml-studio/labs**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/ml-studio/models?**', route => route.fulfill({json: {
    items: [{model_id: 'model-a', version: 'v1', stage: 'candidate'}],
  }}));
  await page.route('**/v1/ml-studio/models/model-a/v1/artifact**', async route => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get('offset'));
    requests.push(offset);
    const common = {model_id: 'model-a', version: 'v1', digest: 'a'.repeat(64), media_type: 'application/octet-stream', size_bytes: 5};
    await route.fulfill({json: offset === 0
      ? {...common, offset: 0, next_offset: 3, complete: false, data_base64: 'YWJj'}
      : {...common, offset: 3, next_offset: null, complete: true, data_base64: 'ZGU='}});
  });
  await page.goto('./#mlstudio', {waitUntil: 'domcontentloaded'});
  const downloadPromise = page.waitForEvent('download');
  await page.locator('[data-feature="ml-download"]').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('model-a-v1.artifact');
  await expect(page.locator('#ml-output')).toContainText('Downloaded model-a@v1 (5 bytes');
  expect(requests).toEqual([0, 3]);
});
