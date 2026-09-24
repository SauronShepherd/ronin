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

test('Workspace and project Studio journey covers environment, Bundle and archive actions', async ({ page }) => {
  let archived = false;
  await page.route('**/v1/workspaces', async route => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({ id: 'workspace-journey', name: 'Journey', description: 'P1-006' });
      await route.fulfill({ json: { id: 'workspace-journey', name: 'Journey', status: 'active' } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'workspace-journey', name: 'Journey', status: 'active' }] } });
  });
  await page.route('**/v1/workspaces/workspace-journey/projects', async route => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({ project: { id: 'project-journey', name: 'Project Journey' } });
      await route.fulfill({ json: { project: { id: 'project-journey', name: 'Project Journey' } } });
      return;
    }
    await route.fulfill({ json: { items: archived ? [] : [{ id: 'project-journey', name: 'Project Journey' }] } });
  });
  await page.route('**/v1/workspaces/workspace-journey/projects/project-journey/environments/local/bindings', async route => {
    expect(route.request().method()).toBe('PUT');
    expect(route.request().postDataJSON()).toEqual({ project_id: 'project-journey', environment_id: 'local', bindings: { runtime: 'local' } });
    await route.fulfill({ json: { status: 'bound', environment_id: 'local' } });
  });
  await page.route('**/v1/workspaces/workspace-journey/projects/project-journey/bundle/archive', async route => {
    await route.fulfill({ json: { media_type: 'application/vnd.ronin.bundle+zip', content_base64: 'UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA==' } });
  });
  await page.route('**/v1/workspaces/workspace-journey/projects/project-journey/archive', async route => {
    expect(route.request().method()).toBe('POST');
    archived = true;
    await route.fulfill({ json: { id: 'project-journey', status: 'archived' } });
  });

  await page.goto('./#workspaces');
  await page.locator('#workspace-create-id').fill('workspace-journey');
  await page.locator('#workspace-create-name').fill('Journey');
  await page.locator('#workspace-create-description').fill('P1-006');
  await page.getByRole('button', { name: 'Create' }).click();
  await page.getByRole('link', { name: 'Open projects' }).click();
  await page.locator('#project-manifest').fill('{"project":{"id":"project-journey","name":"Project Journey"}}');
  await page.getByRole('button', { name: 'Create project' }).click();
  await page.locator('#project-environment-form input[name="project_id"]').fill('project-journey');
  await page.locator('#project-environment-form textarea[name="bindings"]').fill('{"bindings":{"runtime":"local"}}');
  await page.getByRole('button', { name: 'Replace environment binding' }).click();
  await expect(page.locator('#project-environment-result')).toContainText('bound');
  await page.getByRole('button', { name: 'Download Bundle' }).click();
  await expect(page.locator('#project-journey-result')).toContainText('Downloaded project-journey.roninbundle');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Archive', exact: true }).click();
  await expect(page.locator('#project-list')).toContainText('No active projects');
});

test('Notebook Studio edits, creates and executes a bounded notebook', async ({ page }) => {
  let saved = false;
  await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/notebooks', async route => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({ id: 'new-notebook', document: { schema: 'ronin.notebook/v1', cells: [] }, source_revision: null, execution_binding: null, parameter_schema: [] });
      await route.fulfill({ json: { id: 'new-notebook', revision: 1, document: { schema: 'ronin.notebook/v1', cells: [] } } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: 'etl', revision: saved ? 2 : 1 }] } });
  });
  await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/notebooks/etl', async route => {
    if (route.request().method() === 'PUT') {
      expect(route.request().postDataJSON().expected_revision).toBe(1);
      saved = true;
      await route.fulfill({ json: { id: 'etl', revision: 2, document: route.request().postDataJSON().document } });
      return;
    }
    await route.fulfill({ json: { id: 'etl', revision: 1, runtime: 'local', document: { schema: 'ronin.notebook/v1', cells: [{ id: 'cell-1', source: 'SELECT 1' }] } } });
  });
  await page.route('**/v1/jobs', async route => {
    expect(route.request().postDataJSON().target).toBe('notebook:etl');
    await route.fulfill({ json: { id: 'job-notebook-1', state: 'queued' } });
  });
  await page.route('**/v1/jobs/job-notebook-1/cancel', async route => {
    expect(route.request().method()).toBe('POST');
    await route.fulfill({ json: { id: 'job-notebook-1', state: 'cancelling' } });
  });
  await page.route('**/v1/jobs/job-notebook-1', async route => {
    await route.fulfill({ json: { id: 'job-notebook-1', state: 'succeeded' } });
  });
  await page.route('**/v1/jobs/job-notebook-1/results', async route => {
    await route.fulfill({ json: { items: [{ cell_id: 'cell-1', state: 'succeeded' }] } });
  });

  await page.goto('./#notebooks');
  await page.getByRole('button', { name: 'etl (r1)' }).click();
  const documentField = page.locator('#notebook-editor textarea[name="document"]');
  await documentField.fill('{"schema":"ronin.notebook/v1","cells":[{"id":"cell-1","source":"SELECT 2"}]}');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('#notebook-result')).toContainText('"revision": 2');
  await page.locator('#notebook-editor input[name="id"]').fill('new-notebook');
  await page.locator('#notebook-editor input[name="revision"]').fill('1');
  await documentField.fill('{"schema":"ronin.notebook/v1","cells":[]}');
  await page.getByRole('button', { name: 'Create' }).click();
  await expect(page.locator('#notebook-result')).toContainText('new-notebook');
  await page.locator('#notebook-editor input[name="id"]').fill('etl');
  await page.locator('#notebook-editor input[name="revision"]').fill('2');
  await documentField.fill('{"schema":"ronin.notebook/v1","cells":[{"id":"cell-1","source":"SELECT 2"}]}');
  await page.getByRole('button', { name: 'Run all cells' }).click();
  await expect(page.locator('#notebook-run')).toContainText('succeeded');
  await page.getByRole('button', { name: 'Cancel run' }).click();
  await expect(page.locator('#notebook-run')).toContainText('cancelling');
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
