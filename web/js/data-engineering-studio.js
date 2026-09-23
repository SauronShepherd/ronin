import { get, post } from './api.js';
import { json, page } from './dom.js';

const sample = '{"runtime":"local-preview","pipeline":{"nodes":[],"edges":[]}}';
function render() {
  if (location.hash.slice(1) !== 'data') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Data Engineering', 'PIPELINES')}<section class="panel"><div class="toolbar"><button class="button" data-action="de-health">Health</button><button class="button" data-action="de-runtimes">Runtimes</button></div><pre id="de-health-result" class="code">No health check requested.</pre></section><section class="panel"><h2>SQL editor</h2><form id="de-sql-form"><div class="grid three"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Project<input class="field" name="project" value="examples/demo" required></label><label>Profile<select class="field" name="profile"><option value="local">Local</option><option value="queryflux">QueryFlux</option></select></label></div><label>SQL<textarea class="field sql-editor" name="sql" rows="6" required>SELECT 1 AS value</textarea><button class="button primary" data-action="de-sql-execute" type="button">Execute bounded query</button><button class="button" data-action="de-sql-export" type="button">Export CSV</button></form><pre id="de-sql-result" class="code" aria-live="polite">No SQL operation requested.</pre></section><section class="panel"><form id="de-pipeline-form"><div class="grid three"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Project<input class="field" name="project" value="examples/demo" required></label><label>Pipeline<input class="field" name="pipeline_id" value="main" required></label><label>Revision<input class="field" name="revision" type="number" min="1"></label><label>Compare revision<input class="field" name="compare_revision" type="number" min="1"></label><label>Revision key<input class="field" name="revision_key" value="main/working"></label><label>IR digest<input class="field" name="ir_digest" minlength="64" maxlength="64"></label><label>Runtime<input class="field" name="runtime" value="local-preview"></label><label>Run ID<input class="field" name="run_id"></label></div><label>Pipeline JSON<textarea class="field sql-editor" name="pipeline" rows="8">${sample}</textarea></label><button class="button primary" data-action="de-validate" type="button">Validate</button><button class="button" data-action="de-preview" type="button">Preview</button><button class="button" data-action="de-pipelines" type="button">List pipelines</button><button class="button" data-action="de-revisions" type="button">List revisions</button><button class="button" data-action="de-compare" type="button">Compare revisions</button><button class="button" data-action="de-revision" type="button">Get revision</button><button class="button" data-action="de-run" type="button">Run pipeline</button><button class="button" data-action="de-run-inspect" type="button">Inspect run</button><button class="button" data-action="de-archive" type="button">Archive pipeline</button></form><pre id="de-pipeline-result" class="code" aria-live="polite">No pipeline operation requested.</pre></section>`;
}
document.addEventListener('click', async event => {
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (!action || !action.startsWith('de-')) return;
  const out = document.querySelector(action === 'de-health' || action === 'de-runtimes' ? '#de-health-result' : action.startsWith('de-sql-') ? '#de-sql-result' : '#de-pipeline-result');
  try {
    if (action === 'de-health') out.textContent = json(await get('/v1/data-engineering/health'));
    else if (action === 'de-sql-execute' || action === 'de-sql-export') { const data = new FormData(document.querySelector('#de-sql-form')); const workspace = encodeURIComponent(data.get('workspace')); const project = encodeURIComponent(data.get('project')); const result = await post(`/v1/workspaces/${workspace}/projects/${project}/sql/query`, { sql: data.get('sql'), max_rows: 1000, profile: data.get('profile'), translation_policy: data.get('translation_policy') }); if (action === 'de-sql-export') { const columns = (result.columns || []).map(column => typeof column === 'string' ? column : column.name); const rows = result.rows || []; out.textContent = [columns.join(','), ...rows.map(row => row.map(value => JSON.stringify(value ?? '')).join(','))].join('\n'); } else out.textContent = json(result); }
    else if (action === 'de-runtimes') out.textContent = json(await get('/v1/data-engineering/runtimes'));
    else if (action === 'de-run' || action === 'de-run-inspect') { const data = new FormData(document.querySelector('#de-pipeline-form')); const workspace = encodeURIComponent(data.get('workspace')); const project = encodeURIComponent(data.get('project')); const pipeline = encodeURIComponent(data.get('pipeline_id')); if (action === 'de-run') { const parameters = JSON.parse(data.get('pipeline')); const result = await post(`/v1/workspaces/${workspace}/projects/${project}/pipelines/${pipeline}/runs`, { revision_key: data.get('revision_key'), ir_digest: data.get('ir_digest'), runtime: data.get('runtime'), parameters: { pipeline: parameters } }); if (result.id) document.querySelector('[name="run_id"]').value = result.id; out.textContent = json(result); } else { const runId = String(data.get('run_id') || '').trim(); if (!runId) throw new Error('Enter a workflow run ID'); out.textContent = json(await get(`/v1/workspaces/${workspace}/workflow-runs/${encodeURIComponent(runId)}`)); } }
    else if (action === 'de-archive') { const data = new FormData(document.querySelector('#de-pipeline-form')); if (!confirm(`Archive pipeline ${data.get('pipeline_id')}?`)) return; out.textContent = json(await post(`/v1/workspaces/${encodeURIComponent(data.get('workspace'))}/projects/${encodeURIComponent(data.get('project'))}/pipelines/${encodeURIComponent(data.get('pipeline_id'))}/archive`, {})); }
    else if (action === 'de-pipelines' || action === 'de-revisions' || action === 'de-revision' || action === 'de-compare') { const data = new FormData(document.querySelector('#de-pipeline-form')); const projectBase = `/v1/workspaces/${encodeURIComponent(data.get('workspace'))}/projects/${encodeURIComponent(data.get('project'))}/pipelines`; const base = `${projectBase}/${encodeURIComponent(data.get('pipeline_id'))}/revisions`; const revision = String(data.get('revision') || ''); const compareRevision = String(data.get('compare_revision') || ''); if ((action === 'de-revision' && !revision) || (action === 'de-compare' && (!revision || !compareRevision))) throw new Error('Enter both revision numbers'); const compareUrl = `${base}/compare?left_revision=${encodeURIComponent(revision)}&right_revision=${encodeURIComponent(compareRevision)}`; out.textContent = json(await get(action === 'de-pipelines' ? projectBase : action === 'de-revision' ? `${base}/${encodeURIComponent(revision)}` : action === 'de-compare' ? compareUrl : base)); }
    else { const body = JSON.parse(new FormData(document.querySelector('#de-pipeline-form')).get('pipeline')); const result = await post(`/v1/data-engineering/pipelines/${action === 'de-validate' ? 'validate' : 'preview'}`, body); if (action === 'de-validate' && result.ir_digest) document.querySelector('[name="ir_digest"]').value = result.ir_digest; out.textContent = json(result); }
  } catch (error) { out.textContent = `Data Engineering operation failed: ${error.message}`; }
});
setTimeout(() => { window.addEventListener('hashchange', render); if (location.hash.slice(1) === 'data') render(); }, 0);

function addQueryTranslationPolicy() {
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
}
setTimeout(addQueryTranslationPolicy, 0);
window.addEventListener('hashchange', addQueryTranslationPolicy);
