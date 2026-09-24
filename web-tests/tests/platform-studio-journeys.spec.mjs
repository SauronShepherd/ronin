import { test, expect } from '@playwright/test';

test('Performance Studio submits a normalized run and renders the report', async ({ page }) => {
  await page.route('**/api/v1/performance/analyze', async route => {
    const body = route.request().postDataJSON();
    expect(body.run.run_id).toBe('demo-run');
    await route.fulfill({ json: { score: 0.91, series: { stages: [] }, issues: [] } });
  });
  await page.goto('./#performance');
  await page.locator('#performance-run').fill('{"run_id":"demo-run","stages":[]}');
  await page.getByRole('button', { name: 'Analyze performance' }).click();
  await expect(page.locator('#performance-result')).toContainText('0.91');
});

test('Debugger Studio creates a session and sets a breakpoint', async ({ page }) => {
  await page.route('**/v1/data-engineering/debugger/**', async route => {
    await route.fulfill({ json: { status: 'ok', session_id: 'studio-debug' } });
  });
  await page.goto('./#debugger');
  await page.getByRole('button', { name: 'Create session' }).click();
  await expect(page.locator('#debugger-result')).toContainText('studio-debug');
  await page.locator('#debugger-cell').fill('cell-1');
  await page.getByRole('button', { name: 'Set breakpoint' }).click();
  await expect(page.locator('#debugger-result')).toContainText('"status": "ok"');
});

test('Cloud Studio validates a target and generates a reviewable plan', async ({ page }) => {
  await page.route('**/v1/cloud-studio/**', async route => {
    await route.fulfill({ json: { status: 'ok', resources: [] } });
  });
  await page.goto('./#cloud');
  await page.getByRole('button', { name: 'Validate target' }).click();
  await expect(page.locator('#cloud-result')).toContainText('"status": "ok"');
  await page.getByRole('button', { name: 'Generate plan' }).click();
  await expect(page.locator('#cloud-result')).toContainText('resources');
});

test('Access Studio renders workspace role scope inventory', async ({ page }) => {
  await page.route('**/v1/admin/security/principals**', async route => {
    if (route.request().method() === 'PUT') {
      expect(route.request().postDataJSON()).toEqual({ kind: 'user', display_name: 'Alice', issuer: 'oidc', subject: 'alice-sub', email: 'alice@example.test', active: true });
      await route.fulfill({ json: { id: 'alice', kind: 'user' } });
      return;
    }
    await route.fulfill({ json: { items: [] } });
  });
  await page.route('**/v1/admin/security/principals/alice', async route => {
    expect(route.request().method()).toBe('PUT');
    expect(route.request().postDataJSON()).toEqual({ kind: 'user', display_name: 'Alice', issuer: 'oidc', subject: 'alice-sub', email: 'alice@example.test', active: true });
    await route.fulfill({ json: { id: 'alice', kind: 'user' } });
  });
  await page.route('**/v1/admin/security/groups', async route => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route('**/v1/admin/security/role-bindings', async route => {
    await route.fulfill({ json: { items: [{ workspace_id: 'workspace-1', subject_kind: 'principal', subject_id: 'alice', role: 'admin' }] } });
  });
  await page.route('**/v1/admin/security/groups/team', async route => {
    expect(route.request().method()).toBe('PUT');
    expect(route.request().postDataJSON()).toEqual({ name: 'Data Team' });
    await route.fulfill({ json: { id: 'team', name: 'Data Team' } });
  });
  await page.goto('./#access');
  await expect(page.locator('#role-name option')).toHaveCount(4);
  await expect(page.locator('#group-form')).toBeVisible();
  await page.locator('#user-id').fill('alice');
  await page.locator('#user-display-name').fill('Alice');
  await page.locator('#user-subject').fill('alice-sub');
  await page.locator('#user-email').fill('alice@example.test');
  await page.getByRole('button', { name: 'Create/update user' }).click();
  await expect(page.locator('#access-inventory-output')).toContainText('alice');
  await page.locator('#group-id').fill('team');
  await page.locator('#group-name').fill('Data Team');
  await page.getByRole('button', { name: 'Create/update group' }).click();
  await expect(page.locator('#access-inventory-output')).toContainText('Data Team');
  await expect(page.locator('#access-scope-table')).toContainText('workspace-1');
  await expect(page.locator('#access-scope-table')).toContainText('principal:alice');
  await expect(page.locator('#access-scope-table')).toContainText('admin');
});

test('Ingestion Studio exposes sync plan and checkpoint health', async ({ page }) => {
  await page.route('**/v1/platform/connectors', async route => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route('**/v1/platform/connectors/plan', async route => {
    expect(route.request().postDataJSON().checkpoint_identity).toBe('preview-1');
    await route.fulfill({ json: { plan: { mode: 'snapshot' }, checkpoint: { present: false } } });
  });
  await page.route('**/v1/platform/connectors/checkpoint-health', async route => {
    expect(route.request().postDataJSON()).toEqual({ checkpoint_identity: 'preview-1' });
    await route.fulfill({ json: { identity: 'preview-1', present: false } });
  });
  await page.goto('./#ingestion');
  await page.getByRole('button', { name: 'Plan sync' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('snapshot');
  await page.getByRole('button', { name: 'Checkpoint health' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('preview-1');
});

test('Data Engineering Studio executes a bounded read-only SQL query', async ({ page }) => {
  await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/sql/query', async route => {
    const body = route.request().postDataJSON();
    expect(body.sql).toBe('SELECT 1 AS value');
    expect(body.max_rows).toBe(1000);
    await route.fulfill({ json: { columns: [{ name: 'value', type_name: 'INTEGER' }], rows: [[1]], row_count: 1 } });
  });
  await page.goto('./#data');
  await page.getByRole('button', { name: 'Execute bounded query' }).click();
  await expect(page.locator('#de-sql-result')).toContainText('INTEGER');
  await expect(page.locator('#de-sql-result')).toContainText('[\n    1\n  ]');
});
