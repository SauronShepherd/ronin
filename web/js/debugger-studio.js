import { post } from './api.js';

let lastDebuggerAction = null;

function workspaceQuery() {
  const workspace = globalThis.roninStudioContext?.workspace || sessionStorage.getItem('ronin.workspace') || 'default';
  return `?workspace_id=${encodeURIComponent(workspace)}`;
}

document.addEventListener('submit', async event => {
  if (event.target.id === 'debugger-create-form') {
    event.preventDefault();
    const output = document.querySelector('#debugger-result');
    try {
      const session = document.querySelector('#debugger-session').value;
      lastDebuggerAction = 'create';
      const data = await post(`/v1/data-engineering/debugger/sessions${workspaceQuery()}`, {session_id: session, cells: JSON.parse(document.querySelector('#debugger-cells').value)});
      document.querySelector('#debugger-breakpoint-session').value = session;
      output.textContent = JSON.stringify(data, null, 2);
    } catch (error) { output.innerHTML = `<div class="error"><strong>Could not create debugger session.</strong><p>${String(error.message).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</p><button class="button" type="button" data-debugger-retry>Retry session creation</button></div>`; }
  }
  if (event.target.id === 'debugger-breakpoint-form') {
    event.preventDefault();
    const output = document.querySelector('#debugger-result');
    try {
      const session = encodeURIComponent(document.querySelector('#debugger-breakpoint-session').value);
      const cell = encodeURIComponent(document.querySelector('#debugger-cell').value);
      output.textContent = JSON.stringify(await post(`/v1/data-engineering/debugger/sessions/${session}/breakpoints/${cell}${workspaceQuery()}`, {}), null, 2);
    } catch (error) { output.textContent = `Could not set breakpoint: ${error.message}`; }
  }
});

document.addEventListener('click', event => {
  if (!event.target.closest('[data-debugger-retry]') || lastDebuggerAction !== 'create') return;
  document.querySelector('#debugger-create-form')?.requestSubmit();
});
