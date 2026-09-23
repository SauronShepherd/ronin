import {studioContextKeys} from './studio-context.js';

const labels = Object.freeze({
  project: 'Project', revision: 'Revision', runtime: 'Runtime',
  dataset: 'Dataset', run: 'Run', compare: 'Compare',
});

export function renderContextBar(context = globalThis.roninStudioContext || {}) {
  const topbar = document.querySelector('.topbar');
  if (!topbar) return;
  let bar = topbar.querySelector('.context-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.className = 'context-bar';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Studio context');
    topbar.append(bar);
  }
  const items = studioContextKeys().filter((key) => context[key]);
  bar.innerHTML = items.map((key) => `<span class="context-chip"><b>${labels[key]}</b><span>${String(context[key]).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}</span></span>`).join('');
  bar.hidden = items.length === 0;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => renderContextBar(), {once: true});
} else {
  renderContextBar();
}
