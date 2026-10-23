const DOG_AVATAR = './assets/ronin-logo-mark.png';

const tutorialCatalog = [
  {
    id: 'ronin-tour',
    title: 'Meet Ronin: the complete product tour',
    subtitle: 'A friendly walk through the control plane, studios, data, AI and delivery.',
    duration: '8 min',
    level: 'New builder',
    tags: ['overview', 'getting started', 'platform', 'navigation'],
    steps: [
      { selector: '.rail-brand', title: 'Welcome to the dojo', body: "Hi, I’m Ronin. I’m a lordless data dog: no vendor throne, just a very good nose for useful workflows. This is your open Data + AI control plane.", placement: 'right' },
      { selector: '.nav-item[href="#workspaces"]', title: 'Start with a workspace', body: 'Workspaces keep teams, projects and permissions together. Think of them as tidy dojo rooms: every experiment knows where it belongs.', placement: 'right' },
      { selector: '.nav-item[href="#data"]', title: 'Shape and move data', body: 'Data Engineering gives you connectors, pipelines, previews and SQL. Build a path once, inspect it, then run it with evidence attached.', placement: 'right' },
      { selector: '.nav-item[href="#mlstudio"]', title: 'Turn data into models', body: 'Machine Learning Studio is the training yard: labs, features, experiments, comparisons, model cards and promotion gates in one trail.', placement: 'right' },
      { selector: '.nav-item[href="#synthetic"]', title: 'Create safe practice data', body: 'Synthetic Data Studio helps teams explore realistic data without passing sensitive records around. More learning, fewer awkward permissions meetings.', placement: 'right' },
      { selector: '.nav-item[href="#quality"]', title: 'Guard the quality gates', body: 'Quality Studio makes contracts and checks visible. Ronin will happily bark before a bad dataset reaches production.', placement: 'right' },
      { selector: '.nav-item[href="#migration"]', title: 'Migrate with evidence', body: 'Migration Studio takes you from discovery to scope, blueprint, generated code, validation and promotion. Every important decision can be reviewed.', placement: 'right' },
      { selector: '#api-url', title: 'Connect your control plane', body: 'Use the top bar to point Studio at the API. The browser keeps the URL locally and the bearer token in session storage. In a static preview, a friendly “API unavailable” message is expected until the control plane is running.', placement: 'bottom' },
      { selector: '[data-action="open-command"]', title: 'Keep your paws on the keyboard', body: 'The command entry is your shortcut door. Use it when you know the destination and want to skip the scenic route.', placement: 'bottom' },
      { selector: '#tutorial-library', title: 'Choose your next trail', body: 'That’s the whole map. Pick a focused tutorial whenever you want a deeper lesson, and leave any tour at any time with Close or Escape.', placement: 'top' }
    ]
  },
  {
    id: 'workspace-foundation',
    title: 'Workspace & project foundations',
    subtitle: 'Organise people, projects and environments before the first run.',
    duration: '4 min',
    level: 'Foundation',
    tags: ['workspace', 'projects', 'permissions', 'environments'],
    steps: [
      { selector: '.nav-item[href="#workspaces"]', title: 'Open Workspaces', body: 'A workspace is the boundary for discovery, access and shared delivery. Start here when you are onboarding a team.', placement: 'right' },
      { selector: '.nav-item[href="#projects"]', title: 'Enter Projects', body: 'Projects hold the portable unit of work: code, configuration, pipelines and environment bindings.', placement: 'right' },
      { selector: '.nav-item[href="#environments"]', title: 'Compare environments', body: 'Use environment views to understand what differs before promoting a change. A calm diff beats a heroic rollback.', placement: 'right' },
      { selector: '.nav-item[href="#access"]', title: 'Keep access explicit', body: 'Access is API-backed and grant-aware. Review principals, groups and role bindings without rendering secret values.', placement: 'right' }
    ]
  },
  {
    id: 'data-engineering',
    title: 'Data Engineering trail',
    subtitle: 'Connect sources, preview transformations and ship repeatable pipelines.',
    duration: '5 min',
    level: 'Builder',
    tags: ['data', 'pipelines', 'connectors', 'sql', 'ingestion'],
    steps: [
      { selector: '.nav-item[href="#data"]', title: 'Open Data Engineering', body: 'This is the workbench for connectors, runtime health, pipeline validation and project-scoped runs.', placement: 'right' },
      { selector: '.nav-item[href="#ingestion"]', title: 'Preview ingestion safely', body: 'Ingestion Studio lets you inspect connector plans and checkpoint health before a source is allowed to flow.', placement: 'right' },
      { selector: '.nav-item[href="#sql"]', title: 'Ask bounded SQL questions', body: 'SQL is read-only and bounded by the request contract. Query to learn, then turn the useful shape into a pipeline.', placement: 'right' },
      { selector: '.nav-item[href="#runs"]', title: 'Follow the run trail', body: 'Runs preserve status, events and evidence. When something barks, the timeline tells you where and why.', placement: 'right' }
    ]
  },
  {
    id: 'ml-ai-studios',
    title: 'ML & AI Studios',
    subtitle: 'From features and experiments to governed GenAI and model delivery.',
    duration: '6 min',
    level: 'Practitioner',
    tags: ['machine learning', 'features', 'genai', 'models', 'experiments'],
    steps: [
      { selector: '.nav-item[href="#mlstudio"]', title: 'Train in ML Studio', body: 'Create a lab, compare candidates and keep model quality attached to the experiment that produced it.', placement: 'right' },
      { selector: '.nav-item[href="#ai"]', title: 'Use AI Studio', body: 'AI Studio exposes model discovery and bounded invocation for practical, inspectable automations.', placement: 'right' },
      { selector: '.nav-item[href="#genai"]', title: 'Ground GenAI work', body: 'GenAI Studio brings providers, prompts, indexes, tools, agents and RAG evaluations into one governed surface.', placement: 'right' },
      { selector: '.nav-item[href="#catalog"]', title: 'Make meaning discoverable', body: 'Catalog search connects people to governed assets and lineage context, so a useful feature is easier to find than to reinvent.', placement: 'right' }
    ]
  },
  {
    id: 'quality-observability',
    title: 'Quality, observability & operations',
    subtitle: 'Make every result reviewable, explainable and easier to operate.',
    duration: '5 min',
    level: 'Operator',
    tags: ['quality', 'monitoring', 'alerts', 'evidence', 'finops'],
    steps: [
      { selector: '.nav-item[href="#quality"]', title: 'Define quality contracts', body: 'Quality Studio turns expectations into visible contracts and state checks instead of tribal knowledge.', placement: 'right' },
      { selector: '.nav-item[href="#alerts"]', title: 'Respond to signals', body: 'Monitoring and Alerts keeps rules, instances, evaluation and acknowledgement in the same operational loop.', placement: 'right' },
      { selector: '.nav-item[href="#runs"]', title: 'Inspect durable evidence', body: 'Run detail brings status, event history and evidence references together for a defensible review.', placement: 'right' },
      { selector: '.nav-item[href="#finops"]', title: 'Keep an eye on cost', body: 'FinOps shows usage, costs and budgets so a successful pipeline does not quietly become a surprise invoice.', placement: 'right' }
    ]
  },
  {
    id: 'delivery-migration',
    title: 'Migration & delivery path',
    subtitle: 'Move from discovery to a portable, qualification-ready release.',
    duration: '5 min',
    level: 'Ship safely',
    tags: ['migration', 'deployment', 'cloud', 'debugger', 'release'],
    steps: [
      { selector: '.nav-item[href="#migration"]', title: 'Discover before converting', body: 'Migration Studio inventories source assets without executing source content. First understand the terrain, then choose the scope.', placement: 'right' },
      { selector: '.nav-item[href="#debugger"]', title: 'Debug with boundaries', body: 'Debugger sessions make snapshots and breakpoints explicit, so troubleshooting is a recorded step rather than a guess.', placement: 'right' },
      { selector: '.nav-item[href="#cloud"]', title: 'Review a cloud plan', body: 'Cloud Studio validates a target and generates a reviewable plan. Ronin prefers a plan everyone can read before anyone applies it.', placement: 'right' },
      { selector: '.nav-item[href="#deployments"]', title: 'Promote with intent', body: 'Deployment bindings connect projects to environments. Pair them with quality and evidence gates before release.', placement: 'right' }
    ]
  },
  {
    id: 'synthetic-data',
    title: 'Synthetic Data Studio',
    subtitle: 'Generate useful test data while keeping sensitive records out of the room.',
    duration: '4 min',
    level: 'Safe practice',
    tags: ['synthetic data', 'privacy', 'generation', 'formats', 'lineage'],
    steps: [
      { selector: '.nav-item[href="#synthetic"]', title: 'Open Synthetic Data Studio', body: 'This studio is your rehearsal kitchen: create realistic data, inspect its lineage and choose an export format before sharing it.', placement: 'right' },
      { selector: '.nav-item[href="#catalog"]', title: 'Find approved assets', body: 'Catalog context helps you locate the governed source or schema that your synthetic recipe is meant to mirror.', placement: 'right' },
      { selector: '.nav-item[href="#quality"]', title: 'Check the result', body: 'Pair generated data with quality contracts so “looks realistic” becomes a measurable statement.', placement: 'right' }
    ]
  },
  {
    id: 'workflows-notebooks',
    title: 'Workflows & Notebook Studio',
    subtitle: 'Turn exploratory work into scheduled, observable steps.',
    duration: '4 min',
    level: 'Builder',
    tags: ['workflows', 'notebooks', 'schedules', 'triggers', 'backfills'],
    steps: [
      { selector: '.nav-item[href="#notebooks"]', title: 'Explore in notebooks', body: 'Notebook Studio gives experiments a durable home with revisions, archive actions and a bridge to jobs.', placement: 'right' },
      { selector: '.nav-item[href="#workflows"]', title: 'Schedule the useful parts', body: 'Workflows turns a repeatable notebook or pipeline into a schedule, event trigger or controlled backfill.', placement: 'right' },
      { selector: '.nav-item[href="#runs"]', title: 'Observe each execution', body: 'Every run should leave a trace. Use events and evidence to make scheduled work explainable to the next person on call.', placement: 'right' }
    ]
  },
  {
    id: 'catalog-governance',
    title: 'Catalog & governance',
    subtitle: 'Make assets findable, understandable and safe to use.',
    duration: '4 min',
    level: 'Governance',
    tags: ['catalog', 'lineage', 'access', 'semantic', 'governance'],
    steps: [
      { selector: '.nav-item[href="#catalog"]', title: 'Search governed assets', body: 'Catalog search is the front door for reusable data. Search by name or tag and keep the result inside its workspace boundary.', placement: 'right' },
      { selector: '.nav-item[href="#semantic"]', title: 'Give data a shared language', body: 'Semantic Studio models joins and dashboards so people can discuss meaning, not just column names.', placement: 'right' },
      { selector: '.nav-item[href="#access"]', title: 'Make permissions visible', body: 'Governance is practical when access is explicit. Review grants without exposing secrets or pretending an unavailable route exists.', placement: 'right' }
    ]
  }
];

