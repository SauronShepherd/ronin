import { test, expect } from '@playwright/test';

test('Connections workbench explains posture, scope and safe metadata on a phone', async ({ page }) => {
  await page.route('**/v1/workspaces/default/connections', async route => {
    await route.fulfill({ json: { items: [{ id: 'warehouse', name: 'Warehouse', connector_id: 'postgres', state: 'active', secret_refs: { password: 'secret://warehouse/password' } }] } });
  });
  await page.goto('./#data');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('#connections-studio')).toBeVisible();
  await expect(page.locator('.connections-mode-card')).toHaveCount(3);
  await expect(page.locator('#connection-count')).toHaveText('1');
  await expect(page.locator('#connection-health')).toHaveText('Unverified');
  await expect(page.locator('#connection-next')).toHaveText('Review refs');
  await expect(page.locator('#connection-list')).toContainText('Reference only');
  await expect(page.locator('#connection-list')).not.toContainText('secret://');
  const layout = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    modeOverflow: document.querySelector('.connections-mode-nav').scrollWidth > document.querySelector('.connections-mode-nav').clientWidth,
  }));
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
  expect(layout.modeOverflow).toBe(false);
  await page.locator('.connections-mode-card[data-connections-mode="configure"]').click();
  await expect(page.locator('#connection-editor-form')).toBeInViewport();
});

test('Connections workbench keeps unknown API failures visible', async ({ page }) => {
  await page.route('**/v1/workspaces/default/connections', async route => {
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'service unavailable' }) });
  });
  await page.goto('./#data');
  await expect(page.locator('#connection-count')).toHaveText('Unknown');
  await expect(page.locator('#connection-health')).toHaveText('Review error');
  await expect(page.locator('#connection-next')).toHaveText('Retry lookup');
  await expect(page.locator('#connection-list')).toContainText('Connection lookup failed');
});
