import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('home control plane', () => {
  test('exposes an action-first, honest starting point', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });

    await expect(page.locator('#home-overview-title')).toHaveText('One clear path from data to decision.');
    await expect(page.locator('.home-view > .page-header')).toBeHidden();
    await expect(page.locator('.command-open-label')).toHaveText('Search or jump');
    await expect(page.locator('.command-open kbd')).toHaveText('⌘K');
    await expect(page.locator('.home-context-card')).toContainText('default / examples/demo');
    await expect(page.locator('.home-context-source')).toContainText('Example context');
    await expect(page.locator('.context-bar')).toContainText('Workspacedefault');
    await expect(page.locator('.context-change')).toHaveAttribute('data-action', 'open-context');
    await expect(page.locator('.home-status-card')).toHaveCount(4);
    await expect(page.locator('.home-journey-list li')).toHaveCount(3);
    await expect(page.locator('.home-shortcuts')).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText('undefined');

    for (const route of ['workspaces', 'data', 'quality', 'runs', 'migration', 'sql']) {
      await expect(page.locator(`a[href="#${route}"]`).first()).toBeVisible();
    }
  });

  test('renders launch context without inventing live telemetry', async ({ page }) => {
    await page.goto('./?workspace=team-a&project=project-z#home', { waitUntil: 'load' });

    await expect(page.locator('.home-context-card')).toContainText('team-a / project-z');
    await expect(page.locator('.context-bar')).toContainText('team-a');
    await expect(page.locator('.context-bar')).toContainText('project-z');
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
    await page.locator('.command-open').click();
    await expect(page.locator('.command-palette')).toBeVisible();
    await expect(page.locator('.command-palette')).toHaveAttribute('aria-label', 'Search commands…');
    await expect(page.locator('#ronin-command-search')).toHaveAttribute('aria-controls', 'ronin-command-list');
    await page.locator('#ronin-command-search').fill('quality');
    await expect(page.locator('.command-option')).toContainText('Quality Studio');
    await expect(page.locator('#ronin-command-list')).toHaveAttribute('aria-activedescendant', /ronin-command-/);
    await expect(page.locator('.command-option[aria-selected="true"]')).toHaveCount(1);
    await expect(page.locator('.command-option-copy small')).toContainText('Run checks and review promotion gates.');
    await page.locator('#ronin-command-search').fill('promotion gates');
    await expect(page.locator('.command-option')).toContainText('Quality Studio');
    await page.keyboard.press('Escape');
    await expect(page.locator('.command-palette')).not.toBeVisible();
    await expect(page.locator('.command-open')).toBeFocused();
  });

  test('opens a context picker and carries the selected boundary through the shell', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });
    await page.locator('.context-change').click();
    await expect(page.locator('#context-dialog')).toBeVisible();
    await page.locator('#context-form [name="workspace"]').fill('team-a');
    await page.locator('#context-form [name="project"]').fill('project-z');
    await page.locator('#context-form [name="environment"]').fill('staging');
    await page.locator('#context-form [name="runtime"]').fill('container');
    await page.locator('#context-form button[type="submit"]').click();
    await expect(page.locator('#context-dialog')).not.toBeVisible();
    await expect(page.locator('.home-context-card')).toContainText('team-a / project-z');
    await expect(page.locator('.context-bar')).toContainText('team-a');
    await expect(page.locator('.context-bar')).toContainText('project-z');
    await expect(page).toHaveURL(/workspace=team-a.*project=project-z.*environment=staging.*runtime=container/);
    await page.locator('a[href="#sql"]').first().click();
    await expect(page.locator('#sql-workspace')).toHaveValue('team-a');
    await expect(page.locator('#sql-project')).toHaveValue('project-z');
    await page.locator('a[href="#migration"]').first().click();
    await expect(page.locator('#migration-cockpit-workspace')).toHaveValue('team-a');
    await expect(page.locator('#migration-cockpit-project')).toHaveValue('project-z');
  });

  test('remembers safe recent contexts for fast cross-studio switching', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });
    await page.locator('.context-change').click();
    await expect(page.locator('.context-recent-empty')).toHaveText(/recent working contexts/i);
    await page.locator('#context-form [name="workspace"]').fill('team-a');
    await page.locator('#context-form [name="project"]').fill('project-z');
    await page.locator('#context-form [name="environment"]').fill('staging');
    await page.locator('#context-form [name="runtime"]').fill('container');
    await page.locator('#context-form button[type="submit"]').click();
    await page.locator('.context-change').click();
    await expect(page.locator('.context-recent-option')).toHaveCount(1);
    await expect(page.locator('.context-recent-option')).toContainText('team-a / project-z');
    await expect(page.locator('.context-recent-option')).toContainText('staging · container');
    await page.locator('.context-recent-option').press('Enter');
    await expect(page.locator('#context-dialog')).not.toBeVisible();
    await expect(page).toHaveURL(/workspace=team-a.*project=project-z.*environment=staging.*runtime=container/);
    const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('ronin.recent-contexts')));
    expect(saved).toEqual([{ workspace: 'team-a', project: 'project-z', environment: 'staging', runtime: 'container' }]);
  });

  test('opens a surface when a command palette option is clicked', async ({ page }) => {
    await page.goto('./#home', { waitUntil: 'load' });
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+K' : 'Control+K');
    await page.locator('#ronin-command-search').fill('quality');
    await page.locator('.command-option').first().click();
    await expect(page).toHaveURL(/#quality$/);
    await expect(page.locator('#quality-form')).toBeVisible();
  });

  test('shows bounded recent activity for the active project without inventing telemetry', async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem('ronin.session', 'static-home-token'));
    await page.route('**/v1/jobs**', async route => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get('project')).toBe('examples/demo');
      await route.fulfill({
        json: {
          items: [
            { id: 'run-42', project_id: 'examples/demo', state: 'running', created_at: '2026-11-07T04:00:00Z', updated_at: '2026-11-07T04:01:00Z' },
            { id: 'run-41', project_id: 'examples/demo', state: 'succeeded', created_at: '2026-11-07T03:00:00Z', updated_at: '2026-11-07T03:03:00Z' },
          ],
        },
      });
    });
    await page.goto('./#home', { waitUntil: 'load' });
    await expect(page.locator('#home-activity')).toContainText('run-42');
    await expect(page.locator('#home-activity')).toContainText('running');
    await expect(page.locator('[data-home-activity-row]')).toHaveCount(2);
    await expect(page.locator('#home-activity')).not.toContainText('undefined');
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
