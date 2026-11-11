import { get } from './api.js';
import { esc, json, page } from './dom.js';

const activeWorkspace = () => globalThis.roninStudioContext?.workspace || sessionStorage.getItem('ronin.workspace') || 'default';
let lastFinopsRequest = null;

export function finopsStudio() {
  if (location.hash.slice(1) !== 'finops') return;
  const view = document.querySelector('#view'); if (!view) return;
  view.innerHTML = `${page('FinOps Studio', 'USAGE · COSTS · BUDGETS')}<section class="panel workspace-hero"><div><p class="eyebrow">FINOPS CONTROL PLANE</p><h2>Make runtime spend explainable before it becomes a surprise.</h2><p>Inspect usage, costs and budget posture inside the active workspace and keep the selected period attached to the result.</p></div><div class="workspace-hero-aside"><span class="status blue">Workspace scoped</span><p>Budgets do not require a period; usage and costs do.</p></div></section><section class="alerts-workbench"><section class="panel"><div class="alerts-section-heading"><div><p class="eyebrow">LEDGER CONTEXT</p><h2>Choose the measure and its window.</h2><p class="muted">The request stays bounded and reviewable.</p></div><span class="alerts-section-index">01</span></div><form id="finops-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="${esc(activeWorkspace())}" required></label><label>Period start<input class="field" type="datetime-local" name="period_start" aria-label="Period start"></label><label>Period end<input class="field" type="datetime-local" name="period_end" aria-label="Period end"></label><button class="button" name="kind" value="usage">Load usage</button><button class="button" name="kind" value="costs">Load costs</button><button class="button primary" name="kind" value="budgets">Load budgets</button></form></section><aside class="panel alerts-insight"><p class="eyebrow">OPERATING NOTE</p><h2>Budget posture is not telemetry.</h2><p>Ronin keeps returned ledger evidence visible and does not infer spend from a missing or failed response.</p></aside></section><section class="panel alerts-result-panel"><div class="alerts-section-heading"><div><p class="eyebrow">EVIDENCE</p><h2>Ledger result</h2><p class="muted">The server response remains available for review.</p></div><span class="alerts-section-index">02</span></div><div id="finops-result" class="code" aria-live="polite">No ledger data loaded.</div></section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target; if (!(form instanceof HTMLFormElement) || form.id !== 'finops-form') return;
  event.preventDefault(); const data = new FormData(form);
  if (event.submitter instanceof HTMLButtonElement && event.submitter.name) data.set(event.submitter.name, event.submitter.value);
  const kind = String(data.get('kind'));
  const periodStart = String(data.get('period_start') || '');
  const periodEnd = String(data.get('period_end') || '');
  const result = document.querySelector('#finops-result');
  lastFinopsRequest = { kind, periodStart, periodEnd };
  if (kind !== 'budgets' && (!periodStart || !periodEnd)) {
    result.textContent = 'Choose both a period start and end to load usage or costs.';
    return;
  }
  const workspace = encodeURIComponent(String(data.get('workspace')));
  const query = kind === 'budgets' ? '' : `?period_start=${encodeURIComponent(periodStart)}&period_end=${encodeURIComponent(periodEnd)}`;
  try { result.textContent = json(await get(`/v1/workspaces/${workspace}/finops/${kind}${query}`)); }
  catch (error) { result.innerHTML = `<div class="error"><strong>FinOps operation failed.</strong><p>${esc(error.message)}</p><button class="button" type="button" data-finops-retry>Retry this request</button></div>`; }
});

document.addEventListener('click', event => {
  if (!event.target.closest('[data-finops-retry]') || !lastFinopsRequest) return;
  const button = document.querySelector(`#finops-form [name="kind"][value="${CSS.escape(lastFinopsRequest.kind)}"]`);
  button?.click();
});

setTimeout(() => { window.addEventListener('hashchange', finopsStudio); if (location.hash.slice(1) === 'finops') finopsStudio(); }, 0);
