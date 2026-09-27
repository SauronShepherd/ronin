import { get, post, put } from './api.js';
import { json, page } from './dom.js';

const field = (label, name, value) => `<label>${label}<input class="field" name="${name}" value="${value}" required></label>`;

export function schedulerStudio() {
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Scheduler Studio', 'ORCHESTRATION')}<section class="panel"><form id="scheduler-form"><div class="grid three">${field('Workspace', 'workspace', 'default')}${field('Schedule ID', 'schedule_id', 'daily')}${field('Workflow ID', 'workflow_id', 'main')}${field('Run ID', 'run_id', 'run-1')}${field('Idempotency key', 'idempotency_key', 'studio-run-1')}${field('Cron', 'cron', '0 0 * * *')}${field('Event trigger ID', 'trigger_id', 'on-data')}${field('Event type', 'event_type', 'manual')}${field('Event source', 'source_ref', 'studio')}${field('Backfill ID', 'backfill_id', 'backfill-1')}${field('After', 'after', '2026-01-01T00:00:00.000000Z')}${field('Backfill start', 'start_at', '2026-01-01T00:00:00.000000Z')}${field('Backfill end', 'end_at', '2026-01-02T00:00:00.000000Z')}</div><div class="toolbar"><button class="button" data-scheduler-action="list" type="button">List schedules</button><button class="button primary" data-scheduler-action="save" type="button">Save schedule</button><button class="button" data-scheduler-action="next-runs" type="button">Preview next runs</button><button class="button" data-scheduler-action="history" type="button">View history</button><button class="button primary" data-scheduler-action="run" type="button">Run workflow</button><button class="button" data-scheduler-action="inspect-run" type="button">Inspect run</button><button class="button" data-scheduler-action="events" type="button">List event triggers</button><button class="button primary" data-scheduler-action="save-event" type="button">Save event trigger</button><button class="button" data-scheduler-action="ingest" type="button">Ingest event</button><button class="button" data-scheduler-action="backfill" type="button">Start backfill</button><button class="button danger" data-scheduler-action="cancel" type="button">Cancel backfill</button></div></form><pre id="scheduler-result" class="code" aria-live="polite">No scheduler operation requested.</pre></section>`;
}

async function payloadDigest(payload) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join('');
}

document.addEventListener('click', async event => {
  const action = event.target.closest('[data-scheduler-action]')?.dataset.schedulerAction;
  if (!action || location.hash.slice(1) !== 'workflows') return;
  const values = Object.fromEntries(new FormData(document.querySelector('#scheduler-form')));
  const workspace = encodeURIComponent(values.workspace);
  const schedule = encodeURIComponent(values.schedule_id);
  const output = document.querySelector('#scheduler-result');
  try {
    let result;
    if (action === 'list') result = await get(`/v1/workspaces/${workspace}/schedules`);
    else if (action === 'save') result = await put(`/v1/workspaces/${workspace}/schedules/${schedule}`, { id: values.schedule_id, workflow_id: values.workflow_id, cron: values.cron, timezone: 'UTC', enabled: true });
    else if (action === 'next-runs') result = await get(`/v1/workspaces/${workspace}/schedules/${schedule}/next-runs?after=${encodeURIComponent(values.after)}&count=10`);
    else if (action === 'history') result = await get(`/v1/workspaces/${workspace}/schedules/${schedule}/history?limit=100`);
    else if (action === 'run') result = await post(`/v1/workspaces/${workspace}/workflows/${encodeURIComponent(values.workflow_id)}/runs`, { trigger: { kind: 'api', source_ref: 'studio' }, idempotency_key: values.idempotency_key });
    else if (action === 'inspect-run') result = await get(`/v1/workspaces/${workspace}/workflow-runs/${encodeURIComponent(values.run_id)}`);
    else if (action === 'events') result = await get(`/v1/workspaces/${workspace}/event-triggers`);
    else if (action === 'save-event') result = await put(`/v1/workspaces/${workspace}/event-triggers/${encodeURIComponent(values.trigger_id)}`, { id: values.trigger_id, workflow_id: values.workflow_id, event_type: values.event_type, source_ref: values.source_ref || null, subject_ref: null, enabled: true });
    else if (action === 'ingest') { const eventPayload = { source: 'studio', event_type: values.event_type }; result = await post(`/v1/workspaces/${workspace}/events`, { event_id: `studio-${Date.now()}`, event_type: values.event_type, payload_digest: await payloadDigest(eventPayload), occurred_at: new Date().toISOString().replace('Z', '.000000Z'), source_ref: 'studio' }); }
    else if (action === 'backfill') result = await post(`/v1/workspaces/${workspace}/backfills`, { id: values.backfill_id, schedule_id: values.schedule_id, start_at: values.start_at, end_at: values.end_at });
    else result = await post(`/v1/workspaces/${workspace}/backfills/${encodeURIComponent(values.backfill_id)}/cancel`, {});
    output.textContent = json(result);
  } catch (error) { output.textContent = `Scheduler operation failed: ${error.message}`; }
});

window.addEventListener('hashchange', () => { if (location.hash.slice(1) === 'workflows') schedulerStudio(); });
if (location.hash.slice(1) === 'workflows') setTimeout(schedulerStudio, 0);
setInterval(() => { if (location.hash.slice(1) === 'workflows' && !document.querySelector('#scheduler-form')) schedulerStudio(); }, 100);

setInterval(() => {
  const toolbar = document.querySelector('#scheduler-form .toolbar');
  if (!toolbar || toolbar.querySelector('[data-scheduler-action="deliveries"]')) return;
  const button = document.createElement('button');
  button.className = 'button';
  button.type = 'button';
  button.dataset.schedulerAction = 'deliveries';
  button.textContent = 'List pending deliveries';
  toolbar.insertBefore(button, toolbar.querySelector('[data-scheduler-action="ingest"]'));
}, 100);

document.addEventListener('click', async event => {
  if (event.target.closest('[data-scheduler-action="deliveries"]') === null) return;
  const values = Object.fromEntries(new FormData(document.querySelector('#scheduler-form')));
  const output = document.querySelector('#scheduler-result');
  try {
    const result = await get(`/v1/workspaces/${encodeURIComponent(values.workspace)}/event-deliveries?limit=100`);
    output.textContent = json(result);
  } catch (error) {
    output.textContent = `Scheduler operation failed: ${error.message}`;
  }
});
