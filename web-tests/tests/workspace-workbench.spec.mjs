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

test('Project workbench keeps authoring modes and scope usable on a phone', async ({ page }) => {
  await page.route('**/v1/workspaces/workspace-a/projects', async route => {
    await route.fulfill({ json: { items: [{ id: 'project-a', name: 'Analytics' }] } });
  });
  await page.goto('./#projects/workspace-a');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.project-hero')).toBeVisible();
  await expect(page.locator('#project-overview-title')).toContainText('project boundary');
  await expect(page.locator('#project-overview-count')).toHaveText('1');
  await expect(page.locator('#project-source-state')).toHaveText('Unconfigured');
  await expect(page.locator('.project-mode-card')).toHaveCount(4);
  const layout = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    modeOverflow: document.querySelector('.project-mode-nav').scrollWidth > document.querySelector('.project-mode-nav').clientWidth,
  }));
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
  expect(layout.modeOverflow).toBe(false);
  await page.getByRole('button', { name: 'Connect project' }).click();
  await expect(page.locator('#project-environment-form')).toBeInViewport();
});
