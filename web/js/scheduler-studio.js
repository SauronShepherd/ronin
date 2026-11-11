import { get, post, put, request } from './api.js';
import { esc, json, page } from './dom.js';

const field = (label, name, value) => `<label>${label}<input class="field" name="${name}" value="${value}" required></label>`;
const retryableSchedulerActions = new Set(['list', 'inspect-schedule', 'next-runs', 'history', 'inspect-run', 'events', 'deliveries', 'inspect-backfill']);
let lastRetryableSchedulerAction = null;
const activeWorkspace = () => globalThis.roninStudioContext?.workspace || sessionStorage.getItem('ronin.workspace') || 'default';

export function schedulerStudio() {
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Scheduler Studio', 'ORCHESTRATION')}
    <section class="panel scheduler-hero"><div><p class="eyebrow">ORCHESTRATION CONTROL PLANE</p><h2>Make durable workflow operations feel calm.</h2><p>Observe schedules, trigger work, and rehearse recovery from one workspace-scoped control surface.</p></div><div class="scheduler-hero-signals"><span class="status blue">Workspace scoped</span><span class="status green">Durable actions</span><span class="scheduler-hero-note">Every action returns reviewable evidence.</span></div></section>
    <section class="scheduler-cockpit"><section class="panel scheduler-context-panel"><div class="scheduler-section-heading"><div><p class="eyebrow">CONTROL CONTEXT</p><h2>Choose the object before the action.</h2><p class="muted">Identifiers stay visible so a cancel, retry or backfill cannot target the wrong scope.</p></div><span class="scheduler-section-index">01</span></div><form id="scheduler-form" class="scheduler-form"><div class="grid three scheduler-context-grid">${field('Workspace', 'workspace', 'default')}${field('Schedule ID', 'schedule_id', 'daily')}${field('Workflow ID', 'workflow_id', 'main')}${field('Run ID', 'run_id', 'run-1')}${field('Idempotency key', 'idempotency_key', 'studio-run-1')}${field('Cron', 'cron', '0 0 * * *')}${field('Timezone', 'timezone', 'UTC')}${field('After', 'after', '2026-01-01T00:00:00.000000Z')}${field('Backfill ID', 'backfill_id', 'backfill-1')}${field('Backfill start', 'start_at', '2026-01-01T00:00:00.000000Z')}${field('Backfill end', 'end_at', '2026-01-02T00:00:00.000000Z')}${field('Event trigger ID', 'trigger_id', 'on-data')}${field('Event type', 'event_type', 'manual')}${field('Event source', 'source_ref', 'studio')}${field('Subject ref', 'subject_ref', '')}${field('Event ID', 'event_id', 'studio-event-1')}<label class="checkbox"><input type="checkbox" name="enabled" checked> Schedule enabled</label><label class="checkbox"><input type="checkbox" name="event_enabled" checked> Event trigger enabled</label></div><div class="scheduler-action-groups"><div class="scheduler-action-group" data-action-group="observe"><span>Observe</span><div class="toolbar"><button class="button" data-scheduler-action="list" type="button">List schedules</button><button class="button" data-scheduler-action="inspect-schedule" type="button">Inspect schedule</button><button class="button" data-scheduler-action="next-runs" type="button">Preview next runs</button><button class="button" data-scheduler-action="history" type="button">View history</button><button class="button" data-scheduler-action="events" type="button">List event triggers</button><button class="button" data-scheduler-action="deliveries" type="button">Inspect event deliveries</button></div></div><div class="scheduler-action-group" data-action-group="change"><span>Change</span><div class="toolbar"><button class="button primary" data-scheduler-action="save" type="button">Save schedule</button><button class="button primary" data-scheduler-action="save-event" type="button">Save event trigger</button></div></div><div class="scheduler-action-group" data-action-group="execute"><span>Execute</span><div class="toolbar"><button class="button primary" data-scheduler-action="run" type="button">Run workflow</button><button class="button" data-scheduler-action="inspect-run" type="button">Inspect run</button><button class="button danger" data-scheduler-action="cancel-run" type="button">Cancel workflow run</button><button class="button" data-scheduler-action="ingest" type="button">Ingest event</button></div></div><div class="scheduler-action-group" data-action-group="recover"><span>Recover</span><div class="toolbar"><button class="button" data-scheduler-action="backfill-preview" type="button">Preview backfill</button><button class="button" data-scheduler-action="inspect-backfill" type="button">Inspect backfill</button><button class="button primary" data-scheduler-action="backfill" type="button">Start backfill</button><button class="button danger" data-scheduler-action="cancel" type="button">Cancel backfill</button></div></div></div></form></section><aside class="panel scheduler-insight"><p class="eyebrow">OPERATING NOTE</p><h2>Recovery is a first-class path.</h2><p>Preview next runs and backfill windows before changing durable state. Inspect the run or delivery when the result needs context.</p><div class="scheduler-insight-state"><span class="scheduler-insight-mark">↗</span><span>Choose an action to create an auditable scheduler result.</span></div></aside></section>
    <section class="panel scheduler-result-panel"><div class="scheduler-section-heading"><div><p class="eyebrow">EVIDENCE</p><h2>Operator result</h2><p class="muted">Responses stay bounded and visible after every action.</p></div><span class="scheduler-section-index">02</span></div><pre id="scheduler-result" class="code scheduler-result" aria-live="polite">No scheduler operation requested.</pre></section>`;
  const contextField = document.querySelector('#scheduler-form [name="workspace"]');
  if (contextField) contextField.value = activeWorkspace();
}

async function payloadDigest(payload) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join('');
}

document.addEventListener('click', async event => {
  if (event.target.closest('[data-scheduler-retry]')) {
    document.querySelector(`[data-scheduler-action="${lastRetryableSchedulerAction || ''}"]`)?.click();
    return;
  }
  const action = event.target.closest('[data-scheduler-action]')?.dataset.schedulerAction;
  if (!action || location.hash.slice(1) !== 'workflows') return;
  const values = Object.fromEntries(new FormData(document.querySelector('#scheduler-form')));
  const workspace = encodeURIComponent(values.workspace);
  const schedule = encodeURIComponent(values.schedule_id);
  const output = document.querySelector('#scheduler-result');
  try {
    let result;
    if (action === 'list') result = await get(`/v1/workspaces/${workspace}/schedules`);
    else if (action === 'inspect-schedule') result = await get(`/v1/workspaces/${workspace}/schedules/${schedule}`);
    else if (action === 'save') result = await put(`/v1/workspaces/${workspace}/schedules/${schedule}`, { id: values.schedule_id, workflow_id: values.workflow_id, cron: values.cron, timezone: values.timezone, enabled: values.enabled === 'on' });
    else if (action === 'next-runs') result = await get(`/v1/workspaces/${workspace}/schedules/${schedule}/next-runs?after=${encodeURIComponent(values.after)}&count=10`);
    else if (action === 'history') result = await get(`/v1/workspaces/${workspace}/schedules/${schedule}/history?limit=100`);
    else if (action === 'run') result = await post(`/v1/workspaces/${workspace}/workflows/${encodeURIComponent(values.workflow_id)}/runs`, { trigger: { kind: 'api', key: values.idempotency_key, source_ref: 'studio' }, idempotency_key: values.idempotency_key });
    else if (action === 'inspect-run') result = await get(`/v1/workspaces/${workspace}/workflow-runs/${encodeURIComponent(values.run_id)}`);
    else if (action === 'cancel-run') result = await request(`/v1/workspaces/${workspace}/workflow-runs/${encodeURIComponent(values.run_id)}/cancel`, { method: 'POST' });
    else if (action === 'events') result = await get(`/v1/workspaces/${workspace}/event-triggers`);
    else if (action === 'save-event') result = await put(`/v1/workspaces/${workspace}/event-triggers/${encodeURIComponent(values.trigger_id)}`, { id: values.trigger_id, workflow_id: values.workflow_id, event_type: values.event_type, source_ref: values.source_ref || null, subject_ref: values.subject_ref || null, enabled: values.event_enabled === 'on' });
    else if (action === 'ingest') { const eventPayload = { source: values.source_ref || 'studio', event_type: values.event_type, subject_ref: values.subject_ref || null }; const occurredAt = new Date().toISOString().replace(/\.(\d{3})Z$/, (_match, milliseconds) => `.${milliseconds}000Z`); result = await post(`/v1/workspaces/${workspace}/events`, { event_id: values.event_id, event_type: values.event_type, payload_digest: await payloadDigest(eventPayload), occurred_at: occurredAt, source_ref: values.source_ref || 'studio', subject_ref: values.subject_ref || null }); }
    else if (action === 'backfill-preview') result = await post(`/v1/workspaces/${workspace}/backfills/preview`, { schedule_id: values.schedule_id, start_at: values.start_at, end_at: values.end_at, max_runs: 1000 });
    else if (action === 'inspect-backfill') result = await get(`/v1/workspaces/${workspace}/backfills/${encodeURIComponent(values.backfill_id)}`);
    else if (action === 'backfill') result = await post(`/v1/workspaces/${workspace}/backfills`, { id: values.backfill_id, schedule_id: values.schedule_id, start_at: values.start_at, end_at: values.end_at });
    else if (action === 'cancel') result = await post(`/v1/workspaces/${workspace}/backfills/${encodeURIComponent(values.backfill_id)}/cancel`, {});
    else return;
    output.textContent = json(result);
  } catch (error) { output.innerHTML = retryableSchedulerActions.has(action) ? `<div class="error"><strong>Scheduler operation failed.</strong><p>${esc(error.message)}</p><button class="button" type="button" data-scheduler-retry>Retry this observation</button></div>` : `Scheduler operation failed: ${error.message}`; }
  if (retryableSchedulerActions.has(action)) lastRetryableSchedulerAction = action;
});

window.addEventListener('hashchange', () => { if (location.hash.slice(1) === 'workflows') schedulerStudio(); });
if (location.hash.slice(1) === 'workflows') setTimeout(schedulerStudio, 0);
setInterval(() => { if (location.hash.slice(1) === 'workflows' && !document.querySelector('#scheduler-form')) schedulerStudio(); }, 100);

// Deliveries are rendered with the other observation actions; keep this listener
// separate so older deep links that inject the button still retain the contract.
document.addEventListener('click', async event => {
  if (event.target.closest('[data-scheduler-action="deliveries"]') === null) return;
  const values = Object.fromEntries(new FormData(document.querySelector('#scheduler-form')));
  const output = document.querySelector('#scheduler-result');
  try {
    const result = await get(`/v1/workspaces/${encodeURIComponent(values.workspace)}/event-deliveries?limit=100`);
    if (output) output.textContent = json(result);
  } catch (error) {
    if (output) output.innerHTML = `<div class="error"><strong>Scheduler operation failed.</strong><p>${esc(error.message)}</p><button class="button" type="button" data-scheduler-retry>Retry this observation</button></div>`;
    lastRetryableSchedulerAction = 'deliveries';
  }
});
