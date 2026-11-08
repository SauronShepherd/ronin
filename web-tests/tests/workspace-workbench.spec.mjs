import { test, expect } from '@playwright/test';

test('Workspace workbench keeps context, modes and create flow usable on a phone', async ({ page }) => {
  await page.route('**/v1/workspaces', async route => {
    await route.fulfill({ json: { items: [{ id: 'workspace-a', name: 'Analytics', status: 'active' }] } });
  });
  await page.goto('./#workspaces');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.workspace-hero')).toBeVisible();
  await expect(page.locator('.workspace-mode-card')).toHaveCount(3);
  const layout = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    modeOverflow: document.querySelector('.workspace-mode-nav').scrollWidth > document.querySelector('.workspace-mode-nav').clientWidth,
  }));
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
  expect(layout.modeOverflow).toBe(false);
  await page.getByRole('button', { name: 'Register workspace' }).click();
  await expect(page.locator('#workspace-create-form')).toBeInViewport();
});
