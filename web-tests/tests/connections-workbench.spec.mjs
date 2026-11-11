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

test('Connections workbench inherits the active workspace and retries inventory', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/workspaces/team-a/connections', async route => {
    attempts += 1;
    if (attempts <= 2) {
      await route.fulfill({ status: 503, json: { detail: 'connection index is warming up' } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'warehouse', name: 'Warehouse', connector_id: 'postgres' }] } });
  });
  await page.goto('./?workspace=team-a&project=project-z#data');
  await expect(page.locator('#connection-list-form [name="workspace"]')).toHaveValue('team-a');
  await expect(page.locator('#connection-list')).toContainText('Connection lookup failed');
  await page.getByRole('button', { name: 'Retry inventory' }).click();
  await expect(page.locator('#connection-list')).toContainText('Warehouse');
  expect(attempts).toBe(3);
});

test('Connections workbench saves a secret-safe definition and refreshes its inventory', async ({ page }) => {
  let saved = false;
  await page.route('**/v1/workspaces/default/connections', async route => {
    if (route.request().method() === 'POST') {
      saved = true;
      await route.fulfill({ status: 201, json: { id: 'warehouse', name: 'Warehouse', connector_id: 'postgres', secret_refs: { password: 'secret://warehouse/password' } } });
      return;
    }
    await route.fulfill({ json: { items: saved ? [{ id: 'warehouse', name: 'Warehouse', connector_id: 'postgres', secret_refs: { password: 'secret://warehouse/password' } }] : [] } });
  });
  await page.goto('./#data');
  await expect(page.locator('#connections-studio')).toBeVisible();
  await expect(page.locator('#connection-editor-form')).toBeVisible();
  const form = page.locator('#connection-editor-form');
  await form.locator('[name="id"]').fill('warehouse');
  await form.locator('[name="name"]').fill('Warehouse');
  await form.locator('[name="connector_id"]').fill('postgres');
  await form.locator('[name="secret_refs"]').fill('{"password":"secret://warehouse/password"}');
  const save = page.getByRole('button', { name: 'Save connection' });
  await save.click();
  await expect(page.locator('#connection-result')).toContainText('warehouse');
  await expect(page.locator('#connection-result .connection-operation-summary')).toContainText('Saved connection');
  await expect(page.locator('#connection-result .connections-raw')).not.toHaveAttribute('open', '');
  await expect(page.locator('#connection-list')).toContainText('Warehouse');
  await expect(page.locator('#connection-list')).not.toContainText('secret://');
  expect(saved).toBe(true);
});

test('Connections workbench keeps save failures actionable', async ({ page }) => {
  await page.route('**/v1/workspaces/default/connections', async route => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'connector is not supported' }) });
      return;
    }
    await route.fulfill({ json: { items: [] } });
  });
  await page.goto('./#data');
  await expect(page.locator('#connections-studio')).toBeVisible();
  await expect(page.locator('#connection-editor-form')).toBeVisible();
  const form = page.locator('#connection-editor-form');
  await form.locator('[name="id"]').fill('unsupported');
  await form.locator('[name="name"]').fill('Unsupported');
  await form.locator('[name="connector_id"]').fill('unknown');
  await page.getByRole('button', { name: 'Save connection' }).click();
  await expect(page.locator('#connection-result')).toContainText('Connection save failed');
  await expect(page.locator('#connection-result')).toContainText('connector is not supported');
});
