import {t} from './i18n.js';
import routesManifest from '../routes.json' with {type: 'json'};

const commands = routesManifest.map(({id}) => [`nav.${id}`, id]);

let dialog;
let input;
let list;
let selected = 0;

function ensure() {
  if (dialog) return;
  dialog = document.createElement('dialog');
  dialog.className = 'dialog command-palette';
  dialog.innerHTML = `<form method="dialog"><label class="sr-only" for="ronin-command-search">${t('command.search')}</label><input id="ronin-command-search" class="field" autocomplete="off" placeholder="${t('command.search')}"><div id="ronin-command-list" role="listbox"></div><div class="muted">${t('command.help')}</div></form>`;
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
    if (option) open(commands.find(([, route]) => route === option.dataset.commandRoute));
  });
}

function filtered() {
  const query = (input?.value || '').toLowerCase().trim();
  return commands.filter(([id, route]) => t(id).toLowerCase().includes(query) || route.toLowerCase().includes(query));
}

function render() {
  const visible = filtered();
  selected = Math.min(selected, Math.max(visible.length - 1, 0));
  list.innerHTML = visible.map(([id, route], index) => `<button type="button" class="command-option" role="option" aria-selected="${index === selected}" data-command-route="${route}">${t(id)}</button>`).join('') || `<p class="muted">${t('command.empty')}</p>`;
}

function open(command) {
  if (!command) return;
  dialog.close();
  window.location.hash = command[1];
}

export function openCommandPalette() {
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
