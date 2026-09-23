import { get } from './api.js';
import { json, page } from './dom.js';

export function finopsStudio() {
  if (location.hash.slice(1) !== 'finops') return;
  const view = document.querySelector('#view'); if (!view) return;
  view.innerHTML = `${page('FinOps Studio', 'USAGE · COSTS · BUDGETS')}<section class="panel"><form id="finops-form" class="toolbar"><input class="field" name="workspace" value="default" required><input class="field" type="datetime-local" name="period_start" required><input class="field" type="datetime-local" name="period_end" required><button class="button" name="kind" value="usage">Load usage</button><button class="button" name="kind" value="costs">Load costs</button><button class="button primary" name="kind" value="budgets">Load budgets</button></form><pre id="finops-result" class="code">No ledger data loaded.</pre></section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target; if (!(form instanceof HTMLFormElement) || form.id !== 'finops-form') return;
  event.preventDefault(); const data = new FormData(form); const kind = String(data.get('kind'));
  const workspace = encodeURIComponent(String(data.get('workspace')));
  const query = kind === 'budgets' ? '' : `?period_start=${encodeURIComponent(String(data.get('period_start')))}&period_end=${encodeURIComponent(String(data.get('period_end')))}`;
  try { document.querySelector('#finops-result').textContent = json(await get(`/v1/workspaces/${workspace}/finops/${kind}${query}`)); }
  catch (error) { document.querySelector('#finops-result').textContent = `FinOps operation failed: ${error.message}`; }
});

setTimeout(() => { window.addEventListener('hashchange', finopsStudio); if (location.hash.slice(1) === 'finops') finopsStudio(); }, 0);
