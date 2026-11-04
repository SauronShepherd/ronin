import { get } from './api.js';
import { json, page } from './dom.js';

export function finopsStudio() {
  if (location.hash.slice(1) !== 'finops') return;
  const view = document.querySelector('#view'); if (!view) return;
  view.innerHTML = `${page('FinOps Studio', 'USAGE · COSTS · BUDGETS')}<section class="panel"><form id="finops-form" class="toolbar"><input class="field" name="workspace" value="default" required><input class="field" type="datetime-local" name="period_start" aria-label="Period start"><input class="field" type="datetime-local" name="period_end" aria-label="Period end"><button class="button" name="kind" value="usage">Load usage</button><button class="button" name="kind" value="costs">Load costs</button><button class="button primary" name="kind" value="budgets">Load budgets</button></form><pre id="finops-result" class="code">No ledger data loaded.</pre></section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target; if (!(form instanceof HTMLFormElement) || form.id !== 'finops-form') return;
  event.preventDefault(); const data = new FormData(form);
  if (event.submitter instanceof HTMLButtonElement && event.submitter.name) data.set(event.submitter.name, event.submitter.value);
  const kind = String(data.get('kind'));
  const periodStart = String(data.get('period_start') || '');
  const periodEnd = String(data.get('period_end') || '');
  const result = document.querySelector('#finops-result');
  if (kind !== 'budgets' && (!periodStart || !periodEnd)) {
    result.textContent = 'Choose both a period start and end to load usage or costs.';
    return;
  }
  const workspace = encodeURIComponent(String(data.get('workspace')));
  const query = kind === 'budgets' ? '' : `?period_start=${encodeURIComponent(periodStart)}&period_end=${encodeURIComponent(periodEnd)}`;
  try { result.textContent = json(await get(`/v1/workspaces/${workspace}/finops/${kind}${query}`)); }
  catch (error) { result.textContent = `FinOps operation failed: ${error.message}`; }
});

setTimeout(() => { window.addEventListener('hashchange', finopsStudio); if (location.hash.slice(1) === 'finops') finopsStudio(); }, 0);
