import { get, post, put } from './api.js';
import { esc, json } from './dom.js';

function renderProjects() {
  if (location.hash.slice(1).split('/')[0] !== 'projects') return;
  const view = document.querySelector('#view');
  if (!view || document.querySelector('#project-journey-form')) return;
  const workspaceId = decodeURIComponent(location.hash.slice(1).split('/')[1] || '');
  view.innerHTML = `<section class="panel"><h1 id="view-title">Projects</h1>
    <p class="muted">Workspace: <code>${esc(workspaceId || 'select a workspace')}</code></p>
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
    <div id="project-list" class="table-wrap" aria-live="polite">Loading projects…</div></section>`;
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
  loadProjects(workspaceId);
}

async function loadProjects(workspaceId) {
  const target = document.querySelector('#project-list');
  if (!target || !workspaceId) return;
  try {
    const data = await get(`/v1/workspaces/${encodeURIComponent(workspaceId)}/projects`);
    const items = data.items || data;
    target.innerHTML = Array.isArray(items) && items.length
      ? `<table><caption class="sr-only">Active projects</caption><thead><tr><th>ID</th><th>Name</th><th>Actions</th></tr></thead><tbody>${items.map((item) => { const id = item.project?.id || item.id || ''; return `<tr><td>${esc(id)}</td><td>${esc(item.project?.name || item.name || '')}</td><td><button class="button project-edit" data-project="${esc(id)}" type="button">Edit manifest</button> <button class="button project-bundle" data-project="${esc(id)}" type="button">Export manifest</button> <button class="button project-bundle-archive" data-project="${esc(id)}" type="button">Download Bundle</button> <button class="button project-archive" data-project="${esc(id)}" type="button">Archive</button></td></tr>`; }).join('')}</tbody></table>`
      : '<div class="empty">No active projects are visible.</div>';
  } catch (error) {
    target.innerHTML = `<div class="error">${esc(error.message)}</div>`;
  }
}

document.addEventListener('click', async (event) => {
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
