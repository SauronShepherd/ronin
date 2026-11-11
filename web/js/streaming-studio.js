import { get, put, post } from './api.js';
import { esc, json, page } from './dom.js';

let reviewedBundle = null;

function bytesToBase64(bytes) {
  const chunkSize = 0x8000;
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

function clearBundleReview(message = 'Choose a Bundle file and preview it before importing.') {
  reviewedBundle = null;
  const review = document.querySelector('#stream-bundle-import-review');
  const commit = document.querySelector('#stream-bundle-import-commit');
  if (review) review.replaceChildren(Object.assign(document.createElement('p'), { textContent: message }));
  if (commit) commit.disabled = true;
}

function updateBundleImportButton() {
  const commit = document.querySelector('#stream-bundle-import-commit');
  if (!commit) return;
  const bindings = [...document.querySelectorAll('[data-binding-source]')];
  const checkpoints = [...document.querySelectorAll('[data-checkpoint-stream]')];
  commit.disabled = !reviewedBundle || checkpoints.length === 0 ||
    bindings.some(input => !input.value.trim()) || checkpoints.some(select => !select.value);
}

function renderBundleReview(plan, file) {
  const review = document.querySelector('#stream-bundle-import-review');
  const commit = document.querySelector('#stream-bundle-import-commit');
  review.replaceChildren();
  reviewedBundle = { digest: plan.bundle_digest, file, workspace: formWorkspace() };
  const summary = document.createElement('p');
  summary.textContent = `Verified ${plan.items.length} stream definition(s), ${plan.unresolved_bindings.length} binding(s), ${plan.size_bytes} bytes. Choose every target and checkpoint action before importing.`;
  review.append(summary);

  const bindings = document.createElement('fieldset');
  const bindingsLegend = document.createElement('legend');
  bindingsLegend.textContent = 'Explicit binding targets';
  bindings.append(bindingsLegend);
  for (const binding of plan.unresolved_bindings) {
    const label = document.createElement('label');
    label.textContent = `${binding.kind}: ${binding.source_ref}`;
    const input = document.createElement('input');
    input.className = 'field';
    input.dataset.bindingSource = binding.source_ref;
    input.value = binding.suggested_target_ref || binding.source_ref;
    input.required = true;
    label.append(input);
    bindings.append(label);
  }
  review.append(bindings);

  const checkpoints = document.createElement('fieldset');
  const checkpointsLegend = document.createElement('legend');
  checkpointsLegend.textContent = 'Checkpoint action per stream';
  checkpoints.append(checkpointsLegend);
  for (const definition of plan.items) {
    const label = document.createElement('label');
    label.textContent = definition.id;
    const select = document.createElement('select');
    select.className = 'field';
    select.dataset.checkpointStream = definition.id;
    select.required = true;
    for (const [value, text] of [
      ['', 'Choose reset or resume'],
      ['reset', 'Reset checkpoint to the beginning'],
      ['resume', 'Resume only if this exact definition already exists'],
    ]) select.add(new Option(text, value));
    label.append(select);
    checkpoints.append(label);
  }
  review.append(checkpoints);
  const digest = document.createElement('code');
  digest.textContent = `SHA-256 ${plan.bundle_digest}`;
  review.append(digest);
  updateBundleImportButton();
}

function formWorkspace() {
  const form = document.querySelector('#stream-bundle-import-form');
  return String(new FormData(form).get('workspace') || '').trim();
}

function renderStreamHealth(output, payload) {
  const state = payload?.status || (payload?.healthy === true ? 'healthy' : payload?.healthy === false ? 'lagging' : 'unknown');
  const tone = state === 'healthy' ? 'green' : ['lagging', 'degraded'].includes(state) ? 'amber' : 'blue';
  const totalLag = Number.isFinite(payload?.total_lag) ? payload.total_lag : Number.isFinite(payload?.lag) ? payload.lag : null;
  const partitions = Number.isFinite(payload?.partitions) ? payload.partitions : (payload?.lag && typeof payload.lag === 'object' ? Object.keys(payload.lag).length : null);
  const emptyPartitions = Array.isArray(payload?.empty_partitions) ? payload.empty_partitions : [];
  const emptyCopy = emptyPartitions.length ? `No records available yet on partition${emptyPartitions.length === 1 ? '' : 's'} ${emptyPartitions.join(', ')}.` : 'All observed partitions have data or a committed checkpoint.';
  const observedAt = payload?.observed_at ? `Observed ${esc(payload.observed_at)}` : 'Observation time unavailable';
  output.innerHTML = `<div class="stream-health-summary"><div><span class="status ${tone}" data-state="${esc(state)}" aria-label="Stream health: ${esc(state)}">${esc(state)}</span><strong>${esc(payload?.stream_id || 'Selected stream')}</strong></div><dl><div><dt>Total lag</dt><dd>${totalLag == null ? '—' : esc(totalLag)}</dd></div><div><dt>Partitions</dt><dd>${partitions == null ? '—' : esc(partitions)}</dd></div></dl><p class="muted" data-empty-partitions>${esc(emptyCopy)}</p><small class="muted" data-observed-at>${observedAt}</small></div><details class="stream-health-raw"><summary>Advanced: raw health evidence</summary><pre class="code">${esc(json(payload))}</pre></details>`;
}

function render() {
  if (location.hash.slice(1) !== 'streaming') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Streaming', 'REAL-TIME')}
    <section class="panel">
      <h2>Stream definitions</h2>
      <form id="stream-definition-form" class="grid two">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Stream ID<input class="field" name="id" required placeholder="events/main"></label>
        <label>Name<input class="field" name="name" required placeholder="Order events"></label>
        <label>Kafka connection ID<input class="field" name="connection_id" required placeholder="kafka-local"></label>
        <label>Topic<input class="field" name="resource" required placeholder="orders"></label>
        <label>Partitions<input class="field" name="partitions" required value="0" placeholder="0, 1"></label>
        <label>Sink<select class="field" name="sink_kind"><option value="table">Local table</option><option value="parquet">Parquet files</option></select></label>
        <label>Sink target<input class="field" name="target_ref" required placeholder="orders-table"></label>
        <label>Runtime profile<input class="field" name="profile_id" value="local" required></label>
        <label>Batch limit<input class="field" name="batch_limit" type="number" min="1" max="100000" value="1000" required></label>
        <label>Poll timeout (seconds)<input class="field" name="timeout_seconds" type="number" min="0" max="300" step="0.1" value="1" required></label>
        <label>Checkpoint policy<select class="field" name="checkpoint_policy"><option value="reset">Reset offsets</option><option value="resume">Resume unchanged definition</option></select></label>
        <label class="full">Schema (JSON array)<textarea class="field" name="schema" rows="3" required>[{"name":"event","data_type":"json","nullable":true}]</textarea></label>
        <button class="button primary" type="submit">Save stream</button>
        <button class="button" id="stream-refresh" type="button">Refresh stream list</button>
        <label class="full">Saved streams<select class="field" id="stream-list" size="4"><option value="">No stream loaded</option></select></label>
      </form>
      <pre id="stream-definition-result" class="code" aria-live="polite">Save a definition or refresh the workspace streams.</pre>
    </section>
    <section class="panel">
      <h2>Portable stream Bundle</h2>
      <p>Export definitions without offsets, or verify a Bundle and review every binding and checkpoint action before importing.</p>
      <button class="button" id="stream-bundle-export" type="button">Download stream Bundle</button>
      <form id="stream-bundle-import-form" class="grid two">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Bundle file<input class="field" name="bundle" type="file" accept=".roninbundle,application/zip" required></label>
        <button class="button" id="stream-bundle-preview" type="submit">Verify and preview Bundle</button>
        <div id="stream-bundle-import-review" class="full" aria-live="polite"><p>Choose a Bundle file and preview it before importing.</p></div>
        <button class="button primary full" id="stream-bundle-import-commit" type="button" disabled>Import reviewed Bundle</button>
      </form>
      <pre id="stream-bundle-result" class="code" aria-live="polite">No stream Bundle action performed.</pre>
    </section>
    <section class="panel">
      <h2>Health and micro-batches</h2>
      <form id="stream-health-form" class="grid two">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Stream ID<input class="field" name="stream" required placeholder="events/main"></label>
        <label>Batch limit<input class="field" name="limit" type="number" min="1" max="100000" value="1000" required></label>
        <button class="button" name="action" value="health" type="submit">Check health</button>
        <button class="button primary" name="action" value="run" type="submit">Run one batch</button>
      </form>
      <pre id="stream-health-result" class="code" aria-live="polite">Choose a saved stream, check health, or run one bounded batch.</pre>
    </section>`;
}

async function loadDefinitions(workspace, list, output) {
  const result = await get(`/v1/workspaces/${encodeURIComponent(workspace)}/streams`);
  list.replaceChildren();
  if (!result.items.length) list.add(new Option('No streams saved', ''));
  for (const definition of result.items) {
    const option = new Option(`${definition.id} — ${definition.name}`, definition.id);
    option.dataset.definition = JSON.stringify(definition);
    list.add(option);
  }
  output.textContent = json(result);
  return result.items;
}

document.addEventListener('submit', async event => {
  const form = event.target;
  // Read the attribute explicitly: the form contains a control named "id",
  // which can shadow legacy named properties on HTMLFormElement.
  if (!(form instanceof HTMLFormElement) || form.getAttribute('id') !== 'stream-definition-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const output = document.querySelector('#stream-definition-result');
  try {
    const definition = {
      id: String(data.get('id')).trim(),
      name: String(data.get('name')).trim(),
      source: {
        connection_id: String(data.get('connection_id')).trim(),
        resource: String(data.get('resource')).trim(),
        partitions: String(data.get('partitions')).split(',').map(value => Number(value.trim())),
        format: 'json',
      },
      sink: {
        kind: String(data.get('sink_kind')),
        target_ref: String(data.get('target_ref')).trim(),
        mode: 'append',
      },
      schema: JSON.parse(String(data.get('schema'))),
      runtime: {
        profile_id: String(data.get('profile_id')).trim(),
        batch_limit: Number(data.get('batch_limit')),
        timeout_seconds: Number(data.get('timeout_seconds')),
      },
    };
    const result = await put(
      `/v1/workspaces/${encodeURIComponent(String(data.get('workspace')))}/streams/${encodeURIComponent(definition.id)}`,
      { definition, checkpoint_policy: String(data.get('checkpoint_policy')) },
    );
    output.textContent = json(result);
    document.querySelector('#stream-health-form [name="workspace"]').value = String(data.get('workspace'));
    document.querySelector('#stream-health-form [name="stream"]').value = definition.id;
    await loadDefinitions(String(data.get('workspace')), document.querySelector('#stream-list'), output);
    output.textContent = `Saved stream ${definition.id} with ${String(data.get('checkpoint_policy'))} checkpoint policy.\n${json(result)}`;
  } catch (error) {
    output.textContent = `Saving stream failed: ${error.message}`;
  }
});

document.addEventListener('click', async event => {
  if (event.target.closest('[data-stream-retry]')) {
    document.querySelector('#stream-health-form')?.requestSubmit();
    return;
  }
  if (event.target instanceof HTMLButtonElement && event.target.id === 'stream-bundle-export') {
    const workspace = String(new FormData(document.querySelector('#stream-definition-form')).get('workspace'));
    const output = document.querySelector('#stream-bundle-result');
    try {
      const payload = await get(`/v1/workspaces/${encodeURIComponent(workspace)}/streams/bundle`);
      if (payload.media_type !== 'application/vnd.ronin.bundle+zip' || typeof payload.content_base64 !== 'string') throw new Error('Invalid stream Bundle response');
      const bytes = Uint8Array.from(atob(payload.content_base64), character => character.charCodeAt(0));
      if (bytes.length !== payload.size_bytes) throw new Error('Stream Bundle size does not match its receipt');
      const digestBytes = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
      const digest = [...digestBytes].map(value => value.toString(16).padStart(2, '0')).join('');
      if (digest !== payload.digest) throw new Error('Stream Bundle digest does not match its receipt');
      const url = URL.createObjectURL(new Blob([bytes], { type: payload.media_type }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${workspace}-streams.roninbundle`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      output.textContent = `Downloaded ${link.download} (${payload.size_bytes} bytes, SHA-256 ${payload.digest}).`;
    } catch (error) {
      output.textContent = `Could not download stream Bundle: ${error.message}`;
    }
    return;
  }
  if (event.target instanceof HTMLButtonElement && event.target.id === 'stream-bundle-import-commit') {
    const fileInput = document.querySelector('#stream-bundle-import-form [name="bundle"]');
    const workspace = String(new FormData(document.querySelector('#stream-bundle-import-form')).get('workspace')).trim();
    const output = document.querySelector('#stream-bundle-result');
    if (!reviewedBundle || fileInput.files[0] !== reviewedBundle.file || workspace !== reviewedBundle.workspace) {
      clearBundleReview('The selected file changed. Verify and preview it again before importing.');
      return;
    }
    const bindingRemaps = Object.fromEntries(
      [...document.querySelectorAll('[data-binding-source]')].map(input => [input.dataset.bindingSource, input.value.trim()]),
    );
    const checkpointPolicies = Object.fromEntries(
      [...document.querySelectorAll('[data-checkpoint-stream]')].map(select => [select.dataset.checkpointStream, select.value]),
    );
    if (Object.values(bindingRemaps).some(value => !value) || Object.values(checkpointPolicies).some(value => !value)) {
      output.textContent = 'Choose a target for every binding and reset or resume for every stream.';
      return;
    }
    const button = event.target;
    button.disabled = true;
    try {
      const bytes = new Uint8Array(await reviewedBundle.file.arrayBuffer());
      const result = await post(
        `/v1/workspaces/${encodeURIComponent(workspace)}/streams/bundle/import`,
        {
          content_base64: bytesToBase64(bytes),
          binding_remaps: bindingRemaps,
          checkpoint_policies: checkpointPolicies,
          expected_digest: reviewedBundle.digest,
        },
      );
      output.textContent = `Imported ${result.items.length} stream definition(s). Checkpoint policies were applied atomically.\n${json(result)}`;
      await loadDefinitions(workspace, document.querySelector('#stream-list'), document.querySelector('#stream-definition-result'));
    } catch (error) {
      output.textContent = `Could not import stream Bundle: ${error.message}`;
    } finally {
      if (reviewedBundle) button.disabled = false;
    }
    return;
  }
  if (!(event.target instanceof HTMLButtonElement) || event.target.id !== 'stream-refresh') return;
  const form = document.querySelector('#stream-definition-form');
  const output = document.querySelector('#stream-definition-result');
  try {
    await loadDefinitions(String(new FormData(form).get('workspace')), document.querySelector('#stream-list'), output);
  } catch (error) {
    output.textContent = `Loading streams failed: ${error.message}`;
  }
});

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'stream-bundle-import-form') return;
  event.preventDefault();
  const file = form.elements.namedItem('bundle').files[0];
  const workspace = String(new FormData(form).get('workspace')).trim();
  const output = document.querySelector('#stream-bundle-result');
  if (!file || !workspace) return;
  const preview = form.querySelector('#stream-bundle-preview');
  if (file.size > 700 * 1024) {
    clearBundleReview('Bundle exceeds the 700 KiB archive limit.');
    output.textContent = 'Stream Bundle exceeds the 700 KiB import limit.';
    return;
  }
  preview.disabled = true;
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const plan = await post(
      `/v1/workspaces/${encodeURIComponent(workspace)}/streams/bundle/plan`,
      { content_base64: bytesToBase64(bytes) },
    );
    renderBundleReview(plan, file);
    output.textContent = `Verified ${plan.items.length} stream definition(s). Review bindings and checkpoint actions above.`;
  } catch (error) {
    clearBundleReview('Bundle verification failed; no definitions were imported.');
    output.textContent = `Could not preview stream Bundle: ${error.message}`;
  } finally {
    preview.disabled = false;
  }
});

