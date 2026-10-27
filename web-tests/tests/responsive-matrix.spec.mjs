import { test, expect } from '@playwright/test';
import routes from '../../web/routes.json' with { type: 'json' };

for (const viewport of [
  { name: 'small phone', width: 320, height: 720 },
  { name: 'phone', width: 390, height: 844 },
  { name: 'mobile breakpoint', width: 520, height: 900 },
  { name: 'just above mobile', width: 521, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'tablet breakpoint', width: 900, height: 900 },
  { name: 'just above tablet', width: 901, height: 900 },
  { name: 'small desktop', width: 1024, height: 900 },
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'wide desktop', width: 1440, height: 900 },
]) {
  test(`shell remains usable at ${viewport.name} (${viewport.width}px)`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const pageErrors = [];
    const failedRequests = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    page.on('requestfailed', (request) => failedRequests.push(`${request.url()}: ${request.failure()?.errorText || 'failed'}`));
    await page.goto('./#home', { waitUntil: 'load' });
    expect(pageErrors, 'uncaught browser errors during app initialization').toEqual([]);
    expect(failedRequests, 'failed browser requests during app initialization').toEqual([]);
    await expect(page.locator('#rail')).toBeVisible();
    await expect(page.locator('#rail .nav-item')).toHaveCount(routes.length);
    await expect(page.locator('#main')).toBeVisible();
    await expect(page.locator('#breadcrumb')).toHaveText('Overview');
    await expect(page.locator('body')).not.toContainText('undefined');
    const mainBox = await page.locator('#main').boundingBox();
    expect(mainBox?.width).toBeGreaterThan(0);

    const layout = await page.evaluate(() => {
      const rail = document.querySelector('#rail');
      const nav = rail.querySelector('.nav-sections');
      const main = document.querySelector('#main');
      const railBox = rail.getBoundingClientRect();
      return {
        documentWidth: document.documentElement.scrollWidth,
        htmlOverflowY: getComputedStyle(document.documentElement).overflowY,
        bodyOverflowY: getComputedStyle(document.body).overflowY,
        shellOverflow: getComputedStyle(document.querySelector('#app')).overflow,
        railPosition: getComputedStyle(rail).position,
        railBottom: railBox.bottom,
        appColumns: getComputedStyle(document.querySelector('#app')).gridTemplateColumns,
        navHasInternalOverflow: nav.scrollWidth > nav.clientWidth,
        mainHasInternalScroll: main.scrollHeight > main.clientHeight,
      };
    });

    expect(layout.documentWidth).toBeLessThanOrEqual(viewport.width);
    expect(layout.htmlOverflowY).toBe('hidden');
    expect(layout.bodyOverflowY).toBe('hidden');
    expect(layout.shellOverflow).toBe('hidden');
    expect(layout.mainHasInternalScroll).toBe(true);
    expect(pageErrors).toEqual([]);
    if (viewport.width <= 900) {
      expect(layout.railPosition).toBe('fixed');
      expect(layout.railBottom).toBeCloseTo(viewport.height, 0);
      expect(layout.navHasInternalOverflow).toBe(true);
      expect(layout.appColumns.split(' ').length).toBe(1);
    } else {
      expect(layout.railPosition).toBe('relative');
    }
  });
}
