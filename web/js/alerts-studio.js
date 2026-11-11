import { get, post } from './api.js';
import { esc, json, page } from './dom.js';

const activeWorkspace = () => globalThis.roninStudioContext?.workspace || sessionStorage.getItem('ronin.workspace') || 'default';
let lastAlertAction = 'list';

function renderAlertDecision(result, action, payload) {
  const state = payload?.state || {};
  const status = state.status || payload?.status || 'unknown';
  const metric = payload?.metric;
  const value = metric?.value === undefined ? 'no metric value' : `metric ${metric.value}`;
  const title = action === 'evaluate' ? `Rule ${payload?.rule_id || 'unknown'} evaluated` : `Alert ${payload?.rule_id || 'unknown'} acknowledged`;
  const copy = action === 'evaluate' ? `${status} · ${value} · ${payload?.changed ? 'state changed' : 'no state change'}` : `${status} · operator acknowledgement recorded`;
  result.innerHTML = `<div class="alert-decision-summary"><strong>${esc(title)}</strong><span>${esc(copy)}</span><p>Review the rule and fingerprint before using this signal downstream.</p></div><details class="alerts-raw"><summary>Advanced: raw alert response</summary><pre class="code"></pre></details>`;
  result.querySelector('pre').textContent = json(payload);
}
function renderAlertItems(result, items, instances) {
  if (!items.length) { result.innerHTML = '<div class="empty">No alert states found.</div>'; return; }
  const columns = instances
    ? [['rule_id', 'Rule'], ['status', 'State'], ['value', 'Value'], ['fingerprint', 'Fingerprint'], ['acknowledged_at', 'Acknowledged']]
    : [['id', 'Rule'], ['state', 'State'], ['severity', 'Severity'], ['metric', 'Metric']];
  const cell = (item, key) => (item[key] ?? (key === 'rule_id' ? item.id : key === 'status' ? item.state : key === 'metric' ? item.name : '')) || '—';
  result.innerHTML = `<div class="table-wrap"><table><caption class="sr-only">${instances ? 'Alert instances' : 'Alert rules'}</caption><thead><tr>${columns.map(([, label]) => `<th>${label}</th>`).join('')}</tr></thead><tbody>${items.map(item => `<tr>${columns.map(([key]) => `<td>${esc(cell(item, key))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

export function alertsStudio() {
  if (location.hash.slice(1) !== 'alerts') return;
  const view = document.querySelector('#view');
  if (!view) return;
view.innerHTML = `${page('Monitoring & Alerts', 'OBSERVABILITY')}<section class="panel alerts-hero"><div><p class="eyebrow">OBSERVABILITY CONTROL PLANE</p><h2>Turn a signal into a governed decision.</h2><p>Inspect rules, evaluate the current state and acknowledge a known alert without losing its workspace or fingerprint context.</p></div><div class="alerts-hero-signals"><span class="status blue">Workspace scoped</span><span class="status green">Reviewable action</span></div></section><section class="alerts-workbench"><section class="panel"><div class="alerts-section-heading"><div><p class="eyebrow">CONTROL CONTEXT</p><h2>Choose the signal before the action.</h2><p class="muted">The workspace, rule and fingerprint remain visible for every operation.</p></div><span class="alerts-section-index">01</span></div><form id="alerts-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="${esc(activeWorkspace())}" required></label><label>Rule ID<input class="field" name="rule_id" placeholder="rule-1"></label><label>Fingerprint<input class="field" name="fingerprint" placeholder="sha256 fingerprint"></label><button class="button" name="action" value="list">List rules</button><button class="button" name="action" value="instances">List states</button><button class="button primary" name="action" value="evaluate">Evaluate rule</button><button class="button" name="action" value="acknowledge">Acknowledge alert</button></form></section><aside class="panel alerts-insight"><p class="eyebrow">OPERATING NOTE</p><h2>Keep the decision traceable.</h2><p>Evaluation shows current evidence; acknowledgement records operator intent against the same rule and fingerprint.</p></aside></section><section class="panel alerts-result-panel"><div class="alerts-section-heading"><div><p class="eyebrow">EVIDENCE</p><h2>Operator result</h2><p class="muted">Responses stay bounded and visible after every action.</p></div><span class="alerts-section-index">02</span></div><div id="alerts-result" class="code" aria-live="polite">No alert operation executed.</div></section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'alerts-form') return;
  event.preventDefault();
  const data = new FormData(form);
  if (event.submitter instanceof HTMLButtonElement && event.submitter.name) {
    data.set(event.submitter.name, event.submitter.value);
  }
  const workspaceValue = String(data.get('workspace') || '').trim();
  const result = document.querySelector('#alerts-result');
  try {
    if (!workspaceValue) throw new Error('Workspace is required');
    const workspace = encodeURIComponent(workspaceValue);
    const action = String(data.get('action'));
    lastAlertAction = action;
    const evaluating = action === 'evaluate';
    const acknowledging = action === 'acknowledge';
    const instances = action === 'instances';
    if (!['list', 'instances', 'evaluate', 'acknowledge'].includes(action)) {
      throw new Error('Unsupported alert operation');
    }
    const payload = evaluating
      ? await post(`/v1/workspaces/${workspace}/alerts/evaluate`, { rule_id: String(data.get('rule_id')) })
      : acknowledging
        ? await post(`/v1/workspaces/${workspace}/alerts/acknowledge`, { rule_id: String(data.get('rule_id')), fingerprint: String(data.get('fingerprint')) })
        : instances
          ? await get(`/v1/workspaces/${workspace}/alerts/instances`)
        : await get(`/v1/workspaces/${workspace}/alerts/rules`);
    if (evaluating || acknowledging) { renderAlertDecision(result, action, payload); return; }
    if (!Array.isArray(payload.items)) { result.textContent = json(payload); return; }
    renderAlertItems(result, payload.items, instances);
  } catch (error) {
    result.innerHTML = `<div class="error"><strong>Alert operation failed.</strong><p>${esc(error.message)}</p><button class="button" type="button" data-alert-retry>Retry this operation</button></div>`;
  }
});

document.addEventListener('click', event => {
  if (!event.target.closest('[data-alert-retry]')) return;
  document.querySelector(`#alerts-form [name="action"][value="${CSS.escape(lastAlertAction)}"]`)?.click();
});

setTimeout(() => {
  window.addEventListener('hashchange', alertsStudio);
  if (location.hash.slice(1) === 'alerts') alertsStudio();
}, 0);
