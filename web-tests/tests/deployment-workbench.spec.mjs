import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('deployment workbench', () => {
  test('keeps observe, bind and operate steps visible in the active context', async ({ page }) => {
    await page.goto('./?workspace=team-a&project=project-z&environment=staging#deployments', { waitUntil: 'load' });
    await expect(page.locator('.deployment-hero')).toContainText('Bind a project to an environment');
    await expect(page.locator('.deployment-mode-nav')).toContainText('Observe');
    await expect(page.locator('.deployment-mode-nav')).toContainText('Bind');
    await expect(page.locator('.deployment-mode-nav')).toContainText('Operate');
    await expect(page.locator('#deployment-bindings-form [name="workspace"]')).toHaveValue('team-a');
    await expect(page.locator('#deployment-bindings-form [name="project"]')).toHaveValue('project-z');
    await expect(page.locator('#deployment-bindings-form [name="environment"]')).toHaveValue('staging');
    const layout = await page.locator('#main').evaluate(element => ({ client: element.clientWidth, scroll: element.scrollWidth }));
    expect(layout.scroll).toBe(layout.client);
  });

  test('reads and replaces a binding with an explicit project scope', async ({ page }) => {
    await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/environments/local/bindings', async route => {
      if (route.request().method() === 'PUT') {
        expect(route.request().postDataJSON()).toEqual({ project_id: 'examples/demo', environment_id: 'local', bindings: [{ key: 'runtime', value: 'container' }] });
        await route.fulfill({ json: { status: 'bound', environment_id: 'local', bindings: [{ key: 'runtime', value: 'container' }] } });
        return;
      }
      await route.fulfill({ json: { bindings: { runtime: 'local' } } });
    });
    await page.goto('./#deployments', { waitUntil: 'load' });
    await page.getByRole('button', { name: 'Read bindings', exact: true }).click();
    await expect(page.locator('#deployment-result')).toContainText('runtime');
    await page.locator('[name="bindings"]').fill('[{"key":"runtime","value":"container"}]');
    await page.getByRole('button', { name: 'Replace bindings', exact: true }).click();
    await expect(page.locator('#deployment-result')).toContainText('bound');
  });

  test('has no serious accessibility violations', async ({ page }) => {
    await page.goto('./#deployments', { waitUntil: 'load' });
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.filter(item => ['critical', 'serious'].includes(item.impact))).toEqual([]);
  });
});
