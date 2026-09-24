import { get, post } from './api.js';
import { json, page } from './dom.js';

const sample = '{"runtime":"local-preview","pipeline":{"nodes":[],"edges":[]}}';
const pipelineHistory = [];
let pipelineHistoryIndex = -1;
function pipelineDocument() {
  const field = document.querySelector('#de-pipeline-form [name="pipeline"]');
  if (!field) throw new Error('Pipeline editor is not available');
  const documentValue = JSON.parse(field.value);
  if (!documentValue.pipeline || !Array.isArray(documentValue.pipeline.nodes) || !Array.isArray(documentValue.pipeline.edges)) throw new Error('Pipeline JSON must contain pipeline.nodes and pipeline.edges');
  return { field, documentValue };
}
function recordPipelineHistory() {
  const { field } = pipelineDocument();
  pipelineHistory.splice(pipelineHistoryIndex + 1);
  pipelineHistory.push(field.value);
  pipelineHistoryIndex = pipelineHistory.length - 1;
}
function renderPipelineEditor() {
  const out = document.querySelector('#de-pipeline-visual-result');
  if (!out) return;
  try {
    const { documentValue } = pipelineDocument();
    const nodes = documentValue.pipeline.nodes;
    const edges = documentValue.pipeline.edges;
    out.innerHTML = `<strong>${nodes.length} node(s), ${edges.length} edge(s)</strong><div class="toolbar">${nodes.map(node => `<button class="button" type="button" data-action="de-node-remove" data-node-id="${node.id}">Remove ${node.id}</button>`).join(' ') || '<span class="muted">No nodes yet.</span>'}</div><pre class="code">${json({ nodes, edges })}</pre>`;
  } catch (error) { out.textContent = `Visual editor error: ${error.message}`; }
}
function addPipelineEditor() {
  const view = document.querySelector('#view');
  if (!view || !view.querySelector('#de-pipeline-form') || view.querySelector('#de-pipeline-visual')) return;
  const panel = document.createElement('section');
  panel.id = 'de-pipeline-visual';
  panel.className = 'panel';
  panel.innerHTML = '<h2>Pipeline visual editor</h2><p class="muted">Edit nodes and typed edges while keeping the canonical JSON representation synchronized.</p><div class="grid three"><label>Node ID<input class="field" id="de-node-id" value="node-1"></label><label>Node operator<input class="field" id="de-node-operator" value="source"></label><label>Node port<input class="field" id="de-node-port" value="out"></label></div><div class="grid three"><label>From node<select class="field" id="de-edge-from"></select></label><label>To node<select class="field" id="de-edge-to"></select></label><label>To port<input class="field" id="de-edge-port" value="in"></label></div><div class="toolbar"><button class="button" type="button" data-action="de-node-add">Add node</button><button class="button" type="button" data-action="de-edge-connect">Connect nodes</button><button class="button" type="button" data-action="de-edge-disconnect">Disconnect nodes</button><button class="button" type="button" data-action="de-visual-undo">Undo</button><button class="button" type="button" data-action="de-visual-redo">Redo</button><button class="button primary" type="button" data-action="de-save-revision">Save revision</button></div><div id="de-pipeline-visual-result" class="code" aria-live="polite">No visual edit requested.</div>';
  view.append(panel);
  recordPipelineHistory();
  renderPipelineEditor();
  refreshPipelineEdgeSelectors();
}
function base64(value) { const bytes = new TextEncoder().encode(value); let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte); return btoa(binary); }
function showPipelineRunEvidence(out, runId, data) {
  out.textContent = '';
  const heading = document.createElement('strong');
  heading.textContent = `Pipeline run ${runId}: ${data.state || data.status || 'unknown'}`;
  const evidence = document.createElement('p');
  evidence.textContent = `Evidence: ${data.evidence_digest || data.evidence?.digest || 'not available yet'} · Lineage: ${data.lineage_id || data.lineage?.id || 'not available yet'}`;
  const details = document.createElement('pre');
  details.className = 'code';
  details.textContent = json(data);
  out.append(heading, evidence, details);
}
function refreshPipelineEdgeSelectors() {
  const { documentValue } = pipelineDocument();
  for (const id of ['#de-edge-from', '#de-edge-to']) { const select = document.querySelector(id); if (select) select.innerHTML = documentValue.pipeline.nodes.map(node => `<option value="${node.id}">${node.id}</option>`).join(''); }
}
function createsCycle(edges, source, target) {
  const next = new Map();
  for (const edge of edges) { if (!next.has(edge.source)) next.set(edge.source, []); next.get(edge.source).push(edge.target); }
  if (!next.has(source)) next.set(source, []);
  next.get(source).push(target);
  const seen = new Set();
  const visiting = new Set();
  function visit(node) { if (visiting.has(node)) return true; if (seen.has(node)) return false; visiting.add(node); for (const child of next.get(node) || []) if (visit(child)) return true; visiting.delete(node); seen.add(node); return false; }
  return [...next.keys()].some(visit);
}
function render() {
  if (location.hash.slice(1) !== 'data') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Data Engineering', 'PIPELINES')}<section class="panel"><div class="toolbar"><button class="button" data-action="de-health">Health</button><button class="button" data-action="de-runtimes">Runtimes</button></div><pre id="de-health-result" class="code">No health check requested.</pre></section><section class="panel"><h2>SQL editor</h2><form id="de-sql-form"><div class="grid three"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Project<input class="field" name="project" value="examples/demo" required></label><label>Profile<select class="field" name="profile"><option value="local">Local</option><option value="queryflux">QueryFlux</option></select></label></div><label>SQL<textarea class="field sql-editor" name="sql" rows="6" required>SELECT 1 AS value</textarea><button class="button primary" data-action="de-sql-execute" type="button">Execute bounded query</button><button class="button" data-action="de-sql-export" type="button">Export CSV</button></form><pre id="de-sql-result" class="code" aria-live="polite">No SQL operation requested.</pre></section><section class="panel"><form id="de-pipeline-form"><div class="grid three"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Project<input class="field" name="project" value="examples/demo" required></label><label>Pipeline<input class="field" name="pipeline_id" value="main" required></label><label>Revision<input class="field" name="revision" type="number" min="1"></label><label>Compare revision<input class="field" name="compare_revision" type="number" min="1"></label><label>Revision key<input class="field" name="revision_key" value="main/working"></label><label>IR digest<input class="field" name="ir_digest" minlength="64" maxlength="64"></label><label>Runtime<input class="field" name="runtime" value="local-preview"></label><label>Run ID<input class="field" name="run_id"></label></div><label>Pipeline JSON<textarea class="field sql-editor" name="pipeline" rows="8">${sample}</textarea></label><button class="button primary" data-action="de-validate" type="button">Validate</button><button class="button" data-action="de-preview" type="button">Preview</button><button class="button" data-action="de-pipelines" type="button">List pipelines</button><button class="button" data-action="de-revisions" type="button">List revisions</button><button class="button" data-action="de-compare" type="button">Compare revisions</button><button class="button" data-action="de-revision" type="button">Get revision</button><button class="button" data-action="de-run" type="button">Run pipeline</button><button class="button" data-action="de-run-inspect" type="button">Inspect run</button><button class="button" data-action="de-archive" type="button">Archive pipeline</button></form><pre id="de-pipeline-result" class="code" aria-live="polite">No pipeline operation requested.</pre></section>`;
}
document.addEventListener('click', async event => {
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (!action || !action.startsWith('de-')) return;
  if (action === 'de-save-revision') {
    const out = document.querySelector('#de-pipeline-visual-result');
    try {
      const { documentValue } = pipelineDocument();
      const data = new FormData(document.querySelector('#de-pipeline-form'));
      const project = String(data.get('project')).trim();
      const pipelineId = String(data.get('pipeline_id')).trim();
      if (!project || !pipelineId) throw new Error('Project and pipeline ID are required');
      const result = await post(`/v1/workspaces/${encodeURIComponent(data.get('workspace'))}/projects/${encodeURIComponent(project)}/pipelines/${encodeURIComponent(pipelineId)}/revisions`, { project_name: project, project_yaml_base64: base64(`name: ${project}\n`), pipeline_documents: [{ name: `${pipelineId}.json`, content_base64: base64(JSON.stringify(documentValue)) }], expected_revision: Number(data.get('revision') || 0) });
      if (result.revision) document.querySelector('[name="revision"]').value = result.revision;
      out.textContent = json(result);
    } catch (error) { out.textContent = `Pipeline revision save failed: ${error.message}`; }
    return;
  }
  if (['de-node-add', 'de-edge-connect', 'de-edge-disconnect', 'de-node-remove', 'de-visual-undo', 'de-visual-redo'].includes(action)) {
    try {
      const { field, documentValue } = pipelineDocument();
      if (action === 'de-visual-undo' || action === 'de-visual-redo') {
        const next = pipelineHistoryIndex + (action === 'de-visual-undo' ? -1 : 1);
        if (next < 0 || next >= pipelineHistory.length) throw new Error('No visual edit available');
        pipelineHistoryIndex = next;
        field.value = pipelineHistory[pipelineHistoryIndex];
      } else if (action === 'de-node-add') {
        const id = document.querySelector('#de-node-id').value.trim();
        const operator = document.querySelector('#de-node-operator').value.trim();
        const port = document.querySelector('#de-node-port').value.trim();
        if (!id || !operator || !port) throw new Error('Node ID, operator and port are required');
        if (documentValue.pipeline.nodes.some(node => node.id === id)) throw new Error(`Node already exists: ${id}`);
        documentValue.pipeline.nodes.push({ id, operator: { name: operator }, ports: [{ name: port, direction: 'output' }, { name: 'in', direction: 'input' }] });
        field.value = JSON.stringify(documentValue);
      } else if (action === 'de-node-remove') {
        const id = event.target.closest('[data-node-id]').dataset.nodeId;
        documentValue.pipeline.nodes = documentValue.pipeline.nodes.filter(node => node.id !== id);
        documentValue.pipeline.edges = documentValue.pipeline.edges.filter(edge => edge.from?.node !== id && edge.to?.node !== id && edge.source !== id && edge.target !== id);
        field.value = JSON.stringify(documentValue);
      } else if (action === 'de-edge-disconnect') {
        const from = document.querySelector('#de-edge-from').value;
        const to = document.querySelector('#de-edge-to').value;
        const port = document.querySelector('#de-edge-port').value.trim();
        const remaining = documentValue.pipeline.edges.filter(edge => !(edge.source === from && edge.target === to && (!port || edge.target_port === port)));
        if (remaining.length === documentValue.pipeline.edges.length) throw new Error('Connection does not exist');
        documentValue.pipeline.edges = remaining;
        field.value = JSON.stringify(documentValue);
      } else {
        const from = document.querySelector('#de-edge-from').value;
        const to = document.querySelector('#de-edge-to').value;
        const port = document.querySelector('#de-edge-port').value.trim();
        if (!from || !to || !port || from === to) throw new Error('Choose two distinct nodes and a target port');
        const targetNode = documentValue.pipeline.nodes.find(node => node.id === to);
        if (!targetNode?.ports?.some(candidate => candidate.name === port && candidate.direction === 'input')) throw new Error(`Target port does not exist: ${to}.${port}`);
        if (documentValue.pipeline.edges.some(edge => edge.source === from && edge.target === to && edge.target_port === port)) throw new Error('Edge already exists');
        if (createsCycle(documentValue.pipeline.edges, from, to)) throw new Error('Connection would create a pipeline cycle');
        documentValue.pipeline.edges.push({ source: from, source_port: 'out', target: to, target_port: port });
        field.value = JSON.stringify(documentValue);
      }
      if (action !== 'de-visual-undo' && action !== 'de-visual-redo') recordPipelineHistory();
      renderPipelineEditor();
      refreshPipelineEdgeSelectors();
    } catch (error) { document.querySelector('#de-pipeline-visual-result').textContent = `Visual editor error: ${error.message}`; }
    return;
  }
  const out = document.querySelector(action === 'de-health' || action === 'de-runtimes' ? '#de-health-result' : action.startsWith('de-sql-') ? '#de-sql-result' : '#de-pipeline-result');
  try {
    if (action === 'de-queryflux-capabilities') {
      const result = document.querySelector('#de-queryflux-result');
      result.textContent = json(await get('/v1/data-engineering/queryflux/capabilities'));
      return;
    }
    if (action === 'de-health') out.textContent = json(await get('/v1/data-engineering/health'));
    else if (action === 'de-sql-execute' || action === 'de-sql-export') { const data = new FormData(document.querySelector('#de-sql-form')); const workspace = encodeURIComponent(data.get('workspace')); const project = encodeURIComponent(data.get('project')); const result = await post(`/v1/workspaces/${workspace}/projects/${project}/sql/query`, { sql: data.get('sql'), max_rows: 1000, profile: data.get('profile'), translation_policy: data.get('translation_policy') }); if (action === 'de-sql-export') { const columns = (result.columns || []).map(column => typeof column === 'string' ? column : column.name); const rows = result.rows || []; out.textContent = [columns.join(','), ...rows.map(row => row.map(value => JSON.stringify(value ?? '')).join(','))].join('\n'); } else out.textContent = json(result); }
    else if (action === 'de-runtimes') out.textContent = json(await get('/v1/data-engineering/runtimes'));
    else if (action === 'de-run' || action === 'de-run-inspect') { const data = new FormData(document.querySelector('#de-pipeline-form')); const workspace = encodeURIComponent(data.get('workspace')); const project = encodeURIComponent(data.get('project')); const pipeline = encodeURIComponent(data.get('pipeline_id')); if (action === 'de-run') { const parameters = JSON.parse(data.get('pipeline')); const result = await post(`/v1/workspaces/${workspace}/projects/${project}/pipelines/${pipeline}/runs`, { revision_key: data.get('revision_key'), ir_digest: data.get('ir_digest'), runtime: data.get('runtime'), parameters: { pipeline: parameters } }); if (result.id) document.querySelector('[name="run_id"]').value = result.id; out.textContent = json(result); } else { const runId = String(data.get('run_id') || '').trim(); if (!runId) throw new Error('Enter a workflow run ID'); showPipelineRunEvidence(out, runId, await get(`/v1/workspaces/${workspace}/workflow-runs/${encodeURIComponent(runId)}`)); } }
    else if (action === 'de-archive') { const data = new FormData(document.querySelector('#de-pipeline-form')); if (!confirm(`Archive pipeline ${data.get('pipeline_id')}?`)) return; out.textContent = json(await post(`/v1/workspaces/${encodeURIComponent(data.get('workspace'))}/projects/${encodeURIComponent(data.get('project'))}/pipelines/${encodeURIComponent(data.get('pipeline_id'))}/archive`, {})); }
    else if (action === 'de-pipelines' || action === 'de-revisions' || action === 'de-revision' || action === 'de-compare') { const data = new FormData(document.querySelector('#de-pipeline-form')); const projectBase = `/v1/workspaces/${encodeURIComponent(data.get('workspace'))}/projects/${encodeURIComponent(data.get('project'))}/pipelines`; const base = `${projectBase}/${encodeURIComponent(data.get('pipeline_id'))}/revisions`; const revision = String(data.get('revision') || ''); const compareRevision = String(data.get('compare_revision') || ''); if ((action === 'de-revision' && !revision) || (action === 'de-compare' && (!revision || !compareRevision))) throw new Error('Enter both revision numbers'); const compareUrl = `${base}/compare?left_revision=${encodeURIComponent(revision)}&right_revision=${encodeURIComponent(compareRevision)}`; out.textContent = json(await get(action === 'de-pipelines' ? projectBase : action === 'de-revision' ? `${base}/${encodeURIComponent(revision)}` : action === 'de-compare' ? compareUrl : base)); }
    else { const body = JSON.parse(new FormData(document.querySelector('#de-pipeline-form')).get('pipeline')); const result = await post(`/v1/data-engineering/pipelines/${action === 'de-validate' ? 'validate' : 'preview'}`, body); if (action === 'de-validate' && result.ir_digest) document.querySelector('[name="ir_digest"]').value = result.ir_digest; out.textContent = json(result); }
  } catch (error) { out.textContent = `Data Engineering operation failed: ${error.message}`; }
});
setTimeout(() => { window.addEventListener('hashchange', render); if (location.hash.slice(1) === 'data') { render(); addPipelineEditor(); } }, 0);

