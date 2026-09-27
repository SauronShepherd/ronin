import {post} from './api.js';

let activeJob = null;
const plan = () => JSON.parse(document.querySelector('#synthetic-studio-plan')?.value || '{}');
const result = (value) => {
  const target = document.querySelector('#synthetic-studio-result');
  if (target) target.textContent = JSON.stringify(value, null, 2);
};

function injectControls() {
  if (location.hash !== '#synthetic' || !document.querySelector('#synthetic-studio-form') || document.querySelector('#synthetic-journey-controls')) return;
  document.querySelector('#synthetic-studio-form').insertAdjacentHTML('beforeend', `
    <div id="synthetic-journey-controls" class="toolbar">
      <button class="button" type="button" data-sds-validate>Validate plan</button>
      <button class="button" type="button" data-sds-async>Generate asynchronously</button>
      <button class="button danger" type="button" data-sds-cancel disabled>Cancel async job</button>
    </div>`);
}

document.addEventListener('click', async (event) => {
  const validate = event.target.closest('[data-sds-validate]');
  const asyncGenerate = event.target.closest('[data-sds-async]');
  const cancel = event.target.closest('[data-sds-cancel]');
  if (!validate && !asyncGenerate && !cancel) return;
  try {
    if (validate) {
      result(await post('/v1/synthetic-data-studio/validate', {plan: plan()}));
    } else if (asyncGenerate) {
      activeJob = await post('/v1/synthetic-data-studio/generate/async', {plan: plan()});
      result(activeJob);
      document.querySelector('[data-sds-cancel]').disabled = !activeJob.job_id;
    } else if (cancel && activeJob?.job_id) {
      result(await post(`/v1/synthetic-data-studio/jobs/${encodeURIComponent(activeJob.job_id)}/cancel`, {}));
      cancel.disabled = true;
    }
  } catch (error) {
    result({error: error.message});
  }
});

new MutationObserver(injectControls).observe(document.body, {childList: true, subtree: true});
window.addEventListener('hashchange', injectControls);
injectControls();
