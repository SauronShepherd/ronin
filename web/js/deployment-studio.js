import { get, put } from './api.js';
import { json, page } from './dom.js';

function render() {
  if (location.hash.slice(1) !== 'deployments') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Deployments', 'RUNTIME BINDINGS')}<section class="panel"><form id="deployment-bindings-form"><div class="grid two"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Project<input class="field" name="project" value="examples/demo" required></label><label>Environment<input class="field" name="environment" value="local" required></label></div><label>Bindings JSON<textarea class="field sql-editor" name="bindings" rows="5">{}</textarea></label><button class="button" data-action="deployment-read" type="button">Read bindings</button><button class="button primary" type="submit">Replace bindings</button></form><pre id="deployment-result" class="code" aria-live="polite">No deployment binding loaded.</pre></section>`;
}

function path(data) {
  return `/v1/workspaces/${encodeURIComponent(String(data.get('workspace')))}/projects/${encodeURIComponent(String(data.get('project')))}/environments/${encodeURIComponent(String(data.get('environment')))}/bindings`;
}

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action="deployment-read"]');
  if (!button) return;
  const form = document.querySelector('#deployment-bindings-form');
  const result = document.querySelector('#deployment-result');
  try { result.textContent = json(await get(path(new FormData(form)))); } catch (error) { result.textContent = `Binding lookup failed: ${error.message}`; }
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'deployment-bindings-form') return;
  event.preventDefault();
  const result = document.querySelector('#deployment-result');
  try { const data = new FormData(form); result.textContent = json(await put(path(data), JSON.parse(String(data.get('bindings'))))); } catch (error) { result.textContent = `Binding update failed: ${error.message}`; }
});
setTimeout(() => { window.addEventListener('hashchange', render); if (location.hash.slice(1) === 'deployments') render(); }, 0);
