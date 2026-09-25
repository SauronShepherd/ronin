import {get, post} from './api.js';
import {esc, page, status} from './dom.js';

export function qualityStudio() {
  const view = document.querySelector('#view');
  view.innerHTML = `${page('Quality Studio', 'DATA QUALITY')}<div class="panel"><h2>Quality evidence</h2><p class="muted">Inspect the latest status and immutable run history for an asset revision.</p><form id="quality-form" class="toolbar"><input class="field" id="quality-workspace" value="default" placeholder="Workspace" required><input class="field" id="quality-asset" placeholder="Asset ID" required><input class="field" id="quality-version" value="v1" placeholder="Version" required><button class="button primary">Load state</button></form><div id="quality-result" class="loading" aria-live="polite">Enter an asset revision to inspect.</div></div>`;
}

export async function loadQualityState() {
  const result = document.querySelector('#quality-result');
  const workspace = encodeURIComponent(document.querySelector('#quality-workspace').value);
  const asset = encodeURIComponent(document.querySelector('#quality-asset').value);
  const version = encodeURIComponent(document.querySelector('#quality-version').value);
  result.textContent = 'Loading…';
  try {
    const data = await get(`/v1/workspaces/${workspace}/quality/state/${asset}/${version}`);
    result.innerHTML = `<div class="grid three"><div class="card"><h3>Latest status</h3>${status(data.latest_status || 'unknown')}<p>${esc(data.latest_run_id || 'No runs')}</p></div><div class="card"><h3>Runs</h3><strong>${data.run_count ?? 0}</strong><p class="muted">durable evidence</p></div></div><div class="table-wrap"><table><caption class="sr-only">Quality run history</caption><thead><tr><th>Run</th><th>Asset</th><th>Status</th></tr></thead><tbody>${(data.history || []).map(run => `<tr><td>${esc(run.run_id)}</td><td>${esc(run.asset?.asset_id || '—')}@${esc(run.asset?.version || '—')}</td><td>${status(run.status)}</td></tr>`).join('') || '<tr><td colspan="3">No quality runs.</td></tr>'}</tbody></table></div>`;
  } catch (error) {
    result.innerHTML = `<div class="error"><strong>Could not load quality state.</strong><p>${esc(error.message)}</p></div>`;
  }
}

function qualityValues() {
  return {
    workspace: encodeURIComponent(document.querySelector('#quality-workspace').value),
    asset: encodeURIComponent(document.querySelector('#quality-asset').value),
    version: encodeURIComponent(document.querySelector('#quality-version').value),
  };
}

document.addEventListener('click', async event => {
  const action = event.target.closest('[data-quality-action]')?.dataset.qualityAction;
  if (!action) return;
  const result = document.querySelector('#quality-result');
  const values = qualityValues();
  result.textContent = 'Loading…';
  try {
    if (action === 'contract') {
      const data = await get(`/v1/workspaces/${values.workspace}/quality/contracts/${values.asset}/${values.version}`);
      result.textContent = JSON.stringify(data, null, 2);
    } else {
      const rows = JSON.parse(document.querySelector('#quality-rows').value || '[]');
      const data = await post(`/v1/workspaces/${values.workspace}/quality/runs`, {
        asset: {asset_id: decodeURIComponent(values.asset), version: decodeURIComponent(values.version)},
        rows, run_id: `studio-${Date.now()}`,
      });
      result.textContent = JSON.stringify(data, null, 2);
      await loadQualityState();
    }
  } catch (error) {
    result.innerHTML = `<div class="error"><strong>Quality operation failed.</strong><p>${esc(error.message)}</p></div>`;
  }
});

setInterval(() => {
  const form = document.querySelector('#quality-form');
  if (!form || form.querySelector('[data-quality-action]')) return;
  form.insertAdjacentHTML('beforeend', '<button class="button" type="button" data-quality-action="contract">Load contract</button><button class="button" type="button" data-quality-action="run">Dry-run rows</button><textarea class="field" id="quality-rows" rows="1" placeholder="Rows JSON, e.g. [{&quot;id&quot;:1}]"></textarea>');
}, 100);
