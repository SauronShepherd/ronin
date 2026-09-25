import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import routes from '../../web/routes.json' with { type: 'json' };

for (const route of routes) {
  test(`${route.id} has no serious accessibility violations`, async ({ page }) => {
    await page.goto('./', { waitUntil: 'domcontentloaded' });
    await page.goto(`#${route.id}`, { waitUntil: 'domcontentloaded' });
    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations.filter((item) => ['critical', 'serious'].includes(item.impact)),
    ).toEqual([]);
  });
}
