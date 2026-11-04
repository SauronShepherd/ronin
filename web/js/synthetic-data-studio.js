import {get as apiGet, post as apiPost} from './api.js';
import {esc, page} from './dom.js';

const workspace = () => sessionStorage.getItem('ronin.workspace') || 'workspace-1';
const scoped = (path) => path.includes('workspace_id=') ? path : `${path}${path.includes('?') ? '&' : '?'}workspace_id=${encodeURIComponent(workspace())}`;
const get = (path) => apiGet(scoped(path));
const post = (path, body) => apiPost(scoped(path), body);
let lastGeneration = null;
let renderRevision = 0;
let catalogRequestRevision = 0;

async function renderSyntheticDataStudio() {
  const revision = ++renderRevision;
  if (location.hash !== '#synthetic') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Synthetic Data Studio', 'DATA GOVERNANCE')}
    <div class="grid two">
      <section class="panel"><h2>Generate synthetic data</h2>
        <p class="muted">Generation runs against the configured local Ronin backend.</p>
        <form id="synthetic-studio-form">
          <label for="synthetic-studio-plan">Plan JSON</label>
          <textarea class="field sql-editor" id="synthetic-studio-plan" rows="14">{"tables":[{"name":"customers","rows":10,"primary_key":"id","columns":[{"name":"id","kind":"integer","nullable":false}]}],"seed":42}</textarea>
          <button class="button primary" type="submit">Generate</button>
        </form>
        <div id="synthetic-studio-export" hidden>
          <label for="synthetic-studio-table">Table</label><select class="field" id="synthetic-studio-table"></select>
          <label for="synthetic-studio-format">Format</label><select class="field" id="synthetic-studio-format"></select>
          <button class="button" id="synthetic-studio-export-button" type="button">Export</button>
        </div>
        <pre id="synthetic-studio-result" class="code" aria-live="polite">No run submitted.</pre>
      </section>
      <section class="panel"><h2>Local catalog</h2>
        <form id="synthetic-studio-catalog-search" class="inline-form"><label class="sr-only" for="synthetic-studio-search">Search catalog</label><input class="field" id="synthetic-studio-search" placeholder="Search assets, tags or classifications"/><button class="button" type="submit">Search</button></form>
        <div id="synthetic-studio-providers" class="loading">Loading catalog profiles…</div>
        <div id="synthetic-studio-assets" class="loading">Loading…</div>
        <h2>Recent runs</h2><div id="synthetic-studio-runs" class="loading">Loading…</div>
        <h2>Governance boundary</h2><p class="muted">Synthetic output is not automatically classified as anonymous or privacy-preserving.</p>
      </section>
    </div>`;
  const providersTarget = view.querySelector('#synthetic-studio-providers');
  const assetsTarget = view.querySelector('#synthetic-studio-assets');
  const runsTarget = view.querySelector('#synthetic-studio-runs');
  const isCurrent = () => revision === renderRevision && location.hash === '#synthetic' && view === document.querySelector('#view');
  try {
    const providers = await get('/v1/synthetic-data-studio/catalog/providers');
    if (!isCurrent()) return;
    providersTarget.innerHTML = `<p class="muted">Mode: ${esc(providers.mode)} · external connections: ${providers.external_connections ? 'enabled' : 'disabled'}</p>` +
      (providers.items || []).map((item) => `<span class="tag">${esc(item.display_name)}</span> `).join('');
  } catch (error) {
    if (!isCurrent()) return;
    providersTarget.innerHTML = `<p class="muted">Catalog profiles unavailable: ${esc(error.message)}</p>`;
  }
  try {
    await loadCatalogAssets('', revision, view);
  } catch (error) {
    if (!isCurrent()) return;
    assetsTarget.innerHTML = `<p class="muted">Catalog unavailable: ${esc(error.message)}</p>`;
  }
  if (!isCurrent()) return;
  view.querySelector('#synthetic-studio-catalog-search').addEventListener('submit', async (event) => {
    event.preventDefault();
    await loadCatalogAssets(view.querySelector('#synthetic-studio-search').value, revision, view);
  });
  try {
    const runs = await get('/v1/synthetic-data-studio/runs');
    if (!isCurrent()) return;
    runsTarget.innerHTML = (runs.items || []).map((run) =>
      `<p><strong>${esc(run.run_id)}</strong><br><span class="muted">${esc(run.status)}</span></p>`
    ).join('') || '<p class="muted">No runs yet.</p>';
  } catch (error) {
    if (!isCurrent()) return;
    runsTarget.innerHTML = `<p class="muted">Runs unavailable: ${esc(error.message)}</p>`;
  }
  if (!isCurrent()) return;
  view.querySelector('#synthetic-studio-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = view.querySelector('#synthetic-studio-result');
    try {
      const plan = JSON.parse(view.querySelector('#synthetic-studio-plan').value);
      const generation = await post('/v1/synthetic-data-studio/generate', {plan});
      if (!isCurrent() || !output.isConnected) return;
      lastGeneration = generation;
      output.textContent = JSON.stringify(lastGeneration, null, 2);
      await prepareExport(lastGeneration, isCurrent);
    } catch (error) {
      if (!isCurrent() || !output.isConnected) return;
      output.textContent = `Generation failed: ${error.message}`;
    }
  });
}

async function prepareExport(generation, isCurrent) {
  const tables = (generation.tables || []).map((table) => table.name);
  const tableSelect = document.querySelector('#synthetic-studio-table');
  const formatSelect = document.querySelector('#synthetic-studio-format');
  const panel = document.querySelector('#synthetic-studio-export');
  if (!generation.run_id || !tables.length || !tableSelect || !formatSelect || !panel || !isCurrent()) return;
  tableSelect.innerHTML = tables.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join('');
  const formats = await get('/v1/synthetic-data-studio/formats');
  if (!isCurrent() || !tableSelect.isConnected || !formatSelect.isConnected || !panel.isConnected) return;
  // The plugin contract uses `ready`/`optional_missing`; never expose an
  // optional table provider as writable until its dependency is installed.
  const available = (formats || []).filter((item) => item.status === 'ready');
  formatSelect.innerHTML = available.map((item) => `<option value="${esc(item.format_id)}">${esc(item.format_id)}</option>`).join('');
  panel.hidden = !available.length;
}

document.addEventListener('click', async (event) => {
  if (!(event.target instanceof Element) || !event.target.closest('#synthetic-studio-export-button') || !lastGeneration || location.hash !== '#synthetic') return;
  const output = document.querySelector('#synthetic-studio-result');
  const tableSelect = document.querySelector('#synthetic-studio-table');
  const formatSelect = document.querySelector('#synthetic-studio-format');
  if (!output || !tableSelect || !formatSelect) return;
  try {
    const content = await post('/v1/synthetic-data-studio/export', {
      run_id: lastGeneration.run_id,
      table: tableSelect.value,
      format_id: formatSelect.value,
    });
    if (!output.isConnected || location.hash !== '#synthetic') return;
    output.textContent = JSON.stringify(content, null, 2);
  } catch (error) {
    if (!output.isConnected || location.hash !== '#synthetic') return;
    output.textContent = `Export failed: ${error.message}`;
  }
});

async function loadCatalogAssets(search = '', renderGeneration = renderRevision, view = document.querySelector('#view')) {
  const requestRevision = ++catalogRequestRevision;
  const target = view?.querySelector('#synthetic-studio-assets');
  const isCurrent = () => renderGeneration === renderRevision && requestRevision === catalogRequestRevision && location.hash === '#synthetic' && Boolean(target?.isConnected);
  if (!target || !isCurrent()) return;
  const params = new URLSearchParams({workspace_id: workspace()});
  if (search.trim()) params.set('search', search.trim());
  try {
    const data = await get(`/v1/synthetic-data-studio/catalog/assets?${params}`);
    if (!isCurrent()) return;
    target.innerHTML = (data.items || []).map((asset) =>
      `<p><strong>${esc(asset.name)}</strong><br><span class="muted">${esc(asset.id)}</span><br><button class="button" data-sds-lineage="${esc(asset.id)}">View lineage</button> <button class="button" data-sds-revisions="${esc(asset.id)}">Versions</button></p>`
    ).join('') || '<p class="muted">No matching assets visible.</p>';
  } catch (error) {
    if (!isCurrent()) return;
    target.innerHTML = `<p class="muted">Catalog unavailable: ${esc(error.message)}</p>`;
  }
}

document.addEventListener('click', async (event) => {
  if (!(event.target instanceof Element) || location.hash !== '#synthetic') return;
  const button = event.target.closest('[data-sds-lineage]');
  const revisions = event.target.closest('[data-sds-revisions]');
  if (!button && !revisions) return;
  const output = document.querySelector('#synthetic-studio-result');
  try {
    const assetId = button?.dataset.sdsLineage || revisions.dataset.sdsRevisions;
    const endpoint = button
      ? `/v1/synthetic-data-studio/catalog/assets/${encodeURIComponent(assetId)}/lineage?workspace_id=${encodeURIComponent(workspace())}&version=1`
      : `/v1/synthetic-data-studio/catalog/assets/${encodeURIComponent(assetId)}/revisions?workspace_id=${encodeURIComponent(workspace())}`;
    const data = await get(endpoint);
    if (!output?.isConnected || location.hash !== '#synthetic') return;
    output.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    if (!output?.isConnected || location.hash !== '#synthetic') return;
    output.textContent = `Lineage unavailable: ${error.message}`;
  }
});

window.addEventListener('hashchange', renderSyntheticDataStudio);
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => setTimeout(renderSyntheticDataStudio, 0), {once: true});
} else if (location.hash === '#synthetic') {
  setTimeout(renderSyntheticDataStudio, 0);
}
