import { get, post } from './api.js';
import { esc, json, page } from './dom.js';

let catalogPageCursor = null;
let catalogPreviousCursors = [];

function valuesOf(value) {
  if (!Array.isArray(value)) return [];
  return value.map(item => {
    if (typeof item === 'string') return item;
    if (item && typeof item === 'object') return item.name || item.id || item.value || '';
    return String(item ?? '');
  }).filter(Boolean);
}

function pills(value, empty = 'None assigned') {
  const values = valuesOf(value);
  return values.length
    ? `<div class="catalog-pills">${values.map(item => `<span class="catalog-pill">${esc(item)}</span>`).join('')}</div>`
    : `<span class="catalog-muted">${esc(empty)}</span>`;
}

function catalogAssetId(item) {
  return String(item?.id || item?.asset_id || item?.name || '').trim();
}

function assetTable(items) {
  return `<div class="table-wrap catalog-table-wrap"><table class="catalog-table"><caption class="sr-only">Governed catalog assets</caption><thead><tr><th>Asset</th><th>Kind</th><th>Tags</th><th>Classification</th><th>Action</th></tr></thead><tbody>${items.map(item => {
    const id = catalogAssetId(item);
    const name = item.name || id || 'Unnamed asset';
    return `<tr><td><button class="catalog-asset-link" type="button" data-action="catalog-select-asset" data-asset-id="${esc(id)}"><strong>${esc(name)}</strong></button><span class="catalog-subline">${esc(id || 'Identity not published')}</span></td><td><span class="catalog-kind">${esc(item.kind || 'asset')}</span></td><td>${pills(item.tags)}</td><td>${pills(item.classifications)}</td><td><button class="button" type="button" data-action="catalog-select-asset" data-asset-id="${esc(id)}">Inspect lineage</button></td></tr>`;
  }).join('')}</tbody></table></div>`;
}

function lineageView(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) return '<div class="catalog-empty"><strong>No lineage edges returned.</strong><span>The asset is governed, but this direction has no published relationship.</span></div>';
  return `<div class="catalog-lineage-map" aria-label="Lineage relationships">${items.map(edge => {
    const source = edge.source || {};
    const target = edge.target || {};
    const sourceId = source.asset_id || source.id || 'source';
    const targetId = target.asset_id || target.id || 'target';
    return `<article class="catalog-lineage-edge"><div class="catalog-lineage-node"><span class="eyebrow">SOURCE</span><strong>${esc(sourceId)}</strong><span class="catalog-subline">${esc(source.version || 'unversioned')}</span></div><span class="catalog-lineage-arrow" aria-hidden="true">→</span><div class="catalog-lineage-node"><span class="eyebrow">TARGET</span><strong>${esc(targetId)}</strong><span class="catalog-subline">${esc(target.version || 'unversioned')}</span></div><div class="catalog-lineage-meta"><span>${esc(edge.operation || 'derived')}</span><span>${esc(edge.mode || 'observed')}</span>${edge.execution_ref ? `<span>Run ${esc(edge.execution_ref)}</span>` : ''}</div></article>`;
  }).join('')}</div><details class="catalog-raw"><summary>View raw lineage response</summary><pre class="code">${esc(json(payload))}</pre></details>`;
}

