import {createStudioContext,DEFAULT_STUDIO_CONTEXT,studioContextKeys} from './studio-context.js';

const labels = Object.freeze({
  workspace: 'Workspace', project: 'Project', environment: 'Environment', revision: 'Revision', runtime: 'Runtime',
  dataset: 'Dataset', run: 'Run', compare: 'Compare',
});

const editableFields = Object.freeze([
  ['workspace', 'Workspace', 'default'],
  ['project', 'Project', 'examples/demo'],
  ['environment', 'Environment', 'local'],
  ['runtime', 'Runtime', 'local'],
]);

const RECENT_CONTEXTS_KEY = 'ronin.recent-contexts';
const MAX_RECENT_CONTEXTS = 5;

let dialog;

function escape(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
}

function pickerContext(values = {}) {
  return createStudioContext(Object.fromEntries(editableFields.map(([key]) => [key, values[key]])));
}

function contextSignature(context) {
  return editableFields.map(([key]) => context[key] || '').join('\u001f');
}

function readRecentContexts() {
  try {
    const saved = JSON.parse(localStorage.getItem(RECENT_CONTEXTS_KEY) || '[]');
    if (!Array.isArray(saved)) return [];
    const contexts = [];
    for (const value of saved) {
      try {
        const context = pickerContext(value);
        if (Object.keys(context).length && !contexts.some((item) => contextSignature(item) === contextSignature(context))) contexts.push(context);
      } catch {
        // Ignore malformed local-only history; the active context remains authoritative.
      }
    }
    return contexts.slice(0, MAX_RECENT_CONTEXTS);
  } catch {
    return [];
  }
}

function rememberContext(values) {
  const context = pickerContext(values);
  if (!Object.keys(context).length) return;
  const recent = [context, ...readRecentContexts().filter((item) => contextSignature(item) !== contextSignature(context))].slice(0, MAX_RECENT_CONTEXTS);
  try {
    localStorage.setItem(RECENT_CONTEXTS_KEY, JSON.stringify(recent));
  } catch {
    // Private browsing or a restricted storage policy must not block context changes.
  }
}

function renderRecentContexts() {
  const list = dialog?.querySelector('#context-recent-list');
  if (!list) return;
  const recent = readRecentContexts();
  list.innerHTML = recent.length
    ? recent.map((context) => {
      const summary = `${context.workspace || '—'} / ${context.project || '—'}`;
      const detail = [context.environment, context.runtime].filter(Boolean).join(' · ') || 'No execution profile set';
      return `<button class="context-recent-option" type="button" data-action="apply-recent-context" data-context-json="${escape(JSON.stringify(context))}"><span class="context-recent-copy"><strong>${escape(summary)}</strong><small>${escape(detail)}</small></span><span class="context-recent-use">Use</span></button>`;
    }).join('')
    : '<p class="context-recent-empty">Your recent working contexts will appear here. They stay in this browser only.</p>';
}

