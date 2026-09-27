import './synthetic-journey.js';
import {get, post} from './api.js';
import {esc, json} from './dom.js';

const workspace = () => encodeURIComponent(sessionStorage.getItem('ronin.workspace') || 'default');
const output = (title, value) => {
  const target = document.querySelector('#ml-output');
  if (target) target.innerHTML = `<h2>${title}</h2><pre class="code">${esc(json(value))}</pre>`;
};

function injectJourneyControls() {
  if (location.hash !== '#mlstudio' || !document.querySelector('#ml-labs') || document.querySelector('#ml-quality-form')) return;
  document.querySelector('#ml-labs').insertAdjacentHTML('afterend', `
    <div class="grid two feature-output">
      <form class="panel" id="ml-quality-form">
        <h2>Quality check</h2>
        <label>Lab ID<input class="field" name="lab_id" value="churn" required></label>
        <label>Rows JSON<textarea class="field" name="rows">[{"x":1,"target":1}]</textarea></label>
        <button class="button" type="submit">Run quality check</button>
      </form>
      <form class="panel" id="ml-search-form">
        <h2>Search trials</h2>
        <label>Lab ID<input class="field" name="lab_id" value="churn" required></label>
        <label>Search spec JSON<textarea class="field" name="spec">{"mode":"single","metric":"accuracy","direction":"maximize","parameters":[{"name":"seed","values":[17,19]}]}</textarea></label>
        <label>Rows JSON<textarea class="field" name="rows">[{"x":1,"target":1}]</textarea></label>
        <button class="button" type="submit">Search trials</button>
      </form>
    </div>`);
}

document.addEventListener('submit', async (event) => {
  if (event.target.id !== 'ml-quality-form' && event.target.id !== 'ml-search-form') return;
  event.preventDefault();
  const form = event.target;
  try {
    const data = Object.fromEntries(new FormData(form));
    const body = {rows: JSON.parse(data.rows)};
    const path = event.target.id === 'ml-quality-form'
      ? `/v1/ml-studio/labs/${encodeURIComponent(data.lab_id)}/quality?workspace_id=${workspace()}`
      : `/v1/ml-studio/labs/${encodeURIComponent(data.lab_id)}/search?workspace_id=${workspace()}`;
    if (event.target.id === 'ml-search-form') body.spec = JSON.parse(data.spec);
    output(event.target.id === 'ml-quality-form' ? 'Quality result' : 'Trial search', await post(path, body));
  } catch (error) {
    output('ML request failed', {error: error.message});
  }
});

new MutationObserver(injectJourneyControls).observe(document.body, {childList: true, subtree: true});
window.addEventListener('hashchange', injectJourneyControls);
injectJourneyControls();
