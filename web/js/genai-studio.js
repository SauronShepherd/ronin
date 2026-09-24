import { get } from './api.js';
import { esc, json, page } from './dom.js';

function renderGenAI() {
  if (location.hash.slice(1) !== 'genai') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('GenAI Studio', 'GENAI OPERATIONS')}<section class="panel"><form id="genai-discovery-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="default" required></label><button class="button primary" type="submit">Discover providers</button><button class="button" type="button" id="genai-prompts">List prompts</button><button class="button" type="button" id="genai-indexes">List vector indexes</button><button class="button" type="button" id="genai-health">Check GenAI health</button></form><pre id="genai-result" class="code" aria-live="polite">No GenAI discovery requested.</pre></section>`;
  document.querySelector('#genai-indexes').addEventListener('click', async () => {
    const workspace = encodeURIComponent(document.querySelector('#genai-discovery-form [name="workspace"]').value);
    const output = document.querySelector('#genai-result');
    try { output.textContent = json(await get(`/v1/workspaces/${workspace}/genai/indexes`)); }
    catch (error) { output.textContent = `Index listing failed: ${esc(error.message)}`; }
  });
  document.querySelector('#genai-prompts').addEventListener('click', async () => {
    const workspace = encodeURIComponent(document.querySelector('#genai-discovery-form [name="workspace"]').value);
    const output = document.querySelector('#genai-result');
    try { output.textContent = json(await get(`/v1/workspaces/${workspace}/genai/prompts`)); }
    catch (error) { output.textContent = `Prompt listing failed: ${esc(error.message)}`; }
  });
  document.querySelector('#genai-health').addEventListener('click', async () => {
    const workspace = encodeURIComponent(document.querySelector('#genai-discovery-form [name="workspace"]').value);
    const output = document.querySelector('#genai-result');
    try { output.textContent = json(await get(`/v1/workspaces/${workspace}/genai/health`)); }
    catch (error) { output.textContent = `Health check failed: ${esc(error.message)}`; }
  });
}

document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'genai-discovery-form') return;
  event.preventDefault();
  const workspace = encodeURIComponent(String(new FormData(form).get('workspace')));
  const output = document.querySelector('#genai-result');
  try { output.textContent = json(await get(`/v1/workspaces/${workspace}/genai/providers`)); }
  catch (error) { output.textContent = `Discovery failed: ${esc(error.message)}`; }
});

setTimeout(() => { window.addEventListener('hashchange', renderGenAI); renderGenAI(); }, 0);
