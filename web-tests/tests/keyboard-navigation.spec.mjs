import { test, expect } from '@playwright/test';

test('keyboard users can skip navigation and activate a route', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.locator('.skip-link').focus();
  await expect(page.locator('.skip-link')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();
  await expect(page.locator('#breadcrumb')).toHaveText('Overview');

  await page.locator('#rail a[href="#workspaces"]').focus();
  await expect(page.locator('#rail a[href="#workspaces"]')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#workspaces$/);
  await expect(page.locator('#breadcrumb')).toHaveText('Workspaces');
});

test('navigation opens the current Machine Learning Studio instead of a stale placeholder', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.locator('#rail a[href="#mlstudio"]').click();
  await expect(page.locator('#breadcrumb')).toHaveText('Machine Learning Studio');
  await expect(page.locator('#view')).not.toContainText('Data Science Studio');
});
