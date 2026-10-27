import { get, post } from './api.js';
import { json } from './dom.js';

let capabilities = null;
let resultState = null;

export function getQueryFluxResultState() {
  return resultState;
}

export function getLoadedQueryFluxResult() {
  return resultState ? { columns: resultState.columns, rows: resultState.rows } : null;
}

export function clearQueryFluxResultState() {
  resultState = null;
}

export function updateQueryProfileControls() {
  const form = document.querySelector('#de-sql-form');
  if (!form) return;
  const isQueryFlux = form.querySelector('[name="profile"]')?.value === 'queryflux';
  form.querySelectorAll('[data-queryflux-only]').forEach(label => { label.hidden = !isQueryFlux; });
  form.querySelectorAll('[data-sql-local-only]').forEach(label => { label.hidden = isQueryFlux; });
  const engine = form.querySelector('[name="queryflux_engine"]');
  const allowedEngines = Array.isArray(capabilities?.allowed_engines)
    ? capabilities.allowed_engines.filter(value => typeof value === 'string')
    : [];
  if (engine) {
    const previous = engine.value;
    engine.replaceChildren(...allowedEngines.map(value => new Option(value, value)));
    if (allowedEngines.includes(previous)) engine.value = previous;
  }
  const translation = form.querySelector('[name="translation_policy"]');
  if (translation && isQueryFlux && Array.isArray(capabilities?.translation_policies)) {
    const allowed = capabilities.translation_policies.filter(value => typeof value === 'string');
    const previous = translation.value;
    translation.replaceChildren(...allowed.map(value => new Option(value.replaceAll('_', ' '), value)));
    translation.value = allowed.includes(previous) ? previous : (allowed[0] || 'native_only');
  }
  const execute = form.querySelector('[data-action="de-sql-execute"]');
  if (execute) {
    execute.disabled = isQueryFlux && allowedEngines.length === 0;
    execute.title = execute.disabled ? 'QueryFlux has no authorized engine configured.' : '';
  }
}

function renderQueryFluxResult() {
  const out = document.querySelector('#de-sql-result');
  const next = document.querySelector('#de-queryflux-next-page');
  if (!out || !resultState) return;
  out.textContent = json({
    status: resultState.status,
    selected_engine: resultState.selectedEngine,
    rows_loaded: resultState.rows.length,
    row_count: resultState.rowCount,
    columns: resultState.columns,
    rows: resultState.rows,
    evidence: resultState.evidence,
    run_id: resultState.runId,
    attempt_id: resultState.attemptId,
  });
  if (next) {
    next.hidden = !resultState.nextCursor;
    next.disabled = false;
    next.textContent = resultState.nextCursor
      ? `Load next results page (${resultState.rows.length} of ${resultState.rowCount} rows loaded)`
      : 'All result rows loaded';
  }
}

export async function loadQueryFluxNextPage() {
  const state = resultState;
  if (!state?.nextCursor) return;
  const next = document.querySelector('#de-queryflux-next-page');
  if (next) { next.disabled = true; next.textContent = 'Loading results…'; }
  try {
    const page = await get(`${state.endpoint}?page_size=${state.pageSize}&cursor=${encodeURIComponent(state.nextCursor)}`);
    if (JSON.stringify(page.columns) !== JSON.stringify(state.columns)) {
      throw new Error('QueryFlux returned inconsistent result columns between pages');
    }
    if (page.row_count !== state.rowCount || !Array.isArray(page.rows)) {
      throw new Error('QueryFlux returned an inconsistent result page');
    }
    state.rows.push(...page.rows);
    state.nextCursor = page.next_cursor || null;
    renderQueryFluxResult();
  } catch (error) {
    if (next) { next.disabled = false; next.textContent = 'Retry loading results'; }
    throw error;
  }
}

function queryFluxIdentifier() {
  if (typeof crypto?.randomUUID !== 'function') {
    throw new Error('Secure random IDs are unavailable; open Ronin over localhost or HTTPS.');
  }
  return crypto.randomUUID();
}

function queryFluxResultsEndpoint(workspace, project, runId, attemptId) {
  return `/v1/workspaces/${encodeURIComponent(workspace)}/projects/${encodeURIComponent(project)}/data-engineering/queryflux/executions/${encodeURIComponent(runId)}/${encodeURIComponent(attemptId)}/results`;
}

