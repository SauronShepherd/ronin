import { get, post } from './api.js';
import { esc, json, page } from './dom.js';

export function alertsStudio() {
  if (location.hash.slice(1) !== 'alerts') return;
  const view = document.querySelector('#view');
  if (!view) return;
view.innerHTML = `${page('Monitoring & Alerts', 'OBSERVABILITY')}<section class="panel"><form id="alerts-form" class="toolbar"><label>Workspace<input class="field" name="workspace" value="default" required></label><label>Rule ID<input class="field" name="rule_id" placeholder="rule-1"></label><label>Fingerprint<input class="field" name="fingerprint" placeholder="sha256 fingerprint"></label><button class="button" name="action" value="list">List rules</button><button class="button" name="action" value="instances">List states</button><button class="button primary" name="action" value="evaluate">Evaluate rule</button><button class="button" name="action" value="acknowledge">Acknowledge alert</button></form><pre id="alerts-result" class="code" aria-live="polite">No alert operation executed.</pre></section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'alerts-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const workspaceValue = String(data.get('workspace') || '').trim();
  const result = document.querySelector('#alerts-result');
  try {
    if (!workspaceValue) throw new Error('Workspace is required');
    const workspace = encodeURIComponent(workspaceValue);
    const action = String(data.get('action'));
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
    if (evaluating || !Array.isArray(payload.items)) { result.textContent = json(payload); return; }
    result.innerHTML = payload.items.length
      ? `<div class="table-wrap"><table><caption class="sr-only">Alert rules</caption><thead><tr><th>Rule</th><th>State</th><th>Severity</th><th>Metric</th></tr></thead><tbody>${payload.items.map((rule) => `<tr><td>${esc(rule.id || '')}</td><td>${esc(rule.state || rule.status || '')}</td><td>${esc(rule.severity || '')}</td><td>${esc(rule.metric || rule.name || '')}</td></tr>`).join('')}</tbody></table></div>`
      : '<div class="empty">No alert rules found.</div>';
  } catch (error) {
    result.textContent = `Alert operation failed: ${error.message}`;
  }
});

setTimeout(() => {
  window.addEventListener('hashchange', alertsStudio);
  if (location.hash.slice(1) === 'alerts') alertsStudio();
}, 0);
