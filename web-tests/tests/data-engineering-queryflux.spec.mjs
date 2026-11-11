import { test, expect } from '@playwright/test';

test('Data Engineering Studio follows the active shell context across query and pipeline forms', async ({ page }) => {
  await page.goto('./#data');
  await expect(page.locator('#de-sql-form')).toBeVisible();
  await page.evaluate(() => {
    globalThis.roninStudioContext = { workspace: 'workspace-shell', project: 'project-shell' };
    window.dispatchEvent(new CustomEvent('ronin-context-change', { detail: globalThis.roninStudioContext }));
  });
  await expect(page.locator('#de-sql-form [name="workspace"]')).toHaveValue('workspace-shell');
  await expect(page.locator('#de-sql-form [name="project"]')).toHaveValue('project-shell');
  await expect(page.locator('#de-pipeline-form [name="workspace"]')).toHaveValue('workspace-shell');
  await expect(page.locator('#de-pipeline-form [name="project"]')).toHaveValue('project-shell');
});

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
  await page.route('**/v1/workspaces/workspace-a/projects/project-1/data-engineering/queryflux/executions/*/*', async route => {
    await route.fulfill({
      json: { state: 'succeeded', cancel_requested: false },
    });
  });

  await page.goto('./#data');
  await page.locator('#de-sql-form [name="workspace"]').fill('workspace-a');
  await page.locator('#de-sql-form [name="project"]').fill('project-1');
  await page.locator('#de-sql-form [name="profile"]').selectOption('queryflux');
  await expect(page.getByRole('button', { name: 'Explain query plan' })).toBeHidden();
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
  await expect(page.locator('#de-sql-result .de-result-summary')).toContainText('1 of 2 rows loaded');
  await expect(page.locator('#de-sql-result .de-queryflux-lifecycle')).toHaveAttribute('data-state', 'succeeded');
  await expect(page.locator('#de-sql-result .de-queryflux-lifecycle')).toHaveAttribute('aria-label', 'QueryFlux lifecycle: succeeded');
  await expect(page.locator('#de-sql-result table')).toContainText('1');
  await expect(page.locator('#de-sql-result .de-sql-raw')).not.toHaveAttribute('open', '');
  await page.getByRole('button', { name: /Load next results page/ }).click();
  await expect(page.locator('#de-sql-result')).toContainText('"rows"');
  await expect(page.locator('#de-sql-result')).toContainText('"row_count": 2');
  await expect(page.getByRole('button', { name: 'Load next results page' })).toBeHidden();
  await page.getByRole('button', { name: 'Export CSV' }).click();
  await expect(page.locator('#de-sql-result')).toHaveText(/id\s+1\s+2/);
  expect(resultPageRequests).toBe(1);
});

test('Data Engineering Studio keeps QueryFlux capabilities human-readable before showing raw metadata', async ({ page }) => {
  await page.route('**/v1/data-engineering/queryflux/capabilities', async route => {
    await route.fulfill({
      json: {
        status: 'ready',
        provider: 'queryflux',
        allowed_engines: ['duckdb'],
        translation_policies: ['native_only'],
        capabilities: { stable_result_paging: true },
      },
    });
  });
  await page.goto('./#data');
  await expect(page.locator('.queryflux-capability-summary')).toContainText('ready for bounded execution');
  await expect(page.locator('.queryflux-capability-boundary')).toContainText('cancellation is unavailable');
  await expect(page.locator('.queryflux-raw')).not.toHaveAttribute('open', '');
  await page.locator('.queryflux-raw summary').click();
  await expect(page.locator('.queryflux-raw pre')).toContainText('stable_result_paging');
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

test('Data Engineering Studio retries a failed bounded QueryFlux query without losing scope', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/data-engineering/queryflux/capabilities', async route => {
    await route.fulfill({ json: { status: 'ready', allowed_engines: ['duckdb'], translation_policies: ['native_only'] } });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-1/data-engineering/queryflux/execute', async route => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { error: { code: 'provider_unavailable', message: 'QueryFlux is warming up.' } } });
      return;
    }
    await route.fulfill({ json: { columns: [{ name: 'id', type: 'INTEGER' }], rows: [[9]], row_count: 1, next_cursor: null } });
  });
  await page.goto('./#data');
  await page.locator('#de-sql-form [name="workspace"]').fill('workspace-a');
  await page.locator('#de-sql-form [name="project"]').fill('project-1');
  await page.locator('#de-sql-form [name="profile"]').selectOption('queryflux');
  await page.locator('#de-sql-form [name="sql"]').fill('SELECT 9');
  await page.getByRole('button', { name: 'Execute bounded query' }).click();
  await expect(page.locator('#de-sql-result')).toContainText('QueryFlux is warming up.');
  await page.getByRole('button', { name: 'Retry this query', exact: true }).click();
  await expect(page.locator('#de-sql-result')).toContainText('"row_count": 1');
  await expect(page.locator('#de-sql-form [name="workspace"]')).toHaveValue('workspace-a');
  await expect(page.locator('#de-sql-form [name="project"]')).toHaveValue('project-1');
  expect(attempts).toBe(2);
});

test('Data Engineering Studio keeps unavailable-server details out of the UI', async ({ page }) => {
  await page.route('**/v1/data-engineering/queryflux/capabilities', async route => {
    await route.fulfill({
      status: 502,
      contentType: 'text/html',
      body: '<!doctype html><html><body>gateway unavailable</body></html>',
    });
  });

  await page.goto('./#data');
  await expect(page.locator('#de-queryflux-status')).toHaveText('QueryFlux: degraded');
  await expect(page.locator('#de-queryflux-result')).toContainText('unexpected page');
  await expect(page.locator('#de-queryflux-result')).not.toContainText('127.0.0.1');
  await expect(page.locator('#de-queryflux-result')).not.toContainText('http://');
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
  await expect(page.locator('#de-sql-result .de-result-summary')).toContainText('1 row loaded');
  await expect(page.locator('#de-sql-result table')).toContainText('7');
  await expect(page.locator('#de-sql-result .de-sql-raw')).not.toHaveAttribute('open', '');
  await expect(page.locator('#de-sql-result')).toContainText('"row_count": 1');
  await page.getByRole('button', { name: 'Export CSV' }).click();
  await expect(page.locator('#de-sql-result')).toHaveText(/id\s+7/);
});

test('Data Engineering Studio explains a bounded local SQL plan', async ({ page }) => {
  let postedBody;
  await page.route('**/v1/data-engineering/queryflux/capabilities', async route => {
    await route.fulfill({ json: { status: 'not_configured', allowed_engines: [], translation_policies: [] } });
  });
  await page.route('**/v1/workspaces/workspace-a/projects/project-1/sql/explain', async route => {
    postedBody = route.request().postDataJSON();
    await route.fulfill({ json: { rows: [['physical_plan', 'SEQ_SCAN registered_events']], max_bytes: 2048 } });
  });

  await page.goto('./#data');
  await page.locator('#de-sql-form [name="workspace"]').fill('workspace-a');
  await page.locator('#de-sql-form [name="project"]').fill('project-1');
  await page.locator('#de-sql-form [name="sql"]').fill('SELECT id FROM registered_events');
  await page.locator('#de-sql-form [name="max_explain_bytes"]').fill('2048');
  await page.getByRole('button', { name: 'Explain query plan' }).click();

  await expect.poll(() => postedBody).toEqual({
    sql: 'SELECT id FROM registered_events',
    max_bytes: 2048,
    timeout_ms: 5000,
  });
  await expect(page.locator('#de-sql-result')).toContainText('SEQ_SCAN registered_events');
});
