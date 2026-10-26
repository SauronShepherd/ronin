import { test, expect } from '@playwright/test';

test('catalog search follows the server cursor to the next bounded page', async ({ page }) => {
  const requests = [];
  await page.route('**/v1/workspaces/ws-a/catalog/assets**', async route => {
    const url = new URL(route.request().url());
    requests.push(url);
    if (!url.searchParams.has('cursor')) {
      await route.fulfill({
        json: {
          items: [{ id: 'asset-a', name: 'Orders', kind: 'table', tags: [], classifications: [] }],
          next_cursor: 'opaque-next-page',
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        items: [{ id: 'asset-b', name: 'Orders archive', kind: 'table', tags: [], classifications: [] }],
        next_cursor: null,
      },
    });
  });

  await page.goto('./#catalog', { waitUntil: 'load' });
  const form = page.locator('#catalog-search-form');
  await form.getByLabel('Workspace').fill('ws-a');
  await form.getByLabel('Search').fill('orders');
  await form.getByRole('button', { name: 'Search catalog' }).click();
  await expect(page.locator('#catalog-result')).toContainText('Orders');
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page.locator('#catalog-result')).toContainText('Orders archive');
  await expect(page.getByRole('button', { name: 'Next page' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Previous page' }).click();
  await expect(page.locator('#catalog-result')).toContainText('Orders');
  await expect(page.getByRole('button', { name: 'Previous page' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Next page' })).toBeVisible();

  expect(requests).toHaveLength(3);
  expect(requests[0].searchParams.get('q')).toBe('orders');
  expect(requests[0].searchParams.get('limit')).toBe('50');
  expect(requests[0].searchParams.get('include_governance')).toBeNull();
  expect(requests[0].searchParams.get('cursor')).toBeNull();
  expect(requests[1].searchParams.get('cursor')).toBe('opaque-next-page');
  expect(requests[2].searchParams.get('cursor')).toBeNull();
});
