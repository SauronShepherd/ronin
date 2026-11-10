import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('environment workbench', () => {
  test('keeps observe, author and govern decisions visible in the active context', async ({ page }) => {
    await page.route('**/v1/workspaces/team-a/environments', async route => {
      await route.fulfill({ json: { items: [
        { id: 'local', name: 'Local', description: 'Developer runtime', state: 'active' },
        { id: 'paused', name: 'Paused', description: 'Held for review', state: 'disabled' },
      ] } });
    });
    await page.goto('./?workspace=team-a&project=project-z&environment=staging#environments', { waitUntil: 'load' });

    await expect(page.locator('.environment-hero')).toContainText('Make the execution boundary explicit');
    await expect(page.locator('.environment-mode-nav')).toContainText('Observe');
    await expect(page.locator('.environment-mode-nav')).toContainText('Author');
    await expect(page.locator('.environment-mode-nav')).toContainText('Govern');
    await expect(page.locator('#environment-workspace')).toHaveValue('team-a');
    await expect(page.locator('#environment-result')).toContainText('2 environments visible');
    await expect(page.locator('#environment-result')).toContainText('Developer runtime');
    await expect(page.locator('#environment-result')).toContainText('Restore');
    await expect(page.locator('.environment-advanced')).toBeVisible();
    const layout = await page.locator('#main').evaluate(element => ({ client: element.clientWidth, scroll: element.scrollWidth }));
    expect(layout.scroll).toBe(layout.client);
  });

  test('creates a profile and refreshes the honest inventory', async ({ page }) => {
    let items = [];
    await page.route('**/v1/workspaces/default/environments', async route => {
      if (route.request().method() === 'POST') {
        expect(route.request().postDataJSON()).toEqual({ id: 'prod', name: 'Production', description: 'Shared runtime', state: 'active' });
        items = [{ id: 'prod', name: 'Production', description: 'Shared runtime', state: 'active' }];
        await route.fulfill({ status: 201, json: items[0] });
        return;
      }
      await route.fulfill({ json: { items } });
    });
    await page.route('**/v1/workspaces/default/environments/prod/diff', async route => {
      expect(route.request().method()).toBe('POST');
      expect(route.request().postDataJSON()).toMatchObject({ id: 'prod', name: 'Production', description: 'Shared runtime' });
      await route.fulfill({ json: { preview: 'safe', changes: [] } });
    });
    await page.goto('./#environments', { waitUntil: 'load' });
    await page.locator('#environment-create-form [name="id"]').fill('prod');
    await page.locator('#environment-create-form [name="name"]').fill('Production');
    await page.locator('#environment-create-form [name="description"]').fill('Shared runtime');
    await page.getByRole('button', { name: 'Preview diff', exact: true }).click();
    await expect(page.locator('#environment-create-result')).toContainText('safe');
    await page.getByRole('button', { name: 'Create environment', exact: true }).click();
    await expect(page.locator('#environment-result')).toContainText('Production');
    await expect(page.locator('#environment-create-result')).toContainText('prod is active');
  });

  test('pauses and restores a profile through explicit governance actions', async ({ page }) => {
    let state = 'active';
    await page.route('**/v1/workspaces/default/environments', async route => {
      await route.fulfill({ json: { items: [{ id: 'local', name: 'Local', description: '', state }] } });
    });
    await page.route('**/v1/workspaces/default/environments/local/disable', async route => {
      expect(route.request().method()).toBe('POST');
      state = 'disabled';
      await route.fulfill({ json: { id: 'local', state } });
    });
    await page.route('**/v1/workspaces/default/environments/local/enable', async route => {
      expect(route.request().method()).toBe('POST');
      state = 'active';
      await route.fulfill({ json: { id: 'local', state } });
    });
    await page.goto('./#environments', { waitUntil: 'load' });
    await page.getByRole('button', { name: 'Pause', exact: true }).click();
    await expect(page.locator('#confirm-dialog')).toBeVisible();
    await page.locator('#confirm-submit').click();
    await expect(page.getByRole('button', { name: 'Restore', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Restore', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible();
  });

  test('has no serious accessibility violations', async ({ page }) => {
    await page.route('**/v1/workspaces/default/environments', async route => {
      await route.fulfill({ json: { items: [] } });
    });
    await page.goto('./#environments', { waitUntil: 'load' });
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.filter(item => ['critical', 'serious'].includes(item.impact))).toEqual([]);
  });
});
