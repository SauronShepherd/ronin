import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('home control plane', () => {
  test('exposes an action-first, honest starting point', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });

    await expect(page.locator('#home-overview-title')).toHaveText('One clear path from data to decision.');
    await expect(page.locator('.home-context-card')).toContainText('default / examples/demo');
    await expect(page.locator('.home-context-source')).toContainText('Example context');
    await expect(page.locator('.context-bar')).toContainText('Workspacedefault');
    await expect(page.locator('.context-change')).toHaveAttribute('href', '#workspaces');
    await expect(page.locator('.home-status-card')).toHaveCount(4);
    await expect(page.locator('.home-journey-list li')).toHaveCount(3);
    await expect(page.locator('.home-shortcut')).toHaveCount(3);
    await expect(page.locator('body')).not.toContainText('undefined');

    for (const route of ['workspaces', 'data', 'quality', 'runs', 'migration', 'sql']) {
      await expect(page.locator(`a[href="#${route}"]`).first()).toBeVisible();
    }
  });

  test('renders launch context without inventing live telemetry', async ({ page }) => {
    await page.goto('./?workspace=team-a&project=project-z#home', { waitUntil: 'load' });

    await expect(page.locator('.home-context-card')).toContainText('team-a / project-z');
    await expect(page.locator('.home-context-source')).toContainText('Launch context');
    await expect(page.locator('.home-status-grid')).toHaveAttribute(
      'aria-label',
      'Suggested workflow checkpoints, not live telemetry',
    );
  });

  for (const viewport of [
    { name: 'phone', width: 320, height: 720 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'desktop', width: 1440, height: 900 },
  ]) {
    test(`keeps home sections usable at ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('./#home', { waitUntil: 'load' });
      await expect(page.locator('.home-overview')).toBeVisible();
      await expect(page.locator('.home-workbench')).toBeVisible();
      const layout = await page.evaluate(() => ({
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        statusCards: document.querySelectorAll('.home-status-card').length,
      }));
      expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
      expect(layout.statusCards).toBe(4);
    });
  }

  test('opens and closes the command palette from the home shell', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+K' : 'Control+K');
    await expect(page.locator('.command-palette')).toBeVisible();
    await page.locator('#ronin-command-search').fill('quality');
    await expect(page.locator('.command-option')).toContainText('Quality Studio');
    await expect(page.locator('.command-option-copy small')).toContainText('Run checks and review promotion gates.');
    await page.locator('#ronin-command-search').fill('promotion gates');
    await expect(page.locator('.command-option')).toContainText('Quality Studio');
    await page.keyboard.press('Escape');
    await expect(page.locator('.command-palette')).not.toBeVisible();
  });

  test('has no serious home accessibility violations', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.filter((item) => ['critical', 'serious'].includes(item.impact))).toEqual([]);
  });

  test('keeps the primary home actions keyboard reachable', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });
    const action = page.locator('.home-context-card [data-action="open-connection"]');
    await action.focus();
    await expect(action).toBeFocused();
    await action.press('Enter');
    await expect(page.locator('#connection-dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('#connection-dialog')).not.toBeVisible();
  });
});
