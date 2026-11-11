import {get, post} from './api.js';
import {esc, json, page} from './dom.js';

let discoveryController = null;
let discoveryRequestId = 0;
let discoveryCursor = null;
let discoveryPageNumber = 0;
let discoverySourceKey = '';
let discoveryRetryPending = false;
let activeSyncTimer = null;
let activeSyncScope = null;

function workspaceQuery(path) {
  const workspaceId = document.querySelector('#ingestion-workspace')?.value.trim();
  if (!workspaceId) throw new Error('Workspace ID is required.');
  sessionStorage.setItem('ronin.workspace', workspaceId);
  return `${path}?workspace_id=${encodeURIComponent(workspaceId)}`;
}

export async function ingestionStudio() {
  if (activeSyncTimer) clearTimeout(activeSyncTimer);
  activeSyncTimer = null;
  activeSyncScope = null;
  stopDiscoveryRequest();
  discoveryCursor = null;
  discoveryPageNumber = 0;
  discoverySourceKey = '';
  discoveryRetryPending = false;

  const view = document.querySelector('#view');
  const workspaceId = globalThis.roninStudioContext?.workspace || sessionStorage.getItem('ronin.workspace') || 'default';
  view.innerHTML = `${page('Ingestion Studio', 'DATA PLANE')}
    <section class="ing-hero panel">
      <div>
        <p class="eyebrow">DATA PLANE · DECISION WORKBENCH</p>
        <h2>Move source data with a clear decision at every step.</h2>
        <p>Discover bounded assets, preview the contract, then run a governed sync. The page keeps scope, limits, recovery and evidence visible before anything durable starts.</p>
      </div>
      <div class="ing-hero-aside">
        <span class="status blue">Discover → preview → sync → evidence</span>
        <p>Read-only discovery is paged. Durable execution requires governed source and destination references.</p>
      </div>
    </section>
    <div class="ing-mode-nav" role="group" aria-label="Ingestion workbench modes">
      <a class="ing-mode-card" href="#ingestion-discovery"><span class="ing-mode-index">01</span><strong>Discover</strong><span>Find source assets without loading an unbounded catalog.</span></a>
      <a class="ing-mode-card" href="#ingestion-preview"><span class="ing-mode-index">02</span><strong>Preview</strong><span>Inspect the plan and source response before a write.</span></a>
      <a class="ing-mode-card" href="#ingestion-sync"><span class="ing-mode-index">03</span><strong>Sync</strong><span>Submit a durable, idempotent job inside a project.</span></a>
      <a class="ing-mode-card" href="#ingestion-observe"><span class="ing-mode-index">04</span><strong>Observe</strong><span>Follow state, evidence and recorded lineage after commit.</span></a>
    </div>
    <section class="ing-workbench panel" id="ingestion-discovery" aria-labelledby="ingestion-discovery-title">
      <div class="ing-section-heading"><div><span class="ing-section-index">01 · DISCOVER</span><h2 id="ingestion-discovery-title">Start with a governed source</h2><p>Use a bounded page to establish the source boundary before defining a sync.</p></div><span class="ing-boundary">workspace · connection · cursor</span></div>
      <div class="ing-callout"><span class="status blue">Read-only</span><p>Ronin keeps only the current page and continuation cursor in this view. Stop safely if the provider is slow or the source settings change.</p></div>
      <form id="ingestion-discover-form">
        <div class="grid three">
          <label>Workspace ID<input class="field" id="ingestion-workspace" name="workspace_id" value="${esc(workspaceId)}" required></label>
          <label>Connector ID<input class="field" name="connector_id" value="postgres" required></label>
          <label>Connection reference<input class="field" name="connection_ref" placeholder="connection ID" required></label>
          <label>Page size<input class="field" name="page_size" type="number" min="1" max="1000" value="100" required></label>
        </div>
        <div class="toolbar">
          <button class="button primary" type="submit" id="ingestion-discover-start">Discover assets</button>
          <button class="button" type="button" id="ingestion-discover-next" disabled>Load next page</button>
          <button class="button" type="button" id="ingestion-discover-cancel" disabled>Stop discovery</button>
        </div>
      </form>
      <p id="ingestion-discovery-status" role="status" aria-live="polite">No discovery requested.</p>
      <pre id="ingestion-discovery-result" class="code" aria-label="Discovered asset page">No assets loaded.</pre>
    </section>
    <section class="ing-workbench panel" id="ingestion-preview" aria-labelledby="ingestion-preview-title">
      <div class="ing-section-heading"><div><span class="ing-section-index">02 · PREVIEW</span><h2 id="ingestion-preview-title">Make the write boundary explicit</h2><p>Use one definition for preview, planning, checkpoint health and the eventual durable run.</p></div><span class="ing-boundary">project · contract · checkpoint</span></div>
      <form id="ingestion-preview-form">
        <div class="grid three">
          <label>Project ID<input class="field" id="ingestion-project" value="${esc(globalThis.roninStudioContext?.project || 'default')}" required></label>
        </div>
        <div class="ing-callout"><span class="status amber">Governed write</span><p>A durable sync needs an existing governed source revision and destination asset. Preview and plan are safe checks; only the explicit sync action submits work.</p></div>
        <label>Definition JSON<textarea id="ingestion-definition" class="field sql-editor" rows="10" required>{"id":"preview-1","connector_id":"http.json","connection_ref":"connection://demo","asset_ref":"connection://demo::orders","destination_ref":"asset://preview","checkpoint_identity":"preview-1","mode":"snapshot","source_revision_ref":{"asset_id":"governed-source","version":"v1"},"destination_asset_id":"governed-target"}</textarea></label>
        <details class="ing-advanced"><summary>What the worker records</summary><p class="muted">Bind catalog properties <code>ronin.connector_id</code>, <code>ronin.connection_ref</code> and <code>ronin.asset_ref</code>. A successful worker run records observed lineage with its Run ID and evidence digest.</p></details>
        <div class="ing-form-actions"><p class="ing-form-note">Preview the provider response first, then inspect the plan and checkpoint before running.</p><div class="toolbar"><button class="button" type="button" id="ingestion-plan-button">Plan sync</button><button class="button" type="button" id="ingestion-health-button">Checkpoint health</button><button class="button primary" type="button" id="ingestion-sync-button">Run durable sync</button><button class="button">Preview source</button></div></div>
      </form>
      <pre id="ingestion-preview-result" class="code" aria-live="polite">No operation requested.</pre>
    </section>
    <section class="ing-workbench panel" id="ingestion-sync" aria-labelledby="ingestion-sync-title">
      <div class="ing-section-heading"><div><span class="ing-section-index">03 · SYNC</span><h2 id="ingestion-sync-title">Commit a durable sync</h2><p>The API applies project scope and an idempotency key before the worker processes the queued job.</p></div><span class="ing-boundary">queued · retryable · cancellable</span></div>
      <div class="ing-sync-brief"><span class="status blue">Worker handoff</span><p>Keep a Ronin worker running with the same storage configuration. The browser monitors the durable job; it does not pretend a submission is a completed load.</p></div>
      <p id="ingestion-sync-status" role="status" aria-live="polite">No sync submitted.</p><button class="button" type="button" id="ingestion-sync-cancel" hidden>Cancel sync</button>
    </section>
    <section class="ing-workbench panel" id="ingestion-observe" aria-labelledby="ingestion-observe-title">
      <div class="ing-section-heading"><div><span class="ing-section-index">04 · OBSERVE</span><h2 id="ingestion-observe-title">Keep evidence with the outcome</h2><p>Capabilities, events, evidence and lineage make the result reviewable after the browser leaves.</p></div><span class="ing-boundary">capabilities · evidence · lineage</span></div>
      <div class="ing-observe-grid">
        <section class="ing-observe-card"><h3>Connector capabilities</h3><p class="muted">What the configured server can safely execute.</p><pre id="ingestion-capabilities" class="code" aria-live="polite">Loading…</pre></section>
        <section class="ing-observe-card"><h3>Run events and evidence</h3><pre id="ingestion-sync-evidence" class="code">Job events and evidence will appear here.</pre></section>
        <section class="ing-observe-card"><h3>Recorded lineage</h3><pre id="ingestion-sync-lineage" class="code" aria-live="polite">Lineage will appear after the run commits.</pre></section>
      </div>
    </section>`;

  try {
    const capabilities = await get('/v1/platform/connectors');
    const target = document.querySelector('#ingestion-capabilities');
    if (target) target.textContent = json(capabilities);
  } catch (error) {
    const target = document.querySelector('#ingestion-capabilities');
    if (target) target.textContent = `Capabilities unavailable: ${error.message}`;
  }
}

