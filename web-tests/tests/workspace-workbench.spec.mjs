import { test, expect } from '@playwright/test';

test('Workspace inventory recovers through retry after a refresh error', async ({ page }) => {
  let attempts = 0;
  let failNext = false;
  await page.route('**/v1/workspaces', async route => {
    attempts += 1;
    if (failNext) {
      failNext = false;
      await route.fulfill({ status: 503, json: { error: { code: 'service_unavailable', message: 'Workspace index is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'workspace-a', name: 'Analytics', status: 'active' }] } });
  });
  await page.goto('./#workspaces');
  await expect(page.getByText('Analytics')).toBeVisible();
  failNext = true;
  await page.getByRole('button', { name: 'Refresh workspaces' }).click();
  await expect(page.getByText('Workspace index is warming up.')).toBeVisible();
  await page.getByRole('button', { name: 'Retry workspace inventory' }).click();
  await expect(page.getByText('Analytics')).toBeVisible();
  expect(attempts).toBeGreaterThanOrEqual(3);
});

test('Workspace workbench keeps context, modes and create flow usable on a phone', async ({ page }) => {
  await page.route('**/v1/workspaces', async route => {
    await route.fulfill({ json: { items: [{ id: 'workspace-a', name: 'Analytics', status: 'active' }] } });
  });
  await page.goto('./#workspaces');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.workspace-hero')).toBeVisible();
  await expect(page.locator('.workspace-mode-card')).toHaveCount(3);
  const layout = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    modeOverflow: document.querySelector('.workspace-mode-nav').scrollWidth > document.querySelector('.workspace-mode-nav').clientWidth,
  }));
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
  expect(layout.modeOverflow).toBe(false);
  await page.getByRole('button', { name: 'Register workspace' }).click();
  await expect(page.locator('#workspace-create-form')).toBeInViewport();
});

test('Project workbench keeps authoring modes and scope usable on a phone', async ({ page }) => {
  await page.route('**/v1/workspaces/workspace-a/projects', async route => {
    await route.fulfill({ json: { items: [{ id: 'project-a', name: 'Analytics' }] } });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-a', async route => {
    await route.fulfill({ json: { schema: 'ronin.project/v1', project: { id: 'project-a', name: 'Analytics', repositories: [{ adapter_id: 'git', alias: 'source', default_ref: 'main', role: 'primary', sync_policy: 'manual', uri: 'https://git.example.com/analytics.git', subdirectory: null }] } } });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-a/pipelines/main/revisions', async route => {
    await route.fulfill({ json: { items: [{ revision: 2, source_digest: 'sha256:revision-two', revision_key: 'main/2' }] } });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-a/pipelines/main/revisions/compare?left_revision=1&right_revision=2', async route => {
    await route.fulfill({ json: { left_revision: 1, right_revision: 2, changes: [{ path: 'pipeline.yaml', kind: 'changed' }] } });
  });
  await page.goto('./#projects/workspace-a');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.project-hero')).toBeVisible();
  await expect(page.locator('.context-bar')).toContainText('workspace-a');
  await expect(page.locator('.context-bar')).not.toContainText('examples/demo');
  await expect(page.locator('#project-overview-title')).toContainText('project boundary');
  await expect(page.locator('#project-overview-count')).toHaveText('1');
  await expect(page.locator('#project-source-state')).toHaveText('Unconfigured');
  await expect(page.locator('.project-mode-card')).toHaveCount(4);
  const layout = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    modeOverflow: document.querySelector('.project-mode-nav').scrollWidth > document.querySelector('.project-mode-nav').clientWidth,
  }));
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
  expect(layout.modeOverflow).toBe(false);
  await page.getByRole('button', { name: 'Connect project' }).click();
  await expect(page.locator('#project-environment-form')).toBeInViewport();
  await page.getByRole('button', { name: 'Use context' }).click();
  await expect(page.locator('input[name="project_id"]')).toHaveCount(4);
  await expect(page.locator('input[name="project_id"]').first()).toHaveValue('project-a');
  const manifest = JSON.parse(await page.locator('#project-manifest').inputValue());
  expect(manifest.schema).toBe('ronin.project/v1');
  expect(manifest.project.id).toBe('new-project');
  expect(manifest.project.repositories[0].adapter_id).toBe('git');
  await expect(page.locator('#project-manifest')).toHaveAttribute('rows', '14');
  await page.getByRole('button', { name: 'Edit manifest' }).click();
  await expect(page.locator('#project-authoring-mode')).toHaveText('Edit project-a');
  await expect(page.locator('#project-cancel-edit')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel edit' }).click();
  await expect(page.locator('#project-authoring-mode')).toHaveText('Create project');
  await expect(page.locator('#project-cancel-edit')).toBeHidden();
  await page.locator('#project-revisions-form [name="revision_project"]').fill('project-a');
  await page.locator('#project-revisions-form button[type="submit"]').click();
  await expect(page.locator('#project-revisions-result')).toContainText('sha256:revision-two');
  await expect(page.locator('#project-revisions-result')).toContainText('main/2');
  await page.locator('#project-revisions-compare-form [name="compare_project"]').fill('project-a');
  await page.locator('#project-revisions-compare-form [name="left_revision"]').fill('1');
  await page.locator('#project-revisions-compare-form [name="right_revision"]').fill('2');
  await page.locator('#project-revisions-compare-form button[type="submit"]').click();
  await expect(page.locator('#project-revisions-compare-result')).toContainText('pipeline.yaml');
});
