import { del, get, post, put } from './api.js';
import { esc, json } from './dom.js';
import { confirmImpact } from './features.js';

const activeWorkspace = () => globalThis.roninStudioContext?.workspace || sessionStorage.getItem('ronin.workspace') || 'default';

function connectionPath(workspace, id = '') {
  const suffix = id ? `/${encodeURIComponent(id)}` : '';
  return `/v1/workspaces/${encodeURIComponent(workspace)}/connections${suffix}`;
}

function connectionState(item) {
  // ConnectionDefinition exposes metadata only. Lifecycle fields such as
  // `state: active` are not proof that the endpoint was verified.
  const raw = String(item?.verification_status || item?.health_status || item?.health || '').trim().toLowerCase();
  if (['healthy', 'ready'].includes(raw)) return 'Healthy';
  if (['degraded', 'warning', 'review'].includes(raw)) return 'Review';
  if (['disabled', 'unavailable', 'blocked'].includes(raw)) return 'Unavailable';
  return 'Unverified';
}

function secretPosture(item) {
  const refs = item?.secret_refs;
  if (refs && typeof refs === 'object' && Object.keys(refs).length) return 'Reference only';
  return 'Not declared';
}

function setMode(mode) {
  document.querySelectorAll('.connections-mode-card').forEach(button => {
    const active = button.dataset.connectionsMode === mode;
    button.setAttribute('aria-pressed', String(active));
  });
  const targets = { discover: '#connection-list', configure: '#connection-editor-form', govern: '#connection-result' };
  document.querySelector(targets[mode] || '#connection-list')?.scrollIntoView({ behavior: 'auto', block: 'start' });
}

function updateOverview(items, error = '') {
  const count = document.querySelector('#connection-count');
  const health = document.querySelector('#connection-health');
  const next = document.querySelector('#connection-next');
  if (!count || !health || !next) return;
  if (error) {
    count.textContent = 'Unknown';
    health.textContent = 'Review error';
    next.textContent = 'Retry lookup';
    return;
  }
  const states = items.map(connectionState);
  const healthy = states.filter(state => state === 'Healthy').length;
  count.textContent = String(items.length);
  health.textContent = items.length === 0 ? 'None configured' : healthy === items.length ? 'Healthy' : healthy ? 'Mixed' : 'Unverified';
  next.textContent = items.length === 0 ? 'Configure' : states.includes('Unverified') ? 'Review refs' : 'Use context';
}

