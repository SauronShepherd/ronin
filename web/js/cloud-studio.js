import { post } from './api.js';

document.addEventListener('click', async event => {
  if (event.target.id !== 'cloud-validate') return;
  const output = document.querySelector('#cloud-result');
  try { output.textContent = JSON.stringify(await post('/v1/cloud-studio/validate', JSON.parse(document.querySelector('#cloud-target').value)), null, 2); }
  catch (error) { output.textContent = `Could not validate target: ${error.message}`; }
});

document.addEventListener('submit', async event => {
  if (event.target.id !== 'cloud-plan-form') return;
  event.preventDefault();
  const output = document.querySelector('#cloud-result');
  try { output.textContent = JSON.stringify(await post('/v1/cloud-studio/plan', JSON.parse(document.querySelector('#cloud-target').value)), null, 2); }
  catch (error) { output.textContent = `Could not generate plan: ${error.message}`; }
});
