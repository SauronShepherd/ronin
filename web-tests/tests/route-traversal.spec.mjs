import { test, expect } from '@playwright/test';
import routes from '../../web/routes.json' with { type: 'json' };

test.describe('Studio route traversal', () => {
  for (const route of routes) {
    test(`${route.id} renders a stable surface`, async ({ page }) => {
      await page.goto('./', { waitUntil: 'networkidle' });
      await page.goto(`#${route.id}`, { waitUntil: 'networkidle' });
      await expect(page.locator('#rail')).toBeVisible();
      await expect(page.locator('#rail .nav-item').first()).toBeVisible();
      await expect(page.locator('#breadcrumb')).not.toHaveText('Studio');
      await expect(page.locator('#view')).toBeVisible();
      await expect(page.locator(route.smoke_selector)).toBeVisible();
      await expect(page.locator('body')).not.toContainText('undefined');
    });
  }
});