const catalogText = item => [item.title, item.subtitle, item.level, ...item.tags, ...item.steps.map(step => `${step.title} ${step.body}`)].join(' ').toLowerCase();
let current = null;
let stepIndex = 0;
let overlay;
let returnFocus = null;
let observer;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
}

function tutorialCard(item) {
  return `<article class="tutorial-card" data-tutorial-card="${item.id}">
    <div class="tutorial-card-top"><span class="tutorial-kicker">${escapeHtml(item.level)}</span><span>${escapeHtml(item.duration)}</span></div>
    <h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.subtitle)}</p>
    <div class="tutorial-tags">${item.tags.slice(0, 4).map(tag => `<span>${escapeHtml(tag)}</span>`).join('')}</div>
    <button class="button tutorial-start" type="button" data-tutorial-start="${item.id}">${item.id === 'ronin-tour' ? 'Start the Ronin tour' : 'Start tutorial'} <span aria-hidden="true">→</span></button>
  </article>`;
}

function renderLibrary(root) {
  if (!root || root.querySelector('#tutorial-library')) return;
  const hero = document.createElement('section');
  hero.className = 'tutorial-hero';
  hero.id = 'tutorial-hero';
  hero.setAttribute('aria-labelledby', 'tutorial-hero-title');
  hero.innerHTML = `<div class="tutorial-hero-art"><img src="${DOG_AVATAR}" alt="Ronin, the samurai water dog" loading="eager"><span class="tutorial-paw" aria-hidden="true">🐾</span></div>
    <div class="tutorial-hero-copy"><p class="eyebrow">YOUR FIRST TRAIL</p><h1 id="tutorial-hero-title">Meet Ronin, your data dojo guide.</h1><p>Take a playful, practical tour through the product. Ronin points, explains and occasionally makes a terrible dog joke. You can pause or leave whenever you like.</p>
    <div class="tutorial-hero-actions"><button class="button primary tutorial-start" type="button" data-tutorial-start="ronin-tour">Start the Ronin tour <span aria-hidden="true">→</span></button><span class="tutorial-hint">English · 8 minutes · always skippable</span></div></div>`;
  root.prepend(hero);

  const library = document.createElement('section');
  library.className = 'tutorial-library';
  library.id = 'tutorial-library';
  library.setAttribute('aria-labelledby', 'tutorial-library-title');
  library.innerHTML = `<div class="tutorial-library-head"><div><p class="eyebrow">RONIN ACADEMY</p><h2 id="tutorial-library-title">Choose a guided trail</h2><p class="muted">Search by feature, studio or concept. Finish one trail and Ronin will suggest the next paw-step.</p></div><label class="tutorial-search"><span aria-hidden="true">⌕</span><span class="sr-only">Search tutorials</span><input id="tutorial-search" type="search" placeholder="Search tutorials or content…" autocomplete="off"></label></div><div class="tutorial-grid" id="tutorial-grid">${tutorialCatalog.map(tutorialCard).join('')}</div><p class="tutorial-empty" id="tutorial-empty" hidden>No trails match that search. Try “data”, “quality” or “models”.</p>`;
  root.append(library);
}