export async function executeQueryFlux(data, out) {
  const workspace = String(data.get('workspace')).trim();
  const project = String(data.get('project')).trim();
  const engine = String(data.get('queryflux_engine') || '').trim();
  if (!workspace || !project) throw new Error('Workspace and project are required for QueryFlux.');
  if (!engine) throw new Error('No QueryFlux engine is authorized. Check the QueryFlux status panel.');
  const runId = queryFluxIdentifier();
  const attemptId = queryFluxIdentifier();
  const endpoint = queryFluxResultsEndpoint(workspace, project, runId, attemptId);
  const pageSize = Number(data.get('page_size'));
  const result = await post(
    `/v1/workspaces/${encodeURIComponent(workspace)}/projects/${encodeURIComponent(project)}/data-engineering/queryflux/execute`,
    {
      sql: String(data.get('sql')),
      profile: 'queryflux',
      engine,
      run_id: runId,
      attempt_id: attemptId,
      max_rows: Number(data.get('max_rows')),
      page_size: pageSize,
      max_result_bytes: Number(data.get('max_result_bytes')),
      translation_policy: String(data.get('translation_policy')),
      parameters: [],
    },
  );
  resultState = {
    endpoint,
    runId,
    attemptId,
    pageSize,
    nextCursor: result.next_cursor || null,
    rowCount: result.row_count || 0,
    columns: result.columns || [],
    rows: result.rows || [],
    status: result.status,
    selectedEngine: result.selected_engine,
    evidence: result.evidence,
  };
  renderQueryFluxResult();
  if (!resultState.nextCursor) {
    const next = document.querySelector('#de-queryflux-next-page');
    if (next) next.hidden = true;
  }
  out.dataset.runId = runId;
  return getLoadedQueryFluxResult();
}

export async function loadQueryFluxCapabilities() {
  const result = document.querySelector('#de-queryflux-result');
  const status = document.querySelector('#de-queryflux-status');
  if (!result || !status) return;
  try {
    const payload = await get('/v1/data-engineering/queryflux/capabilities');
    capabilities = payload;
    updateQueryProfileControls();
    const state = payload.status || (payload.healthy === true ? 'ready' : 'degraded');
    const enabled = Object.entries(payload.capabilities || {})
      .filter(([, isEnabled]) => isEnabled === true)
      .map(([name]) => name)
      .sort();
    status.textContent = `QueryFlux: ${state}${enabled.length ? ` · ${enabled.length} capabilities` : ''}`;
    result.textContent = json({
      provider: payload.provider || 'queryflux',
      status: state,
      capabilities: enabled,
      translation_policies: payload.translation_policies || ['native_only', 'best_effort'],
    });
  } catch (error) {
    capabilities = null;
    updateQueryProfileControls();
    status.textContent = 'QueryFlux: degraded';
    result.textContent = `QueryFlux capability check failed: ${error.message}`;
  }
}

export function addQueryFluxPanel() {
  const view = document.querySelector('#view');
  const existing = view?.querySelector('#de-queryflux-result')?.closest('.panel');
  if (location.hash.slice(1).split('/')[0] !== 'data') { existing?.remove(); return; }
  if (!view || existing) return;
  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.innerHTML = '<h2>QueryFlux</h2><p class="muted">Provider-neutral query routing evidence; raw cluster configuration is intentionally hidden.</p><div class="toolbar"><button class="button" data-action="de-queryflux-capabilities">Refresh capabilities</button></div><p id="de-queryflux-status" class="status" aria-live="polite">Loading QueryFlux health…</p><pre id="de-queryflux-result" class="code" aria-live="polite">No capability response yet.</pre>';
  view.prepend(panel);
  loadQueryFluxCapabilities();
}

export function addQueryTranslationPolicy() {
  const form = document.querySelector('#de-sql-form');
  if (!form || form.querySelector('[name="translation_policy"]')) return;
  const label = document.createElement('label');
  label.textContent = 'Translation policy';
  const select = document.createElement('select');
  select.className = 'field';
  select.name = 'translation_policy';
  for (const [value, text] of [['native_only', 'Native only'], ['best_effort', 'Best effort'], ['strict', 'Strict']]) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = text;
    select.append(option);
  }
  label.append(select);
  form.querySelector('.grid')?.append(label);
  const dialectLabel = document.createElement('label');
  dialectLabel.textContent = 'Dialect';
  const dialect = document.createElement('select');
  dialect.className = 'field';
  dialect.name = 'dialect';
  for (const value of ['ansi', 'postgres', 'duckdb', 'trino']) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    dialect.append(option);
  }
  dialectLabel.append(dialect);
  form.querySelector('.grid')?.append(dialectLabel);
}

setTimeout(addQueryFluxPanel, 100);
window.addEventListener('hashchange', () => setTimeout(addQueryFluxPanel, 100));
setTimeout(addQueryTranslationPolicy, 0);
window.addEventListener('hashchange', addQueryTranslationPolicy);
