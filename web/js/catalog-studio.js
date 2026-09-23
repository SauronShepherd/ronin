import { get } from './api.js';
import { esc, json, page } from './dom.js';

function render() {
  if (location.hash.slice(1) !== 'catalog') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Catalog', 'GOVERNANCE')}<section class="panel">
    <form id="catalog-search-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Search<input class="field" name="query" placeholder="asset, tag or classification"></label><button class="button primary" type="submit">Search catalog</button></form>
    <div id="catalog-result" class="loading" aria-live="polite">Enter a workspace and search.</div>
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

setTimeout(() => {
  window.addEventListener('hashchange', render);
  if (location.hash.slice(1) === 'catalog') render();
}, 0);
