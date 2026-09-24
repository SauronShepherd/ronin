import { get, post } from './api.js';
import { esc, json } from './dom.js';

function workspace() {
  return encodeURIComponent(document.querySelector('#ml-workspace')?.value.trim() || 'default');
}

function inject() {
  if (location.hash.slice(1) !== 'mlstudio' || document.querySelector('#ml-feature-form')) return;
  const target = document.querySelector('#ml-output');
  if (!target) return;
  target.insertAdjacentHTML('beforebegin', `<section class="panel"><h2>Feature definitions</h2>
    <form id="ml-feature-form" class="toolbar"><input class="field" name="id" placeholder="customer_age" required><input class="field" name="version" value="1" required><input class="field" name="dataset" placeholder="customers" required><input class="field" name="column" placeholder="age" required><select class="field" name="type"><option>numeric</option><option>categorical</option><option>text</option></select><button class="button primary">Publish feature</button><button class="button" type="button" data-ml-feature-action="list">Refresh</button></form><pre id="ml-features-result" class="code" aria-live="polite">No feature operation executed.</pre></section>`);
}

async function list() {
  const output = document.querySelector('#ml-features-result');
  if (!output) return;
  try { output.textContent = json(await get(`/v1/ml-studio/features?workspace_id=${workspace()}`)); }
  catch (error) { output.textContent = `Feature lookup failed: ${error.message}`; }
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'ml-feature-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const output = document.querySelector('#ml-features-result');
  const body = { schema: 'ronin.ml-feature/v1', id: String(data.get('id')).trim(), version: String(data.get('version')).trim(), dataset: { asset_id: String(data.get('dataset')).trim(), version: '1' }, columns: [{ name: String(data.get('column')).trim(), type: String(data.get('type')) }] };
  try { output.textContent = json(await post(`/v1/ml-studio/features?workspace_id=${workspace()}`, body)); await list(); }
  catch (error) { output.textContent = `Feature publication failed: ${error.message}`; }
});

document.addEventListener('click', event => { if (event.target.closest('[data-ml-feature-action="list"]')) list(); });
const observer = new MutationObserver(inject);
observer.observe(document.body, { childList: true, subtree: true });
setTimeout(inject, 0);
