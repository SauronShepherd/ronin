import { test, expect } from '@playwright/test';
import routes from '../../web/routes.json' with { type: 'json' };

test.describe('Studio route traversal', () => {
  for (const route of routes) {
    test(`${route.id} renders a stable surface`, async ({ page }) => {
      await page.goto(`./#${route.id}`, { waitUntil: 'load' });
      await expect(page.locator('#rail')).toBeVisible();
      await expect(page.locator('#rail .nav-item')).toHaveCount(routes.length);
      await expect(page.locator('#rail .nav-item').first()).toBeVisible();
      await expect(page.locator('#breadcrumb')).not.toHaveText('Studio');
      await expect(page.locator('#view')).toBeVisible();
      await expect(page.locator(route.smoke_selector)).toBeVisible();
      await expect(page.locator('body')).not.toContainText('undefined');
    });
  }

  test('full navigation and responsive sweep stay usable', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });
    const links = page.locator('#rail .nav-item');
    await expect(links).toHaveCount(routes.length);

    for (const route of routes) {
      await page.locator(`#rail .nav-item[href="#${route.id}"]`).click();
      await expect(page).toHaveURL(new RegExp(`#${route.id}$`));
      await expect(page.locator(route.smoke_selector)).toBeVisible();
      await expect(page.locator('#rail .nav-item[aria-current="page"]')).toHaveCount(1);
      await expect(page.locator(`#rail .nav-item[href="#${route.id}"]`)).toHaveAttribute('aria-current', 'page');
    }

    await page.locator('#rail .nav-item[href="#home"]').click();
    for (const viewport of [
      { width: 320, height: 720 },
      { width: 390, height: 844 },
      { width: 520, height: 900 },
      { width: 521, height: 900 },
      { width: 768, height: 1024 },
      { width: 900, height: 900 },
      { width: 901, height: 900 },
      { width: 1024, height: 900 },
      { width: 1280, height: 900 },
      { width: 1440, height: 900 },
    ]) {
      await page.setViewportSize(viewport);
      const layout = await page.evaluate(() => {
        const rail = document.querySelector('#rail');
        const nav = rail.querySelector('.nav-sections');
        const railBox = rail.getBoundingClientRect();
        return {
          documentWidth: document.documentElement.scrollWidth,
          htmlOverflowY: getComputedStyle(document.documentElement).overflowY,
          bodyOverflowY: getComputedStyle(document.body).overflowY,
          mainOverflowY: getComputedStyle(document.querySelector('#main')).overflowY,
          mainHasInternalScroll: document.querySelector('#main').scrollHeight > document.querySelector('#main').clientHeight,
          railPosition: getComputedStyle(rail).position,
          railBottom: railBox.bottom,
          navHasInternalOverflow: nav.scrollWidth > nav.clientWidth,
        };
      });
      expect(layout.documentWidth).toBeLessThanOrEqual(viewport.width);
      expect(layout.htmlOverflowY).toBe('hidden');
      expect(layout.bodyOverflowY).toBe('hidden');
      expect(layout.mainOverflowY).toBe('auto');
      expect(layout.mainHasInternalScroll).toBe(true);
      await expect(links).toHaveCount(routes.length);
      if (viewport.width <= 900) {
        expect(layout.railPosition).toBe('fixed');
        expect(layout.railBottom).toBeCloseTo(viewport.height, 0);
        expect(layout.navHasInternalOverflow).toBe(true);
      } else {
        expect(layout.railPosition).toBe('relative');
      }
    }
  });
});