function ensureOverlay() {
  if (overlay) return overlay;
  overlay = document.createElement('div');
  overlay.id = 'tutorial-overlay';
  overlay.className = 'tutorial-overlay';
  overlay.hidden = true;
  overlay.innerHTML = `<div class="tutorial-backdrop" data-tutorial-close="true"></div><div class="tutorial-spotlight" aria-hidden="true"></div><div class="tutorial-pointer" aria-hidden="true"></div>
    <section class="tutorial-dialog" role="dialog" aria-modal="true" aria-labelledby="tutorial-step-title" aria-describedby="tutorial-step-body" tabindex="-1"><button class="tutorial-close" type="button" data-tutorial-close="true" aria-label="Close tutorial">×</button><div class="tutorial-dialog-header"><img src="${DOG_AVATAR}" alt="" class="tutorial-avatar"><div><p class="tutorial-kicker" id="tutorial-step-counter" aria-live="polite">STEP 1 OF 1</p><h2 id="tutorial-step-title"></h2></div></div><p id="tutorial-step-body"></p><div class="tutorial-progress"><span id="tutorial-progress-bar"></span></div><div class="tutorial-dialog-actions"><button class="button" type="button" data-tutorial-skip="true">Exit tutorial</button><div class="tutorial-next-actions"><button class="button" type="button" data-tutorial-prev="true">Back</button><button class="button primary" type="button" data-tutorial-next="true">Next <span aria-hidden="true">→</span></button></div></div><div id="tutorial-recommendations" class="tutorial-recommendations" hidden></div></section>`;
  document.body.append(overlay);
  return overlay;
}

