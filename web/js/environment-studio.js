import { get, post, put } from './api.js';
import { esc, json, page } from './dom.js';

function render() {
  if (location.hash.slice(1) !== 'environments') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Environments', 'DEPLOYMENT')}<section class="panel"><form id="environment-list-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="default" required></label><button class="button" type="submit">Refresh</button></form><div id="environment-result" class="loading">No environments loaded.</div></section><section class="panel"><h2>Create environment</h2><form id="environment-create-form"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Environment JSON<textarea class="field sql-editor" name="definition" rows="7">{"id":"local","name":"Local","kind":"local","state":"active"}</textarea></label><button class="button primary" type="submit">Create</button></form><pre id="environment-create-result" class="code" aria-live="polite">No environment created.</pre></section>`;
}

async function load(workspace) {
  const result = document.querySelector('#environment-result');
  try {
    const data = await get(`/v1/workspaces/${encodeURIComponent(workspace)}/environments`);
    const items = data.items || [];
  result.innerHTML = items.length ? `<div class="table-wrap"><table><caption class="sr-only">Environments</caption><thead><tr><th>ID</th><th>Name</th><th>Kind</th><th>State</th><th>Actions</th></tr></thead><tbody>${items.map(item => `<tr><td>${esc(item.id)}</td><td>${esc(item.name)}</td><td>${esc(item.kind)}</td><td>${esc(item.state)}</td><td><button class="button environment-edit" data-workspace="${esc(workspace)}" data-environment="${esc(item.id)}" type="button">Edit</button> <button class="button environment-disable" data-workspace="${esc(workspace)}" data-environment="${esc(item.id)}" type="button">Disable</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No environments found.</div>';
  } catch (error) { result.textContent = `Environment lookup failed: ${error.message}`; }
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  const data = new FormData(form);
  if (form.id === 'environment-list-form') { event.preventDefault(); await load(String(data.get('workspace'))); }
  if (form.id === 'environment-create-form') {
    event.preventDefault();
    const out = document.querySelector('#environment-create-result');
    try { const workspace = String(data.get('workspace')); const definition = JSON.parse(String(data.get('definition'))); const environment = form.dataset.replaceId; const result = environment ? await put(`/v1/workspaces/${encodeURIComponent(workspace)}/environments/${encodeURIComponent(environment)}`, definition) : await post(`/v1/workspaces/${encodeURIComponent(workspace)}/environments`, definition); out.textContent = json(result); form.dataset.replaceId = ''; form.querySelector('button[type="submit"]').textContent = 'Create'; await load(workspace); } catch (error) { out.textContent = `Environment ${form.dataset.replaceId ? 'update' : 'creation'} failed: ${error.message}`; }
  }
});
document.addEventListener('click', async event => {
  const edit = event.target.closest?.('.environment-edit');
  if (edit) {
    const form = document.querySelector('#environment-create-form');
    const out = document.querySelector('#environment-create-result');
    try { const result = await get(`/v1/workspaces/${encodeURIComponent(edit.dataset.workspace)}/environments/${encodeURIComponent(edit.dataset.environment)}`); form.elements.workspace.value = edit.dataset.workspace; form.elements.definition.value = JSON.stringify(result, null, 2); form.dataset.replaceId = edit.dataset.environment; form.querySelector('button[type="submit"]').textContent = 'Update'; out.textContent = `Editing ${edit.dataset.environment}`; form.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (error) { out.textContent = `Environment lookup failed: ${error.message}`; }
    return;
  }
  const button = event.target.closest?.('.environment-disable');
  if (!button) return;
  const out = document.querySelector('#environment-create-result');
  try {
    const result = await post(`/v1/workspaces/${encodeURIComponent(button.dataset.workspace)}/environments/${encodeURIComponent(button.dataset.environment)}/disable`, {});
    out.textContent = json(result);
    await load(button.dataset.workspace);
  } catch (error) { out.textContent = `Environment disable failed: ${error.message}`; }
});
setTimeout(() => { window.addEventListener('hashchange', render); if (location.hash.slice(1) === 'environments') render(); }, 0);