document.addEventListener('change', event => {
  if (event.target instanceof HTMLInputElement && event.target.matches('#stream-bundle-import-form [name="bundle"]')) {
    clearBundleReview('The selected file changed. Verify and preview it before importing.');
  }
  if (event.target instanceof HTMLSelectElement && event.target.matches('[data-checkpoint-stream]')) {
    updateBundleImportButton();
  }
});

document.addEventListener('input', event => {
  if (event.target instanceof HTMLInputElement && event.target.matches('#stream-bundle-import-form [name="workspace"]')) {
    clearBundleReview('Workspace changed. Verify and preview the Bundle again before importing.');
  }
  if (event.target instanceof HTMLInputElement && event.target.matches('[data-binding-source]')) {
    updateBundleImportButton();
  }
});

document.addEventListener('change', event => {
  const list = event.target;
  if (!(list instanceof HTMLSelectElement) || list.id !== 'stream-list') return;
  const option = list.selectedOptions[0];
  if (!option?.dataset.definition) return;
  try {
    const definition = JSON.parse(option.dataset.definition);
    const form = document.querySelector('#stream-definition-form');
    for (const [name, value] of Object.entries({
      id: definition.id,
      name: definition.name,
      connection_id: definition.source.connection_id,
      resource: definition.source.resource,
      partitions: definition.source.partitions.join(', '),
      sink_kind: definition.sink.kind,
      target_ref: definition.sink.target_ref,
      profile_id: definition.runtime.profile_id,
      batch_limit: definition.runtime.batch_limit,
      timeout_seconds: definition.runtime.timeout_seconds,
      schema: JSON.stringify(definition.schema, null, 2),
    })) form.elements.namedItem(name).value = value;
    document.querySelector('#stream-health-form [name="stream"]').value = definition.id;
    document.querySelector('#stream-health-form [name="workspace"]').value = form.elements.namedItem('workspace').value;
  } catch {
    document.querySelector('#stream-definition-result').textContent = 'The selected stream definition is invalid.';
  }
});

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.getAttribute('id') !== 'stream-health-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const action = event.submitter?.value || 'health';
  const output = document.querySelector('#stream-health-result');
  const base = `/v1/workspaces/${encodeURIComponent(String(data.get('workspace')))}/streams/${encodeURIComponent(String(data.get('stream')))}`;
  try {
    const result = action === 'run'
      ? await post(`${base}/run`, { limit: Number(data.get('limit')) })
      : await get(`${base}/health`);
    if (action === 'health') renderStreamHealth(output, result);
    else output.textContent = json(result);
  } catch (error) { output.innerHTML = action === 'health' ? `<div class="error"><strong>Streaming health failed.</strong><p>${esc(error.message)}</p><button class="button" type="button" data-stream-retry>Retry health check</button></div>` : `Streaming batch failed: ${error.message}`; }
});

setTimeout(() => {
  window.addEventListener('hashchange', render);
  if (location.hash.slice(1) === 'streaming') render();
}, 0);
