import { get, post } from './api.js';
import { json, page } from './dom.js';

function render() {
  if (location.hash.slice(1) !== 'graphs') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Knowledge Graph', 'CATALOG · ONTOLOGY')}<section class="panel">
    <p class="muted">Run bounded, read-only RQL queries against a project graph.</p>
    <form id="graph-query-form" class="grid two">
      <label>Graph ID<input class="field" name="graph" value="graph-1" required></label>
      <label>Workspace<input class="field" name="workspace" value="default" required></label>
      <label class="span-two">RQL query<textarea class="field sql-editor" name="query" rows="4" required>SELECT Person LIMIT 20</textarea></label>
      <button class="button primary" type="submit">Run query</button>
    </form><pre id="graph-result" class="code" aria-live="polite">No query executed.</pre>
  </section><section class="panel"><h2>Objects</h2>
    <form id="graph-objects-form" class="toolbar"><input class="field" name="type" value="Person" required><input class="field" name="limit" type="number" min="1" max="100" value="100"><button class="button" type="submit">List objects</button></form>
  </section><section class="panel"><h2>Neighbors</h2>
    <form id="graph-neighbors-form" class="grid two"><label>Object type<input class="field" name="object_type" value="Person" required></label><label>Limit<input class="field" name="limit" type="number" min="1" max="100" value="100"></label><label class="span-two">Key JSON<textarea class="field" name="key" rows="2">[["id","1"]]</textarea></label><button class="button" type="submit">List neighbors</button></form>
  </section><section class="panel"><h2>Authorized action</h2>
    <form id="graph-action-form" class="grid two"><label>Action JSON<textarea class="field" name="action" rows="2">{"id":"inspect"}</textarea></label><label>Target type<input class="field" name="object_type" value="Person" required></label><label>Target key JSON<textarea class="field" name="key" rows="2">[["id","1"]]</textarea></label><label>Inputs JSON<textarea class="field" name="inputs" rows="2">{}</textarea></label><label>Idempotency key<input class="field" name="idempotency_key" value="graph-action-1" required></label><button class="button danger" type="submit">Execute action</button></form>
  </section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (form.id === 'graph-query-form') {
    event.preventDefault();
    const data = new FormData(form);
    const result = document.querySelector('#graph-result');
    result.textContent = 'Running…';
    try {
      const workspace = encodeURIComponent(String(data.get('workspace')));
      const graph = encodeURIComponent(String(data.get('graph')));
      result.textContent = json(await post(`/v1/workspaces/${workspace}/graphs/${graph}/query`, {query: String(data.get('query')), max_limit: 1000}));
    } catch (error) { result.textContent = `Query failed: ${error.message}`; }
  } else if (form.id === 'graph-objects-form') {
    event.preventDefault();
    const queryForm = document.querySelector('#graph-query-form');
    const queryData = new FormData(queryForm);
    const data = new FormData(form);
    const result = document.querySelector('#graph-result');
    try {
      const workspace = encodeURIComponent(String(queryData.get('workspace')));
      const graph = encodeURIComponent(String(queryData.get('graph')));
      result.textContent = json(await get(`/v1/workspaces/${workspace}/graphs/${graph}/objects/${encodeURIComponent(String(data.get('type')))}?limit=${encodeURIComponent(String(data.get('limit')))}`));
    } catch (error) { result.textContent = `Object lookup failed: ${error.message}`; }
  } else if (form.id === 'graph-neighbors-form') {
    event.preventDefault();
    const queryForm = document.querySelector('#graph-query-form');
    const queryData = new FormData(queryForm);
    const data = new FormData(form);
    const result = document.querySelector('#graph-result');
    try {
      const workspace = encodeURIComponent(String(queryData.get('workspace')));
      const graph = encodeURIComponent(String(queryData.get('graph')));
      result.textContent = json(await post(`/v1/workspaces/${workspace}/graphs/${graph}/neighbors`, {object_type: String(data.get('object_type')), key: JSON.parse(String(data.get('key'))), limit: Number(data.get('limit'))}));
    } catch (error) { result.textContent = `Neighbor lookup failed: ${error.message}`; }
  } else if (form.id === 'graph-action-form') {
    event.preventDefault();
    if (!window.confirm('Execute this authorized graph action?')) return;
    const queryForm = document.querySelector('#graph-query-form');
    const queryData = new FormData(queryForm);
    const data = new FormData(form);
    const result = document.querySelector('#graph-result');
    try {
      const workspace = encodeURIComponent(String(queryData.get('workspace')));
      const graph = encodeURIComponent(String(queryData.get('graph')));
      result.textContent = json(await post(`/v1/workspaces/${workspace}/graphs/${graph}/actions`, {action: JSON.parse(String(data.get('action'))), target: {object_type: String(data.get('object_type')), key: JSON.parse(String(data.get('key')))}, inputs: JSON.parse(String(data.get('inputs'))), idempotency_key: String(data.get('idempotency_key'))}));
    } catch (error) { result.textContent = `Action failed: ${error.message}`; }
  }
});

// Register after the host shell's initial render so the graph view owns its route.
setTimeout(() => {
  window.addEventListener('hashchange', render);
  if (location.hash.slice(1) === 'graphs') render();
}, 0);