function targetFor(step) {
  const target = document.querySelector(step.selector);
  const visible = element => {
    if (!element || !element.getClientRects().length) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  if (visible(target)) return target;
  if (step.selector === '.rail-brand' && visible(document.querySelector('.tutorial-hero-art'))) return document.querySelector('.tutorial-hero-art');
  if (step.selector === '#api-url' && visible(document.querySelector('[data-action="open-command"]'))) return document.querySelector('[data-action="open-command"]');
  return ['.page-header', '#tutorial-hero', '.topbar', '#view', '.app-main']
    .map(selector => document.querySelector(selector)).find(visible) || document.querySelector('.app-main');
}

function placeDialog(target, placement = 'bottom') {
  const dialog = overlay.querySelector('.tutorial-dialog');
  const rect = target?.getBoundingClientRect?.();
  if (!rect) return;
  const gap = 18;
  const margin = 24;
  const width = Math.min(420, Math.max(0, window.innerWidth - margin * 2));
  dialog.style.width = `${width}px`;
  const dialogHeight = Math.min(dialog.scrollHeight || 280, Math.max(0, window.innerHeight - margin * 2));
  let left = rect.left + rect.width / 2 - width / 2;
  let top = rect.bottom + gap;
  if (placement === 'right') { left = rect.right + gap; top = rect.top + rect.height / 2 - dialogHeight / 2; }
  if (placement === 'left') { left = rect.left - width - gap; top = rect.top + rect.height / 2 - dialogHeight / 2; }
  if (placement === 'top') top = rect.top - dialogHeight - gap;
  const maxLeft = Math.max(margin, window.innerWidth - width - margin);
  const maxTop = Math.max(margin, window.innerHeight - dialogHeight - margin);
  left = Math.max(margin, Math.min(maxLeft, left));
  top = Math.max(margin, Math.min(maxTop, top));
  dialog.style.left = `${left}px`; dialog.style.top = `${top}px`;
}

function paintSpotlight(target) {
  const spotlight = overlay.querySelector('.tutorial-spotlight');
  const pointer = overlay.querySelector('.tutorial-pointer');
  if (!target) { spotlight.style.opacity = '0'; pointer.style.opacity = '0'; return; }
  const rect = target.getBoundingClientRect();
  const pad = 8;
  Object.assign(spotlight.style, { left: `${Math.max(4, rect.left - pad)}px`, top: `${Math.max(4, rect.top - pad)}px`, width: `${rect.width + pad * 2}px`, height: `${rect.height + pad * 2}px`, opacity: '1' });
  const dialogRect = overlay.querySelector('.tutorial-dialog').getBoundingClientRect();
  const x1 = dialogRect.left + dialogRect.width / 2; const y1 = dialogRect.top + dialogRect.height / 2;
  const x2 = rect.left + rect.width / 2; const y2 = rect.top + rect.height / 2;
  const length = Math.hypot(x2 - x1, y2 - y1); const angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;
  Object.assign(pointer.style, { left: `${x1}px`, top: `${y1}px`, width: `${Math.max(32, length - 14)}px`, transform: `rotate(${angle}deg)`, opacity: length > 70 ? '1' : '0' });
}

function renderStep() {
  if (!current) return;
  const step = current.steps[stepIndex];
  const target = targetFor(step);
  const title = overlay.querySelector('#tutorial-step-title');
  const body = overlay.querySelector('#tutorial-step-body');
  overlay.querySelector('#tutorial-step-counter').textContent = `STEP ${stepIndex + 1} OF ${current.steps.length} · ${current.title.toUpperCase()}`;
  title.textContent = step.title; body.textContent = step.body;
  overlay.querySelector('#tutorial-progress-bar').style.width = `${((stepIndex + 1) / current.steps.length) * 100}%`;
  overlay.querySelector('[data-tutorial-prev]').disabled = stepIndex === 0;
  overlay.querySelector('[data-tutorial-next]').innerHTML = stepIndex === current.steps.length - 1 ? 'Finish <span aria-hidden="true">✓</span>' : 'Next <span aria-hidden="true">→</span>';
  target?.scrollIntoView?.({ block: 'nearest', inline: 'nearest', behavior: 'auto' });
  requestAnimationFrame(() => {
    if (!current || overlay.hidden) return;
    placeDialog(target, step.placement);
    paintSpotlight(target);
  });
}

function showRecommendations() {
  const rec = overlay.querySelector('#tutorial-recommendations');
  const related = tutorialCatalog.filter(item => item.id !== current.id).sort((a, b) => Number(b.tags.some(tag => current.tags.includes(tag))) - Number(a.tags.some(tag => current.tags.includes(tag)))).slice(0, 3);
  rec.hidden = false;
  rec.innerHTML = `<h3>Where should we trot next?</h3><div class="tutorial-recommendation-grid">${related.map(item => `<button type="button" class="tutorial-recommendation" data-tutorial-start="${item.id}"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.duration)} · ${escapeHtml(item.level)}</span></button>`).join('')}</div>`;
}

