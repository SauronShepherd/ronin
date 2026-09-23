import { get, post } from './api.js';
import { esc, json, status } from './dom.js';

function enhanceWorkspaces() {
  if (location.hash.slice(1) !== 'workspaces') return;
  const result = document.querySelector('#workspace-result');
  if (!result || document.querySelector('#workspace-create-form')) return;
  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.innerHTML = `<h2>Create workspace</h2><form id="workspace-create-form" class="toolbar">
    <label>ID<input class="field" id="workspace-create-id" required></label>
    <label>Name<input class="field" id="workspace-create-name" required></label>
    <label>Description<input class="field" id="workspace-create-description"></label>
    <button class="button primary" type="submit">Create</button>
    <pre id="workspace-create-result" class="code" aria-live="polite">No workspace created.</pre>
  </form>`;
  result.before(panel);
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
    result.innerHTML = rows.length ? `<div class="table-wrap"><table><thead><tr><th>Name</th><th>ID</th><th>Status</th><th>Context</th></tr></thead><tbody>${rows.map((workspace) => `<tr><td>${esc(workspace.name || workspace.id)}</td><td>${esc(workspace.id)}</td><td>${status(workspace.state || workspace.status || 'active')}</td><td><a class="button" href="#projects/${encodeURIComponent(workspace.id)}" data-workspace-context="${esc(workspace.id)}">Open projects</a></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No workspaces are visible.</div>';
  } catch (error) {
    result.innerHTML = `<div class="error">${esc(error.message)}</div>`;
  }
}

const observer = new MutationObserver(enhanceWorkspaces);
observer.observe(document.body, { childList: true, subtree: true });
window.addEventListener('hashchange', () => setTimeout(enhanceWorkspaces, 0));
setTimeout(enhanceWorkspaces, 0);

export { enhanceWorkspaces, loadWorkspaceJourney };
