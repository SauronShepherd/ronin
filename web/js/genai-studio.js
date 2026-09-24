import { get, post } from './api.js';
import { esc, json, page } from './dom.js';

function renderGenAI() {
  if (location.hash.slice(1) !== 'genai') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('GenAI Studio', 'GENAI OPERATIONS')}<section class="panel"><form id="genai-discovery-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Provider<input class="field" name="provider" value="default" required></label><label>Model<input class="field" name="model" value="chat" required></label><label>Agent<input class="field" name="agent" value="default" required></label><label>Run ID<input class="field" name="run" value="run-1" required></label><button class="button primary" type="submit">Discover providers</button><button class="button" type="button" id="genai-prompts">List prompts</button><button class="button" type="button" id="genai-indexes">List vector indexes</button><button class="button" type="button" id="genai-evaluations">List RAG evaluations</button><button class="button" type="button" id="genai-agent-runs">List agent runs</button><button class="button" type="button" id="genai-run-evidence">Show run evidence</button><button class="button" type="button" id="genai-qualification">Qualify provider</button><button class="button" type="button" id="genai-health">Check GenAI health</button></form><pre id="genai-result" class="code" aria-live="polite">No GenAI discovery requested.</pre></section>`;
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
  document.querySelector('#genai-evaluations').addEventListener('click', async () => {
    const workspace = encodeURIComponent(document.querySelector('#genai-discovery-form [name="workspace"]').value);
    const output = document.querySelector('#genai-result');
    try { output.textContent = json(await get(`/v1/workspaces/${workspace}/genai/rag/evaluations`)); }
    catch (error) { output.textContent = `Evaluation listing failed: ${esc(error.message)}`; }
  });
  document.querySelector('#genai-qualification').addEventListener('click', async () => {
    const form = document.querySelector('#genai-discovery-form');
    const workspace = encodeURIComponent(form.querySelector('[name="workspace"]').value);
    const provider = encodeURIComponent(form.querySelector('[name="provider"]').value);
    const output = document.querySelector('#genai-result');
    try {
      output.textContent = json(await post(`/v1/workspaces/${workspace}/genai/providers/${provider}/qualification`, {
        model_id: form.querySelector('[name="model"]').value,
        capabilities: ['chat'],
      }));
    } catch (error) { output.textContent = `Qualification failed: ${esc(error.message)}`; }
  });
  document.querySelector('#genai-agent-runs').addEventListener('click', async () => {
    const form = document.querySelector('#genai-discovery-form');
    const workspace = encodeURIComponent(form.querySelector('[name="workspace"]').value);
    const agent = encodeURIComponent(form.querySelector('[name="agent"]').value);
    const output = document.querySelector('#genai-result');
    try { output.textContent = json(await get(`/v1/workspaces/${workspace}/genai/agents/${agent}/runs`)); }
    catch (error) { output.textContent = `Agent runs failed: ${esc(error.message)}`; }
  });
  document.querySelector('#genai-run-evidence').addEventListener('click', async () => {
    const form = document.querySelector('#genai-discovery-form');
    const workspace = encodeURIComponent(form.querySelector('[name="workspace"]').value);
    const run = encodeURIComponent(form.querySelector('[name="run"]').value);
    const output = document.querySelector('#genai-result');
    try { output.textContent = json(await get(`/v1/workspaces/${workspace}/genai/runs/${run}`)); }
    catch (error) { output.textContent = `Run evidence failed: ${esc(error.message)}`; }
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
