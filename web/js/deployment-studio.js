import { get, put } from './api.js';
import { esc, json, page } from './dom.js';

function render() {
  if (location.hash.slice(1) !== 'deployments') return;
  const view = document.querySelector('#view');
  if (!view) return;
  const context = globalThis.roninStudioContext || { workspace: 'default', project: 'examples/demo', environment: 'local' };
  view.innerHTML = `${page('Deployments', 'RUNTIME BINDINGS')}<section class="deployment-hero panel"><div><p class="eyebrow">RUNTIME BINDINGS · DECISION WORKBENCH</p><h2>Bind a project to an environment you can explain.</h2><p>Read the current runtime binding, change it deliberately, then verify the returned state before a new operation starts.</p></div><div class="deployment-hero-aside"><span class="status blue">project-scoped</span><p>Bindings affect future runs. Existing evidence remains attached to the environment that produced it.</p></div></section><div class="deployment-mode-nav" role="group" aria-label="Deployment workbench modes"><a class="deployment-mode-card" href="#deployments-observe"><span class="deployment-mode-index">01</span><strong>Observe</strong><span>Read the binding that is actually stored.</span></a><a class="deployment-mode-card" href="#deployments-bind"><span class="deployment-mode-index">02</span><strong>Bind</strong><span>Replace the project mapping with explicit JSON.</span></a><a class="deployment-mode-card" href="#deployments-operate"><span class="deployment-mode-index">03</span><strong>Operate</strong><span>Keep the next run inside the chosen boundary.</span></a></div><section id="deployments-observe" class="deployment-workbench panel" aria-labelledby="deployments-observe-title"><div class="deployment-section-heading"><div><span class="deployment-section-index">01 · OBSERVE</span><h2 id="deployments-observe-title">Inspect the active binding</h2><p>All reads and writes use the workspace, project and environment below.</p></div><span class="deployment-boundary">workspace · project · environment</span></div><form id="deployment-bindings-form"><div class="grid three"><label>Workspace<input class="field" name="workspace" value="${esc(context.workspace || 'default')}" required></label><label>Project<input class="field" name="project" value="${esc(context.project || 'examples/demo')}" required></label><label>Environment<input class="field" name="environment" value="${esc(context.environment || 'local')}" required></label></div><div class="toolbar deployment-actions"><button class="button" data-action="deployment-read" type="button">Read bindings</button><span class="deployment-scope-note">Scope is explicit and remains visible in this workbench.</span></div><pre id="deployment-result" class="code" aria-live="polite">No deployment binding loaded.</pre><section id="deployments-bind" class="deployment-bind-section" aria-labelledby="deployments-bind-title"><div class="deployment-section-heading"><div><span class="deployment-section-index">02 · BIND</span><h2 id="deployments-bind-title">Replace the project mapping</h2><p>Submit only a JSON array of governed bindings; the API remains the source of truth.</p></div><span class="deployment-boundary">reviewable · durable</span></div><label>Bindings JSON<textarea class="field sql-editor" name="bindings" rows="5">[]</textarea></label><div class="toolbar deployment-actions"><button class="button primary" type="submit">Replace bindings</button></div></section></form></section><section id="deployments-operate" class="deployment-workbench panel" aria-labelledby="deployments-operate-title"><div class="deployment-section-heading"><div><span class="deployment-section-index">03 · OPERATE</span><h2 id="deployments-operate-title">Keep execution aligned</h2><p>After changing a binding, return to Projects or Runs to inspect the operation and its evidence.</p></div><span class="deployment-boundary">context-aware · evidence-linked</span></div><div class="deployment-operate-grid"><a class="deployment-operate-card" href="#projects"><strong>Review project</strong><span>Inspect the manifest and environment handoff.</span></a><a class="deployment-operate-card" href="#runs"><strong>Follow a run</strong><span>Review lifecycle, events and evidence after execution.</span></a></div></section>`;
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
  try {
    const data = new FormData(form);
    const bindings = JSON.parse(String(data.get('bindings')));
    if (!Array.isArray(bindings)) throw new Error('Bindings must be a JSON array.');
    result.textContent = json(await put(path(data), {
      project_id: String(data.get('project')),
      environment_id: String(data.get('environment')),
      bindings,
    }));
  } catch (error) { result.textContent = `Binding update failed: ${error.message}`; }
});
setTimeout(() => { window.addEventListener('hashchange', render); if (location.hash.slice(1) === 'deployments') render(); }, 0);
