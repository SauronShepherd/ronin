import { get, post } from './api.js';
import { esc, json, status } from './dom.js';
import { setStudioContext } from './context-bar.js';

function renderWorkspaceOrientation(view) {
  if (view.querySelector('.workspace-hero')) return;
  const header = view.querySelector('.page-header');
  header?.insertAdjacentHTML('afterend', `<section class="workspace-hero panel">
    <div>
      <p class="eyebrow">FOUNDATION · CONTROL PLANE</p>
      <h2>Make the operating boundary explicit.</h2>
      <p>Choose a workspace, establish its project context, and keep authoring, permissions and portability tied to the same governed boundary.</p>
    </div>
    <div class="workspace-hero-aside">
      <span class="status blue">workspace → project → operation</span>
      <p>Ronin shows the state it can verify. Empty, unavailable and archived resources stay distinct from ready work.</p>
    </div>
  </section>
  <div class="workspace-mode-nav" role="group" aria-label="Workspace workbench modes">
    <button class="workspace-mode-card" type="button" data-workspace-scroll="workspace-observe" aria-controls="workspace-result"><span class="workspace-mode-index">01</span><strong>Observe</strong><span>See the workspaces available to this operator.</span></button>
    <button class="workspace-mode-card" type="button" data-workspace-scroll="workspace-create" aria-controls="workspace-create" aria-label="Register workspace"><span class="workspace-mode-index">02</span><strong>Create</strong><span>Register a workspace with an idempotent identity.</span></button>
    <button class="workspace-mode-card" type="button" data-workspace-scroll="workspace-observe" aria-controls="workspace-result"><span class="workspace-mode-index">03</span><strong>Govern</strong><span>Choose a workspace before opening projects, permissions and portable Bundles.</span></button>
  </div>`);
  const toolbar = view.querySelector(':scope > .toolbar');
  toolbar?.classList.add('workspace-context-toolbar');
  const result = view.querySelector('#workspace-result');
  result?.classList.add('workspace-result');
}

function enhanceWorkspaces() {
  if (location.hash.slice(1) !== 'workspaces') return;
  const view = document.querySelector('#view');
  const result = document.querySelector('#workspace-result');
  if (!view || !result) return;
  renderWorkspaceOrientation(view);
  if (document.querySelector('#workspace-create-form')) return;
  const panel = document.createElement('section');
  panel.className = 'panel workspace-create-panel';
  panel.id = 'workspace-create';
  panel.dataset.workspaceAnchor = 'workspace-create';
  panel.innerHTML = `<div class="workspace-section-heading"><div><span class="workspace-section-index">02 · CREATE</span><h2>Create a governed workspace</h2><p>Start with an idempotent identity; projects and operations inherit this boundary.</p></div><span class="workspace-boundary">id · name · description</span></div><form id="workspace-create-form" class="toolbar">
    <label>ID<input class="field" id="workspace-create-id" required></label>
    <label>Name<input class="field" id="workspace-create-name" required></label>
    <label>Description<input class="field" id="workspace-create-description"></label>
    <button class="button primary" type="submit">Create</button>
    <pre id="workspace-create-result" class="code" aria-live="polite">No workspace created.</pre>
  </form>`;
  result.before(panel);
  result.dataset.workspaceAnchor = 'workspace-observe';
  result.setAttribute('aria-labelledby', 'workspace-observe-title');
  result.insertAdjacentHTML('afterbegin', `<div class="workspace-section-heading workspace-result-heading"><div><span class="workspace-section-index">01 · OBSERVE</span><h2 id="workspace-observe-title">Choose the boundary you can operate</h2><p>Open projects only after the workspace is visible and active.</p></div><span class="workspace-boundary">workspace inventory</span></div>`);
  const projectResult = document.querySelector('#project-result');
  projectResult?.setAttribute('data-workspace-anchor', 'workspace-govern');
  document.querySelector('#workspace-create-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = document.querySelector('#workspace-create-result');
    try {
      const id = document.querySelector('#workspace-create-id').value.trim();
      const data = await post('/v1/workspaces', {
        id,
        name: document.querySelector('#workspace-create-name').value.trim(),
        description: document.querySelector('#workspace-create-description').value.trim(),
      }, { headers: { 'Idempotency-Key': `studio-workspace-${id}` } });
      output.textContent = json(data);
      await loadWorkspaceJourney();
    } catch (error) {
      output.textContent = `Could not create workspace: ${error.message}`;
    }
  });
}

async function loadWorkspaceJourney() {
  const result = document.querySelector('#workspace-result');
  if (!result || location.hash.slice(1) !== 'workspaces') return;
  try {
    const data = await get('/v1/workspaces');
    const rows = data.items || data;
    if (!Array.isArray(rows)) return;
    result.className = 'workspace-result';
    result.innerHTML = rows.length ? `<div class="workspace-section-heading workspace-result-heading"><div><span class="workspace-section-index">01 · OBSERVE</span><h2 id="workspace-observe-title">Choose the boundary you can operate</h2><p>Open projects only after the workspace is visible and active.</p></div><span class="workspace-boundary">workspace inventory</span></div><div class="table-wrap"><table><caption class="sr-only">Available workspaces</caption><thead><tr><th>Name</th><th>ID</th><th>Status</th><th>Context</th></tr></thead><tbody>${rows.map((workspace) => `<tr><td><strong>${esc(workspace.name || workspace.id)}</strong></td><td><code>${esc(workspace.id)}</code></td><td>${status(workspace.state || workspace.status || 'active')}</td><td><a class="button" href="#projects/${encodeURIComponent(workspace.id)}" data-workspace-context="${esc(workspace.id)}">Open projects</a></td></tr>`).join('')}</tbody></table></div>` : '<div class="workspace-section-heading workspace-result-heading"><div><span class="workspace-section-index">01 · OBSERVE</span><h2 id="workspace-observe-title">No workspace is ready yet</h2><p>Create one below, then return here to establish its project context.</p></div></div><div class="empty"><strong>No workspaces are visible.</strong><span>The API returned an empty inventory.</span></div>';
  } catch (error) {
    result.className = 'workspace-result';
    result.innerHTML = `<div class="workspace-section-heading workspace-result-heading"><div><span class="workspace-section-index">01 · OBSERVE</span><h2 id="workspace-observe-title">Workspace inventory unavailable</h2><p>Resolve the connection or authorization issue before creating or operating resources.</p></div></div><div class="error"><strong>Request failed</strong><span>${esc(error.message)}</span></div>`;
  }
}

document.addEventListener('click', (event) => {
  const button = event.target.closest?.('[data-workspace-scroll]');
  if (!button) return;
  event.preventDefault();
  document.querySelector(`[data-workspace-anchor="${button.dataset.workspaceScroll}"]`)?.scrollIntoView({ behavior: 'auto', block: 'start' });
});

const observer = new MutationObserver(enhanceWorkspaces);
observer.observe(document.body, { childList: true, subtree: true });
document.addEventListener('click', (event) => {
  const link = event.target.closest?.('[data-workspace-context]');
  if (!link) return;
  setStudioContext({ workspace: link.dataset.workspaceContext, project: null });
});
window.addEventListener('hashchange', () => setTimeout(enhanceWorkspaces, 0));
setTimeout(enhanceWorkspaces, 0);

export { enhanceWorkspaces, loadWorkspaceJourney };
