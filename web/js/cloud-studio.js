async function cloudPost(path, payload) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error?.message || `HTTP ${response.status}`);
  return data;
}

document.addEventListener('click', async event => {
  if (event.target.id !== 'cloud-validate') return;
  const output = document.querySelector('#cloud-result');
  try { output.textContent = JSON.stringify(await cloudPost('/v1/cloud-studio/validate', JSON.parse(document.querySelector('#cloud-target').value)), null, 2); }
  catch (error) { output.textContent = `Could not validate target: ${error.message}`; }
});

document.addEventListener('submit', async event => {
  if (event.target.id !== 'cloud-plan-form') return;
  event.preventDefault();
  const output = document.querySelector('#cloud-result');
  try { output.textContent = JSON.stringify(await cloudPost('/v1/cloud-studio/plan', JSON.parse(document.querySelector('#cloud-target').value)), null, 2); }
  catch (error) { output.textContent = `Could not generate plan: ${error.message}`; }
});
