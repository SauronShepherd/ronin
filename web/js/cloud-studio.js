import { post } from './api.js';

let lastCloudAction = null;

async function runCloudAction(action) {
  const output = document.querySelector('#cloud-result');
  const target = JSON.parse(document.querySelector('#cloud-target').value);
  lastCloudAction = action;
  try {
    const path = action === 'validate' ? '/v1/cloud-studio/validate' : '/v1/cloud-studio/plan';
    output.textContent = JSON.stringify(await post(path, target), null, 2);
  } catch (error) {
    output.innerHTML = `<div class="error"><strong>Cloud operation failed.</strong><p>${String(error.message).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</p><button class="button" type="button" data-cloud-retry>Retry ${action === 'validate' ? 'validation' : 'plan'}</button></div>`;
  }
}

document.addEventListener('click', async event => {
  if (event.target.id !== 'cloud-validate') return;
  await runCloudAction('validate');
  return;
});

document.addEventListener('click', event => {
  if (!event.target.closest('[data-cloud-retry]') || !lastCloudAction) return;
  runCloudAction(lastCloudAction);
});

document.addEventListener('submit', async event => {
  if (event.target.id !== 'cloud-plan-form') return;
  event.preventDefault();
  await runCloudAction('plan');
});
