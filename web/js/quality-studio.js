import {get, post, put} from './api.js';
import {esc, page, status} from './dom.js';

export function qualityStudio() {
  const view = document.querySelector('#view');
  view.innerHTML = `${page('Quality Studio', 'DATA QUALITY')}<section class="quality-hero panel"><div><p class="eyebrow">PROMOTION CONTROL</p><h2>Make data quality a decision, not a dashboard.</h2><p>Inspect one governed asset revision, understand the latest gate, then author or dry-run the contract that explains the decision.</p></div><div class="quality-hero-signal"><span id="quality-mode" class="status amber">Review required</span><p id="quality-hero-note">No asset revision is selected. Results stay scoped until you choose one.</p></div></section><div class="quality-workbench"><section class="quality-inspector panel"><div class="quality-section-heading"><div><span class="quality-section-index">01</span><h2>Inspect an asset revision</h2><p class="muted">The scope below is the boundary for every read and write in this Studio.</p></div><span class="quality-boundary">workspace · asset · version</span></div><form id="quality-form" class="quality-scope-form"><label>Workspace<input class="field" id="quality-workspace" value="default" placeholder="Workspace" required></label><label>Asset ID<input class="field" id="quality-asset" placeholder="Asset ID" required></label><label>Version<input class="field" id="quality-version" value="v1" placeholder="Version" required></label><button class="button primary">Load state</button></form><div id="quality-result" class="quality-result loading" aria-live="polite">Enter an asset revision to inspect.</div></section><aside class="quality-posture panel"><p class="eyebrow">DECISION POSTURE</p><h2>Evidence before promotion.</h2><p class="muted">A passed rule is evidence for this revision. It is not a blanket certification of the source or of production suitability.</p><ol class="quality-playbook"><li><strong>Scope</strong><span>Choose the exact governed revision.</span></li><li><strong>Author</strong><span>Save a versioned contract with explicit blocking rules.</span></li><li><strong>Run</strong><span>Dry-run rows and review the durable result.</span></li></ol><div class="quality-posture-note"><span aria-hidden="true">◈</span><span>Use the gate state to decide what can move next; do not infer quality from an empty history.</span></div></aside></div><section class="quality-authoring panel"><div class="quality-section-heading"><div><span class="quality-section-index">02</span><h2>Author and test the contract</h2><p class="muted">The editor is deliberately separate from inspection so a review never hides a mutation.</p></div><span class="quality-boundary">versioned · bounded · auditable</span></div><div id="quality-controls" class="quality-controls"><div class="quality-controls-empty">Load the contract editor when you are ready to make a governed change.</div></div></section>`;
}