function finishTutorial() {
  localStorage.setItem(`ronin.tutorial.${current.id}`, 'complete');
  overlay.querySelector('.tutorial-dialog').classList.add('is-complete');
  overlay.querySelector('#tutorial-step-counter').textContent = 'TRAIL COMPLETE';
  overlay.querySelector('#tutorial-step-title').textContent = 'You made it to the other side of the bridge.';
  overlay.querySelector('#tutorial-step-body').textContent = 'Nice work. Ronin has left a few paw prints on the map so you can return whenever you need a refresher.';
  overlay.querySelector('.tutorial-progress').hidden = true;
  overlay.querySelector('[data-tutorial-prev]').hidden = true;
  overlay.querySelector('[data-tutorial-next]').textContent = 'Close';
  showRecommendations();
}

function closeTutorial() {
  if (!overlay) return;
  overlay.hidden = true; document.body.classList.remove('tutorial-active'); current = null;
  overlay.querySelector('.tutorial-dialog').classList.remove('is-complete');
  overlay.querySelector('#tutorial-recommendations').hidden = true;
  returnFocus?.focus?.(); returnFocus = null;
}

function startTutorial(id) {
  const item = tutorialCatalog.find(tutorial => tutorial.id === id);
  if (!item) return;
  if (!current) returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  current = item; stepIndex = 0; ensureOverlay().hidden = false; document.body.classList.add('tutorial-active'); renderStep();
  overlay.querySelector('.tutorial-close').focus();
}

