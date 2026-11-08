import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { test, expect } from '@playwright/test';
import {
  connectLiveStudio,
  flushLiveTraffic,
  installLiveApiProxy,
  liveConfigurationReady,
} from './live-support.mjs';

const routes = JSON.parse(
  fs.readFileSync(new URL('../../web/routes.json', import.meta.url), 'utf8'),
).filter(route => route.state === 'active');
// Project and environment are fixtures consumed by later live journeys.
const fixtureOrder = new Map([['projects', 0], ['environments', 1]]);
routes.sort((left, right) => (fixtureOrder.get(left.id) ?? 2) - (fixtureOrder.get(right.id) ?? 2));
const liveReady = liveConfigurationReady();
const liveWorkerReady = liveReady && process.env.RONIN_LIVE_WORKER_ENABLED === '1';
// The shell refreshes the shared jobs activity on every route. This is
// published by the home/runs contracts but is not a settings-specific read.
const routeIndependentApiPaths = new Set(['/v1/jobs']);

function templatePattern(template) {
  const escaped = template.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^${escaped.replace(/\\\{[^}]+\\\}/g, '[^/]+')}(?:$|/)`);
}

for (const route of routes) {
  const routeHasApiContract = Array.isArray(route.required_api) && route.required_api.length > 0;
  const routeTestName = routeHasApiContract
    ? `route ${route.id} loads and reaches the live API`
    : `route ${route.id} renders (UI-only: no API route declared)`;
  test(routeTestName, async ({ page }) => {
    test.setTimeout(route.id === 'mlstudio' ? 240_000 : 60_000);
    test.skip(!liveReady, 'Run via npm run test:live with a live Ronin API and PostgreSQL fixture.');
    const calls = installLiveApiProxy(page);
    await connectLiveStudio(page);

    const before = calls.length;
    const routeHash = route.id === 'projects'
      ? `projects/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}`
      : route.id;
    await page.goto(`./#${routeHash}`);
    await expect(page.locator(route.smoke_selector)).toBeVisible({ timeout: 30_000 });

    // These views intentionally wait for enough user context before reading.
    // Exercise the same safe read a user would invoke instead of treating the
    // initial empty form as a successful functional journey.
    if (route.id === 'runs') {
      await page.getByLabel('Project filter').fill('examples/demo');
      await page.getByRole('button', { name: 'Refresh runs', exact: true }).click();
    } else if (route.id === 'projects') {
      await page.locator('#project-manifest').fill(JSON.stringify({
        schema: 'ronin.project/v1',
        project: {
          id: 'examples/demo',
          name: 'Ronin Live Qualification Fixture',
          repositories: [{
            adapter_id: 'git', alias: 'code', default_ref: 'main', role: 'primary',
            subdirectory: null, sync_policy: 'manual', uri: 'https://git.example.test/ronin/live.git',
          }],
          execution: { requirements: [], resolution: 'strict', runtime: { adapter_id: 'python', profile_id: '3.11' } },
        },
      }));
      const createResponse = page.waitForResponse(response =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === `/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/projects`,
      );
      await page.getByRole('button', { name: 'Create project', exact: true }).click();
      const created = await createResponse;
      expect([200, 201], await created.text()).toContain(created.status());
      await expect(page.locator('#project-journey-result')).toContainText('examples/demo');
    } else if (route.id === 'quality') {
      const workspace = process.env.RONIN_LIVE_WORKSPACE;
      const assetId = 'live-lineage-target';
      const version = '1';
      const contractPath = `/v1/workspaces/${encodeURIComponent(workspace)}/quality/contracts/${encodeURIComponent(assetId)}/${version}`;
      const runPath = `/v1/workspaces/${encodeURIComponent(workspace)}/quality/runs`;
      const statePath = `/v1/workspaces/${encodeURIComponent(workspace)}/quality/state/${encodeURIComponent(assetId)}/${version}`;
      await page.locator('#quality-workspace').fill(workspace);
      await page.locator('#quality-asset').fill(assetId);
      await page.locator('#quality-version').fill(version);
      const contract = {
        asset: { asset_id: assetId, version },
        compatibility: 'exact',
        freshness_seconds: null,
        rules: [
          {
            id: 'minimum-rows', kind: 'row_count', name: 'At least two rows',
            severity: 'error', blocking: true, field: null, parameters: { min: '2' },
          },
          {
            id: 'email-present', kind: 'null', name: 'Email must be present',
            severity: 'warning', blocking: false, field: 'email', parameters: {},
          },
        ],
      };
      await page.locator('#quality-contract').fill(JSON.stringify(contract));
      let response = page.waitForResponse(item =>
        item.request().method() === 'PUT' && new URL(item.url()).pathname === contractPath,
      );
      await page.getByRole('button', { name: 'Save contract', exact: true }).click();
      const savedContract = await response;
      expect(savedContract.status(), await savedContract.text()).toBe(200);
      expect((await savedContract.json()).rules).toHaveLength(2);

      await page.locator('#quality-rows').fill(JSON.stringify([
        { id: 1, email: 'ronin@example.test' },
        { id: 2, email: 'dojo@example.test' },
      ]));
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === runPath,
      );
      await page.getByRole('button', { name: 'Dry-run rows', exact: true }).click();
      const passingRun = await response;
      expect(passingRun.status(), await passingRun.text()).toBe(201);
      const passingPayload = await passingRun.json();
      expect(passingPayload.gate_passed).toBe(true);
      expect(passingPayload.run.status).toBe('passed');
      await expect(page.locator('#quality-result')).toContainText('passed');

      await page.locator('#quality-rows').fill(JSON.stringify([{ id: 1, email: null }]));
      await page.locator('#quality-enforce-blocking').check();
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === runPath,
      );
      await page.getByRole('button', { name: 'Dry-run rows', exact: true }).click();
      const blockedRun = await response;
      expect(blockedRun.status(), await blockedRun.text()).toBe(409);
      expect((await blockedRun.json()).error.code).toBe('quality_gate_blocked');
      await expect(page.locator('#quality-result')).toContainText('Quality operation failed.');
      await expect(page.locator('#quality-result')).toContainText('blocking quality rules failed');
      expect(calls.some(call => call.path === runPath && call.status === 409 && call.outcome === 'WARN')).toBe(true);

      response = page.waitForResponse(item =>
        item.request().method() === 'GET' && new URL(item.url()).pathname === statePath,
      );
      await page.getByRole('button', { name: 'Load state', exact: true }).click();
      expect((await response).status()).toBe(200);
      await expect(page.locator('#quality-result')).toContainText('failed');
      await expect(page.locator('#quality-result')).toContainText('email-present');
    } else if (route.id === 'mlstudio') {
      const workspace = process.env.RONIN_LIVE_WORKSPACE;
      const labId = `live-ml-${Date.now()}`;
      const labPath = `/v1/ml-studio/labs?workspace_id=${encodeURIComponent(workspace)}`;
      const labForm = page.locator('[data-feature-form="ml-create"]');
      await page.locator('#ml-workspace').fill(workspace);
      await labForm.locator('[name="id"]').fill(labId);
      await labForm.locator('[name="name"]').fill('Ronin live classical ML qualification');
      await labForm.locator('[name="asset_id"]').fill('live-lineage-target');
      await labForm.locator('[name="version"]').fill('1');
      await labForm.locator('[name="target"]').fill('target');
      await labForm.locator('[name="feature"]').fill('x');
      let response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === '/v1/ml-studio/labs',
      );
      await labForm.getByRole('button', { name: 'Create lab', exact: true }).click();
      const createdLab = await response;
      expect(createdLab.status(), await createdLab.text()).toBe(200);
      expect((await createdLab.json()).id).toBe(labId);
      await expect(page.locator('#ml-labs')).toContainText(labId);

      const qualityRows = Array.from({ length: 20 }, (_, index) => ({ x: index + 1, target: index % 2 }));
      const qualityForm = page.locator('#ml-quality-form');
      await qualityForm.locator('[name="lab_id"]').fill(labId);
      await qualityForm.locator('[name="rows"]').fill(JSON.stringify(qualityRows));
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' &&
        new URL(item.url()).pathname === `/v1/ml-studio/labs/${labId}/quality`,
      );
      await qualityForm.getByRole('button', { name: 'Run quality check', exact: true }).click();
      const quality = await response;
      expect(quality.status(), await quality.text()).toBe(200);
      expect((await quality.json()).passed).toBe(true);
      await expect(page.locator('#ml-output')).toContainText('"passed": true');

      await page.locator(`[data-feature="ml-drift"][data-lab="${labId}"]`).click();
      const driftForm = page.locator(`[data-feature-form="ml-drift"][data-lab="${labId}"]`);
      const baselineRows = [{x: 1}, {x: 2}, {x: 3}];
      await driftForm.locator('[name="baseline_rows"]').fill(JSON.stringify(baselineRows));
      await driftForm.locator('[name="current_rows"]').fill(JSON.stringify([{x: 1}, {x: 2}, {x: 50}]));
      let driftResponse = page.waitForResponse(item =>
        item.request().method() === 'POST' &&
        new URL(item.url()).pathname === `/v1/ml-studio/labs/${labId}/drift-policies`,
      );
      await driftForm.getByRole('button', {name: 'Save policy version'}).click();
      const savedPolicy = await driftResponse;
      expect(savedPolicy.status(), await savedPolicy.text()).toBe(200);
      expect((await savedPolicy.json()).version).toBe(1);

      driftResponse = page.waitForResponse(item =>
        item.request().method() === 'GET' &&
        new URL(item.url()).pathname === `/v1/ml-studio/labs/${labId}/drift-policies`,
      );
      await driftForm.getByRole('button', {name: 'Load saved policies'}).click();
      expect((await driftResponse).status()).toBe(200);
      await driftForm.locator('[name="saved_policy"]').selectOption('0');
      driftResponse = page.waitForResponse(item =>
        item.request().method() === 'POST' &&
        new URL(item.url()).pathname === `/v1/ml-studio/labs/${labId}/drift`,
      );
      await driftForm.getByRole('button', {name: 'Generate drift report'}).click();
      const drift = await driftResponse;
      expect(drift.status(), await drift.text()).toBe(200);
      expect((await drift.json()).assessment).toMatchObject({status: 'drifted', drifted_features: ['x']});
      await expect(page.locator('#ml-output')).toContainText('Drift report · drifted');

      const searchForm = page.locator('#ml-search-form');
      await searchForm.locator('[name="lab_id"]').fill(labId);
      await searchForm.locator('[name="rows"]').fill(JSON.stringify(qualityRows));
      await searchForm.locator('[name="spec"]').fill(JSON.stringify({
        mode: 'grid', metric: 'accuracy', direction: 'maximize',
        parameters: [{ name: 'seed', values: [17, 19] }],
      }));
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' &&
        new URL(item.url()).pathname === `/v1/ml-studio/labs/${labId}/search`,
      );
      await searchForm.getByRole('button', { name: 'Search trials', exact: true }).click();
      const searched = await response;
      expect(searched.status(), await searched.text()).toBe(200);
      const searchPayload = await searched.json();
      expect(searchPayload.items).toHaveLength(2);
      expect(searchPayload.items.every(item => typeof item.metrics.accuracy === 'number')).toBe(true);
      await expect(page.locator('#ml-output')).toContainText('Trial search');

      const runButton = page.locator(`[data-feature="ml-run"][data-lab="${labId}"]`);
      await expect(runButton).toBeEnabled();
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' &&
        new URL(item.url()).pathname === `/v1/ml-studio/labs/${labId}/executions`,
      );
      await runButton.click();
      const submitted = await response;
      expect(submitted.status(), await submitted.text()).toBe(200);
      const execution = await submitted.json();
      expect(execution.run_id).toMatch(/^ui-live-ml-/);
      await expect.poll(async () => {
        const current = await page.locator('#ml-execution').textContent();
        return JSON.parse(current || '{}').state;
      }, { timeout: 45_000 }).toBe('succeeded');
      await expect(page.locator('#ml-register-execution')).toBeVisible();

      const registerForm = page.locator('#ml-register-execution');
      await registerForm.locator('[name="model_id"]').fill(labId);
      await registerForm.locator('[name="version"]').fill('live-1');
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' &&
        new URL(item.url()).pathname === `/v1/ml-studio/executions/${execution.run_id}/register`,
      );
      await registerForm.getByRole('button', { name: 'Register candidate', exact: true }).click();
      const registered = await response;
      expect(registered.status(), await registered.text()).toBe(200);
      expect((await registered.json()).model_id).toBe(labId);
      await expect(page.locator('#ml-models')).toContainText(labId);

      await page.evaluate(() => { window.prompt = () => 'live qualification promotion'; });
      const promotionPath = `/v1/ml-studio/models/${labId}/live-1/promote`;
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === promotionPath,
      );
      await page.getByRole('button', {name: 'Promote', exact: true}).click();
      const blockedPromotion = await response;
      expect(blockedPromotion.status(), await blockedPromotion.text()).toBe(409);
      await expect(page.locator('#ml-output')).toContainText('no passed evaluation');
      expect(calls.some(call => call.path === promotionPath && call.status === 409 && call.outcome === 'WARN')).toBe(true);

      await page.locator(`[data-feature="ml-review-evaluation"][data-model="${labId}"][data-version="live-1"]`).click();
      const evaluationForm = page.locator('[data-feature-form="ml-evaluation"]');
      await evaluationForm.locator('[name="status"]').selectOption('passed');
      await evaluationForm.locator('[name="review_ref"]').fill('manual-live-review');
      const evaluationPath = `/v1/ml-studio/models/${labId}/live-1/evaluations`;
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === evaluationPath,
      );
      await evaluationForm.getByRole('button', {name: 'Save evaluation review', exact: true}).click();
      const evaluation = await response;
      expect(evaluation.status(), await evaluation.text()).toBe(200);
      expect((await evaluation.json()).evaluation).toMatchObject({
        model_id: labId,
        version: 'live-1',
        status: 'passed',
        execution_ref: 'manual-live-review',
      });
      await expect(page.locator('#ml-output')).toContainText('Saved passed evaluation review');

      const modelCardPath = `/v1/ml-studio/models/${labId}/live-1/card`;
      response = page.waitForResponse(item =>
        item.request().method() === 'GET' && new URL(item.url()).pathname === modelCardPath,
      );
      await page.locator(`[data-feature="ml-card"][data-model="${labId}"][data-version="live-1"]`).click();
      const modelCard = await response;
      expect(modelCard.status(), await modelCard.text()).toBe(200);
      expect((await modelCard.json()).evaluations).toEqual(expect.arrayContaining([
        expect.objectContaining({status: 'passed', execution_ref: 'manual-live-review'}),
      ]));

      response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === promotionPath,
      );
      await page.getByRole('button', {name: 'Promote', exact: true}).click();
      const promoted = await response;
      expect(promoted.status(), await promoted.text()).toBe(200);
      expect((await promoted.json()).stage).toBe('champion');

      const deploymentId = `${labId}-deployment`;
      const deploymentForm = page.locator('[data-feature-form="ml-deployment-create"]');
      await deploymentForm.locator('[name="deployment_id"]').fill(deploymentId);
      await deploymentForm.locator('[name="model_id"]').fill(labId);
      await deploymentForm.locator('[name="version"]').fill('live-1');
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === '/v1/ml-studio/deployments',
      );
      await deploymentForm.getByRole('button', {name: 'Deploy pinned model'}).click();
      const deployed = await response;
      expect([200, 201], await deployed.text()).toContain(deployed.status());
      expect((await deployed.json())).toMatchObject({deployment_id: deploymentId, status: 'ready', readiness: 'ready'});

      response = page.waitForResponse(item =>
        item.request().method() === 'GET' &&
        new URL(item.url()).pathname === `/v1/ml-studio/deployments/${deploymentId}/health`,
      );
      await page.locator(`[data-feature="ml-deployment-health"][data-deployment="${deploymentId}"]`).click();
      const deploymentHealth = await response;
      expect(deploymentHealth.status(), await deploymentHealth.text()).toBe(200);
      await expect(page.locator('#ml-output')).toContainText(deploymentId);

      await page.evaluate(() => { window.prompt = () => JSON.stringify([{x: 1}, {x: 2}]); });
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' &&
        new URL(item.url()).pathname === `/v1/ml-studio/deployments/${deploymentId}/predict`,
      );
      await page.locator(`[data-feature="ml-deployment-predict"][data-deployment="${deploymentId}"]`).click();
      const predictions = await response;
      expect(predictions.status(), await predictions.text()).toBe(200);
      expect((await predictions.json()).predictions).toHaveLength(2);
      await expect(page.locator('#ml-output')).toContainText('Deployment predictions');
    } else if (route.id === 'alerts') {
      await page.locator('#alerts-form [name="workspace"]').fill(process.env.RONIN_LIVE_WORKSPACE);
      await page.getByRole('button', { name: 'List rules', exact: true }).click();
    } else if (route.id === 'finops') {
      await page.locator('#finops-form [name="workspace"]').fill(process.env.RONIN_LIVE_WORKSPACE);
      await page.getByRole('button', { name: 'Load budgets', exact: true }).click();
    } else if (route.id === 'migration') {
      await page.locator('#migration-cockpit-workspace').fill(process.env.RONIN_LIVE_WORKSPACE);
      await page.locator('#migration-cockpit-project').fill('examples/demo');
      await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    } else if (route.id === 'sql') {
      await page.locator('#sql-workspace').fill(process.env.RONIN_LIVE_WORKSPACE);
      await page.locator('#sql-project').fill('examples/demo');
      // Route cases run in parallel; never rely on the Projects route having
      // created this project first. SQL authorization and execution both bind
      // to a real workspace project, so ensure the prerequisite through API.
      const projectUrl = `${process.env.RONIN_LIVE_API_URL}/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/projects`;
      const projectList = await page.request.get(projectUrl, {
        headers: { authorization: `Bearer ${process.env.RONIN_LIVE_API_TOKEN}` },
      });
      expect(projectList.status(), await projectList.text()).toBe(200);
      const projects = (await projectList.json()).items || [];
      if (!projects.some(item => item.project?.id === 'examples/demo')) {
        const projectCreate = await page.request.post(projectUrl, {
          headers: {
            authorization: `Bearer ${process.env.RONIN_LIVE_API_TOKEN}`,
            'Idempotency-Key': `live-sql-${process.env.RONIN_LIVE_WORKSPACE}-examples-demo`,
          },
          data: {
            schema: 'ronin.project/v1',
            project: {
              id: 'examples/demo',
              name: 'Ronin Live Qualification Fixture',
              repositories: [{
                adapter_id: 'git', alias: 'code', default_ref: 'main', role: 'primary',
                subdirectory: null, sync_policy: 'manual', uri: 'https://git.example.test/ronin/live.git',
              }],
              execution: { requirements: [], resolution: 'strict', runtime: { adapter_id: 'python', profile_id: '3.11' } },
            },
          },
        });
        expect([200, 201], await projectCreate.text()).toContain(projectCreate.status());
      }
      const sqlResponse = page.waitForResponse(response =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname ===
          `/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/projects/examples%2Fdemo/sql/query`,
      );
      await page.getByRole('button', { name: 'Run SQL', exact: true }).click();
      const executed = await sqlResponse;
      expect(executed.status(), await executed.text()).toBe(200);
      const result = await executed.json();
      expect(result.columns.map(column => column.name)).toContain('value');
      expect(result.rows).toEqual([[1]]);
      expect(result.row_count).toBe(1);
      await expect(page.locator('#sql-result')).toContainText('"row_count": 1');
    } else if (route.id === 'semantic') {
      const workspace = process.env.RONIN_LIVE_WORKSPACE;
      const project = 'examples/demo';
      const apiBase = `${process.env.RONIN_LIVE_API_URL}/v1/workspaces/${encodeURIComponent(workspace)}/projects/${encodeURIComponent(project)}/semantic`;
      const headers = { authorization: `Bearer ${process.env.RONIN_LIVE_API_TOKEN}` };
      await page.locator('#semantic-model-form [name="workspace"]').fill(workspace);
      await page.locator('#semantic-model-form [name="project"]').fill(project);
      let response = page.waitForResponse(item =>
        item.request().method() === 'GET' && new URL(item.url()).pathname.endsWith('/semantic/models'),
      { timeout: 10_000 });
      await page.getByRole('button', { name: 'List models', exact: true }).click();
      let modelsResponse = await response;
      expect(modelsResponse.status(), await modelsResponse.text()).toBe(200);
      expect((await modelsResponse.json()).items.map(item => item.id)).toContain('live_sales');
      await expect(page.locator('#semantic-model-result')).toContainText('live_sales');

      const exportResponsePromise = page.waitForResponse(item =>
        item.request().method() === 'GET' && new URL(item.url()).pathname.endsWith('/semantic/bundle'),
      { timeout: 10_000 });
      const downloadPromise = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Download semantic Bundle' }).click();
      const [exportResponse, download] = await Promise.all([exportResponsePromise, downloadPromise]);
      expect(exportResponse.status(), await exportResponse.text()).toBe(200);
      const exported = await exportResponse.json();
      expect(exported.digest).toMatch(/^[0-9a-f]{64}$/);
      expect(download.suggestedFilename()).toBe('examples_demo-semantic.roninbundle');
      await expect(page.locator('#semantic-bundle-result')).toContainText(exported.digest);

      const archive = Buffer.from(exported.content_base64, 'base64');
      await page.locator('#semantic-bundle-import-form [name="workspace"]').fill(workspace);
      await page.locator('#semantic-bundle-import-form [name="project"]').fill(project);
      await page.locator('#semantic-bundle-import-form [name="bundle"]').setInputFiles({
        name: download.suggestedFilename(),
        mimeType: 'application/zip',
        buffer: archive,
      });
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname.endsWith('/semantic/bundle/plan'),
      { timeout: 10_000 });
      await page.getByRole('button', { name: 'Verify and preview' }).click();
      const planResponse = await response;
      expect(planResponse.status(), await planResponse.text()).toBe(200);
      const plan = await planResponse.json();
      expect(plan.bundle_digest).toBe(exported.digest);
      expect(plan.models.map(item => item.id)).toContain('live_sales');
      await expect(page.locator('#semantic-bundle-result')).toContainText('live_overview');
      const importButton = page.getByRole('button', { name: 'Import reviewed Bundle' });
      await expect(importButton).toBeEnabled();

      response = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname.endsWith('/semantic/bundle/import'),
      { timeout: 10_000 });
      await importButton.click();
      const importResponse = await response;
      expect(importResponse.status(), await importResponse.text()).toBe(200);
      const imported = await importResponse.json();
      expect(imported.bundle_digest).toBe(exported.digest);
      expect(imported.models.map(item => item.id)).toContain('live_sales');
      await expect(page.locator('#semantic-bundle-result')).toContainText('Imported 1 model(s) and 1 dashboard(s)');

      const persistedModels = await page.request.get(`${apiBase}/models`, { headers });
      const persistedDashboards = await page.request.get(`${apiBase}/dashboards`, { headers });
      expect(persistedModels.status(), await persistedModels.text()).toBe(200);
      expect(persistedDashboards.status(), await persistedDashboards.text()).toBe(200);
      expect((await persistedModels.json()).items.map(item => item.id)).toContain('live_sales');
      expect((await persistedDashboards.json()).items.map(item => item.id)).toContain('live_overview');
      await expect(page.locator('#semantic-model-result')).toContainText('live_sales');
      await expect(page.locator('#semantic-dashboard-result')).toContainText('live_overview');

      await page.locator('#semantic-dashboard-form [name="workspace"]').fill(workspace);
      await page.locator('#semantic-dashboard-form [name="project"]').fill(project);
      await page.locator('#semantic-dashboard-form [name="dashboard"]').fill('live_overview');
      response = page.waitForResponse(item =>
        item.request().method() === 'POST' &&
        new URL(item.url()).pathname.endsWith('/semantic/dashboards/live_overview/execute'),
      { timeout: 10_000 });
      await page.getByRole('button', { name: 'Execute dashboard', exact: true }).click();
      const dashboardResponse = await response;
      expect(dashboardResponse.status(), await dashboardResponse.text()).toBe(200);
      const dashboardResult = await dashboardResponse.json();
      expect(dashboardResult.dashboard_id).toBe('live_overview');
      expect(dashboardResult.tiles).toEqual([
        { tile_id: 'orders', columns: [{ name: 'orders', type: 'BIGINT' }], rows: [[5]] },
      ]);
      const renderedDashboard = JSON.parse(await page.locator('#semantic-dashboard-result').textContent());
      expect(renderedDashboard).toEqual(dashboardResult);
    } else if (route.id === 'synthetic') {
      const generatePath = '/v1/synthetic-data-studio/generate';
      const generateResponse = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === generatePath,
      );
      await page.locator('#synthetic-studio-form button[type="submit"]').click();
      const generated = await generateResponse;
      expect([200, 201], await generated.text()).toContain(generated.status());
      const generation = await generated.json();
      expect(generation.status).toBe('generated');
      expect(generation.run_id).toBeTruthy();
      expect(generation.tables).toHaveLength(1);
      expect(generation.tables[0].name).toBe('customers');
      expect(generation.tables[0].rows).toHaveLength(10);
      await expect(page.locator('#synthetic-studio-result')).toContainText(generation.run_id);
      await expect(page.locator('#synthetic-studio-export')).toBeVisible();
      await page.locator('#synthetic-studio-format').selectOption('jsonl');

      const exportPath = '/v1/synthetic-data-studio/export';
      const exportResponse = page.waitForResponse(item =>
        item.request().method() === 'POST' && new URL(item.url()).pathname === exportPath,
      );
      await page.locator('#synthetic-studio-export-button').click();
      const exported = await exportResponse;
      expect(exported.status(), await exported.text()).toBe(200);
      const exportPayload = await exported.json();
      expect(exportPayload).toMatchObject({
        status: 'completed', run_id: generation.run_id, format_id: 'jsonl', table: 'customers',
      });
      expect(exportPayload.content.trim().split('\n')).toHaveLength(10);
      await expect(page.locator('#synthetic-studio-result')).toContainText('completed');
    } else if (route.id === 'catalog') {
      await page.locator('#catalog-search-form [name="workspace"]').fill(process.env.RONIN_LIVE_WORKSPACE);
      await page.locator('#catalog-search-form').evaluate(form => form.requestSubmit());
      await page.locator('#catalog-lineage-form [name="asset_id"]').fill('live-lineage-target');
      await page.locator('#catalog-lineage-form [name="version"]').fill('1');
      await page.locator('#catalog-lineage-form [name="direction"]').selectOption('upstream');
      const lineageResponse = page.waitForResponse(response => {
        const requestUrl = new URL(response.url());
        return requestUrl.pathname ===
          `/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/catalog/lineage/live-lineage-target/1` &&
          requestUrl.searchParams.get('direction') === 'upstream' &&
          requestUrl.searchParams.get('limit') === '100';
      });
      await page.getByRole('button', { name: 'Inspect lineage', exact: true }).click();
      const lineage = await lineageResponse;
      expect(lineage.status(), await lineage.text()).toBe(200);
      const lineagePayload = await lineage.json();
      expect(lineagePayload.items).toHaveLength(1);
      expect(lineagePayload.items[0].source.asset_id).toBe('live-lineage-source');
      await expect(page.locator('#catalog-lineage-result')).toContainText('live-lineage-source');
    } else if (route.id === 'data') {
      await page.getByRole('button', { name: 'Health', exact: true }).click();
      await page.locator('#de-sql-form [name="workspace"]').fill(process.env.RONIN_LIVE_WORKSPACE);
      await page.locator('#de-sql-form [name="project"]').fill('examples/demo');
      await page.locator('#de-sql-form [name="sql"]').fill('SELECT 1 AS live_value');
      const explainResponse = page.waitForResponse(response =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === `/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/projects/examples%2Fdemo/sql/explain`,
      );
      await page.getByRole('button', { name: 'Explain query plan', exact: true }).click();
      const explained = await explainResponse;
      expect(explained.status(), await explained.text()).toBe(200);
      expect((await explained.json()).rows.length).toBeGreaterThan(0);
      await expect(page.locator('#de-sql-result')).toContainText('physical_plan');
    } else if (route.id === 'streaming') {
      const workspace = process.env.RONIN_LIVE_WORKSPACE;
      const waitForStreamResponse = (method, pathname) => page.waitForResponse(response =>
        response.request().method() === method && new URL(response.url()).pathname === pathname,
      { timeout: 10_000 });
      await page.locator('#stream-definition-form [name="workspace"]').fill(workspace);
      const listResponse = waitForStreamResponse('GET', `/v1/workspaces/${encodeURIComponent(workspace)}/streams`);
      await page.getByRole('button', { name: 'Refresh stream list', exact: true }).click();
      const listed = await listResponse;
      expect(listed.status(), await listed.text()).toBe(200);
      expect((await listed.json()).items.map(item => item.id)).toContain('events/main');
      await page.locator('#stream-list').selectOption('events/main');
      // Fail near the broken interaction instead of consuming the 60 s
      // journey timeout if native form submission stops reaching the API.
      await expect(page.locator('#stream-definition-form [name="id"]')).toHaveValue('events/main');
      await expect(page.locator('#stream-definition-form [name="name"]')).toHaveValue('Live qualification events');
      page.setDefaultTimeout(10_000);
      const definitionPath = `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Fmain`;
      const saveDefinitionResponse = waitForStreamResponse('PUT', definitionPath);
      await page.getByRole('button', { name: 'Save stream', exact: true }).click();
      const savedDefinition = await saveDefinitionResponse;
      expect(savedDefinition.status(), await savedDefinition.text()).toBe(200);
      expect((await savedDefinition.json()).checkpoint_policy).toBe('reset');
      await expect(page.locator('#stream-definition-result')).toContainText('events/main');
      const bundleDownloadResponse = waitForStreamResponse('GET', `/v1/workspaces/${encodeURIComponent(workspace)}/streams/bundle`);
      const bundleDownloadPromise = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Download stream Bundle' }).click();
      const bundleDownloadResponseValue = await bundleDownloadResponse;
      expect(bundleDownloadResponseValue.status(), await bundleDownloadResponseValue.text()).toBe(200);
      const bundleExport = await bundleDownloadResponseValue.json();
      expect(bundleExport.media_type).toBe('application/vnd.ronin.bundle+zip');
      expect(bundleExport.size_bytes).toBeGreaterThan(0);
      const bundleDownload = await bundleDownloadPromise;
      const bundlePath = await bundleDownload.path();
      expect(bundlePath).toBeTruthy();
      await page.locator('#stream-bundle-import-form [name="workspace"]').fill(workspace);
      await page.locator('#stream-bundle-import-form [name="bundle"]').setInputFiles(bundlePath);
      const bundlePlanResponse = waitForStreamResponse('POST', `/v1/workspaces/${encodeURIComponent(workspace)}/streams/bundle/plan`);
      await page.getByRole('button', { name: 'Verify and preview Bundle' }).click();
      const bundlePlanResponseValue = await bundlePlanResponse;
      expect(bundlePlanResponseValue.status(), await bundlePlanResponseValue.text()).toBe(200);
      const bundlePlan = await bundlePlanResponseValue.json();
      expect(bundlePlan.bundle_digest).toBe(bundleExport.digest);
      expect(bundlePlan.items.map(item => item.id).sort()).toEqual(['events/main', 'events/oversized', 'events/poison']);
      await expect(page.locator('#stream-bundle-import-review')).toContainText('Verified 3 stream definition(s)');
      await expect(page.locator('#stream-bundle-import-commit')).toBeDisabled();
      for (const policy of await page.locator('[data-checkpoint-stream]').all()) await policy.selectOption('reset');
      const bundleImportResponse = waitForStreamResponse('POST', `/v1/workspaces/${encodeURIComponent(workspace)}/streams/bundle/import`);
      await page.getByRole('button', { name: 'Import reviewed Bundle' }).click();
      const bundleImportResponseValue = await bundleImportResponse;
      expect(bundleImportResponseValue.status(), await bundleImportResponseValue.text()).toBe(200);
      const bundleImport = await bundleImportResponseValue.json();
      expect(bundleImport.bundle_digest).toBe(bundlePlan.bundle_digest);
      expect(bundleImport.checkpoint_policies).toEqual({ 'events/main': 'reset', 'events/oversized': 'reset', 'events/poison': 'reset' });
      await expect(page.locator('#stream-bundle-result')).toContainText('Imported 3 stream definition(s)');
      await page.locator('#stream-health-form [name="workspace"]').fill(process.env.RONIN_LIVE_WORKSPACE);
      await page.locator('#stream-health-form [name="stream"]').fill('events/main');
      const healthPath = `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Fmain/health`;
      const streamingResponse = waitForStreamResponse('GET', healthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const health = await streamingResponse;
      expect(health.status(), await health.text()).toBe(200);
      const payload = await health.json();
      expect(payload.source_status).toBe('available');
      expect(payload.partitions).toBe(1);
      expect(payload.total_lag).toBe(5);
      await expect(page.locator('#stream-health-result')).toContainText('source_status');
      const runPath = `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Fmain/run`;
      await page.locator('#stream-health-form [name="limit"]').fill('2');
      const runResponse = waitForStreamResponse('POST', runPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      const run = await runResponse;
      expect(run.status(), await run.text()).toBe(200);
      const runPayload = await run.json();
      expect(runPayload).toMatchObject({ stream_id: 'events/main', status: 'succeeded', records: 2, rows: 2 });
      await expect(page.locator('#stream-health-result')).toContainText('sink_commit_id');
      const healthAfterFirstBatchResponse = waitForStreamResponse('GET', healthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const healthAfterFirstBatch = await healthAfterFirstBatchResponse;
      expect(healthAfterFirstBatch.status(), await healthAfterFirstBatch.text()).toBe(200);
      expect((await healthAfterFirstBatch.json()).total_lag).toBe(3);
      for (const policy of await page.locator('[data-checkpoint-stream]').all()) await policy.selectOption('resume');
      const bundleResumeResponse = waitForStreamResponse('POST', `/v1/workspaces/${encodeURIComponent(workspace)}/streams/bundle/import`);
      await page.getByRole('button', { name: 'Import reviewed Bundle' }).click();
      const bundleResume = await bundleResumeResponse;
      expect(bundleResume.status(), await bundleResume.text()).toBe(200);
      expect((await bundleResume.json()).checkpoint_policies).toEqual({ 'events/main': 'resume', 'events/oversized': 'resume', 'events/poison': 'resume' });
      const healthAfterBundleResumeResponse = waitForStreamResponse('GET', healthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const healthAfterBundleResume = await healthAfterBundleResumeResponse;
      expect(healthAfterBundleResume.status(), await healthAfterBundleResume.text()).toBe(200);
      expect((await healthAfterBundleResume.json()).total_lag).toBe(3);
      await page.locator('#stream-definition-form [name="checkpoint_policy"]').selectOption('resume');
      const resumeDefinitionResponse = waitForStreamResponse('PUT', definitionPath);
      await page.getByRole('button', { name: 'Save stream', exact: true }).click();
      const resumedDefinition = await resumeDefinitionResponse;
      expect(resumedDefinition.status(), await resumedDefinition.text()).toBe(200);
      expect((await resumedDefinition.json()).checkpoint_policy).toBe('resume');
      await expect(page.locator('#stream-definition-result')).toContainText('resume checkpoint policy');
      const secondRunResponse = waitForStreamResponse('POST', runPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      const secondRun = await secondRunResponse;
      expect(secondRun.status(), await secondRun.text()).toBe(200);
      expect(await secondRun.json()).toMatchObject({ stream_id: 'events/main', status: 'succeeded', records: 2, rows: 2 });
      const healthAfterSecondBatchResponse = waitForStreamResponse('GET', healthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const healthAfterSecondBatch = await healthAfterSecondBatchResponse;
      expect(healthAfterSecondBatch.status(), await healthAfterSecondBatch.text()).toBe(200);
      expect((await healthAfterSecondBatch.json()).total_lag).toBe(1);
      const thirdRunResponse = waitForStreamResponse('POST', runPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      const thirdRun = await thirdRunResponse;
      expect(thirdRun.status(), await thirdRun.text()).toBe(200);
      expect(await thirdRun.json()).toMatchObject({ stream_id: 'events/main', status: 'succeeded', records: 1, rows: 1 });
      const replayResponse = waitForStreamResponse('POST', runPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      const replay = await replayResponse;
      expect(replay.status(), await replay.text()).toBe(200);
      expect(await replay.json()).toMatchObject({ stream_id: 'events/main', status: 'idle', records: 0, rows: 0 });
      const postRunHealthResponse = waitForStreamResponse('GET', healthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const postRunHealth = await postRunHealthResponse;
      expect(postRunHealth.status(), await postRunHealth.text()).toBe(200);
      expect((await postRunHealth.json()).total_lag).toBe(0);
      await page.locator('#stream-health-form').evaluate(form => { form.noValidate = true; });
      await page.locator('#stream-health-form [name="limit"]').fill('0');
      const invalidRunResponse = waitForStreamResponse('POST', runPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      const invalidRun = await invalidRunResponse;
      expect(invalidRun.status(), await invalidRun.text()).toBe(400);
      await expect(page.locator('#stream-health-result')).toContainText('Streaming batch failed:');

      await page.locator('#stream-list').selectOption('events/poison');
      await expect(page.locator('#stream-definition-form [name="id"]')).toHaveValue('events/poison');
      await page.locator('#stream-definition-form [name="checkpoint_policy"]').selectOption('reset');
      const poisonDefinitionResponse = waitForStreamResponse('PUT', `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Fpoison`);
      await page.getByRole('button', { name: 'Save stream', exact: true }).click();
      const poisonDefinition = await poisonDefinitionResponse;
      expect(poisonDefinition.status(), await poisonDefinition.text()).toBe(200);
      expect((await poisonDefinition.json()).checkpoint_policy).toBe('reset');
      await page.locator('#stream-health-form [name="limit"]').fill('1');
      const poisonHealthPath = `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Fpoison/health`;
      const poisonHealthResponse = waitForStreamResponse('GET', poisonHealthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const poisonHealth = await poisonHealthResponse;
      expect(poisonHealth.status(), await poisonHealth.text()).toBe(200);
      expect((await poisonHealth.json()).total_lag).toBe(1);

      const poisonRunPath = `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Fpoison/run`;
      const poisonRunResponse = waitForStreamResponse('POST', poisonRunPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      const poisonRun = await poisonRunResponse;
      expect(poisonRun.status(), await poisonRun.text()).toBe(422);
      const poisonError = await poisonRun.json();
      expect(poisonError.error.code).toBe('stream_input_rejected');
      expect(poisonError.error.message).toContain('checkpoint was not advanced');
      expect(JSON.stringify(poisonError)).not.toContain('invalid-json');
      await expect(page.locator('#stream-health-result')).toContainText('checkpoint was not advanced');

      const poisonHealthAfterResponse = waitForStreamResponse('GET', poisonHealthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const poisonHealthAfter = await poisonHealthAfterResponse;
      expect((await poisonHealthAfter.json()).total_lag).toBe(1);
      const poisonRetryResponse = waitForStreamResponse('POST', poisonRunPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      expect((await poisonRetryResponse).status()).toBe(422);
      await expect(page.locator('#stream-health-result')).toContainText('checkpoint was not advanced');

      await page.locator('#stream-list').selectOption('events/oversized');
      await expect(page.locator('#stream-definition-form [name="id"]')).toHaveValue('events/oversized');
      await page.locator('#stream-definition-form [name="checkpoint_policy"]').selectOption('reset');
      const oversizedDefinitionPath = `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Foversized`;
      const oversizedDefinitionResponse = waitForStreamResponse('PUT', oversizedDefinitionPath);
      await page.getByRole('button', { name: 'Save stream', exact: true }).click();
      expect((await oversizedDefinitionResponse).status()).toBe(200);
      const oversizedHealthPath = `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Foversized/health`;
      const oversizedHealthResponse = waitForStreamResponse('GET', oversizedHealthPath);
      await page.locator('#stream-health-form [name="stream"]').fill('events/oversized');
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      expect((await oversizedHealthResponse).status()).toBe(200);
      expect((await (await oversizedHealthResponse).json()).total_lag).toBe(1);

      const oversizedRunPath = `/v1/workspaces/${encodeURIComponent(workspace)}/streams/events%2Foversized/run`;
      const oversizedRunResponse = waitForStreamResponse('POST', oversizedRunPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      const oversizedRun = await oversizedRunResponse;
      expect(oversizedRun.status(), await oversizedRun.text()).toBe(422);
      const oversizedError = await oversizedRun.json();
      expect(oversizedError.error.code).toBe('stream_input_rejected');
      expect(oversizedError.error.message).toContain('exceeds local processing limits');
      expect(JSON.stringify(oversizedError)).not.toContain('x'.repeat(1024));
      await expect(page.locator('#stream-health-result')).toContainText('checkpoint was not advanced');
      const oversizedHealthAfterResponse = waitForStreamResponse('GET', oversizedHealthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const oversizedHealthAfter = await oversizedHealthAfterResponse;
      expect((await oversizedHealthAfter.json()).total_lag).toBe(1);

      // Recover by explicitly repointing the stream to a valid source and resetting its
      // checkpoint. The rejected oversized record must remain uncommitted beforehand.
      await page.locator('#stream-definition-form [name="resource"]').fill('ronin-live-recovery-events');
      await page.locator('#stream-definition-form [name="checkpoint_policy"]').selectOption('reset');
      const recoveredDefinitionResponse = waitForStreamResponse('PUT', oversizedDefinitionPath);
      await page.getByRole('button', { name: 'Save stream', exact: true }).click();
      expect((await recoveredDefinitionResponse).status()).toBe(200);
      const recoveredRunResponse = waitForStreamResponse('POST', oversizedRunPath);
      await page.getByRole('button', { name: 'Run one batch', exact: true }).click();
      const recoveredRun = await recoveredRunResponse;
      expect(recoveredRun.status(), await recoveredRun.text()).toBe(200);
      expect(await recoveredRun.json()).toMatchObject({ stream_id: 'events/oversized', status: 'succeeded', records: 1, rows: 1 });
      await expect(page.locator('#stream-health-result')).toContainText('sink_commit_id');
      const recoveredHealthResponse = waitForStreamResponse('GET', oversizedHealthPath);
      await page.getByRole('button', { name: 'Check health', exact: true }).click();
      const recoveredHealth = await recoveredHealthResponse;
      expect((await recoveredHealth.json()).total_lag).toBe(0);
    } else if (route.id === 'graphs') {
      const workspace = process.env.RONIN_LIVE_WORKSPACE;
      await page.locator('#graph-query-form [name="workspace"]').fill(workspace);
      const queryPath = `/v1/workspaces/${encodeURIComponent(workspace)}/graphs/graph-1/query`;
      let graphResponse = page.waitForResponse(response =>
        response.request().method() === 'POST' && new URL(response.url()).pathname === queryPath,
      );
      await page.getByRole('button', { name: 'Run query', exact: true }).click();
      let graphResult = await graphResponse;
      expect(graphResult.status(), await graphResult.text()).toBe(200);
      const queryPayload = await graphResult.json();
      expect(queryPayload.objects).toHaveLength(1);
      expect(queryPayload.objects[0].properties).toContainEqual(['name', 'Ronin Live Fixture']);
      await expect(page.locator('#graph-result')).toContainText('Ronin Live Fixture');

      const objectsPath = `/v1/workspaces/${encodeURIComponent(workspace)}/graphs/graph-1/objects/Person`;
      graphResponse = page.waitForResponse(response =>
        response.request().method() === 'GET' && new URL(response.url()).pathname === objectsPath,
      );
      await page.getByRole('button', { name: 'List objects', exact: true }).click();
      graphResult = await graphResponse;
      expect(graphResult.status(), await graphResult.text()).toBe(200);
      const objectsPayload = await graphResult.json();
      expect(objectsPayload.items).toHaveLength(1);
      expect(objectsPayload.items[0]).toMatchObject({
        object_type: 'Person',
        key: [['id', '1']],
      });
      await expect(page.locator('#graph-result')).toContainText('Ronin Live Fixture');

      const neighborsPath = `/v1/workspaces/${encodeURIComponent(workspace)}/graphs/graph-1/neighbors`;
      graphResponse = page.waitForResponse(response =>
        response.request().method() === 'POST' && new URL(response.url()).pathname === neighborsPath,
      );
      await page.getByRole('button', { name: 'List neighbors', exact: true }).click();
      graphResult = await graphResponse;
      expect(graphResult.status(), await graphResult.text()).toBe(200);
      expect(await graphResult.json()).toEqual({
        items: [{ object_type: 'Organization', key: [['id', '2']] }],
      });
      await expect(page.locator('#graph-result')).toContainText('Organization');
    } else if (route.id === 'performance') {
      await page.getByRole('button', { name: 'Analyze performance', exact: true }).click();
    } else if (route.id === 'debugger') {
      await page.getByRole('button', { name: 'Create session', exact: true }).click();
    } else if (route.id === 'cloud') {
      await page.getByRole('button', { name: 'Validate target', exact: true }).click();
    } else if (route.id === 'deployments') {
      await page.locator('#deployment-bindings-form [name="workspace"]').fill(process.env.RONIN_LIVE_WORKSPACE);
      const updateResponse = page.waitForResponse(response =>
        response.request().method() === 'PUT' &&
        new URL(response.url()).pathname === `/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/projects/examples%2Fdemo/environments/local/bindings`,
      );
      await page.getByRole('button', { name: 'Replace bindings', exact: true }).click();
      const updated = await updateResponse;
      expect(updated.status(), await updated.text()).toBe(200);
      await page.getByRole('button', { name: 'Read bindings', exact: true }).click();
    } else if (route.id === 'environments') {
      await page.locator('#environment-workspace').fill(process.env.RONIN_LIVE_WORKSPACE);
      await page.getByRole('button', { name: 'Refresh environments', exact: true }).click();
      const environmentForm = page.locator('[data-feature-form="environment-create"]');
      await environmentForm.locator('[name="id"]').fill('local');
      await environmentForm.locator('[name="name"]').fill('Local live fixture');
      const createResponse = page.waitForResponse(response =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === `/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/environments`,
      );
      await environmentForm.evaluate(form => form.requestSubmit());
      const created = await createResponse;
      expect([200, 201], await created.text()).toContain(created.status());
      await expect(page.locator('#environment-result')).toContainText('Local live fixture');
    } else if (route.id === 'workflows') {
      const workspace = process.env.RONIN_LIVE_WORKSPACE;
      const schedulerPath = `/v1/workspaces/${encodeURIComponent(workspace)}`;
      const responseFor = (method, pathname) => page.waitForResponse(response =>
        response.request().method() === method && new URL(response.url()).pathname === pathname,
      );
      const form = page.locator('#scheduler-form');
      await form.locator('[name="workspace"]').fill(workspace);
      await form.locator('[name="workflow_id"]').fill('live-main');
      await form.locator('[name="schedule_id"]').fill('live-daily');
      await form.locator('[name="cron"]').fill('0 0 * * *');
      await form.locator('[name="timezone"]').fill('Europe/Madrid');
      await form.locator('[name="after"]').fill('2026-09-17T00:00:00.000000Z');
      await form.locator('[name="start_at"]').fill('2026-09-17T00:00:00.000000Z');
      await form.locator('[name="end_at"]').fill('2026-09-20T00:00:00.000000Z');
      await form.locator('[name="idempotency_key"]').fill(`live-run-${Date.now()}`);

      const schedulePath = `${schedulerPath}/schedules/live-daily`;
      let response = responseFor('PUT', schedulePath);
      await page.getByRole('button', { name: 'Save schedule', exact: true }).click();
      let savedSchedule = await response;
      expect(savedSchedule.status(), await savedSchedule.text()).toBe(200);

      response = responseFor('GET', schedulePath);
      await page.getByRole('button', { name: 'Inspect schedule', exact: true }).click();
      const inspectedSchedule = await response;
      expect(inspectedSchedule.status(), await inspectedSchedule.text()).toBe(200);
      expect((await inspectedSchedule.json()).timezone).toBe('Europe/Madrid');

      response = responseFor('GET', `${schedulerPath}/schedules`);
      await page.getByRole('button', { name: 'List schedules', exact: true }).click();
      const listedSchedules = await response;
      expect(listedSchedules.status(), await listedSchedules.text()).toBe(200);
      expect(JSON.stringify(await listedSchedules.json())).toContain('live-daily');

      response = responseFor('GET', `${schedulePath}/next-runs`);
      await page.getByRole('button', { name: 'Preview next runs', exact: true }).click();
      const nextRuns = await response;
      expect(nextRuns.status(), await nextRuns.text()).toBe(200);
      const nextRunItems = (await nextRuns.json()).items;
      expect(nextRunItems.length).toBeGreaterThan(0);
      expect(nextRunItems[0]).toContain('2026-09-17T22:00:00');

      response = responseFor('GET', `${schedulePath}/history`);
      await page.getByRole('button', { name: 'View history', exact: true }).click();
      expect((await response).status()).toBe(200);

      const runPath = `${schedulerPath}/workflows/live-main/runs`;
      response = responseFor('POST', runPath);
      await page.getByRole('button', { name: 'Run workflow', exact: true }).click();
      const createdRunResponse = await response;
      expect(createdRunResponse.status(), await createdRunResponse.text()).toBe(201);
      const createdRun = await createdRunResponse.json();
      expect(createdRun.state).toBe('pending');
      response = responseFor('POST', runPath);
      await page.getByRole('button', { name: 'Run workflow', exact: true }).click();
      const retriedRunResponse = await response;
      expect(retriedRunResponse.status()).toBe(201);
      expect((await retriedRunResponse.json()).id).toBe(createdRun.id);
      await form.locator('[name="run_id"]').fill(createdRun.id);
      response = responseFor('GET', `${schedulerPath}/workflow-runs/${encodeURIComponent(createdRun.id)}`);
      await page.getByRole('button', { name: 'Inspect run', exact: true }).click();
      expect((await response).status()).toBe(200);
      await expect(page.locator('#scheduler-result')).toContainText(createdRun.id);
      response = responseFor('POST', `${schedulerPath}/workflow-runs/${encodeURIComponent(createdRun.id)}/cancel`);
      await page.getByRole('button', { name: 'Cancel workflow run', exact: true }).click();
      expect((await response).status()).toBe(200);
      response = responseFor('GET', `${schedulerPath}/workflow-runs/${encodeURIComponent(createdRun.id)}`);
      await page.getByRole('button', { name: 'Inspect run', exact: true }).click();
      expect((await response).status()).toBe(200);
      await expect(page.locator('#scheduler-result')).toContainText('"state": "cancelled"');

      await form.locator('[name="trigger_id"]').fill('live-trigger');
      await form.locator('[name="event_type"]').fill('ronin.live.qualification');
      await form.locator('[name="source_ref"]').fill('live-studio');
      const triggerPath = `${schedulerPath}/event-triggers/live-trigger`;
      response = responseFor('PUT', triggerPath);
      await page.getByRole('button', { name: 'Save event trigger', exact: true }).click();
      expect((await response).status()).toBe(200);
      response = responseFor('GET', `${schedulerPath}/event-triggers`);
      await page.getByRole('button', { name: 'List event triggers', exact: true }).click();
      expect((await response).status()).toBe(200);

      const eventId = `live-event-${Date.now()}`;
      await form.locator('[name="event_id"]').fill(eventId);
      response = responseFor('POST', `${schedulerPath}/events`);
      await page.getByRole('button', { name: 'Ingest event', exact: true }).click();
      const ingestedEvent = await response;
      expect(ingestedEvent.status()).toBe(202);
      expect((await ingestedEvent.json()).deliveries).toContain('pending');
      let deliveredEvent;
      await expect.poll(async () => {
        response = responseFor('GET', `${schedulerPath}/event-deliveries`);
        await page.getByRole('button', { name: 'Inspect event deliveries', exact: true }).click();
        const deliveryResponse = await response;
        if (deliveryResponse.status() !== 200) return `HTTP ${deliveryResponse.status()}`;
        deliveredEvent = (await deliveryResponse.json()).items.find(item => item.event_id === eventId);
        return deliveredEvent?.state || 'not visible';
      }, { timeout: 15_000, message: 'the running scheduler daemon should deliver the event' }).toBe('delivered');
      expect(deliveredEvent.workflow_run_id).toMatch(/^workflow-run-event-/);
      await expect(page.locator('#scheduler-result')).toContainText('delivered');

      response = responseFor('POST', `${schedulerPath}/backfills/preview`);
      await page.getByRole('button', { name: 'Preview backfill', exact: true }).click();
      const backfillPreview = await response;
      expect(backfillPreview.status(), await backfillPreview.text()).toBe(200);
      expect((await backfillPreview.json()).items).toHaveLength(3);

      const backfillId = `live-backfill-${Date.now()}`;
      await form.locator('[name="backfill_id"]').fill(backfillId);
      response = responseFor('POST', `${schedulerPath}/backfills`);
      await page.getByRole('button', { name: 'Start backfill', exact: true }).click();
      const createdBackfill = await response;
      expect(createdBackfill.status(), await createdBackfill.text()).toBe(201);
      expect((await createdBackfill.json()).state).toBe('pending');
      let activeBackfill;
      await expect.poll(async () => {
        response = responseFor('GET', `${schedulerPath}/backfills/${encodeURIComponent(backfillId)}`);
        await page.getByRole('button', { name: 'Inspect backfill', exact: true }).click();
        const inspection = await response;
        if (inspection.status() !== 200) return `HTTP ${inspection.status()}`;
        activeBackfill = await inspection.json();
        return activeBackfill.state;
      }, { timeout: 15_000, message: 'the running scheduler daemon should generate a backfill run' }).toBe('running');
      response = responseFor('POST', `${schedulerPath}/backfills/${encodeURIComponent(backfillId)}/cancel`);
      await page.getByRole('button', { name: 'Cancel backfill', exact: true }).click();
      expect((await response).status()).toBe(200);
      await expect(page.locator('#scheduler-result')).toContainText('cancelled');
    }

    if (!route.required_api?.length) {
      const routeCalls = calls.slice(before).filter(call => !routeIndependentApiPaths.has(call.path));
      expect(routeCalls, `route ${route.id} has no published API contract`).toHaveLength(0);
      await flushLiveTraffic();
      return;
    }
    const patterns = route.required_api.map(templatePattern);
    await expect
      .poll(
        () => calls.slice(before).filter(call => patterns.some(pattern => pattern.test(call.path))),
        { timeout: 8_000, message: `route ${route.id} did not call one of its published API paths` },
      )
      .not.toHaveLength(0);

    const matched = calls
      .slice(before)
      .filter(call => patterns.some(pattern => pattern.test(call.path)));
    expect(matched.every(call => call.authorization === 'present')).toBe(true);
    const expectedQualityBlock = route.id === 'quality' && matched.some(
      call => call.status === 409 && call.outcome === 'WARN',
    );
    const expectedMlPromotionBlock = route.id === 'mlstudio' && matched.some(
      call => call.method === 'POST' && /\/v1\/ml-studio\/models\/[^/]+\/[^/]+\/promote$/.test(call.path) &&
        call.status === 409 && call.outcome === 'WARN',
    );
    const expectedStreamingInputBlock = route.id === 'streaming' && matched.some(
      call => call.method === 'POST' && /\/streams\/[^/]+\/run$/.test(call.path) &&
        call.status === 400 && call.outcome === 'WARN' && call.errorCode === 'invalid_request',
    );
    const expectedStreamingDataBlock = route.id === 'streaming' && matched.some(
      call => call.method === 'POST' && /\/streams\/[^/]+\/run$/.test(call.path) &&
        call.status === 422 && call.outcome === 'WARN' && call.errorCode === 'stream_input_rejected',
    );
    expect(
      matched.every(call => (call.status >= 200 && call.status < 400) ||
        (expectedQualityBlock && call.status === 409 && call.outcome === 'WARN') ||
        (expectedStreamingInputBlock && call.method === 'POST' &&
          /\/streams\/[^/]+\/run$/.test(call.path) && call.status === 400 &&
          call.outcome === 'WARN' && call.errorCode === 'invalid_request') ||
        (expectedStreamingDataBlock && call.method === 'POST' &&
          /\/streams\/[^/]+\/run$/.test(call.path) && call.status === 422 &&
          call.outcome === 'WARN' && call.errorCode === 'stream_input_rejected') ||
        (expectedMlPromotionBlock && call.method === 'POST' &&
          /\/v1\/ml-studio\/models\/[^/]+\/[^/]+\/promote$/.test(call.path) &&
          call.status === 409 && call.outcome === 'WARN')),
      `live API responses: ${JSON.stringify(matched.map(({ method, path, status, surface, errorCode }) => ({ method, path, status, surface, errorCode })))}`,
    ).toBe(true);
    if (route.id === 'workflows') {
      await page.locator('#scheduler-form [name="cron"]').fill('not a cron expression');
      const schedulePath = `/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/schedules/live-daily`;
      const invalidSave = page.waitForResponse(response =>
        response.request().method() === 'PUT' &&
        new URL(response.url()).pathname === schedulePath,
      );
      await page.getByRole('button', { name: 'Save schedule', exact: true }).click();
      expect((await invalidSave).status()).toBe(400);
      await expect(page.locator('#scheduler-result')).toContainText('Scheduler operation failed:');
      expect(calls.some(call => call.status === 400 && call.outcome === 'WARN')).toBe(true);
      await page.locator('#scheduler-form [name="cron"]').fill('0 0 * * *');
      const unchangedSchedule = page.waitForResponse(response =>
        response.request().method() === 'GET' && new URL(response.url()).pathname === schedulePath,
      );
      await page.getByRole('button', { name: 'Inspect schedule', exact: true }).click();
      expect((await unchangedSchedule).status()).toBe(200);
      expect(JSON.parse((await page.locator('#scheduler-result').textContent()) || '{}').cron).toBe('0 0 * * *');
    }
    await flushLiveTraffic();
  });
}

test('live Projects create, export, and reimport a secret-safe Bundle through the UI', async ({ page }) => {
  test.setTimeout(60_000);
  test.skip(!liveReady, 'Run via npm run test:live with a live Ronin API and PostgreSQL fixture.');
  const calls = installLiveApiProxy(page);
  await connectLiveStudio(page);

  const workspace = process.env.RONIN_LIVE_WORKSPACE;
  const projectId = `live-bundle-${Date.now()}`;
  const projectsPath = `/v1/workspaces/${encodeURIComponent(workspace)}/projects`;
  const projectPath = `${projectsPath}/${encodeURIComponent(projectId)}`;
  const manifest = uri => ({
    schema: 'ronin.project/v1',
    project: {
      id: projectId,
      name: 'Ronin live Bundle qualification',
      repositories: [{
        adapter_id: 'git', alias: 'code', default_ref: 'main', role: 'primary',
        subdirectory: null, sync_policy: 'manual', uri,
      }],
      execution: { requirements: [], resolution: 'strict', runtime: { adapter_id: 'python', profile_id: '3.11' } },
    },
  });

  await page.goto(`./#projects/${encodeURIComponent(workspace)}`);
  await expect(page.locator('#project-manifest')).toBeVisible();

  const unsafeSentinel = 'live-secret-do-not-leak';
  await page.locator('#project-manifest').fill(JSON.stringify(
    manifest(`https://user:${unsafeSentinel}@git.example.test/team/project.git`),
  ));
  let response = page.waitForResponse(item =>
    item.request().method() === 'POST' && new URL(item.url()).pathname === projectsPath,
  );
  await page.getByRole('button', { name: 'Create project', exact: true }).click();
  let result = await response;
  expect(result.status(), await result.text()).toBe(400);
  const visibleWarning = await page.locator('#project-journey-result').innerText();
  expect(visibleWarning).toContain('Could not create project');
  expect(visibleWarning).not.toContain(unsafeSentinel);
  expect(calls.some(call => call.path === projectsPath && call.status === 400 && call.outcome === 'WARN')).toBe(true);

  await page.locator('#project-manifest').fill(JSON.stringify(
    manifest('https://git.example.test/team/project.git'),
  ));
  response = page.waitForResponse(item =>
    item.request().method() === 'POST' && new URL(item.url()).pathname === projectsPath,
  );
  await page.getByRole('button', { name: 'Create project', exact: true }).click();
  result = await response;
  expect([200, 201], await result.text()).toContain(result.status());
  const created = await result.json();
  expect(created.project.id).toBe(projectId);
  await expect(page.locator('#project-journey-result')).toContainText(projectId);

  const projectRow = page.locator('#project-list tbody tr').filter({ hasText: projectId });
  await expect(projectRow).toBeVisible();
  response = page.waitForResponse(item =>
    item.request().method() === 'GET' && new URL(item.url()).pathname === `${projectPath}/bundle`,
  );
  await projectRow.getByRole('button', { name: 'Export manifest', exact: true }).click();
  result = await response;
  expect(result.status()).toBe(200);
  const exportedManifest = await result.json();
  expect(exportedManifest.project.id).toBe(projectId);
  expect(exportedManifest.project.repositories[0]).not.toHaveProperty('auth_ref');
  const manifestText = JSON.stringify(exportedManifest);
  expect(manifestText).not.toContain(unsafeSentinel);
  expect(manifestText).not.toContain(process.env.RONIN_LIVE_API_TOKEN);

  const archiveResponse = page.waitForResponse(item =>
    item.request().method() === 'GET' && new URL(item.url()).pathname === `${projectPath}/bundle/archive`,
  );
  const downloadEvent = page.waitForEvent('download');
  await projectRow.getByRole('button', { name: 'Download Bundle', exact: true }).click();
  const archivePayloadResponse = await archiveResponse;
  expect(archivePayloadResponse.status()).toBe(200);
  const archivePayload = await archivePayloadResponse.json();
  expect(archivePayload.media_type).toBe('application/vnd.ronin.bundle+zip');
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/\.roninbundle$/);
  const archiveBytes = fs.readFileSync(await download.path());
  expect(createHash('sha256').update(archiveBytes).digest('hex')).toBe(archivePayload.digest);
  expect(archiveBytes.includes(Buffer.from(unsafeSentinel))).toBe(false);
  expect(archiveBytes.includes(Buffer.from(process.env.RONIN_LIVE_API_TOKEN))).toBe(false);

  await page.locator('#project-bundle-import-form [name="project_id"]').fill(projectId);
  await page.locator('#project-bundle-import-form [name="bundle"]').setInputFiles({
    name: download.suggestedFilename(),
    mimeType: archivePayload.media_type,
    buffer: archiveBytes,
  });
  const importResponse = page.waitForResponse(item =>
    item.request().method() === 'POST' && new URL(item.url()).pathname === `${projectPath}/bundle/import`,
  );
  await page.getByRole('button', { name: 'Import Bundle', exact: true }).click();
  const importedResponse = await importResponse;
  expect(importedResponse.status(), await importedResponse.text()).toBe(200);
  const imported = await importedResponse.json();
  expect(imported.project.project.id).toBe(projectId);
  expect(imported.bundle_digest).toBe(archivePayload.digest);
  await expect(page.locator('#project-journey-result')).toContainText(projectId);
  await expect(projectRow).toBeVisible();
  expect(calls.some(call => call.path === `${projectPath}/bundle/import` && call.status === 200 && call.outcome === 'OK')).toBe(true);
  expect(calls.every(call => call.authorization === 'present')).toBe(true);
  await flushLiveTraffic();
});

test('live single-operator authorization shows OK and WARN for token and workspace scope decisions', async ({ page }) => {
  test.setTimeout(60_000);
  test.skip(!liveReady, 'Run via npm run test:live with a live Ronin API and PostgreSQL fixture.');
  const calls = installLiveApiProxy(page);
  const validToken = process.env.RONIN_LIVE_API_TOKEN;
  await connectLiveStudio(page);

  const requestFor = (method, pathname) => page.waitForResponse(response =>
    response.request().method() === method && new URL(response.url()).pathname === pathname,
  );
  const setToken = async (token, clear = false) => {
    await page.getByRole('button', { name: 'Server connection' }).click();
    if (token) await page.locator('#api-token').fill(token);
    if (clear) await page.locator('#api-token-clear').check();
    await page.getByRole('button', { name: 'Save connection', exact: true }).click();
  };

  let response = requestFor('GET', '/v1/workspaces');
  await page.goto('./#workspaces');
  response = await response;
  expect(response.status(), await response.text()).toBe(200);
  await expect(page.locator('#workspace-result')).toContainText('Live Qualification Workspace');
  const createWorkspace = page.locator('#workspace-create-form');
  await expect(createWorkspace).toBeVisible();
  const createdWorkspaceId = `live-auth-${Date.now()}`;
  await page.locator('#workspace-create-id').fill(createdWorkspaceId);
  await page.locator('#workspace-create-name').fill('Live authorization fixture');
  await page.locator('#workspace-create-description').fill('Isolated single-operator qualification');
  response = requestFor('POST', '/v1/workspaces');
  await createWorkspace.getByRole('button', { name: 'Create', exact: true }).click();
  const createdWorkspace = await response;
  expect(createdWorkspace.status(), await createdWorkspace.text()).toBe(201);
  await expect(page.locator('#workspace-create-result')).toContainText(createdWorkspaceId);
  await expect(page.locator('#workspace-result')).toContainText('Live authorization fixture');
  await expect(page.locator('#workspace-result')).toContainText(createdWorkspaceId);

  response = requestFor('GET', '/v1/workspaces');
  await setToken('', true);
  let rejected = await response;
  expect(rejected.status(), await rejected.text()).toBe(401);
  await expect(page.locator('#workspace-result')).toContainText('valid authorization required');

  response = requestFor('GET', '/v1/workspaces');
  await setToken('ronin-invalid-live-token');
  rejected = await response;
  expect(rejected.status(), await rejected.text()).toBe(401);
  await expect(page.locator('#workspace-result')).toContainText('valid authorization required');

  response = requestFor('GET', '/v1/workspaces');
  await setToken(validToken);
  expect((await response).status()).toBe(200);
  await page.goto('./#catalog');
  const unauthorizedWorkspace = 'outside-live-qualification-scope';
  await page.locator('#catalog-search-form [name="workspace"]').fill(unauthorizedWorkspace);
  let scopedResponse = requestFor(
    'GET',
    `/v1/workspaces/${encodeURIComponent(unauthorizedWorkspace)}/catalog/assets`,
  );
  await page.getByRole('button', { name: 'Search catalog', exact: true }).click();
  const forbidden = await scopedResponse;
  expect(forbidden.status(), await forbidden.text()).toBe(403);
  await expect(page.locator('#catalog-result')).toContainText('required workspace permission is not granted');

  await page.locator('#catalog-search-form [name="workspace"]').fill(process.env.RONIN_LIVE_WORKSPACE);
  scopedResponse = requestFor(
    'GET',
    `/v1/workspaces/${encodeURIComponent(process.env.RONIN_LIVE_WORKSPACE)}/catalog/assets`,
  );
  await page.getByRole('button', { name: 'Search catalog', exact: true }).click();
  expect((await scopedResponse).status()).toBe(200);

  expect(calls.some(call => call.path === '/v1/workspaces' && call.status === 200 && call.outcome === 'OK')).toBe(true);
  expect(calls.some(call => call.path === '/v1/workspaces' && call.authorizationKind === 'missing' && call.status === 401 && call.outcome === 'WARN')).toBe(true);
  expect(calls.some(call => call.path === '/v1/workspaces' && call.authorizationKind === 'other' && call.status === 401 && call.outcome === 'WARN')).toBe(true);
  expect(calls.some(call => call.path.endsWith('/catalog/assets') && call.authorizationKind === 'expected' && call.status === 403 && call.outcome === 'WARN')).toBe(true);
  expect(calls.some(call => call.outcome === 'ERROR')).toBe(false);
  await flushLiveTraffic();
});

test('live Notebook Studio creates, versions and executes a notebook on a Docker worker', async ({ page }) => {
  test.setTimeout(120_000);
  test.skip(!liveWorkerReady, 'Run via the live qualification harness with a real Ronin API and Docker worker.');
  const calls = installLiveApiProxy(page);
  await connectLiveStudio(page);
  await page.goto('./#notebooks');

  const workspace = process.env.RONIN_LIVE_WORKSPACE;
  const project = 'examples/demo';
  await page.locator('#notebook-context [name="workspace"]').fill(workspace);
  await page.locator('#notebook-context [name="project"]').fill(project);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();

  const notebookId = `live-notebook-${Date.now()}`;
  const notebookPath = `/v1/workspaces/${encodeURIComponent(workspace)}/projects/${encodeURIComponent(project)}/notebooks`;
  const documentField = page.locator('#notebook-editor textarea[name="document"]');
  const identity = {
    boundary: 'authoring',
    namespace: `${project}/notebooks/${notebookId}`,
    reference: 'live-cell',
  };
  const cellId = createHash('sha256')
    .update(`ronin-notebook-cell-v1\0${identity.boundary}\0${identity.namespace}\0${identity.reference}`)
    .digest('hex');
  const notebookDocument = (message) => ({
    schema: 'ronin.notebook/v1',
    cells: [{
      dependencies: [],
      id: cellId,
      identity,
      kind: 'code',
      language: 'python',
      source: `print('${message}')`,
    }],
  });
  await page.locator('#notebook-editor input[name="id"]').fill(notebookId);
  // Revision is a required editor field even for a new notebook; the API stores
  // the first saved snapshot as revision 1.
  await page.locator('#notebook-editor input[name="revision"]').fill('1');
  await page.locator('#notebook-editor select[name="runtime"]').selectOption('container');
  await documentField.fill(JSON.stringify(notebookDocument('ronin-live-notebook-revision-1')));
  const createResponse = page.waitForResponse(response =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === notebookPath,
  );
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  const created = await createResponse;
  expect(created.status(), await created.text()).toBe(201);
  await expect(page.locator('#notebook-result')).toContainText('"revision": 1');

  await page.locator('#notebook-editor input[name="revision"]').fill('1');
  await documentField.fill(JSON.stringify(notebookDocument('ronin-live-notebook-revision-2')));
  const saveResponse = page.waitForResponse(response =>
    response.request().method() === 'PUT' && new URL(response.url()).pathname === `${notebookPath}/${encodeURIComponent(notebookId)}`,
  );
  await page.locator('#notebook-editor [data-notebook-action="save"]').click();
  const saved = await saveResponse;
  expect(saved.status(), await saved.text()).toBe(200);
  await expect(page.locator('#notebook-result')).toContainText('"revision": 2');

  const jobResponse = page.waitForResponse(response =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/v1/jobs',
  );
  await page.getByRole('button', { name: 'Run all cells', exact: true }).click();
  const submitted = await jobResponse;
  expect(submitted.status(), await submitted.text()).toBe(201);
  const job = await submitted.json();
  expect(job.id).toBeTruthy();
  const runPanel = page.locator('#notebook-run');
  await expect.poll(async () => {
    try {
      const report = JSON.parse((await runPanel.textContent()) || '{}');
      return report.job?.state === 'succeeded' && report.results?.items?.length > 0;
    } catch {
      return false;
    }
  }, { timeout: 90_000 }).toBe(true);
  const runReport = JSON.parse((await runPanel.textContent()) || '{}');
  const cellResult = runReport.results.items[0];
  expect(cellResult.state).toBe('succeeded');
  const execution = JSON.parse(cellResult.result_json);
  expect(execution.state).toBe('succeeded');
  expect(execution.evidence.map(item => item.role)).toContain('log');

  const expectedPaths = [notebookPath, `${notebookPath}/${encodeURIComponent(notebookId)}`, '/v1/jobs'];
  for (const path of expectedPaths) {
    expect(calls.some(call => call.path === path && call.status >= 200 && call.status < 300),
      `expected successful live API call to ${path}`).toBe(true);
  }
  expect(calls.every(call => call.authorization === 'present')).toBe(true);
  expect(calls.some(call => call.status >= 500 || call.status === 0)).toBe(false);
  await flushLiveTraffic();
});
test('live API traffic contains route, method and response status without credentials', async () => {
  test.skip(!liveReady, 'Run via npm run test:live with a live Ronin API and PostgreSQL fixture.');
  await flushLiveTraffic();
  const reportPath = process.env.RONIN_LIVE_API_TRAFFIC_OUTPUT;
  const traffic = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  expect(traffic.length).toBeGreaterThan(0);
  for (const call of traffic) {
    expect(call).toHaveProperty('method');
    expect(call).toHaveProperty('path');
    expect(call).toHaveProperty('status');
    expect(call).toHaveProperty('outcome');
    expect(call.requestId).toMatch(/^req-[0-9a-f]{32}$/);
    expect(call.duration_ms).toEqual(expect.any(Number));
    expect(call.duration_ms).toBeGreaterThanOrEqual(0);
    const expectedOutcome = call.network_error || call.status >= 500
      ? 'ERROR'
      : call.status >= 400
        ? 'WARN'
        : call.status >= 200
          ? 'OK'
          : 'ERROR';
    expect(call.outcome).toBe(expectedOutcome);
    expect(JSON.stringify(call)).not.toContain(process.env.RONIN_LIVE_API_TOKEN);
  }
});
