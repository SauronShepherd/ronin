import { del, get, post, put } from './api.js';
import { esc, json } from './dom.js';

function connectionPath(workspace, id = '') {
  const suffix = id ? `/${encodeURIComponent(id)}` : '';
  return `/v1/workspaces/${encodeURIComponent(workspace)}/connections${suffix}`;
}

function addConnectionsPanel() {
  if (location.hash.slice(1) !== 'data') return;
  const view = document.querySelector('#view');
  if (!view || view.querySelector('#connections-studio')) return;
  const panel = document.createElement('section');
  panel.id = 'connections-studio';
  panel.className = 'panel';
  panel.innerHTML = `<h2>Connections</h2><p class="muted">Portable metadata only. Credentials remain opaque secret references.</p>
    <form id="connection-list-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="default" required></label><button class="button" type="submit">Refresh</button></form>
    <div id="connection-list" class="loading" aria-live="polite">No connections loaded.</div>
    <form id="connection-editor-form" class="stack"><input type="hidden" name="editing"><label>ID<input class="field" name="id" required></label><label>Name<input class="field" name="name" required></label><label>Connector ID<input class="field" name="connector_id" required placeholder="postgres"></label><label>Options JSON<textarea class="field" name="options" rows="3">{}</textarea></label><label>Secret refs JSON<textarea class="field" name="secret_refs" rows="3">{}</textarea></label><div class="toolbar"><button class="button primary">Save connection</button><button class="button" type="button" data-action="connection-clear">Clear</button></div></form><pre id="connection-result" class="code" aria-live="polite">No connection operation executed.</pre>`;
  view.append(panel);
  loadConnections();
}

async function loadConnections() {
  const form = document.querySelector('#connection-list-form');
  const result = document.querySelector('#connection-list');
  if (!form || !result) return;
  const workspace = String(new FormData(form).get('workspace') || '').trim();
  try {
    const payload = await get(connectionPath(workspace));
    const items = payload.items || [];
    result.innerHTML = items.length ? `<div class="table-wrap"><table><caption class="sr-only">Connections</caption><thead><tr><th>ID</th><th>Name</th><th>Connector</th><th>Actions</th></tr></thead><tbody>${items.map(item => `<tr><td>${esc(item.id)}</td><td>${esc(item.name)}</td><td>${esc(item.connector_id)}</td><td><button class="button" type="button" data-action="connection-edit" data-workspace="${esc(workspace)}" data-id="${esc(item.id)}">Edit</button><button class="button danger" type="button" data-action="connection-delete" data-workspace="${esc(workspace)}" data-id="${esc(item.id)}">Delete</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No connections found.</div>';
  } catch (error) { result.textContent = `Connection lookup failed: ${error.message}`; }
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (form.id === 'connection-list-form') { event.preventDefault(); await loadConnections(); return; }
  if (form.id !== 'connection-editor-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const workspace = String(document.querySelector('#connection-list-form [name="workspace"]')?.value || '').trim();
  const id = String(data.get('id') || '').trim();
  const payload = { id, name: String(data.get('name') || '').trim(), connector_id: String(data.get('connector_id') || '').trim(), options: JSON.parse(String(data.get('options') || '{}')), secret_refs: JSON.parse(String(data.get('secret_refs') || '{}')) };
  const editing = String(data.get('editing') || '').trim();
  const output = document.querySelector('#connection-result');
  try {
    output.textContent = json(editing ? await put(connectionPath(workspace, editing), payload) : await post(connectionPath(workspace), payload));
    form.reset(); await loadConnections();
  } catch (error) { output.textContent = `Connection save failed: ${error.message}`; }
});

document.addEventListener('click', async event => {
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
      form.elements.editing.value = id; form.elements.id.value = item.id; form.elements.name.value = item.name; form.elements.connector_id.value = item.connector_id; form.elements.options.value = JSON.stringify(item.options || {}, null, 2); form.elements.secret_refs.value = JSON.stringify(item.secret_refs || {}, null, 2); output.textContent = `Editing ${id}`; return;
    }
    if (action === 'connection-delete') { output.textContent = json(await del(connectionPath(workspace, id), { body: '{}' })); await loadConnections(); }
  } catch (error) { output.textContent = `Connection operation failed: ${error.message}`; }
});

window.addEventListener('hashchange', addConnectionsPanel);
setTimeout(addConnectionsPanel, 0);