function stopDiscoveryRequest() {
  discoveryRequestId += 1;
  discoveryController?.abort();
  discoveryController = null;
}

function discoveryInputs() {
  const form = document.querySelector('#ingestion-discover-form');
  const connectorId = form.elements.connector_id.value.trim();
  const connectionRef = form.elements.connection_ref.value.trim();
  const pageSize = Number(form.elements.page_size.value);
  const workspaceId = form.elements.workspace_id.value.trim();
  if (!workspaceId) throw new Error('Workspace ID is required.');
  if (!connectorId || !connectionRef) throw new Error('Connector ID and connection are required.');
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 1000) {
    throw new Error('Page size must be an integer between 1 and 1000.');
  }
  return {workspaceId, connectorId, connectionRef, pageSize};
}

function updateDiscoveryControls({loading, hasMore}) {
  const start = document.querySelector('#ingestion-discover-start');
  const next = document.querySelector('#ingestion-discover-next');
  const cancel = document.querySelector('#ingestion-discover-cancel');
  if (!start || !next || !cancel) return;
  start.disabled = loading;
  start.textContent = discoveryRetryPending ? 'Retry discovery page' : 'Discover assets';
  next.disabled = loading || !hasMore;
  cancel.disabled = !loading;
}

async function loadDiscoveryPage({restart}) {
  const status = document.querySelector('#ingestion-discovery-status');
  const result = document.querySelector('#ingestion-discovery-result');
  if (!status || !result || discoveryController) return;

  let inputs;
  try {
    inputs = discoveryInputs();
  } catch (error) {
    status.textContent = `Discovery not started: ${error.message}`;
    return;
  }

  const sourceKey = JSON.stringify(inputs);
  if (!restart && sourceKey !== discoverySourceKey) {
    status.textContent = 'Connection settings changed. Start discovery again to get a new cursor.';
    updateDiscoveryControls({loading: false, hasMore: false});
    return;
  }
  if (restart) {
    discoveryCursor = null;
    discoveryPageNumber = 0;
    discoverySourceKey = sourceKey;
    discoveryRetryPending = false;
    result.textContent = 'Waiting for the first page…';
  }

  const requestId = ++discoveryRequestId;
  const controller = new AbortController();
  discoveryController = controller;
  const pageNumber = discoveryPageNumber + 1;
  status.textContent = `Loading page ${pageNumber}…`;
  updateDiscoveryControls({loading: true, hasMore: false});

  const body = {
    connector_id: inputs.connectorId,
    connection_ref: inputs.connectionRef,
    page_size: inputs.pageSize,
  };
  if (!restart && discoveryCursor) body.cursor = discoveryCursor;

  try {
    const data = await post(workspaceQuery('/v1/platform/connectors/discover'), body, {
      signal: controller.signal,
    });
    if (requestId !== discoveryRequestId) return;
    if (
      data?.schema !== 'ronin.connector-discovery/v1' ||
      !Array.isArray(data.items) ||
      !Number.isInteger(data.count) ||
      data.count !== data.items.length ||
      typeof data.has_more !== 'boolean' ||
      (data.has_more && (typeof data.next_cursor !== 'string' || !data.next_cursor)) ||
      (!data.has_more && data.next_cursor !== null)
    ) {
      throw new Error('Connector discovery returned an invalid page.');
    }
    discoveryPageNumber = pageNumber;
    discoveryCursor = data.has_more ? data.next_cursor : null;
    result.textContent = json(data);
    status.textContent = `Page ${pageNumber} loaded · ${data.count} assets on this page · ${data.has_more ? 'more pages available' : 'discovery complete'}.`;
    discoveryRetryPending = false;
    updateDiscoveryControls({loading: false, hasMore: data.has_more});
  } catch (error) {
    if (requestId !== discoveryRequestId) return;
    if (error.name === 'AbortError') {
      status.textContent = 'Stopped this request. No page was loaded; a read-only provider request already accepted by the server may finish.';
    } else {
      status.textContent = `Discovery failed: ${error.message}`;
      discoveryRetryPending = true;
    }
    updateDiscoveryControls({loading: false, hasMore: discoveryCursor !== null});
  } finally {
    if (requestId === discoveryRequestId) discoveryController = null;
  }
}

