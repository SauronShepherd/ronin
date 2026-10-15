import { get } from './api.js';
import { json, page } from './dom.js';

function render() {
  if (location.hash.slice(1) !== 'streaming') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Streaming', 'REAL-TIME')}<section class="panel"><form id="stream-health-form" class="grid two"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Stream ID<input class="field" name="stream" required placeholder="events/main"></label><button class="button primary" type="submit">Check health</button></form><pre id="stream-health-result" class="code" aria-live="polite">No stream selected.</pre></section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'stream-health-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const out = document.querySelector('#stream-health-result');
  try { out.textContent = json(await get(`/v1/workspaces/${encodeURIComponent(String(data.get('workspace')))}/streams/${encodeURIComponent(String(data.get('stream')))}/health`)); } catch (error) { out.textContent = `Streaming health failed: ${error.message}`; }
});
setTimeout(() => { window.addEventListener('hashchange', render); if (location.hash.slice(1) === 'streaming') render(); }, 0);