function addQueryFluxPanel() {
  const view = document.querySelector('#view');
  if (!view || view.querySelector('#de-queryflux-result')) return;
  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.innerHTML = '<h2>QueryFlux</h2><p class="muted">Provider-neutral query routing evidence; raw cluster configuration is intentionally hidden.</p><div class="toolbar"><button class="button" data-action="de-queryflux-capabilities">Inspect capabilities</button></div><pre id="de-queryflux-result" class="code" aria-live="polite">No QueryFlux capability check requested.</pre>';
  view.prepend(panel);
}

setTimeout(addQueryFluxPanel, 0);
window.addEventListener('hashchange', addQueryFluxPanel);

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
window.addEventListener('hashchange', addPipelineEditor);
document.addEventListener('keydown', event => {
  if (location.hash.slice(1) !== 'data' || !document.querySelector('#de-pipeline-visual')) return;
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target.isContentEditable) return;
  if (!(event.ctrlKey || event.metaKey)) return;
  if (event.key.toLowerCase() === 'z') {
    event.preventDefault();
    document.querySelector(`[data-action="de-visual-${event.shiftKey ? 'redo' : 'undo'}"]`)?.click();
  } else if (event.key.toLowerCase() === 'y') {
    event.preventDefault();
    document.querySelector('[data-action="de-visual-redo"]')?.click();
  }
});
