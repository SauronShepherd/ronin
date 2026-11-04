import { get, post, put } from './api.js';
import { json, page } from './dom.js';

const MAX_BUNDLE_BYTES = 700 * 1024;
let reviewedBundle = null;

function render() {
  if (location.hash.slice(1) !== 'semantic') return;
  const view = document.querySelector('#view');
  if (!view) return;
  view.innerHTML = `${page('Semantic Studio', 'METRICS · DASHBOARDS')}
    <section class="panel">
      <h2>Semantic models</h2>
      <form id="semantic-model-form" class="toolbar">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Project<input class="field" name="project" value="examples/demo" required></label>
        <button class="button" type="submit">List models</button>
      </form>
      <pre id="semantic-model-result" class="code" aria-live="polite">No models loaded.</pre>
    </section>
    <section class="panel">
      <h2>Dashboards</h2>
      <form id="semantic-dashboard-form" class="toolbar">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Project<input class="field" name="project" value="examples/demo" required></label>
        <label>Dashboard ID<input class="field" name="dashboard" value="sales_dashboard" required></label>
        <button class="button" type="submit" name="action" value="list">List dashboards</button>
        <button class="button primary" type="submit" name="action" value="execute">Execute dashboard</button>
        <button class="button" type="submit" name="action" value="save">Save dashboard</button>
        <label>Definition<textarea class="field" name="definition" rows="5">{"id":"sales_dashboard","name":"Sales","tiles":[{"id":"orders","title":"Orders","chart":"number","query":{"model_id":"sales","measures":["orders"],"dimensions":[],"filters":[],"limit":100}}]}</textarea></label>
      </form>
      <pre id="semantic-dashboard-result" class="code" aria-live="polite">No dashboards loaded.</pre>
    </section>
    <section class="panel">
      <h2>Portable semantic Bundle</h2>
      <p>Export model and dashboard definitions, or verify a Bundle before importing it into a project.</p>
      <form id="semantic-bundle-export-form" class="toolbar">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Project<input class="field" name="project" value="examples/demo" required></label>
        <button class="button" id="semantic-bundle-export" type="button">Download semantic Bundle</button>
      </form>
      <form id="semantic-bundle-import-form" class="toolbar">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Target project<input class="field" name="project" value="examples/demo" required></label>
        <label>Bundle file<input class="field" name="bundle" type="file" accept=".roninbundle,.zip,application/zip" required></label>
        <button class="button" type="button" id="semantic-bundle-preview">Verify and preview</button>
        <button class="button primary" type="button" id="semantic-bundle-import" disabled>Import reviewed Bundle</button>
      </form>
      <pre id="semantic-bundle-result" class="code" aria-live="polite">Choose a Bundle to review before importing.</pre>
    </section>
    <section class="panel">
      <h2>Metric query</h2>
      <form id="semantic-query-form">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Project<input class="field" name="project" value="examples/demo" required></label>
        <label>Metric query JSON<textarea class="field sql-editor" name="query" rows="5">{"model_id":"sales","measures":["revenue"],"dimensions":[],"filters":[],"limit":100}</textarea></label>
        <button class="button primary" type="submit">Run metric query</button>
      </form>
      <pre id="semantic-query-result" class="code" aria-live="polite">No query executed.</pre>
    </section>
    <section class="panel">
      <h2>Semantic join</h2>
      <form id="semantic-join-form">
        <label>Workspace<input class="field" name="workspace" value="default" required></label>
        <label>Project<input class="field" name="project" value="examples/demo" required></label>
        <label>Join JSON<textarea class="field sql-editor" name="join" rows="5">{"base_model_id":"sales","steps":[],"limit":100}</textarea></label>
        <button class="button" type="submit">Run join</button>
      </form>
      <pre id="semantic-join-result" class="code" aria-live="polite">No join executed.</pre>
    </section>`;
  reviewedBundle = null;
}

function scopeFrom(form) {
  const data = new FormData(form);
  return {
    workspace: String(data.get('workspace')).trim(),
    project: String(data.get('project')).trim(),
  };
}

function bundlePath({ workspace, project }) {
  return `/v1/workspaces/${encodeURIComponent(workspace)}/projects/${encodeURIComponent(project)}/semantic/bundle`;
}

async function archiveDigest(bytes) {
  const digestBytes = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return [...digestBytes].map(value => value.toString(16).padStart(2, '0')).join('');
}

function bytesToBase64(bytes) {
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

function clearReview(message) {
  reviewedBundle = null;
  const button = document.querySelector('#semantic-bundle-import');
  if (button) button.disabled = true;
  const output = document.querySelector('#semantic-bundle-result');
  if (output && message) output.textContent = message;
}

function describeBundle(plan) {
  const names = values => values.map(item => item.id).join(', ') || 'none';
  return `Verified ${plan.models.length} model(s): ${names(plan.models)}\nVerified ${plan.dashboards.length} dashboard(s): ${names(plan.dashboards)}\nSHA-256 ${plan.bundle_digest}\nReview the target project before importing.`;
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  const data = event.submitter
    ? new FormData(form, event.submitter)
    : new FormData(form);
  const scope = scopeFrom(form);
  const path = `/v1/workspaces/${encodeURIComponent(scope.workspace)}/projects/${encodeURIComponent(scope.project)}/semantic/`;
  try {
    if (form.id === 'semantic-model-form') {
      event.preventDefault();
      document.querySelector('#semantic-model-result').textContent = json(await get(`${path}models`));
    } else if (form.id === 'semantic-dashboard-form') {
      event.preventDefault();
      const action = String(data.get('action'));
      const dashboard = encodeURIComponent(String(data.get('dashboard')));
      const result = action === 'execute'
        ? await post(`${path}dashboards/${dashboard}/execute`, {})
        : action === 'save'
          ? await put(`${path}dashboards/${dashboard}`, JSON.parse(String(data.get('definition'))))
          : await get(`${path}dashboards`);
      document.querySelector('#semantic-dashboard-result').textContent = json(result);
    } else if (form.id === 'semantic-query-form') {
      event.preventDefault();
      document.querySelector('#semantic-query-result').textContent = json(await post(`${path}query`, JSON.parse(String(data.get('query')))));
    } else if (form.id === 'semantic-join-form') {
      event.preventDefault();
      document.querySelector('#semantic-join-result').textContent = json(await post(`${path}join`, JSON.parse(String(data.get('join')))));
    }
  } catch (error) {
    const target = form.id === 'semantic-model-form' ? '#semantic-model-result'
      : form.id === 'semantic-dashboard-form' ? '#semantic-dashboard-result'
        : form.id === 'semantic-join-form' ? '#semantic-join-result' : '#semantic-query-result';
    document.querySelector(target).textContent = `Semantic operation failed: ${error.message}`;
  }
});

