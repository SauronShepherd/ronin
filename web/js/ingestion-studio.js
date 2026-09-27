import {get, post} from './api.js';
import {esc, json, page} from './dom.js';

export async function ingestionStudio() {
  const view = document.querySelector('#view');
  view.innerHTML = `${page('Ingestion Studio', 'DATA PLANE')}<section class="panel"><h2>Connector capabilities</h2><pre id="ingestion-capabilities" class="code" aria-live="polite">Loading…</pre></section><section class="panel"><h2>Ingestion sync</h2><form id="ingestion-preview-form"><label>Definition JSON<textarea id="ingestion-definition" class="field sql-editor" rows="10" required>{"id":"preview-1","connector_id":"http-json","connection_ref":"connection://demo","asset_ref":"asset://demo","destination_ref":"asset://preview","checkpoint_identity":"preview-1","mode":"snapshot"}</textarea></label><div class="toolbar"><button class="button" type="button" id="ingestion-plan-button">Plan sync</button><button class="button" type="button" id="ingestion-health-button">Checkpoint health</button><button class="button primary">Preview source</button></div></form><pre id="ingestion-preview-result" class="code" aria-live="polite">No operation requested.</pre></section>`;
  try {
    document.querySelector('#ingestion-capabilities').textContent = json(await get('/v1/platform/connectors'));
  } catch (error) {
    document.querySelector('#ingestion-capabilities').textContent = `Capabilities unavailable: ${esc(error.message)}`;
  }
}

document.addEventListener('submit', async event => {
  if (event.target.id !== 'ingestion-preview-form') return;
  event.preventDefault();
  const result = document.querySelector('#ingestion-preview-result');
  try {
    const payload = JSON.parse(document.querySelector('#ingestion-definition').value);
    result.textContent = json(await post('/v1/platform/connectors/preview', payload));
  } catch (error) {
    result.textContent = `Preview failed: ${error.message}`;
  }
});

document.addEventListener('click', async event => {
  const button = event.target.closest('#ingestion-plan-button, #ingestion-health-button');
  if (!button) return;
  const result = document.querySelector('#ingestion-preview-result');
  try {
    const definition = JSON.parse(document.querySelector('#ingestion-definition').value);
    const path = button.id === 'ingestion-plan-button' ? '/v1/platform/connectors/plan' : '/v1/platform/connectors/checkpoint-health';
    const payload = button.id === 'ingestion-plan-button' ? definition : { checkpoint_identity: definition.checkpoint_identity };
    result.textContent = json(await post(path, payload));
  } catch (error) { result.textContent = `Operation failed: ${error.message}`; }
});

window.addEventListener('hashchange', () => {
  if (location.hash.slice(1) === 'ingestion') ingestionStudio();
});
if (location.hash.slice(1) === 'ingestion') setTimeout(ingestionStudio, 0);