document.addEventListener('submit', async event => {
  if (event.target.id === 'ingestion-discover-form') {
    event.preventDefault();
    await loadDiscoveryPage({restart: !discoveryRetryPending});
    return;
  }
  if (event.target.id !== 'ingestion-preview-form') return;
  event.preventDefault();
  const result = document.querySelector('#ingestion-preview-result');
  try {
    const payload = JSON.parse(document.querySelector('#ingestion-definition').value);
    result.textContent = json(await post(workspaceQuery('/v1/platform/connectors/preview'), payload));
  } catch (error) {
    result.textContent = `Preview failed: ${error.message}`;
  }
});

document.addEventListener('click', async event => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest('#ingestion-discover-next')) {
    await loadDiscoveryPage({restart: false});
    return;
  }
  if (target.closest('#ingestion-discover-cancel')) {
    if (!discoveryController) return;
    const status = document.querySelector('#ingestion-discovery-status');
    status.textContent = 'Stopping discovery…';
    discoveryController.abort();
    return;
  }
  const button = target.closest('#ingestion-plan-button, #ingestion-health-button');
  if (target.closest('#ingestion-sync-button')) {
    const result = document.querySelector('#ingestion-sync-status');
    const evidence = document.querySelector('#ingestion-sync-evidence');
    const workspaceId = document.querySelector('#ingestion-workspace')?.value.trim();
    const projectId = document.querySelector('#ingestion-project')?.value.trim();
    const buttonElement = target.closest('#ingestion-sync-button');
    try {
      const definition = JSON.parse(document.querySelector('#ingestion-definition').value);
      if (!workspaceId || !projectId) throw new Error('Workspace ID and Project ID are required.');
      if (!definition || typeof definition !== 'object' || Array.isArray(definition)) throw new Error('The sync definition must be a JSON object.');
      if (!definition.id || !definition.connector_id || !definition.connection_ref || !definition.asset_ref || !definition.destination_ref || !definition.checkpoint_identity || !['snapshot', 'incremental'].includes(definition.mode)) throw new Error('Complete the sync definition before running it.');
      if (!definition.source_revision_ref?.asset_id || !definition.source_revision_ref?.version || !definition.destination_asset_id) throw new Error('Durable sync requires an existing governed source revision and destination asset.');
      buttonElement.disabled = true;
      const query = `?workspace_id=${encodeURIComponent(workspaceId)}`;
      const job = await post(`/v1/platform/connectors/syncs${query}`, {project_id: projectId, definition}, {headers: {'Idempotency-Key': `ingestion-${globalThis.crypto.randomUUID()}`}});
      activeSyncScope = {jobId: job.id, workspaceId, projectId};
      document.querySelector('#ingestion-sync-cancel').hidden = false;
      result.textContent = `Sync job ${job.id} submitted (${job.state}).`;
      evidence.textContent = json(job);
      monitorSync({jobId: job.id, workspaceId, projectId, result, evidence, lineage: document.querySelector('#ingestion-sync-lineage')});
    } catch (error) {
      result.textContent = `Sync submission failed: ${error.message}`;
    } finally {
      buttonElement.disabled = false;
    }
    return;
  }
  if (target.closest('#ingestion-sync-cancel')) {
    if (!activeSyncScope) return;
    const {jobId, workspaceId, projectId} = activeSyncScope;
    const status = document.querySelector('#ingestion-sync-status');
    try {
      const query = `workspace_id=${encodeURIComponent(workspaceId)}&project_id=${encodeURIComponent(projectId)}`;
      const state = await post(`/v1/platform/connectors/syncs/${encodeURIComponent(jobId)}/cancel?${query}`, {});
      status.textContent = `Sync job ${jobId}: ${state.state || 'cancellation requested'}.`;
    } catch (error) {
      status.textContent = `Could not cancel sync job ${jobId}: ${error.message}`;
    }
    return;
  }
  if (!button) return;
  const result = document.querySelector('#ingestion-preview-result');
  try {
    const definition = JSON.parse(document.querySelector('#ingestion-definition').value);
    const endpoint = button.id === 'ingestion-plan-button'
      ? '/v1/platform/connectors/plan'
      : '/v1/platform/connectors/checkpoint-health';
    const payload = button.id === 'ingestion-plan-button'
      ? definition
      : {checkpoint_identity: definition.checkpoint_identity};
    result.textContent = json(await post(workspaceQuery(endpoint), payload));
  } catch (error) {
    result.textContent = `Operation failed: ${error.message}`;
  }
});