function glossaryView(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) return '<div class="catalog-empty"><strong>No glossary terms found.</strong><span>Publish a term to give teams a shared vocabulary.</span></div>';
  return `<div class="table-wrap catalog-table-wrap"><table class="catalog-table glossary-table"><caption class="sr-only">Published glossary terms</caption><thead><tr><th>Term</th><th>Definition</th><th>Owner</th><th>References</th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${esc(item.name || item.id || 'Unnamed term')}</strong><span class="catalog-subline">v${esc(item.version || '1')} · ${esc(item.id || '')}</span></td><td>${esc(item.definition || 'No definition published')}</td><td>${esc(item.owner || 'Unassigned')}</td><td>${pills(item.references, 'No references')}</td></tr>`).join('')}</tbody></table></div>`;
}

function render() {
  if (location.hash.slice(1) !== 'catalog') return;
  catalogPageCursor = null;
  catalogPreviousCursors = [];
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Catalog', 'GOVERNANCE')}<section class="catalog-hero panel"><div><p class="eyebrow">GOVERNED DATA</p><h2>Find the trusted source before you build.</h2><p>Search approved assets, inspect their lineage and give teams a shared vocabulary without leaving the operating context.</p></div><div class="catalog-hero-signals"><span class="status blue">Workspace scoped</span><span class="status green">Evidence linked</span><span class="catalog-hero-note">Search results never cross workspace boundaries.</span></div></section><div class="catalog-workbench"><section class="panel catalog-assets-panel"><div class="catalog-section-heading"><div><p class="eyebrow">DISCOVERY</p><h2>Asset registry</h2><p class="muted">Search by asset, tag or classification. Select an asset to inspect its graph.</p></div><span class="catalog-section-index">01</span></div><form id="catalog-search-form" class="toolbar catalog-search-form"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Search<input class="field" name="query" placeholder="asset, tag or classification"></label><button class="button primary" type="submit">Search catalog</button></form><div id="catalog-result" class="loading" aria-live="polite">Enter a workspace and search.</div></section><aside class="panel catalog-insight"><p class="eyebrow">OPERATING NOTE</p><h2>Context travels with the asset.</h2><p>Lineage responses keep source, target, version and execution reference visible so a catalog result can lead to a reviewable run.</p><div id="catalog-insight-state" class="catalog-insight-state"><span class="catalog-insight-mark">↗</span><span>Select an asset to prepare a lineage review.</span></div></aside></div><section class="panel catalog-lineage-panel"><div class="catalog-section-heading"><div><p class="eyebrow">PROVENANCE</p><h2>Lineage review</h2><p class="muted">Move upstream to understand origin or downstream to see impact.</p></div><span class="catalog-section-index">02</span></div><form id="catalog-lineage-form" class="toolbar catalog-lineage-form"><label>Asset ID<input class="field" name="asset_id" required placeholder="curated-orders"></label><label>Version<input class="field" name="version" value="1" required></label><label>Direction<select class="field" name="direction"><option value="upstream">Upstream</option><option value="downstream">Downstream</option></select></label><button class="button" type="submit">Inspect lineage</button></form><div id="catalog-lineage-result" class="catalog-lineage-result" aria-live="polite"><div class="catalog-empty"><strong>No lineage query executed.</strong><span>Select an asset above or from the registry.</span></div></div></section><section class="panel catalog-glossary-panel"><div class="catalog-section-heading"><div><p class="eyebrow">SHARED LANGUAGE</p><h2>Glossary</h2><p class="muted">Publish definitions once and make them discoverable across projects.</p></div><span class="catalog-section-index">03</span></div><div class="catalog-glossary-grid"><form id="glossary-form" class="stack"><div class="catalog-form-heading"><strong>Publish a term</strong><span>Idempotent and workspace scoped</span></div><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Term ID<input class="field" name="id" placeholder="customer" required></label><div class="grid two"><label>Version<input class="field" name="version" value="1" required></label><label>Owner<input class="field" name="owner" required></label></div><label>Name<input class="field" name="name" required></label><label>Definition<textarea class="field" name="definition" required></textarea></label><label>References<input class="field" name="references" placeholder="catalog:customer"></label><button class="button primary" type="submit">Publish term</button></form><div class="catalog-terms-column"><form id="glossary-search-form" class="toolbar"><label>Search terms<input class="field" name="query" placeholder="name, owner or definition"></label><button class="button" type="submit">Load terms</button></form><div id="glossary-result" class="catalog-result" aria-live="polite"><div class="catalog-empty"><strong>No glossary search yet.</strong><span>Load the shared language for this workspace.</span></div></div></div></div></section>`;
}

async function showCatalogPage(form, cursor = null) {
  const result = document.querySelector('#catalog-result');
  if (!result) return false;
  const workspace = encodeURIComponent(form.elements.workspace.value.trim());
  const query = form.elements.query.value.trim();
  const params = new URLSearchParams({ limit: '50' });
  if (query) params.set('q', query);
  if (cursor) params.set('cursor', cursor);
  result.className = 'loading catalog-result';
  result.textContent = 'Loading governed assets…';
  try {
    const payload = await get(`/v1/workspaces/${workspace}/catalog/assets?${params}`);
    const items = Array.isArray(payload.items) ? payload.items : [];
    const previous = catalogPreviousCursors.length ? '<button class="button" type="button" data-action="catalog-previous">Previous page</button>' : '';
    const next = typeof payload.next_cursor === 'string' && payload.next_cursor ? `<button class="button" type="button" data-action="catalog-next" data-cursor="${esc(payload.next_cursor)}">Next page</button>` : '';
    result.className = 'catalog-result';
    result.innerHTML = `<div class="catalog-result-summary"><strong>${items.length}</strong><span>assets visible in <code>${esc(form.elements.workspace.value.trim())}</code>${query ? ` matching <code>${esc(query)}</code>` : ''}</span></div>${items.length ? assetTable(items) : '<div class="catalog-empty"><strong>No governed assets matched the query.</strong><span>Try a broader term or check the workspace context.</span></div>'}${previous || next ? `<div class="toolbar catalog-pagination">${previous}${next}</div>` : ''}`;
    catalogPageCursor = cursor;
    return true;
  } catch (error) {
    result.className = 'catalog-result';
    result.innerHTML = `<div class="error"><strong>Catalog lookup failed.</strong><span>${esc(error.message)}</span><button class="button" type="button" data-action="catalog-retry">Retry this search</button></div>`;
    return false;
  }
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'catalog-search-form') return;
  event.preventDefault();
  catalogPageCursor = null;
  catalogPreviousCursors = [];
  await showCatalogPage(form);
});

