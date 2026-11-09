import { get, post, put } from './api.js';
import { esc, json } from './dom.js';
import { setStudioContext } from './context-bar.js';

function renderProjects() {
  if (location.hash.slice(1).split('/')[0] !== 'projects') return;
  const view = document.querySelector('#view');
  if (!view || document.querySelector('#project-journey-form')) return;
  const workspaceId = decodeURIComponent(location.hash.slice(1).split('/')[1] || '');
  view.innerHTML = `<section class="project-hero panel">
    <div><p class="eyebrow">GOVERNANCE · PROJECT CONTROL PLANE</p><h2>Build inside a governed project.</h2><p>Keep the manifest, environment binding, operation and permission evidence connected to one workspace-scoped project.</p></div>
    <div class="project-hero-aside"><span class="status blue">project → environment → operation</span><p>Ronin makes the project boundary explicit before a run, import or permission decision.</p></div>
  </section>
  <nav class="project-mode-nav" aria-label="Project workbench modes">
    <button class="project-mode-card" type="button" data-project-scroll="project-authoring" aria-controls="project-journey-form" aria-label="Author project"><span class="project-mode-index">01</span><strong>Author</strong><span>Define or revise the project manifest.</span></button>
    <button class="project-mode-card" type="button" data-project-scroll="project-connection" aria-controls="project-environment-form" aria-label="Connect project"><span class="project-mode-index">02</span><strong>Connect</strong><span>Bind a declared environment and runtime.</span></button>
    <button class="project-mode-card" type="button" data-project-scroll="project-operation" aria-controls="project-operation-form" aria-label="Operate project"><span class="project-mode-index">03</span><strong>Operate</strong><span>Run a reviewed, idempotent pipeline operation.</span></button>
    <button class="project-mode-card" type="button" data-project-scroll="project-govern" aria-controls="project-permissions-form" aria-label="Govern project"><span class="project-mode-index">04</span><strong>Govern</strong><span>Inspect permissions and move portable evidence.</span></button>
  </nav>
  <section class="panel project-workbench"><h1 id="view-title">Projects</h1>
    <p class="muted">Workspace: <code>${esc(workspaceId || 'select a workspace')}</code></p>
    <section class="project-overview" aria-labelledby="project-overview-title">
      <div class="project-overview-heading"><div><p class="eyebrow">OPERATING BRIEF</p><h2 id="project-overview-title">See the project boundary before you edit it.</h2><p>Ronin keeps source, runtime and operation decisions attached to the same project identity. Values stay unknown until the API confirms them.</p></div><span class="status blue">workspace-scoped</span></div>
      <div class="project-overview-grid">
        <div class="project-metric"><span>Visible projects</span><strong id="project-overview-count">—</strong><small id="project-overview-count-note">Loading inventory…</small></div>
        <div class="project-metric"><span>Source posture</span><strong id="project-source-state">Unknown</strong><small id="project-source-note">Waiting for a project inventory.</small></div>
        <div class="project-metric"><span>Next gate</span><strong id="project-next-gate">Choose a project</strong><small id="project-next-gate-note">Use context before operating on a project.</small></div>
      </div>
    </section>
    <form id="project-journey-form" class="stack"><label>Project manifest JSON
      <textarea id="project-manifest" class="field" rows="8" required>{}</textarea></label>
      <button class="button primary" type="submit">Create project</button>
      <pre id="project-journey-result" class="code" aria-live="polite">No project created.</pre></form>
    <form id="project-bundle-import-form" class="stack"><h2>Import project Bundle</h2>
      <label>Project ID<input class="field" name="project_id" required></label>
      <label>Bundle archive<input class="field" name="bundle" type="file" accept=".roninbundle,application/zip" required></label>
      <button class="button" type="submit">Import Bundle</button></form>
    <form id="project-environment-form" class="stack"><h2>Bind project environment</h2>
      <label>Project ID<input class="field" name="project_id" required></label>
      <label>Environment ID<input class="field" name="environment_id" value="local" required></label>
      <label>Bindings JSON<textarea class="field" name="bindings" rows="5">{"project_id":"","environment_id":"local","bindings":{}}</textarea></label>
      <button class="button" type="submit">Replace environment binding</button>
      <pre id="project-environment-result" class="code" aria-live="polite">No environment binding changed.</pre></form>
    <form id="project-operation-form" class="stack"><h2>Run governed operation</h2>
      <label>Project ID<input class="field" name="project_id" required></label>
      <label>Pipeline ID<input class="field" name="pipeline_id" value="main" required></label>
      <label>Operation JSON<textarea class="field" name="operation" rows="6" required>{"revision_key":"main/working","ir_digest":"","runtime":"local-preview","parameters":{"pipeline":{"config":{"name":"main"},"nodes":[],"edges":[]}}}</textarea></label>
      <button class="button primary" type="submit">Run governed pipeline</button>
      <pre id="project-operation-result" class="code" aria-live="polite">No governed operation submitted.</pre></form>
    <form id="project-permissions-form" class="stack"><h2>Inspect project permissions</h2>
      <label>Project ID<input class="field" name="project_id" required></label>
      <button class="button" type="submit">Inspect permissions</button>
      <pre id="project-permissions-result" class="code" aria-live="polite">No permission inspection performed.</pre></form>
    <div id="project-list" class="table-wrap" aria-live="polite">Loading projects…</div></section>`;
  const projectAnchors = {
    'project-journey-form': 'project-authoring',
    'project-environment-form': 'project-connection',
    'project-operation-form': 'project-operation',
    'project-permissions-form': 'project-govern',
  };
  Object.entries(projectAnchors).forEach(([id, anchor]) => document.getElementById(id)?.setAttribute('data-project-anchor', anchor));
  const form = document.querySelector('#project-journey-form');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = document.querySelector('#project-journey-result');
    try {
      const manifest = JSON.parse(document.querySelector('#project-manifest').value);
      const projectId = manifest?.project?.id || 'unknown';
      const editing = form.dataset.editProject;
      const data = editing
        ? await put(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(editing)}`, manifest)
        : await post(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects`, manifest, { headers: { 'Idempotency-Key': `studio-project-${workspaceId}-${projectId}` } });
      output.textContent = json(data);
      delete form.dataset.editProject;
      form.querySelector('button[type="submit"]').textContent = 'Create project';
      await loadProjects(workspaceId);
    } catch (error) {
      output.textContent = `Could not create project: ${error.message}`;
    }
  });
  document.querySelector('#project-bundle-import-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const output = document.querySelector('#project-journey-result');
    const file = data.get('bundle');
    const projectId = String(data.get('project_id') || '').trim();
    if (!(file instanceof File) || !projectId) { output.textContent = 'Select a Bundle file and project ID.'; return; }
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
      const result = await post(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(projectId)}/bundle/import`, { content_base64: btoa(binary) }, { headers: { 'Idempotency-Key': `studio-bundle-import-${workspaceId}-${projectId}-${file.size}` } });
      output.textContent = json(result); await loadProjects(workspaceId);
    } catch (error) { output.textContent = `Could not import project Bundle: ${error.message}`; }
  });
  document.querySelector('#project-environment-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const output = document.querySelector('#project-environment-result');
    const projectId = String(data.get('project_id') || '').trim();
    const environmentId = String(data.get('environment_id') || '').trim();
    try {
      const payload = JSON.parse(String(data.get('bindings') || '{}'));
      payload.project_id = projectId; payload.environment_id = environmentId;
      const result = await put(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(environmentId)}/bindings`, payload);
      output.textContent = json(result);
    } catch (error) { output.textContent = `Could not bind environment: ${error.message}`; }
  });
  document.querySelector('#project-operation-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const output = document.querySelector('#project-operation-result');
    const projectId = String(data.get('project_id') || '').trim();
    const pipelineId = String(data.get('pipeline_id') || '').trim();
    try {
      const payload = JSON.parse(String(data.get('operation') || '{}'));
      if (!payload.revision_key || !payload.ir_digest || !payload.runtime) throw new Error('Operation requires revision_key, ir_digest and runtime.');
      const result = await post(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(projectId)}/pipelines/${encodeURIComponent(pipelineId)}/runs`, payload, { headers: { 'Idempotency-Key': `studio-pipeline-run-${workspaceId}-${projectId}-${pipelineId}-${payload.revision_key}` } });
      output.textContent = json(result);
    } catch (error) { output.textContent = `Could not run governed operation: ${error.message}`; }
  });
  document.querySelector('#project-permissions-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = document.querySelector('#project-permissions-result');
    const projectId = String(new FormData(event.currentTarget).get('project_id') || '').trim();
    try {
      output.textContent = json(await get(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(projectId)}/permissions`));
    } catch (error) { output.textContent = `Could not inspect project permissions: ${error.message}`; }
  });
  loadProjects(workspaceId);
}