function monitorSync({jobId, workspaceId, projectId, result, evidence, lineage}) {
  if (activeSyncTimer) clearTimeout(activeSyncTimer);
  let polls = 0;
  const poll = async () => {
    polls += 1;
    try {
      const query = `workspace_id=${encodeURIComponent(workspaceId)}&project_id=${encodeURIComponent(projectId)}`;
      const state = await get(`/v1/platform/connectors/syncs/${encodeURIComponent(jobId)}/status?${query}`);
      result.textContent = `Sync job ${jobId}: ${state.job?.state || 'unknown'}${state.job?.failure_code ? ` · ${state.job.failure_code}` : ''}.`;
      evidence.textContent = json({events: state.events, evidence: state.evidence});
      if (state.lineage?.status === 'unavailable') {
        lineage.textContent = 'Lineage is unavailable for this sync.';
      } else if (state.lineage?.status === 'not_recorded') {
        lineage.textContent = 'No lineage was recorded because this sync did not succeed.';
      } else if (state.lineage?.truncated) {
        lineage.textContent = `${json(state.lineage)}\nLineage is truncated to the first 100 edges.`;
      } else if (state.lineage?.items?.length) {
        lineage.textContent = json(state.lineage);
      } else if (state.job?.state === 'succeeded') {
        lineage.textContent = 'The run succeeded but no lineage edge was returned.';
      } else {
        lineage.textContent = 'Lineage will appear after the run commits.';
      }
      if (['succeeded', 'failed', 'cancelled'].includes(state.job?.state)) {
        activeSyncTimer = null;
        document.querySelector('#ingestion-sync-cancel').hidden = true;
        return;
      }
    } catch (error) {
      result.textContent = `Could not refresh sync job ${jobId}: ${error.message}`;
    }
    if (polls < 180) activeSyncTimer = setTimeout(poll, 2000);
    else result.textContent += ' Polling stopped after 6 minutes; the durable job continues on the worker.';
  };
  activeSyncTimer = setTimeout(poll, 1000);
}
