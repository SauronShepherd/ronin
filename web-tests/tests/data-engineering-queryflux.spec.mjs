import { test, expect } from '@playwright/test';

test('Data Engineering Studio executes QueryFlux and reads stable result pages', async ({ page }) => {
  let postedBody;
  let resultPageRequests = 0;
  await page.route('**/v1/data-engineering/queryflux/capabilities', async route => {
    await route.fulfill({
      json: {
        status: 'ready',
        provider: 'queryflux',
        allowed_engines: ['duckdb'],
        translation_policies: ['native_only', 'best_effort'],
        capabilities: { stable_result_paging: true },
      },
    });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-1/data-engineering/queryflux/execute', async route => {
    postedBody = route.request().postDataJSON();
    await route.fulfill({
      json: {
        status: 'succeeded',
        selected_engine: 'duckdb',
        columns: ['id'],
        rows: [[1]],
        row_count: 2,
        next_cursor: 'stable-cursor',
        evidence: { digest: 'a'.repeat(64) },
      },
    });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-1/data-engineering/queryflux/executions/*/*/results**', async route => {
    resultPageRequests += 1;
    expect(new URL(route.request().url()).searchParams.get('cursor')).toBe('stable-cursor');
    await route.fulfill({
      json: { columns: ['id'], rows: [[2]], row_count: 2, next_cursor: null },
    });
  });

  await page.goto('./#data');
  await page.locator('#de-sql-form [name="workspace"]').fill('workspace-a');
  await page.locator('#de-sql-form [name="project"]').fill('project-1');
  await page.locator('#de-sql-form [name="profile"]').selectOption('queryflux');
  await expect(page.locator('#de-sql-form [name="queryflux_engine"]')).toHaveValue('duckdb');
  await page.locator('#de-sql-form [name="page_size"]').fill('1');
  await page.locator('#de-sql-form [name="sql"]').fill('SELECT 1 AS id');
  await page.getByRole('button', { name: 'Execute bounded query' }).click();

  await expect.poll(() => postedBody).toMatchObject({
    sql: 'SELECT 1 AS id',
    profile: 'queryflux',
    engine: 'duckdb',
    page_size: 1,
    max_rows: 1000,
    translation_policy: 'native_only',
  });
  expect(postedBody.run_id).toMatch(/^[0-9a-f-]{36}$/i);
  expect(postedBody.attempt_id).toMatch(/^[0-9a-f-]{36}$/i);
  await expect(page.getByRole('button', { name: /Load next results page/ })).toBeVisible();
  await page.getByRole('button', { name: /Load next results page/ }).click();
  await expect(page.locator('#de-sql-result')).toContainText('"rows"');
  await expect(page.locator('#de-sql-result')).toContainText('"row_count": 2');
  await expect(page.getByRole('button', { name: 'Load next results page' })).toBeHidden();
  await page.getByRole('button', { name: 'Export CSV' }).click();
  await expect(page.locator('#de-sql-result')).toHaveText(/id\s+1\s+2/);
  expect(resultPageRequests).toBe(1);
});

test('Data Engineering Studio surfaces QueryFlux authorization errors', async ({ page }) => {
  await page.route('**/v1/data-engineering/queryflux/capabilities', async route => {
    await route.fulfill({ json: { status: 'ready', allowed_engines: ['duckdb'], translation_policies: ['native_only'] } });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-1/data-engineering/queryflux/execute', async route => {
    await route.fulfill({ status: 403, json: { error: { code: 'permission_denied', message: 'Project access denied.' } } });
  });

  await page.goto('./#data');
  await page.locator('#de-sql-form [name="workspace"]').fill('workspace-a');
  await page.locator('#de-sql-form [name="project"]').fill('project-1');
  await page.locator('#de-sql-form [name="profile"]').selectOption('queryflux');
  await page.locator('#de-sql-form [name="sql"]').fill('SELECT 1');
  await page.getByRole('button', { name: 'Execute bounded query' }).click();
  await expect(page.locator('#de-sql-result')).toContainText('Project access denied.');
});

test('Data Engineering Studio keeps local SQL requests within the documented contract', async ({ page }) => {
  let postedBody;
  await page.route('**/v1/data-engineering/queryflux/capabilities', async route => {
    await route.fulfill({ json: { status: 'not_configured', allowed_engines: [], translation_policies: [] } });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-1/sql/query', async route => {
    postedBody = route.request().postDataJSON();
    await route.fulfill({
      json: {
        columns: [{ name: 'id', type_name: 'BIGINT' }],
        rows: [[7]],
        row_count: 1,
        max_rows: 1000,
        max_result_bytes: 1048576,
      },
    });
  });

  await page.goto('./#data');
  await page.locator('#de-sql-form [name="workspace"]').fill('workspace-a');
  await page.locator('#de-sql-form [name="project"]').fill('project-1');
  await page.locator('#de-sql-form [name="sql"]').fill('SELECT 7 AS id');
  await page.getByRole('button', { name: 'Execute bounded query' }).click();
  await expect.poll(() => postedBody).toEqual({
    sql: 'SELECT 7 AS id',
    max_rows: 1000,
    timeout_ms: 5000,
    max_result_bytes: 1048576,
  });
  await page.getByRole('button', { name: 'Export CSV' }).click();
  await expect(page.locator('#de-sql-result')).toHaveText(/id\s+7/);
});
