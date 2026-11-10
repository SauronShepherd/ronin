import {t} from './i18n.js';
import routesManifest from '../routes.json' with {type: 'json'};

const groupByRoute = Object.freeze({
  home: 'Overview', runs: 'Operate', workspaces: 'Workspace', projects: 'Workspace', environments: 'Workspace',
  data: 'Build', ingestion: 'Build', notebooks: 'Build', workflows: 'Build', streaming: 'Build',
  migration: 'Studios', synthetic: 'Studios', mlstudio: 'Studios', cloud: 'Studios',
  sql: 'Explore', semantic: 'Explore', catalog: 'Explore', graphs: 'Explore',
  quality: 'Operate', alerts: 'Operate', finops: 'Operate', deployments: 'Operate', performance: 'Operate', debugger: 'Operate',
  settings: 'Settings',
});

const descriptions = Object.freeze({
  home: 'See the current boundary and the next governed action.', runs: 'Follow status, events and evidence for durable work.',
  workspaces: 'Choose the workspace boundary for your work.', projects: 'Create, inspect and move project revisions safely.',
  environments: 'Compare and bind execution environments.', data: 'Shape pipelines, SQL and connector intent.',
  ingestion: 'Discover sources, preview data and plan syncs.', notebooks: 'Author, version and execute notebooks.',
  workflows: 'Schedule and recover durable workflows.', streaming: 'Inspect streams, checkpoints and lag.',
  migration: 'Discover, validate and promote migration candidates.', synthetic: 'Generate governed synthetic data.',
  mlstudio: 'Train, compare and qualify classical ML assets.', cloud: 'Review infrastructure plans without applying them.',
  sql: 'Run bounded, read-only SQL.', semantic: 'Model metrics and execute dashboards.',
  catalog: 'Find governed assets and lineage.', graphs: 'Query relationships and dispatch governed actions.',
  quality: 'Run checks and review promotion gates.', alerts: 'Monitor signals and acknowledge incidents.',
  finops: 'Inspect usage, budgets and cost evidence.', deployments: 'Bind projects to runtime environments.',
  performance: 'Analyze measured runtime evidence.', debugger: 'Inspect bounded sessions and breakpoints.',
  settings: 'Configure connection and navigation preferences.',
});

const commands = routesManifest.map(({id}) => ({id, route: id, label: t(`nav.${id}`), description: descriptions[id] || 'Open this Ronin Studio surface.', group: groupByRoute[id] || 'More'}));

let dialog;
let input;
let list;
let selected = 0;
let lastTrigger;

function ensure() {
  if (dialog) return;
  dialog = document.createElement('dialog');
  dialog.className = 'dialog command-palette';
  dialog.setAttribute('aria-label', t('command.search'));
  dialog.innerHTML = `<form method="dialog"><label class="sr-only" for="ronin-command-search">${t('command.search')}</label><input id="ronin-command-search" class="field" autocomplete="off" placeholder="${t('command.search')}" aria-controls="ronin-command-list"><div id="ronin-command-list" role="listbox" aria-label="${t('command.search')}"></div><div class="muted">${t('command.help')}</div></form>`;
  document.body.append(dialog);
  input = dialog.querySelector('input');
  list = dialog.querySelector('#ronin-command-list');
  input.addEventListener('input', render);
  input.addEventListener('keydown', (event) => {
    const visible = filtered();
    if (!visible.length) return;
    if (event.key === 'ArrowDown') { event.preventDefault(); selected = (selected + 1) % visible.length; render(); }
    if (event.key === 'ArrowUp') { event.preventDefault(); selected = (selected - 1 + visible.length) % visible.length; render(); }
    if (event.key === 'Enter') { event.preventDefault(); open(visible[selected]); }
  });
  dialog.addEventListener('click', (event) => {
    const option = event.target.closest('[data-command-route]');
    if (option) open(commands.find((command) => command.route === option.dataset.commandRoute));
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => {
    lastTrigger?.focus?.();
    lastTrigger = null;
  });
}

function filtered() {
  const query = (input?.value || '').toLowerCase().trim();
  return commands.filter((command) => [command.label, command.route, command.description, command.group].some((value) => value.toLowerCase().includes(query)));
}

function render() {
  const visible = filtered();
  selected = Math.min(selected, Math.max(visible.length - 1, 0));
  list.setAttribute('aria-activedescendant', visible[selected] ? `ronin-command-${visible[selected].route}` : '');
  let previousGroup = '';
  list.innerHTML = visible.map((command, index) => {
    const heading = command.group !== previousGroup ? `<p class="command-group" role="presentation">${command.group}</p>` : '';
    previousGroup = command.group;
    return `${heading}<button id="ronin-command-${command.route}" type="button" class="command-option" role="option" aria-selected="${index === selected}" aria-label="${command.label}: ${command.description}" data-command-route="${command.route}"><span class="command-option-copy"><strong>${command.label}</strong><small>${command.description}</small></span><kbd>${command.route}</kbd></button>`;
  }).join('') || `<p class="muted">${t('command.empty')}</p>`;
}

function open(command) {
  if (!command) return;
  dialog.close();
  window.location.hash = command.route;
}

export function openCommandPalette() {
  lastTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  ensure();
  input.value = '';
  selected = 0;
  render();
  dialog.showModal();
  input.focus();
}

document.addEventListener('click', (event) => {
  if (event.target.closest('[data-action="open-command"]')) {
    event.stopImmediatePropagation();
    openCommandPalette();
  }
}, true);

document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    event.stopImmediatePropagation();
    openCommandPalette();
  }
}, true);