async function loadProjects(workspaceId) {
  const target = document.querySelector('#project-list');
  if (!target || !workspaceId) return;
  try {
    const data = await get(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects`);
    const items = data.items || data;
    const rows = Array.isArray(items) ? items : [];
    const sources = rows.filter((item) => {
      const project = item.project || item;
      return Array.isArray(project.repositories) && project.repositories.length > 0;
    });
    const count = document.querySelector('#project-overview-count');
    const countNote = document.querySelector('#project-overview-count-note');
    const sourceState = document.querySelector('#project-source-state');
    const sourceNote = document.querySelector('#project-source-note');
    const nextGate = document.querySelector('#project-next-gate');
    const nextGateNote = document.querySelector('#project-next-gate-note');
    if (count) count.textContent = String(rows.length);
    if (countNote) countNote.textContent = rows.length === 1 ? 'One active project returned by the API.' : `${rows.length} active projects returned by the API.`;
    if (sourceState) sourceState.textContent = rows.length === 0 || sources.length === 0 ? 'Unconfigured' : sources.length === rows.length ? 'Declared' : 'Mixed';
    if (sourceNote) sourceNote.textContent = rows.length === 0 ? 'Create a project to declare its source.' : `${sources.length} of ${rows.length} project${rows.length === 1 ? '' : 's'} declare a repository.`;
    if (nextGate) nextGate.textContent = rows.length === 0 ? 'Author' : 'Use context';
    if (nextGateNote) nextGateNote.textContent = rows.length === 0 ? 'Start with a manifest and keep the source boundary explicit.' : 'Select a project before binding runtime or submitting a run.';
    target.innerHTML = Array.isArray(items) && items.length
      ? `<table><caption class="sr-only">Active projects</caption><thead><tr><th>ID</th><th>Name</th><th>Source</th><th>Actions</th></tr></thead><tbody>${items.map((item) => { const project = item.project || item; const id = project.id || item.id || ''; const repository = Array.isArray(project.repositories) ? project.repositories[0] : null; const source = repository ? `${repository.adapter_id || 'repository'} · ${repository.default_ref || 'ref unknown'}` : 'Not declared'; return `<tr><td>${esc(id)}</td><td>${esc(project.name || item.name || '')}</td><td><span class="project-source-label">${esc(source)}</span></td><td><button class="button project-context" data-project="${esc(id)}" type="button">Use context</button> <button class="button project-edit" data-project="${esc(id)}" type="button">Edit manifest</button> <button class="button project-bundle" data-project="${esc(id)}" type="button">Export manifest</button> <button class="button project-bundle-archive" data-project="${esc(id)}" type="button">Download Bundle</button> <button class="button project-archive" data-project="${esc(id)}" type="button">Archive</button></td></tr>`; }).join('')}</tbody></table>`
      : '<div class="empty">No active projects are visible.</div>';
  } catch (error) {
    const count = document.querySelector('#project-overview-count');
    const countNote = document.querySelector('#project-overview-count-note');
    const sourceState = document.querySelector('#project-source-state');
    const sourceNote = document.querySelector('#project-source-note');
    const nextGate = document.querySelector('#project-next-gate');
    const nextGateNote = document.querySelector('#project-next-gate-note');
    if (count) count.textContent = '—';
    if (countNote) countNote.textContent = 'Inventory unavailable.';
    if (sourceState) sourceState.textContent = 'Unknown';
    if (sourceNote) sourceNote.textContent = 'The API did not confirm source posture.';
    if (nextGate) nextGate.textContent = 'Review error';
    if (nextGateNote) nextGateNote.textContent = 'Resolve the inventory request before changing project state.';
    target.innerHTML = `<div class="error">${esc(error.message)}</div>`;
  }
}

document.addEventListener('click', async (event) => {
  const scroll = event.target.closest?.('[data-project-scroll]');
  if (scroll) {
    event.preventDefault();
    document.querySelector(`[data-project-anchor="${scroll.dataset.projectScroll}"]`)?.scrollIntoView({ behavior: 'auto', block: 'start' });
    return;
  }
  const context = event.target.closest?.('.project-context');
  if (context) {
    const workspaceId = decodeURIComponent(location.hash.slice(1).split('/')[1] || '');
    setStudioContext({ workspace: workspaceId, project: context.dataset.project });
    return;
  }
  const edit = event.target.closest?.('.project-edit');
  if (edit) {
    const workspaceId = decodeURIComponent(location.hash.slice(1).split('/')[1] || '');
    try { const manifest = await get(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(edit.dataset.project)}`); document.querySelector('#project-manifest').value = JSON.stringify(manifest, null, 2); document.querySelector('#project-journey-form').dataset.editProject = edit.dataset.project; document.querySelector('#project-journey-form button[type="submit"]').textContent = 'Update project'; } catch (error) { document.querySelector('#project-journey-result').textContent = `Could not load project: ${error.message}`; }
    return;
  }
  const archiveButton = event.target.closest?.('.project-bundle-archive');
  if (archiveButton) {
    const workspaceId = decodeURIComponent(location.hash.slice(1).split('/')[1] || '');
    const output = document.querySelector('#project-journey-result');
    try {
      const payload = await get(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(archiveButton.dataset.project)}/bundle/archive`);
      if (payload.media_type !== 'application/vnd.ronin.bundle+zip' || typeof payload.content_base64 !== 'string') throw new Error('Invalid Bundle archive response');
      const binary = atob(payload.content_base64);
      const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: payload.media_type }));
      const link = document.createElement('a'); link.href = url; link.download = `${archiveButton.dataset.project}.roninbundle`; link.click(); URL.revokeObjectURL(url);
      output.textContent = `Downloaded ${link.download}`;
    } catch (error) { output.textContent = `Could not download project Bundle: ${error.message}`; }
    return;
  }
  const bundle = event.target.closest?.('.project-bundle');
  if (bundle) {
    const workspaceId = decodeURIComponent(location.hash.slice(1).split('/')[1] || '');
    const output = document.querySelector('#project-journey-result');
    try { output.textContent = json(await get(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(bundle.dataset.project)}/bundle`)); } catch (error) { output.textContent = `Could not export project manifest: ${error.message}`; }
    return;
  }
  const button = event.target.closest?.('.project-archive');
  if (!button || !confirm(`Archive project ${button.dataset.project}?`)) return;
  const workspaceId = decodeURIComponent(location.hash.slice(1).split('/')[1] || '');
  const output = document.querySelector('#project-journey-result');
  try {
    const result = await post(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(button.dataset.project)}/archive`, {}, { headers: { 'Idempotency-Key': `studio-project-archive-${workspaceId}-${button.dataset.project}` } });
    output.textContent = json(result);
    await loadProjects(workspaceId);
  } catch (error) { output.textContent = `Could not archive project: ${error.message}`; }
});

const observer = new MutationObserver(renderProjects);
observer.observe(document.body, { childList: true, subtree: true });
window.addEventListener('hashchange', () => setTimeout(renderProjects, 0));
setTimeout(renderProjects, 0);

export { renderProjects, loadProjects };