function ensureDialog() {
  if (dialog) return dialog;
  dialog = document.createElement('dialog');
  dialog.id = 'context-dialog';
  dialog.className = 'dialog context-dialog';
  dialog.setAttribute('aria-labelledby', 'context-dialog-title');
  dialog.innerHTML = `<form id="context-form" class="context-settings">
    <div class="context-dialog-heading"><div><p class="eyebrow">WORKING CONTEXT</p><h2 id="context-dialog-title">Choose where you work</h2></div><button class="icon-button" type="button" data-action="close-context" aria-label="Close context settings">×</button></div>
    <p class="context-dialog-copy">Set the boundary once and carry it through every Studio. This changes the local working context and URL; it does not create or modify a server resource.</p>
    <section class="context-recent" aria-labelledby="context-recent-title"><div class="context-recent-heading"><div><p class="eyebrow" id="context-recent-title">RECENT CONTEXTS</p><p class="context-recent-note">Saved locally for fast switching. Credentials are never stored here.</p></div></div><div id="context-recent-list" class="context-recent-list"></div></section>
    <div class="grid two">${editableFields.map(([key,label,placeholder]) => `<label>${label}<input class="field" name="${key}" placeholder="${placeholder}" maxlength="256" autocomplete="off"></label>`).join('')}</div>
    <p class="context-dialog-note">Secrets never belong in this context. Use Server connection for access credentials.</p>
    <div class="dialog-actions"><button class="button" type="button" data-action="close-context">Cancel</button><button class="button primary" type="submit">Apply context</button></div>
  </form>`;
  document.body.append(dialog);
  dialog.querySelector('#context-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      setStudioContext(Object.fromEntries(editableFields.map(([key]) => [key, form.get(key)])));
      dialog.close();
    } catch (error) {
      const message = document.createElement('p');
      message.className = 'context-dialog-error';
      message.setAttribute('role', 'alert');
      message.textContent = error.message;
      dialog.querySelector('.context-dialog-error')?.remove();
      event.currentTarget.prepend(message);
    }
  });
  dialog.addEventListener('click', (event) => {
    const recent = event.target.closest('[data-action="apply-recent-context"]');
    if (!recent) return;
    try {
      setStudioContext(JSON.parse(recent.dataset.contextJson));
      dialog.close();
    } catch (error) {
      const message = document.createElement('p');
      message.className = 'context-dialog-error';
      message.setAttribute('role', 'alert');
      message.textContent = error.message;
      dialog.querySelector('.context-dialog-error')?.remove();
      dialog.querySelector('#context-form')?.prepend(message);
    }
  });
  return dialog;
}

function openContextPicker() {
  const picker = ensureDialog();
  const active = globalThis.roninStudioContext || {};
  const resolved = Object.keys(active).length ? active : DEFAULT_STUDIO_CONTEXT;
  for (const [key] of editableFields) {
    const input = picker.querySelector(`[name="${key}"]`);
    if (input) input.value = resolved[key] || '';
  }
  renderRecentContexts();
  picker.showModal();
  picker.querySelector('[name="workspace"]')?.focus();
}

export function setStudioContext(values = {}) {
  const context = createStudioContext({...globalThis.roninStudioContext, ...values});
  const url = new URL(location.href);
  for (const key of studioContextKeys()) url.searchParams.delete(key);
  for (const [key, value] of Object.entries(context)) url.searchParams.set(key, value);
  history.pushState({}, '', `${url.pathname}${url.search}${url.hash}`);
  globalThis.roninStudioContext = context;
  rememberContext(context);
  renderContextBar(context);
  window.dispatchEvent(new CustomEvent('ronin-context-change', {detail: context}));
  return context;
}

function syncContextFromLocation() {
  const params = new URLSearchParams(location.search);
  const values = Object.fromEntries(studioContextKeys().map((key) => [key, params.get(key) || undefined]));
  const context = createStudioContext(values);
  globalThis.roninStudioContext = context;
  renderContextBar(context);
  window.dispatchEvent(new CustomEvent('ronin-context-change', {detail: context}));
}

export function renderContextBar(context = globalThis.roninStudioContext || {}) {
  const topbar = document.querySelector('.topbar');
  if (!topbar) return;
  let bar = topbar.querySelector('.context-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.className = 'context-bar';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Studio context');
    topbar.insertBefore(bar, topbar.querySelector('.connection-open'));
  }
  const resolved = Object.keys(context).length ? context : DEFAULT_STUDIO_CONTEXT;
  const items = studioContextKeys().filter((key) => resolved[key]);
  bar.innerHTML = `${items.map((key) => `<span class="context-chip"><b>${labels[key]}</b><span title="${escape(resolved[key])}">${escape(resolved[key])}</span></span>`).join('')}<button class="context-change" type="button" data-action="open-context" aria-haspopup="dialog" aria-controls="context-dialog">Change context</button>`;
  bar.hidden = false;
}

document.addEventListener('click', (event) => {
  const control = event.target.closest('[data-action="open-context"],[data-action="close-context"]');
  if (!control) return;
  if (control.dataset.action === 'open-context') openContextPicker();
  else if (dialog?.open) dialog.close();
});

window.addEventListener('popstate', syncContextFromLocation);

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => renderContextBar(), {once: true});
} else {
  renderContextBar();
}
