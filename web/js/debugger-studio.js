function post(path, payload) {
  return fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}).then(async response => {
    const data = await response.json();
    if (!response.ok) throw new Error(data?.error?.message || `HTTP ${response.status}`);
    return data;
  });
}

document.addEventListener('submit', async event => {
  if (event.target.id === 'debugger-create-form') {
    event.preventDefault();
    const output = document.querySelector('#debugger-result');
    try {
      const session = document.querySelector('#debugger-session').value;
      const data = await post('/v1/data-engineering/debugger/sessions', {session_id: session, cells: JSON.parse(document.querySelector('#debugger-cells').value)});
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
      output.textContent = JSON.stringify(await post(`/v1/data-engineering/debugger/sessions/${session}/breakpoints/${cell}`, {}), null, 2);
    } catch (error) { output.textContent = `Could not set breakpoint: ${error.message}`; }
  }
});