export async function loadQualityState() {
  const result = document.querySelector('#quality-result');
  const workspace = encodeURIComponent(document.querySelector('#quality-workspace').value);
  const asset = encodeURIComponent(document.querySelector('#quality-asset').value);
  const version = encodeURIComponent(document.querySelector('#quality-version').value);
  result.textContent = 'Loading…';
  try {
    const data = await get(`/v1/workspaces/${workspace}/quality/state/${asset}/${version}`);
    const latest = data.latest_run || {};
    const latestStatus = data.latest_status || latest.status || 'unknown';
    const ruleResults = latest.results || [];
    const mode = document.querySelector('#quality-mode');
    const heroNote = document.querySelector('#quality-hero-note');
    if (mode) mode.outerHTML = status(latestStatus).replace('<span ', '<span id="quality-mode" ');
    if (heroNote) heroNote.textContent = `${data.run_count ?? 0} durable run${data.run_count === 1 ? '' : 's'} recorded for this revision.`;
    result.className = 'quality-result';
    result.innerHTML = `<div class="quality-result-heading"><div><p class="eyebrow">LATEST DECISION</p><h3>${esc(data.latest_run_id || 'No runs recorded')}</h3><p class="muted">${esc(latest.execution_ref || 'No execution reference recorded.')}</p></div>${status(latestStatus)}</div><div class="grid three"><div class="card"><h3>Gate state</h3>${status(latestStatus)}<p class="muted">latest durable result</p></div><div class="card"><h3>Run history</h3><strong>${data.run_count ?? 0}</strong><p class="muted">recorded executions</p></div><div class="card"><h3>Rule evidence</h3><strong>${ruleResults.length}</strong><p class="muted">latest rule results</p></div></div><section class="quality-evidence-section"><div class="quality-subheading"><div><h3>Latest rule evidence</h3><p class="muted">Review each rule before changing the promotion decision.</p></div><span class="quality-boundary">${esc(latestStatus)}</span></div><div class="table-wrap"><table><caption class="sr-only">Latest quality rule evidence</caption><thead><tr><th>Rule</th><th>Status</th><th>Message</th></tr></thead><tbody>${ruleResults.map(rule => `<tr><td><strong>${esc(rule.rule_id)}</strong></td><td>${status(rule.status)}</td><td>${esc(rule.message || '—')}</td></tr>`).join('') || '<tr><td colspan="3">No latest rule results.</td></tr>'}</tbody></table></div></section><section class="quality-evidence-section"><div class="quality-subheading"><div><h3>Immutable run history</h3><p class="muted">The trail stays attached to this asset revision.</p></div></div><div class="table-wrap"><table><caption class="sr-only">Quality run history</caption><thead><tr><th>Run</th><th>Asset</th><th>Status</th></tr></thead><tbody>${(data.history || []).map(run => `<tr><td><strong>${esc(run.run_id)}</strong></td><td>${esc(run.asset?.asset_id || '—')}@${esc(run.asset?.version || '—')}</td><td>${status(run.status)}</td></tr>`).join('') || '<tr><td colspan="3">No quality runs.</td></tr>'}</tbody></table></div></section>`;
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
      const editor = document.querySelector('#quality-contract');
      if (editor) editor.value = JSON.stringify(data, null, 2);
      result.textContent = JSON.stringify(data, null, 2);
    } else if (action === 'save-contract') {
      const contract = JSON.parse(document.querySelector('#quality-contract').value || '{}');
      const data = await put(`/v1/workspaces/${values.workspace}/quality/contracts/${values.asset}/${values.version}`, contract);
      result.textContent = JSON.stringify(data, null, 2);
    } else {
      const rows = JSON.parse(document.querySelector('#quality-rows').value || '[]');
      const data = await post(`/v1/workspaces/${values.workspace}/quality/runs`, {
        asset: {asset_id: decodeURIComponent(values.asset), version: decodeURIComponent(values.version)},
        rows, run_id: `studio-${Date.now()}`,
        execution_ref: document.querySelector('#quality-execution-ref').value.trim() || null,
        enforce_blocking: document.querySelector('#quality-enforce-blocking').checked,
      });
      result.textContent = JSON.stringify(data, null, 2);
      await loadQualityState();
    }
  } catch (error) {
    result.innerHTML = `<div class="error"><strong>Quality operation failed.</strong><p>${esc(error.message)}</p></div>`;
  }
});

function ensureQualityControls() {
  const form = document.querySelector('#quality-form');
  const controls = document.querySelector('#quality-controls');
  if (!form || !controls || controls.querySelector('[data-quality-action]')) return;
  controls.innerHTML = '<div class="quality-editor-grid"><label>Execution reference<input class="field" id="quality-execution-ref" placeholder="optional review or pipeline ID"></label><label class="quality-blocking"><input type="checkbox" id="quality-enforce-blocking"> Enforce blocking policy<span class="muted">A blocked rule returns a visible conflict instead of a false pass.</span></label></div><div class="quality-editor-columns"><label><span class="quality-editor-label">Contract JSON</span><textarea class="field" id="quality-contract" rows="8" placeholder="Load a contract or author one here"></textarea></label><label><span class="quality-editor-label">Rows JSON for dry-run</span><textarea class="field" id="quality-rows" rows="8" placeholder="[{&quot;id&quot;:1}]"></textarea></label></div><div class="quality-editor-actions"><div><button class="button" type="button" data-quality-action="contract">Load contract</button><button class="button" type="button" data-quality-action="save-contract">Save contract</button><button class="button primary" type="button" data-quality-action="run">Dry-run rows</button></div><p class="muted">Changes stay scoped to the selected workspace, asset and version.</p></div>';
}

const qualityView = document.querySelector('#view');
if (qualityView) {
  new MutationObserver(ensureQualityControls).observe(qualityView, {childList: true, subtree: true});
  ensureQualityControls();
}
