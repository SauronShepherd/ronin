import { get, post } from './api.js';
import { esc, json, page } from './dom.js';

function render() {
  if (location.hash.slice(1) !== 'catalog') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Catalog', 'GOVERNANCE')}<section class="panel">
    <form id="catalog-search-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Search<input class="field" name="query" placeholder="asset, tag or classification"></label><button class="button primary" type="submit">Search catalog</button></form>
    <div id="catalog-result" class="loading" aria-live="polite">Enter a workspace and search.</div>
  </section><section class="panel"><h2>Glossary</h2>
    <form id="glossary-form" class="stack"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Term ID<input class="field" name="id" placeholder="customer" required></label><label>Version<input class="field" name="version" value="1" required></label><label>Name<input class="field" name="name" required></label><label>Definition<textarea class="field" name="definition" required></textarea></label><label>Owner<input class="field" name="owner" required></label><label>References<input class="field" name="references" placeholder="catalog:customer"></label><button class="button primary" type="submit">Publish term</button></form>
    <form id="glossary-search-form" class="toolbar"><label>Search terms<input class="field" name="query" placeholder="name, owner or definition"></label><button class="button" type="submit">Load terms</button></form><pre id="glossary-result" class="code" aria-live="polite">No glossary term published.</pre>
  </section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'catalog-search-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const result = document.querySelector('#catalog-result');
  result.textContent = 'Loading…';
  try {
    const workspace = encodeURIComponent(String(data.get('workspace')));
    const query = String(data.get('query') || '').trim();
    const suffix = query ? `?q=${encodeURIComponent(query)}&limit=100` : '?limit=100';
    const payload = await get(`/v1/workspaces/${workspace}/catalog/assets${suffix}`);
    const items = payload.items || [];
    result.innerHTML = items.length ? `<div class="table-wrap"><table><caption class="sr-only">Catalog assets</caption><thead><tr><th>Name</th><th>Kind</th><th>Tags</th><th>Classifications</th></tr></thead><tbody>${items.map(item => `<tr><td>${esc(item.name)}</td><td>${esc(item.kind)}</td><td>${esc((item.tags || []).join(', '))}</td><td>${esc((item.classifications || []).join(', '))}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No governed assets matched the query.</div>';
  } catch (error) { result.textContent = `Catalog lookup failed: ${error.message}`; }
});

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'glossary-search-form') return;
  event.preventDefault();
  const workspace = encodeURIComponent(String(document.querySelector('#glossary-form [name="workspace"]')?.value || '').trim());
  const query = String(new FormData(form).get('query') || '').trim();
  const suffix = query ? `?q=${encodeURIComponent(query)}&limit=100` : '?limit=100';
  const output = document.querySelector('#glossary-result');
  try {
    const payload = await get(`/v1/workspaces/${workspace}/glossary/terms${suffix}`);
    output.textContent = json(payload);
  } catch (error) { output.textContent = `Glossary lookup failed: ${error.message}`; }
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
    output.textContent = json(await post(`/v1/workspaces/${workspace}/glossary/terms`, body, { headers: { 'Idempotency-Key': `studio-glossary-${workspace}-${termId}-${body.version}` } }));
  } catch (error) { output.textContent = `Glossary publication failed: ${error.message}`; }
});

setTimeout(() => {
  window.addEventListener('hashchange', render);
  if (location.hash.slice(1) === 'catalog') render();
}, 0);