function filterTutorials(query) {
  const normalized = query.trim().toLowerCase(); let visible = 0;
  tutorialCatalog.forEach(item => { const match = !normalized || catalogText(item).includes(normalized); const card = document.querySelector(`[data-tutorial-card="${item.id}"]`); if (card) { card.hidden = !match; if (match) visible += 1; } });
  const empty = document.querySelector('#tutorial-empty'); if (empty) empty.hidden = visible !== 0;
}

function mount() {
  const view = document.querySelector('#view');
  if (view && (location.hash.slice(1) || 'home') === 'home') renderLibrary(view);
  ensureOverlay();
}

document.addEventListener('click', event => {
  const start = event.target.closest('[data-tutorial-start]');
  if (start) { event.preventDefault(); startTutorial(start.dataset.tutorialStart); return; }
  if (event.target.closest('[data-tutorial-close], [data-tutorial-skip]')) { event.preventDefault(); closeTutorial(); return; }
  if (event.target.closest('[data-tutorial-prev]')) { stepIndex = Math.max(0, stepIndex - 1); renderStep(); return; }
  if (event.target.closest('[data-tutorial-next]')) { if (overlay.querySelector('.tutorial-dialog').classList.contains('is-complete')) { closeTutorial(); return; } if (stepIndex >= current.steps.length - 1) finishTutorial(); else { stepIndex += 1; renderStep(); } }
});
document.addEventListener('input', event => { if (event.target.id === 'tutorial-search') filterTutorials(event.target.value); });
document.addEventListener('keydown', event => {
  if (!overlay || overlay.hidden) return;
  if (event.key === 'Escape') { event.preventDefault(); closeTutorial(); return; }
  if (event.key !== 'Tab') return;
  const dialog = overlay.querySelector('.tutorial-dialog');
  const focusable = [...dialog.querySelectorAll('button:not([disabled]):not([hidden]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter(element => element.getClientRects().length > 0);
  if (!focusable.length) { event.preventDefault(); dialog.focus(); return; }
  const first = focusable[0]; const last = focusable[focusable.length - 1];
  if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
});
window.addEventListener('resize', () => { if (current && overlay && !overlay.hidden) renderStep(); });
observer = new MutationObserver(() => mount());
observer.observe(document.querySelector('#view') || document.body, { childList: true, subtree: true });
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true }); else mount();

export { tutorialCatalog, startTutorial };