document.addEventListener('change', event => {
  if (event.target.matches('#semantic-bundle-import-form input[name="bundle"]')) {
    clearReview('The selected file changed. Verify and preview it again before importing.');
  }
});

document.addEventListener('click', async event => {
  const button = event.target;
  if (!(button instanceof HTMLButtonElement)) return;
  if (button.id === 'semantic-bundle-export') {
    const scope = scopeFrom(document.querySelector('#semantic-bundle-export-form'));
    const output = document.querySelector('#semantic-bundle-result');
    try {
      const payload = await get(bundlePath(scope));
      if (payload.media_type !== 'application/vnd.ronin.bundle+zip' || typeof payload.content_base64 !== 'string') throw new Error('Invalid semantic Bundle response');
      const bytes = Uint8Array.from(atob(payload.content_base64), character => character.charCodeAt(0));
      if (bytes.length !== payload.size_bytes || await archiveDigest(bytes) !== payload.digest) throw new Error('Semantic Bundle digest or size does not match its receipt');
      const url = URL.createObjectURL(new Blob([bytes], { type: payload.media_type }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${scope.project.replace(/[^A-Za-z0-9._-]/g, '_')}-semantic.roninbundle`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      output.textContent = `Downloaded ${link.download} (${payload.size_bytes} bytes, SHA-256 ${payload.digest}).`;
    } catch (error) {
      output.textContent = `Could not download semantic Bundle: ${error.message}`;
    }
    return;
  }
  if (button.id === 'semantic-bundle-preview') {
    const form = document.querySelector('#semantic-bundle-import-form');
    const scope = scopeFrom(form);
    const file = form.elements.bundle.files[0];
    const output = document.querySelector('#semantic-bundle-result');
    clearReview();
    if (!file) {
      output.textContent = 'Choose a semantic Bundle file first.';
      return;
    }
    if (file.size > MAX_BUNDLE_BYTES) {
      output.textContent = 'Semantic Bundle exceeds the 700 KiB file limit.';
      return;
    }
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const digest = await archiveDigest(bytes);
      const plan = await post(`${bundlePath(scope)}/plan`, { content_base64: bytesToBase64(bytes) });
      if (plan.bundle_digest !== digest || plan.size_bytes !== bytes.length) throw new Error('The server plan does not match the selected Bundle.');
      reviewedBundle = { file, ...scope, digest, plan };
      output.textContent = describeBundle(plan);
      button.nextElementSibling.disabled = false;
    } catch (error) {
      output.textContent = `Could not verify semantic Bundle: ${error.message}`;
    }
    return;
  }
  if (button.id === 'semantic-bundle-import') {
    const form = document.querySelector('#semantic-bundle-import-form');
    const scope = scopeFrom(form);
    const file = form.elements.bundle.files[0];
    const output = document.querySelector('#semantic-bundle-result');
    const path = `/v1/workspaces/${encodeURIComponent(scope.workspace)}/projects/${encodeURIComponent(scope.project)}/semantic/`;
    if (!reviewedBundle || file !== reviewedBundle.file || scope.workspace !== reviewedBundle.workspace || scope.project !== reviewedBundle.project) {
      clearReview('The file or target project changed. Verify and preview the Bundle again.');
      return;
    }
    button.disabled = true;
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      if (await archiveDigest(bytes) !== reviewedBundle.digest) throw new Error('The selected Bundle changed after review.');
      const result = await post(`${bundlePath(scope)}/import`, {
        content_base64: bytesToBase64(bytes),
        expected_digest: reviewedBundle.digest,
      });
      output.textContent = `Imported ${result.models.length} model(s) and ${result.dashboards.length} dashboard(s) into ${scope.project}.\n${json(result)}`;
      reviewedBundle = null;
      const refreshes = await Promise.allSettled([
        get(`${path}models`).then(value => { document.querySelector('#semantic-model-result').textContent = json(value); }),
        get(`${path}dashboards`).then(value => { document.querySelector('#semantic-dashboard-result').textContent = json(value); }),
      ]);
      const refreshError = refreshes.find(result => result.status === 'rejected');
      if (refreshError) output.textContent += `\nImport succeeded, but refreshing the lists failed: ${refreshError.reason.message}`;
    } catch (error) {
      output.textContent = `Could not import semantic Bundle: ${error.message}`;
    } finally {
      button.disabled = !reviewedBundle;
    }
  }
});

setTimeout(() => {
  window.addEventListener('hashchange', render);
  if (location.hash.slice(1) === 'semantic') render();
}, 0);