function renderConnectionRows(items, workspace) {
  return items.length ? `<div class="table-wrap"><table><caption class="sr-only">Connections</caption><thead><tr><th>ID</th><th>Name</th><th>Connector</th><th>Secret posture</th><th>State</th><th>Actions</th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${esc(item.id)}</strong></td><td>${esc(item.name)}</td><td><code>${esc(item.connector_id)}</code></td><td><span class="connections-secret-posture">${esc(secretPosture(item))}</span></td><td>${esc(connectionState(item))}</td><td><button class="button" type="button" data-action="connection-edit" data-workspace="${esc(workspace)}" data-id="${esc(item.id)}">Edit</button><button class="button danger" type="button" data-action="connection-delete" data-workspace="${esc(workspace)}" data-id="${esc(item.id)}">Delete</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty"><h3>No connections configured</h3><p>Start with a connector and a secret reference. Ronin will keep credential material opaque.</p><button class="button primary" type="button" data-connections-mode="configure">Configure a connection</button></div>';
}
function renderConnectionOperation(output, action, data) {
  const item = data?.connection || data?.item || data;
  const id = item?.id || data?.id || 'connection';
  const name = item?.name || data?.name || id;
  const connector = item?.connector_id || data?.connector_id || 'connector';
  output.innerHTML = `<div class="connection-operation-summary"><strong>${esc(action)}: ${esc(name)}</strong><span>${esc(id)} · ${esc(connector)} · workspace-scoped</span><p>Secret material remains opaque; review the inventory before using this connection.</p></div><details class="connections-raw"><summary>Advanced: raw operation response</summary><pre class="code"></pre></details>`;
  output.querySelector('pre').textContent = json(data);
}

function addConnectionsPanel() {
  if (location.hash.slice(1) !== 'data') return;
  const view = document.querySelector('#view');
  if (!view || view.querySelector('#connections-studio')) return;
  const panel = document.createElement('section');
  panel.id = 'connections-studio';
  panel.className = 'panel connections-workbench';
  panel.innerHTML = `<header class="connections-hero"><div><p class="eyebrow">DATA / CONNECTIONS</p><h1>Connect data with a clear boundary.</h1><p>Discover what is configured, understand what Ronin can verify, then edit the smallest safe definition. Credential material never appears here.</p></div><div class="connections-hero-aside"><span class="connections-boundary">WORKSPACE-SCOPED · SECRET REFERENCES ONLY</span><p>Decision grammar: posture → reason → exact definition.</p></div></header>
    <div class="connections-mode-nav" role="group" aria-label="Connection workbench modes"><button class="connections-mode-card" type="button" aria-pressed="true" data-connections-mode="discover"><span class="connections-mode-index">01</span><strong>Discover</strong><span>See the inventory and its honest state.</span></button><button class="connections-mode-card" type="button" aria-pressed="false" data-connections-mode="configure"><span class="connections-mode-index">02</span><strong>Configure</strong><span>Author connector and secret-reference metadata.</span></button><button class="connections-mode-card" type="button" aria-pressed="false" data-connections-mode="govern"><span class="connections-mode-index">03</span><strong>Govern</strong><span>Review the exact response before using it.</span></button></div>
    <section id="connections-overview" class="connections-overview" aria-labelledby="connections-overview-title"><div class="connections-overview-heading"><div><p class="eyebrow">OPERATING BRIEF</p><h2 id="connections-overview-title">Know what is safe to use before you build.</h2><p>Counts come from the workspace-scoped inventory. Unknown means the API did not provide a verification claim.</p></div><span class="connections-scope">scope: workspace</span></div><div class="connections-overview-grid"><div class="connections-metric"><span>Visible connections</span><strong id="connection-count">Unknown</strong><small>returned by the current workspace</small></div><div class="connections-metric"><span>Verification posture</span><strong id="connection-health">Unknown</strong><small>no health is inferred from presence alone</small></div><div class="connections-metric"><span>Next gate</span><strong id="connection-next">Review lookup</strong><small>the smallest next action available</small></div></div></section>
    <section class="connections-inventory panel" aria-labelledby="connections-inventory-title"><div class="connections-section-heading"><div><p class="eyebrow">DISCOVER</p><h2 id="connections-inventory-title">Workspace inventory</h2><p class="muted">Only connection metadata is listed; secret values are never rendered.</p></div><form id="connection-list-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="${esc(activeWorkspace())}" required></label><button class="button" type="submit">Refresh connections</button></form></div><div id="connection-list" class="loading" aria-live="polite">Loading connections…</div></section>
    <section class="connections-editor panel" aria-labelledby="connection-editor-title"><div class="connections-section-heading"><div><p class="eyebrow">CONFIGURE</p><h2 id="connection-editor-title">Prepare a connection definition</h2><p class="muted">Use references, not credentials. Options remain portable metadata.</p></div><span class="connections-scope">write boundary: workspace</span></div><form id="connection-editor-form" class="stack"><input type="hidden" name="editing"><label>ID<input class="field" name="id" required></label><label>Name<input class="field" name="name" required></label><label>Connector ID<input class="field" name="connector_id" required placeholder="postgres"></label><label>Options JSON<textarea class="field" name="options" rows="3">{}</textarea></label><label>Secret refs JSON<textarea class="field" name="secret_refs" rows="3">{}</textarea></label><div class="toolbar"><button class="button primary">Save connection</button><button class="button" type="button" data-action="connection-clear">Clear</button></div></form></section>
    <section class="connections-evidence panel" aria-labelledby="connection-result-title"><div class="connections-section-heading"><div><p class="eyebrow">GOVERN</p><h2 id="connection-result-title">Exact operation response</h2><p class="muted">Raw JSON is secondary evidence for the action you just took.</p></div><span class="connections-scope">review before reuse</span></div><pre id="connection-result" class="code" aria-live="polite">No connection operation executed.</pre></section>`;
  view.append(panel);
  panel.querySelector('#connection-list-form')?.addEventListener('submit', refreshConnections);
  panel.querySelector('#connection-editor-form')?.addEventListener('submit', saveConnection);
  loadConnections();
}

async function loadConnections() {
  const form = document.querySelector('#connection-list-form');
  const result = document.querySelector('#connection-list');
  if (!form || !result) return;
  const workspace = String(new FormData(form).get('workspace') || '').trim();
  result.className = 'loading';
  result.textContent = 'Loading connections…';
  try {
    const payload = await get(connectionPath(workspace));
    const items = Array.isArray(payload) ? payload : payload.items || [];
    updateOverview(items);
    result.className = 'connections-list';
    result.innerHTML = renderConnectionRows(items, workspace);
  } catch (error) {
    updateOverview([], error);
    result.className = 'error';
    result.innerHTML = `<div class="error"><strong>Connection lookup failed.</strong><p>${esc(error.message)}</p><button class="button" type="button" data-action="connections-retry">Retry inventory</button></div>`;
  }
}

async function refreshConnections(event) {
  event.preventDefault();
  await loadConnections();
}

async function saveConnection(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const workspace = String(document.querySelector('#connection-list-form [name="workspace"]')?.value || '').trim();
  const output = document.querySelector('#connection-result');
  try {
    const id = String(data.get('id') || '').trim();
    const payload = { id, name: String(data.get('name') || '').trim(), connector_id: String(data.get('connector_id') || '').trim(), options: JSON.parse(String(data.get('options') || '{}')), secret_refs: JSON.parse(String(data.get('secret_refs') || '{}')) };
    const editing = String(data.get('editing') || '').trim();
    renderConnectionOperation(output, editing ? 'Updated connection' : 'Saved connection', editing ? await put(connectionPath(workspace, editing), payload) : await post(connectionPath(workspace), payload));
    form.reset();
    await loadConnections();
    setMode('discover');
  } catch (error) { output.textContent = `Connection save failed: ${error.message}`; }
}

document.addEventListener('click', async event => {
  if (event.target.closest?.('[data-action="connections-retry"]')) { await loadConnections(); return; }
  const mode = event.target.closest?.('[data-connections-mode]');
  if (mode) { setMode(mode.dataset.connectionsMode); return; }
  const button = event.target.closest?.('[data-action^="connection-"]');
  if (!button) return;
  const action = button.dataset.action;
  if (action === 'connection-clear') { document.querySelector('#connection-editor-form')?.reset(); return; }
  const workspace = button.dataset.workspace;
  const id = button.dataset.id;
  const output = document.querySelector('#connection-result');
  try {
    if (action === 'connection-edit') {
      const item = await get(connectionPath(workspace, id));
      const form = document.querySelector('#connection-editor-form');
      form.elements.editing.value = id; form.elements.id.value = item.id; form.elements.name.value = item.name; form.elements.connector_id.value = item.connector_id; form.elements.options.value = JSON.stringify(item.options || {}, null, 2); form.elements.secret_refs.value = JSON.stringify(item.secret_refs || {}, null, 2); output.textContent = `Editing ${id}`; setMode('configure'); return;
    }
    if (action === 'connection-delete') {
      if (!await confirmImpact(`Delete connection ${id} from workspace ${workspace}? This removes its definition; secret material is not recoverable from Ronin.`)) return;
      renderConnectionOperation(output, 'Deleted connection', await del(connectionPath(workspace, id), { body: '{}' })); await loadConnections(); setMode('govern');
    }
  } catch (error) { output.textContent = `Connection operation failed: ${error.message}`; }
});

window.addEventListener('hashchange', addConnectionsPanel);
const connectionsView = document.querySelector('#view');
if (connectionsView) new MutationObserver(addConnectionsPanel).observe(connectionsView, { childList: true });
setTimeout(addConnectionsPanel, 0);
