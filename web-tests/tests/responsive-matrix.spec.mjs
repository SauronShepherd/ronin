import { test, expect } from '@playwright/test';

for (const viewport of [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1440, height: 900 },
]) {
  test(`shell remains usable at ${viewport.name} width`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('./#home', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#rail')).toBeVisible();
    await expect(page.locator('#main')).toBeVisible();
    await expect(page.locator('#breadcrumb')).toHaveText('Overview');
    await expect(page.locator('body')).not.toContainText('undefined');
    const mainBox = await page.locator('#main').boundingBox();
    expect(mainBox?.width).toBeGreaterThan(0);
  });
}