document.addEventListener('click', async event => {
  const retry = event.target.closest('[data-action="catalog-retry"]');
  if (retry) {
    const form = document.querySelector('#catalog-search-form');
    if (form) await showCatalogPage(form);
    return;
  }
  const assetButton = event.target.closest('[data-action="catalog-select-asset"]');
  if (assetButton) {
    const assetId = assetButton.dataset.assetId || '';
    const field = document.querySelector('#catalog-lineage-form [name="asset_id"]');
    const insight = document.querySelector('#catalog-insight-state');
    if (field) { field.value = assetId; field.focus(); }
    if (insight) insight.innerHTML = `<span class="catalog-insight-mark">✓</span><span><strong>${esc(assetId)}</strong> is ready for lineage review.</span>`;
    return;
  }
  const button = event.target.closest('[data-action="catalog-next"], [data-action="catalog-previous"]');
  if (!button) return;
  const form = document.querySelector('#catalog-search-form');
  if (!form) return;
  button.disabled = true;
  if (button.dataset.action === 'catalog-next') {
    const nextCursor = button.dataset.cursor || null;
    const previousCursor = catalogPageCursor;
    catalogPreviousCursors.push(previousCursor);
    if (!(await showCatalogPage(form, nextCursor))) catalogPreviousCursors.pop();
    return;
  }
  const previousCursor = catalogPreviousCursors.pop();
  if (!(await showCatalogPage(form, previousCursor ?? null)) && previousCursor !== undefined) catalogPreviousCursors.push(previousCursor);
});

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'catalog-lineage-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const workspace = encodeURIComponent(String(document.querySelector('#catalog-search-form [name="workspace"]')?.value || '').trim());
  const asset = encodeURIComponent(String(data.get('asset_id') || '').trim());
  const version = encodeURIComponent(String(data.get('version') || '').trim());
  const direction = encodeURIComponent(String(data.get('direction') || 'upstream'));
  const output = document.querySelector('#catalog-lineage-result');
  output.className = 'catalog-lineage-result loading';
  output.textContent = 'Loading lineage…';
  try { output.className = 'catalog-lineage-result'; output.innerHTML = lineageView(await get(`/v1/workspaces/${workspace}/catalog/lineage/${asset}/${version}?direction=${direction}&limit=100`)); }
  catch (error) { output.className = 'catalog-lineage-result'; output.innerHTML = `<div class="error"><strong>Lineage lookup failed.</strong><span>${esc(error.message)}</span><button class="button" type="button" data-action="catalog-lineage-retry">Retry lineage</button></div>`; }
});

document.addEventListener('click', async event => {
  if (!event.target.closest('[data-action="catalog-lineage-retry"]')) return;
  const form = document.querySelector('#catalog-lineage-form');
  if (form) form.requestSubmit();
});

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'glossary-search-form') return;
  event.preventDefault();
  const workspace = encodeURIComponent(String(document.querySelector('#glossary-form [name="workspace"]')?.value || '').trim());
  const query = String(new FormData(form).get('query') || '').trim();
  const suffix = query ? `?q=${encodeURIComponent(query)}&limit=100` : '?limit=100';
  const output = document.querySelector('#glossary-result');
  output.className = 'catalog-result loading';
  output.textContent = 'Loading glossary…';
  try { output.className = 'catalog-result'; output.innerHTML = glossaryView(await get(`/v1/workspaces/${workspace}/glossary/terms${suffix}`)); }
  catch (error) { output.className = 'catalog-result'; output.innerHTML = `<div class="error"><strong>Glossary lookup failed.</strong><span>${esc(error.message)}</span></div>`; }
});

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'glossary-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const output = document.querySelector('#glossary-result');
  const workspace = encodeURIComponent(String(data.get('workspace') || '').trim());
  const termId = String(data.get('id') || '').trim();
  const body = {
    id: termId,
    version: String(data.get('version') || '').trim(),
    name: String(data.get('name') || '').trim(),
    definition: String(data.get('definition') || '').trim(),
    owner: String(data.get('owner') || '').trim(),
    references: String(data.get('references') || '').split(',').map(value => value.trim()).filter(Boolean),
  };
  try {
    const response = await post(`/v1/workspaces/${workspace}/glossary/terms`, body, { headers: { 'Idempotency-Key': `studio-glossary-${workspace}-${termId}-${body.version}` } });
    output.className = 'catalog-result';
    output.innerHTML = `<div class="catalog-empty"><strong>Term published.</strong><span>${esc(body.name || termId)} is available in the shared language.</span></div><details class="catalog-raw"><summary>View publication response</summary><pre class="code">${esc(json(response))}</pre></details>`;
  } catch (error) { output.className = 'catalog-result'; output.innerHTML = `<div class="error"><strong>Glossary publication failed.</strong><span>${esc(error.message)}</span></div>`; }
});

setTimeout(() => {
  window.addEventListener('hashchange', render);
  if (location.hash.slice(1) === 'catalog') render();
}, 0);
