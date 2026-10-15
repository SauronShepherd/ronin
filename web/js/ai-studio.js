import { get, post } from './api.js';
import { esc, json, page } from './dom.js';

function render() {
  if (location.hash.slice(1) !== 'ai') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('AI Studio', 'MODEL OPERATIONS')}<section class="panel"><form id="ai-models-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="default" required></label><button class="button" type="submit">Discover models</button><button class="button" type="button" id="ai-health">Check provider health</button></form><pre id="ai-models-result" class="code" aria-live="polite">No discovery requested.</pre></section><section class="panel"><h2>Invoke model</h2><form id="ai-invoke-form"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Model<input class="field" name="model" required></label><label>Request JSON<textarea class="field sql-editor" name="request" rows="5">{"messages":[{"role":"user","content":"Hello"}]}</textarea></label><button class="button primary" type="submit">Invoke</button></form><pre id="ai-invoke-result" class="code" aria-live="polite">No invocation requested.</pre></section>`;
  document.querySelector('#ai-health').onclick = async () => {
    const workspace = encodeURIComponent(document.querySelector('#ai-models-form [name="workspace"]').value);
    const output = document.querySelector('#ai-models-result');
    try { output.textContent = json(await get(`/v1/workspaces/${workspace}/ai-studio/health`)); }
    catch (error) { output.textContent = `Health check failed: ${error.message}`; }
  };
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  const data = new FormData(form);
  if (form.id === 'ai-models-form') {
    event.preventDefault();
    const out = document.querySelector('#ai-models-result');
    try { out.textContent = json(await get(`/v1/workspaces/${encodeURIComponent(String(data.get('workspace')))}/ai-studio/models`)); } catch (error) { out.textContent = `Discovery failed: ${error.message}`; }
  } else if (form.id === 'ai-invoke-form') {
    event.preventDefault();
    const out = document.querySelector('#ai-invoke-result');
    try {
      const body = JSON.parse(String(data.get('request')));
      body.model = String(data.get('model'));
      out.textContent = json(await post(`/v1/workspaces/${encodeURIComponent(String(data.get('workspace')))}/ai-studio/invoke`, body));
    } catch (error) { out.textContent = `Invocation failed: ${error.message}`; }
  }
});
setTimeout(() => { window.addEventListener('hashchange', render); if (location.hash.slice(1) === 'ai') render(); }, 0);
