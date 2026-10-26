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
  await page.route('**/v1/workspaces/workspace-journey/projects/project-journey/pipelines/main/runs', async route => {
    expect(route.request().postDataJSON()).toMatchObject({ revision_key: 'main/working', ir_digest: 'a'.repeat(64), runtime: 'local-preview' });
    await route.fulfill({ status: 201, json: { id: 'pipeline-run-1', state: 'queued' } });
  });
  await page.route('**/v1/workspaces/workspace-journey/projects/project-journey/permissions', async route => {
    await route.fulfill({ json: { project_id: 'project-journey', permissions: { 'project.read': { allowed: true }, 'project.write': { allowed: true } } } });
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
  await expect(page.locator('#project-list')).toContainText('project-journey');
  await page.locator('#project-manifest').fill('{"project":{"id":"project-journey","name":"Project Journey"}}');
  await page.getByRole('button', { name: 'Create project' }).click();
  await page.locator('#project-environment-form input[name="project_id"]').fill('project-journey');
  await page.locator('#project-environment-form textarea[name="bindings"]').fill('{"bindings":{"runtime":"local"}}');
  await page.getByRole('button', { name: 'Replace environment binding' }).click();
  await expect(page.locator('#project-environment-result')).toContainText('bound');
  await page.locator('#project-operation-form input[name="project_id"]').fill('project-journey');
  await page.locator('#project-operation-form textarea[name="operation"]').fill(JSON.stringify({ revision_key: 'main/working', ir_digest: 'a'.repeat(64), runtime: 'local-preview', parameters: { pipeline: { config: { name: 'main' }, nodes: [], edges: [] } } }));
  await page.getByRole('button', { name: 'Run governed pipeline' }).click();
  await expect(page.locator('#project-operation-result')).toContainText('pipeline-run-1');
  await page.locator('#project-permissions-form input[name="project_id"]').fill('project-journey');
  await page.getByRole('button', { name: 'Inspect permissions' }).click();
  await expect(page.locator('#project-permissions-result')).toContainText('project.read');
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
  await page.locator('#notebook-editor [data-notebook-action="save"]').click();
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

test('Ingestion Studio pages source discovery and keeps sync preview controls', async ({ page }) => {
  await page.route('**/v1/platform/connectors', async route => {
    await route.fulfill({ json: { items: [] } });
  });
  const discoveryRequests = [];
  await page.route('**/v1/platform/connectors/discover**', async route => {
    expect(new URL(route.request().url()).searchParams.get('workspace_id')).toBe('default');
    const body = route.request().postDataJSON();
    discoveryRequests.push(body);
    if (!body.cursor) {
      await route.fulfill({ json: {
        schema: 'ronin.connector-discovery/v1',
        items: [{ asset_ref: 'conn-1::public.orders' }],
        count: 1,
        has_more: true,
        next_cursor: 'opaque-page-two',
      } });
      return;
    }
    await route.fulfill({ json: {
      schema: 'ronin.connector-discovery/v1',
      items: [{ asset_ref: 'conn-1::public.users' }],
      count: 1,
      has_more: false,
      next_cursor: null,
    } });
  });
  await page.route('**/v1/platform/connectors/plan**', async route => {
    expect(new URL(route.request().url()).searchParams.get('workspace_id')).toBe('default');
    expect(route.request().postDataJSON().checkpoint_identity).toBe('preview-1');
    await route.fulfill({ json: { plan: { mode: 'snapshot' }, checkpoint: { present: false } } });
  });
  await page.route('**/v1/platform/connectors/preview**', async route => {
    expect(new URL(route.request().url()).searchParams.get('workspace_id')).toBe('default');
    await route.fulfill({ json: { preview: 'source preview ok' } });
  });
  await page.route('**/v1/platform/connectors/checkpoint-health**', async route => {
    expect(new URL(route.request().url()).searchParams.get('workspace_id')).toBe('default');
    expect(route.request().postDataJSON()).toEqual({ checkpoint_identity: 'preview-1' });
    await route.fulfill({ json: { identity: 'preview-1', present: false } });
  });
  await page.goto('./#ingestion');
  await page.locator('[name="connection_ref"]').fill('conn-1');
  await page.getByRole('button', { name: 'Discover assets' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText('Page 1 loaded');
  await expect(page.locator('#ingestion-discovery-result')).toContainText('public.orders');
  await page.getByRole('button', { name: 'Load next page' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText('discovery complete');
  await expect(page.locator('#ingestion-discovery-result')).toContainText('public.users');
  expect(discoveryRequests).toEqual([
    { connector_id: 'postgres', connection_ref: 'conn-1', page_size: 100 },
    { connector_id: 'postgres', connection_ref: 'conn-1', page_size: 100, cursor: 'opaque-page-two' },
  ]);
  await page.getByRole('button', { name: 'Preview source' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('source preview ok');
  await page.getByRole('button', { name: 'Plan sync' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('snapshot');
  await page.getByRole('button', { name: 'Checkpoint health' }).click();
  await expect(page.locator('#ingestion-preview-result')).toContainText('preview-1');
});

test('Ingestion Studio submits and monitors a scoped durable connector sync', async ({ page }) => {
  await page.route('**/v1/platform/connectors', route => route.fulfill({ json: { items: [] } }));
  let submitted;
  await page.route('**/v1/platform/connectors/syncs?**', async route => {
    submitted = route.request();
    expect(submitted.headers()['idempotency-key']).toMatch(/^ingestion-/);
    await route.fulfill({ status: 201, json: { id: 'job-sync-42', state: 'queued' } });
  });
  await page.route('**/v1/platform/connectors/syncs/job-sync-42/status?**', async route => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get('workspace_id')).toBe('default');
    expect(url.searchParams.get('project_id')).toBe('default');
    await route.fulfill({ json: {
      job: { id: 'job-sync-42', state: 'succeeded' },
      events: { items: [{ kind: 'worker.attempt.succeeded' }], next_since: null },
      evidence: { items: [{ digest: 'evidence-digest' }] },
      lineage: { status: 'available', items: [{ source: { asset_id: 'source-orders', version: 'v3' }, target: { asset_id: 'curated-orders', version: 'sha256:' + 'a'.repeat(64) }, operation: 'write', mode: 'observed', execution_ref: 'run-sync-42' }], truncated: false },
    } });
  });
  await page.goto('./#ingestion');
  const definition = {
    id: 'orders-sync', connector_id: 'postgres', connection_ref: 'conn-1',
    asset_ref: 'conn-1::public.orders', destination_ref: 'asset://warehouse/orders',
    checkpoint_identity: 'orders-v1', mode: 'incremental',
    source_revision_ref: { asset_id: 'source-orders', version: 'v3' },
    destination_asset_id: 'curated-orders',
  };
  await page.locator('#ingestion-definition').fill(JSON.stringify(definition));
  await page.getByRole('button', { name: 'Run durable sync' }).click();
  await expect(page.locator('#ingestion-sync-status')).toContainText('submitted');
  await expect(page.locator('#ingestion-sync-status')).toContainText('succeeded');
  await expect(page.locator('#ingestion-sync-evidence')).toContainText('worker.attempt.succeeded');
  await expect(page.locator('#ingestion-sync-evidence')).toContainText('evidence-digest');
  await expect(page.locator('#ingestion-sync-lineage')).toContainText('run-sync-42', { timeout: 5000 });
  expect(submitted.postDataJSON()).toEqual({ project_id: 'default', definition });
  await page.screenshot({ path: 'test-results/ingestion-sync-desktop.png', fullPage: true });
});

test('Ingestion Studio requires governed refs before submitting a durable sync', async ({ page }) => {
  await page.route('**/v1/platform/connectors', route => route.fulfill({ json: { items: [] } }));
  let submitted = false;
  await page.route('**/v1/platform/connectors/syncs?**', async route => {
    submitted = true;
    await route.fulfill({ status: 201, json: { id: 'unexpected', state: 'queued' } });
  });
  await page.goto('./#ingestion');
  await page.locator('#ingestion-definition').fill(JSON.stringify({
    id: 'orders-sync', connector_id: 'postgres', connection_ref: 'conn-1',
    asset_ref: 'conn-1::public.orders', destination_ref: 'asset://warehouse/orders',
    checkpoint_identity: 'orders-v1', mode: 'snapshot',
  }));
  await page.getByRole('button', { name: 'Run durable sync' }).click();
  await expect(page.locator('#ingestion-sync-status')).toContainText('requires an existing governed source revision and destination asset');
  expect(submitted).toBe(false);
});

test('Ingestion Studio stops requesting discovery pages when cancelled', async ({ page }) => {
  await page.route('**/v1/platform/connectors', route => route.fulfill({ json: { items: [] } }));
  let requestStarted;
  const started = new Promise(resolve => { requestStarted = resolve; });
  let releaseRequest;
  const pendingResponse = new Promise(resolve => { releaseRequest = resolve; });
  await page.route('**/v1/platform/connectors/discover**', async route => {
    requestStarted();
    await pendingResponse;
    try {
      await route.fulfill({ json: {
        schema: 'ronin.connector-discovery/v1',
        items: [],
        count: 0,
        has_more: false,
        next_cursor: null,
      } });
    } catch {
      // The browser intentionally aborts this in-flight read-only request.
    }
  });
  await page.goto('./#ingestion');
  await page.locator('[name="connection_ref"]').fill('conn-1');
  await page.getByRole('button', { name: 'Discover assets' }).click();
  await started;
  await page.getByRole('button', { name: 'Stop discovery' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText('Stopped this request.');
  await expect(page.getByRole('button', { name: 'Load next page' })).toBeDisabled();
  releaseRequest();
});

test('Ingestion Studio rejects a malformed discovery page', async ({ page }) => {
  await page.route('**/v1/platform/connectors', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/v1/platform/connectors/discover**', route => route.fulfill({ json: {
    schema: 'ronin.connector-discovery/v1',
    items: [],
    count: 1,
    has_more: false,
    next_cursor: null,
  } }));
  await page.goto('./#ingestion');
  await page.locator('[name="connection_ref"]').fill('conn-1');
  await page.getByRole('button', { name: 'Discover assets' }).click();
  await expect(page.locator('#ingestion-discovery-status')).toContainText('invalid page');
  await expect(page.getByRole('button', { name: 'Load next page' })).toBeDisabled();
});

test('Migration Studio creates one session per submit', async ({ page }) => {
  let createCount = 0;
  await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/migration/sessions', async route => {
    if (route.request().method() === 'POST') {
      createCount += 1;
      await route.fulfill({ json: { id: 'migration-once', state: 'created' } });
      return;
    }
    await route.fulfill({ json: { items: [] } });
  });
  await page.goto('./#migration');
  await page.getByRole('button', { name: 'Create session' }).click();
  await expect(page.locator('#migration-cockpit-control-result')).toContainText('migration-once');
  expect(createCount).toBe(1);
});

test('SQL Studio sends one workspace-scoped request per submit', async ({ page }) => {
  let queryCount = 0;
  await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/sql/query', async route => {
    queryCount += 1;
    expect(route.request().postDataJSON()).toMatchObject({sql: 'SELECT 1 AS value', max_rows: 1000});
    await route.fulfill({ json: { columns: [{ name: 'value' }], rows: [[1]], row_count: 1 } });
  });
  await page.goto('./#sql');
  await page.getByRole('button', { name: 'Run SQL' }).click();
  await expect(page.locator('#sql-result')).toContainText('row_count');
  expect(queryCount).toBe(1);
});

test('Data Engineering Studio executes a bounded read-only SQL query', async ({ page }) => {
  await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/sql/query', async route => {
    const body = route.request().postDataJSON();
    expect(body.sql).toBe('SELECT 1 AS value');
    expect(body.max_rows).toBe(1000);
    expect(body.dialect).toBe('ansi');
    await route.fulfill({ json: { columns: [{ name: 'value', type_name: 'INTEGER' }], rows: [[1]], row_count: 1 } });
  });
  await page.goto('./#data');
  await page.getByRole('button', { name: 'Execute bounded query' }).click();
  await expect(page.locator('#de-sql-result')).toContainText('INTEGER');
  await expect(page.locator('#de-sql-result')).toContainText('[\n    1\n  ]');
  await page.getByRole('button', { name: 'Export CSV' }).click();
  await expect(page.locator('#de-sql-result')).toHaveText('value\n1');
  await page.locator('#de-sql-save-name').fill('daily-value');
  await page.getByRole('button', { name: 'Save current query' }).click();
  await page.locator('#de-sql-form textarea[name="sql"]').fill('SELECT changed');
  await page.getByRole('button', { name: 'daily-value', exact: true }).click();
  await expect(page.locator('#de-sql-form textarea[name="sql"]')).toHaveValue('SELECT 1 AS value');
  await expect(page.locator('#de-sql-history')).toContainText('local: SELECT 1 AS value');
  await page.locator('#de-sql-form textarea[name="sql"]').fill('SELECT changed');
  await page.getByRole('button', { name: 'local: SELECT 1 AS value', exact: true }).click();
  await expect(page.locator('#de-sql-form textarea[name="sql"]')).toHaveValue('SELECT 1 AS value');
  await page.goto('./#home');
  await page.goto('./#data');
  await expect(page.locator('#de-sql-history')).toContainText('local: SELECT 1 AS value');
});

test('Data Engineering Studio visual pipeline editor synchronizes nodes, edges and history', async ({ page }) => {
  await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/pipelines/main/revisions', async route => {
    const body = route.request().postDataJSON();
    expect(body.project_name).toBe('examples/demo');
    expect(body.pipeline_documents[0].name).toBe('main.json');
    await route.fulfill({ json: { pipeline_id: 'main', revision: 1, source_digest: 'digest-1' }, status: 201 });
  });
  await page.route('**/v1/workspaces/default/projects/examples%2Fdemo/pipelines/main/revisions/1', async route => {
    await route.fulfill({ json: { pipeline_id: 'main', revision: 1, pipeline: { runtime: 'local-preview', pipeline: { nodes: [{ id: 'loaded', operator: { name: 'loaded.source' }, ports: [{ name: 'out', direction: 'output' }, { name: 'in', direction: 'input' }] }], edges: [] } } } });
  });
  await page.route('**/v1/workspaces/default/workflow-runs/run-1', async route => {
    await route.fulfill({ json: { id: 'run-1', state: 'succeeded', evidence_digest: 'evidence-1', lineage_id: 'lineage-1' } });
  });
  await page.goto('./#data');
  await expect(page.locator('#de-pipeline-visual')).toBeVisible();
  await page.locator('#de-node-id').fill('source');
  await page.locator('#de-node-operator').fill('csv.read');
  await page.getByRole('button', { name: 'Add node' }).click();
  await page.locator('#de-node-id').fill('sink');
  await page.locator('#de-node-operator').fill('parquet.write');
  await page.getByRole('button', { name: 'Add node' }).click();
  await page.locator('#de-node-id').fill('source');
  await page.locator('#de-node-operator').fill('csv.read.v2');
  await page.getByRole('button', { name: 'Configure node' }).click();
  await expect(page.locator('#de-pipeline-form textarea[name="pipeline"]')).toHaveValue(/csv\.read\.v2/);
  await page.locator('#de-edge-from').selectOption('source');
  await page.locator('#de-edge-to').selectOption('sink');
  await page.getByRole('button', { name: 'Connect nodes', exact: true }).click();
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('2 node(s), 1 edge(s)');
  await page.locator('#de-edge-from').selectOption('source');
  await page.locator('#de-edge-to').selectOption('sink');
  await page.getByRole('button', { name: 'Connect nodes', exact: true }).click();
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('Edge already exists');
  await page.locator('#de-edge-from').selectOption('sink');
  await page.locator('#de-edge-to').selectOption('source');
  await page.getByRole('button', { name: 'Connect nodes', exact: true }).click();
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('Connection would create a pipeline cycle');
  await page.locator('#de-edge-from').selectOption('source');
  await page.locator('#de-edge-to').selectOption('sink');
  await page.locator('#de-edge-port').fill('missing');
  await page.getByRole('button', { name: 'Connect nodes', exact: true }).click();
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('Target port does not exist: sink.missing');
  await expect(page.locator('#de-pipeline-form textarea[name="pipeline"]')).toHaveValue(/csv\.read/);
  await page.locator('body').press('Control+Z');
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('2 node(s), 0 edge(s)');
  await page.locator('body').press('Control+Shift+Z');
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('2 node(s), 1 edge(s)');
  await page.locator('#de-edge-from').selectOption('source');
  await page.locator('#de-edge-to').selectOption('sink');
  await page.locator('#de-edge-port').fill('in');
  await page.getByRole('button', { name: 'Disconnect nodes' }).click();
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('2 node(s), 0 edge(s)');
  await page.locator('#de-edge-from').selectOption('source');
  await page.locator('#de-edge-to').selectOption('sink');
  await page.getByRole('button', { name: 'Connect nodes', exact: true }).click();
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('2 node(s), 1 edge(s)');
  await page.getByRole('button', { name: 'Save revision' }).click();
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('digest-1');
  await page.getByRole('button', { name: 'Load revision' }).click();
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('loaded.source');
  await expect(page.locator('#de-pipeline-visual-result')).toContainText('1 node(s), 0 edge(s)');
  await page.locator('#de-pipeline-form input[name="run_id"]').fill('run-1');
  await page.getByRole('button', { name: 'Inspect run' }).click();
  await expect(page.locator('#de-pipeline-result')).toContainText('evidence-1');
  await expect(page.locator('#de-pipeline-result')).toContainText('lineage-1');
});
