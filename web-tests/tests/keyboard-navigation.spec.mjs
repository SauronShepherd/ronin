import { test, expect } from '@playwright/test';

test('keyboard users can skip navigation and activate a route', async ({ page }) => {
  await page.goto('./', { waitUntil: 'networkidle' });
  await page.locator('.skip-link').focus();
  await expect(page.locator('.skip-link')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();

  await page.locator('#rail a[href="#workspaces"]').focus();
  await expect(page.locator('#rail a[href="#workspaces"]')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#workspaces$/);
  await expect(page.locator('#breadcrumb')).toHaveText('Workspaces');
});
