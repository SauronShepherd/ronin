import {post} from './api.js';
import {json} from './dom.js';
import {confirmImpact} from './features.js';

function ensureCancelField() {
  const form = document.querySelector('#backfill-form');
  if (!form || document.querySelector('#backfill-cancel-id')) return;
  const label = document.createElement('label');
  label.innerHTML = 'Backfill ID to cancel<input class="field" id="backfill-cancel-id" name="cancel_id" placeholder="backfill-1" autocomplete="off">';
  form.querySelector('.toolbar')?.prepend(label);
}

document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-feature="cancel-backfill"]');
  if (!button) return;
  event.stopImmediatePropagation();
  const id = document.querySelector('#backfill-cancel-id')?.value.trim();
  const output = document.querySelector('#backfill-result');
  if (!id) {
    if (output) output.textContent = 'Enter a backfill ID before cancelling.';
    return;
  }
  if (!await confirmImpact(`Cancel backfill ${id}? Produced evidence is preserved and the action cannot be reversed.`)) return;
  const workspace = document.querySelector('#workflow-workspace')?.value.trim() || 'default';
  try {
    const result = await post(`/v1/workspaces/${encodeURIComponent(workspace)}/backfills/${encodeURIComponent(id)}/cancel`, {});
    if (output) output.textContent = json(result);
  } catch (error) {
    if (output) output.textContent = `Backfill cancellation failed: ${error.message}`;
  }
}, true);

new MutationObserver(ensureCancelField).observe(document.body, {childList: true, subtree: true});
setTimeout(ensureCancelField, 0);
