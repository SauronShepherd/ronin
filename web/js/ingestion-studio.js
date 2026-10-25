import {get, post} from './api.js';
import {json, page} from './dom.js';

let discoveryController = null;
let discoveryRequestId = 0;
let discoveryCursor = null;
let discoveryPageNumber = 0;
let discoverySourceKey = '';

export async function ingestionStudio() {
  stopDiscoveryRequest();
  discoveryCursor = null;
  discoveryPageNumber = 0;
  discoverySourceKey = '';

  const view = document.querySelector('#view');
  view.innerHTML = `${page('Ingestion Studio', 'DATA PLANE')}
    <section class="panel">
      <h2>Connector capabilities</h2>
      <pre id="ingestion-capabilities" class="code" aria-live="polite">Loading…</pre>
    </section>
    <section class="panel" aria-labelledby="ingestion-discovery-title">
      <h2 id="ingestion-discovery-title">Discover source assets</h2>
      <p class="muted">Load one bounded page at a time. Ronin keeps only the current page and its continuation cursor.</p>
      <form id="ingestion-discover-form">
        <div class="grid three">
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
    <section class="panel">
      <h2>Ingestion sync</h2>
      <form id="ingestion-preview-form">
        <label>Definition JSON<textarea id="ingestion-definition" class="field sql-editor" rows="10" required>{"id":"preview-1","connector_id":"http-json","connection_ref":"connection://demo","asset_ref":"asset://demo","destination_ref":"asset://preview","checkpoint_identity":"preview-1","mode":"snapshot"}</textarea></label>
        <div class="toolbar">
          <button class="button" type="button" id="ingestion-plan-button">Plan sync</button>
          <button class="button" type="button" id="ingestion-health-button">Checkpoint health</button>
          <button class="button primary">Preview source</button>
        </div>
      </form>
      <pre id="ingestion-preview-result" class="code" aria-live="polite">No operation requested.</pre>
    </section>`;

  try {
    document.querySelector('#ingestion-capabilities').textContent = json(
      await get('/v1/platform/connectors'),
    );
  } catch (error) {
    document.querySelector('#ingestion-capabilities').textContent =
      `Capabilities unavailable: ${error.message}`;
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
  if (!connectorId || !connectionRef) throw new Error('Connector ID and connection are required.');
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 1000) {
    throw new Error('Page size must be an integer between 1 and 1000.');
  }
  return {connectorId, connectionRef, pageSize};
}

function updateDiscoveryControls({loading, hasMore}) {
  const start = document.querySelector('#ingestion-discover-start');
  const next = document.querySelector('#ingestion-discover-next');
  const cancel = document.querySelector('#ingestion-discover-cancel');
  if (!start || !next || !cancel) return;
  start.disabled = loading;
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
    const data = await post('/v1/platform/connectors/discover', body, {
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
    updateDiscoveryControls({loading: false, hasMore: data.has_more});
  } catch (error) {
    if (requestId !== discoveryRequestId) return;
    if (error.name === 'AbortError') {
      status.textContent = 'Stopped this request. No page was loaded; a read-only provider request already accepted by the server may finish.';
    } else {
      status.textContent = `Discovery failed: ${error.message}`;
    }
    updateDiscoveryControls({loading: false, hasMore: discoveryCursor !== null});
  } finally {
    if (requestId === discoveryRequestId) discoveryController = null;
  }
}

document.addEventListener('submit', async event => {
  if (event.target.id === 'ingestion-discover-form') {
    event.preventDefault();
    await loadDiscoveryPage({restart: true});
    return;
  }
  if (event.target.id !== 'ingestion-preview-form') return;
  event.preventDefault();
  const result = document.querySelector('#ingestion-preview-result');
  try {
    const payload = JSON.parse(document.querySelector('#ingestion-definition').value);
    result.textContent = json(await post('/v1/platform/connectors/preview', payload));
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
  if (!button) return;
  const result = document.querySelector('#ingestion-preview-result');
  try {
    const definition = JSON.parse(document.querySelector('#ingestion-definition').value);
    const path = button.id === 'ingestion-plan-button'
      ? '/v1/platform/connectors/plan'
      : '/v1/platform/connectors/checkpoint-health';
    const payload = button.id === 'ingestion-plan-button'
      ? definition
      : {checkpoint_identity: definition.checkpoint_identity};
    result.textContent = json(await post(path, payload));
  } catch (error) {
    result.textContent = `Operation failed: ${error.message}`;
  }
});
