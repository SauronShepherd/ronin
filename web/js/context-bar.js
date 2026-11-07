import {studioContextKeys} from './studio-context.js';

const labels = Object.freeze({
  workspace: 'Workspace', project: 'Project', environment: 'Environment', revision: 'Revision', runtime: 'Runtime',
  dataset: 'Dataset', run: 'Run', compare: 'Compare',
});

const defaultContext = Object.freeze({workspace: 'default', project: 'examples/demo', runtime: 'local'});

function escape(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
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
  const resolved = {...defaultContext, ...context};
  const items = studioContextKeys().filter((key) => resolved[key]);
  bar.innerHTML = `${items.map((key) => `<span class="context-chip"><b>${labels[key]}</b><span>${escape(resolved[key])}</span></span>`).join('')}<a class="context-change" href="#workspaces">Change context</a>`;
  bar.hidden = false;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => renderContextBar(), {once: true});
} else {
  renderContextBar();
}
