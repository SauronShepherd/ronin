import { test, expect } from '@playwright/test';
import routes from '../../web/routes.json' with { type: 'json' };

const diagnosticsByPage = new WeakMap();
const staticOrigin = new URL(process.env.RONIN_STUDIO_E2E_URL || 'http://127.0.0.1:8099/web/').origin;

test.describe('Studio route traversal', () => {
  test.beforeEach(async ({ page }) => {
    const diagnostics = { unexpectedResponses: [], failedRequests: [], staticApiMisses: new Set() };
    diagnosticsByPage.set(page, diagnostics);
    page.on('pageerror', error => console.error(`[browser pageerror] ${error.stack || error.message}`));
    page.on('console', message => {
      if (
        message.type() === 'error' &&
        !message.text().includes('Failed to load resource: the server responded with a status of 404')
      ) {
        console.error(`[browser console] ${message.text()}`);
      }
    });
    page.on('response', response => {
      if (response.status() >= 400) {
        const request = response.request();
        const url = new URL(response.url());
        const expectedStaticApiMiss =
          staticOrigin === 'http://127.0.0.1:8099' &&
          url.origin === staticOrigin &&
          url.pathname.startsWith('/v1/') &&
          response.status() === 404 &&
          request.resourceType() === 'fetch';
        if (expectedStaticApiMiss) {
          diagnostics.staticApiMisses.add(`${request.method()} ${url.pathname}`);
        } else {
          const failure = `${response.status()} ${request.resourceType()} ${response.url()}`;
          diagnostics.unexpectedResponses.push(failure);
          console.error(`[browser response] ${failure}`);
        }
      }
    });
    page.on('requestfailed', request => {
      const failure = `${request.resourceType()} ${request.url()}: ${request.failure()?.errorText || 'unknown error'}`;
      diagnostics.failedRequests.push(failure);
      console.error(`[browser requestfailed] ${failure}`);
    });
  });

  test.afterEach(async ({ page }) => {
    const diagnostics = diagnosticsByPage.get(page);
    expect(diagnostics.unexpectedResponses, 'unexpected failed static resources').toEqual([]);
    expect(diagnostics.failedRequests, 'failed browser network requests').toEqual([]);
  });

  for (const route of routes) {
    test(`${route.id} renders a stable surface`, async ({ page }) => {
      await page.goto(`./#${route.id}`, { waitUntil: 'load' });
      await expect(page.locator('#rail')).toBeVisible();
      await expect(page.locator('#rail .nav-item')).toHaveCount(routes.length, { timeout: 15_000 });
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
    await expect(links).toHaveCount(routes.length, { timeout: 15_000 });

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
