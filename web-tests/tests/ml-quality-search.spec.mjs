import { test, expect } from '@playwright/test';

test('ML Studio exposes quality and trial-search contracts', async ({ page }) => {
  const calls = [];
  await page.route('**/v1/ml-studio/labs**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/ml-studio/models**', route => route.fulfill({json: {items: []}}));
  await page.route('**/v1/ml-studio/labs/churn/quality**', async route => {
    calls.push(['quality', await route.request().postDataJSON()]);
    await route.fulfill({json: {status: 'passed'}});
  });
  await page.route('**/v1/ml-studio/labs/churn/search**', async route => {
    calls.push(['search', await route.request().postDataJSON()]);
    await route.fulfill({json: {items: [{parameters: {seed: 17}, metrics: {accuracy: 0.9}}]}});
  });
  await page.goto('./#mlstudio', {waitUntil: 'domcontentloaded'});
  await page.locator('#ml-quality-form button').click();
  await expect(page.locator('#ml-output')).toContainText('passed');
  await page.locator('#ml-search-form button').click();
  await expect(page.locator('#ml-output')).toContainText('0.9');
  expect(calls.map(([kind]) => kind)).toEqual(['quality', 'search']);
});
