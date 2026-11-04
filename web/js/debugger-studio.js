import { post } from './api.js';

function workspaceQuery() {
  const workspace = sessionStorage.getItem('ronin.workspace') || 'default';
  return `?workspace_id=${encodeURIComponent(workspace)}`;
}

document.addEventListener('submit', async event => {
  if (event.target.id === 'debugger-create-form') {
    event.preventDefault();
    const output = document.querySelector('#debugger-result');
    try {
      const session = document.querySelector('#debugger-session').value;
      const data = await post(`/v1/data-engineering/debugger/sessions${workspaceQuery()}`, {session_id: session, cells: JSON.parse(document.querySelector('#debugger-cells').value)});
      document.querySelector('#debugger-breakpoint-session').value = session;
      output.textContent = JSON.stringify(data, null, 2);
    } catch (error) { output.textContent = `Could not create debugger session: ${error.message}`; }
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
