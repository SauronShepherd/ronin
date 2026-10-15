import {post} from './api.js';

const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const view = () => document.querySelector('#view');

function addNavigation() {
  const nav = document.querySelector('.nav-group');
  if (nav && !nav.querySelector('[data-performance-nav]')) {
    nav.insertAdjacentHTML('beforeend', '<a class="nav-item" data-performance-nav href="#performance" aria-label="Performance Studio" aria-current="false"><span aria-hidden="true">◈</span><span class="nav-label">Performance Studio</span></a>');
  }
}

function renderReport(report) {
  const stages = report.series?.stages || [];
  const max = Math.max(...stages.map(stage => Number(stage.duration_ms || 0)), 1);
  const bars = stages.slice(0, 100).map((stage, index) => {
    const width = Math.max(1, 320 * Number(stage.duration_ms || 0) / max);
    const y = 24 + index * 30;
    return `<text x="0" y="${y + 12}">${esc(stage.id)}</text><rect x="100" y="${y}" width="${width}" height="16" fill="var(--blue)"></rect><text x="${Math.min(440, 106 + width)}" y="${y + 12}">${esc(stage.duration_ms)} ms · shuffle ${esc(stage.shuffle_bytes)} B · spill ${esc(stage.spill_bytes)} B</text>`;
  }).join('');
  return `<div class="panel"><h2>Analysis result</h2><p>Score: <strong>${esc(report.score)}</strong></p><svg viewBox="0 0 720 ${Math.max(64, 24 + stages.length * 30)}" role="img" aria-label="Stage duration, shuffle and spill chart"><title>Stage performance</title>${bars}</svg><details><summary>Findings (${report.issues?.length || 0})</summary><pre class="code">${esc(JSON.stringify(report.issues || [], null, 2))}</pre></details></div>`;
}

export function renderPerformance() {
  if (location.hash !== '#performance') return;
  addNavigation();
  const target = view();
  if (!target) return;
  target.innerHTML = '<div class="page-heading"><div><p class="eyebrow">RUNTIME INTELLIGENCE</p><h1 id="view-title">Performance Studio</h1><p class="muted">Analyze a normalized run and inspect stage bottlenecks.</p></div></div><div class="panel"><form id="performance-form"><label for="performance-run">Normalized run JSON</label><textarea class="field sql-editor" id="performance-run" rows="12" required>{"run_id":"demo","stages":[]}</textarea><label for="performance-baseline">Baseline JSON (optional)</label><textarea class="field sql-editor" id="performance-baseline" rows="6"></textarea><button class="button primary" type="submit">Analyze performance</button></form><pre id="performance-error" class="error" aria-live="polite"></pre></div><div id="performance-result" aria-live="polite"></div>';
}

document.addEventListener('submit', async event => {
  if (event.target.id !== 'performance-form') return;
  event.preventDefault();
  const error = document.querySelector('#performance-error');
  const result = document.querySelector('#performance-result');
  try {
    const payload = {run: JSON.parse(document.querySelector('#performance-run').value)};
    const baseline = document.querySelector('#performance-baseline').value.trim();
    if (baseline) payload.baseline = JSON.parse(baseline);
    result.innerHTML = '<p class="muted">Analyzing…</p>';
    error.textContent = '';
    result.innerHTML = renderReport(await post('/api/v1/performance/analyze', payload));
  } catch (exception) {
    error.textContent = `Analysis failed: ${exception.message}`;
    result.innerHTML = '';
  }
});

new MutationObserver(() => {
  addNavigation();
  if (location.hash === '#performance' && !document.querySelector('#performance-form')) {
    renderPerformance();
  }
}).observe(document.body, {childList: true, subtree: true});
window.addEventListener('hashchange', () => setTimeout(renderPerformance, 0));
addNavigation();
renderPerformance();
