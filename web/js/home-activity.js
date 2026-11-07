import {config, get} from './api.js';
import {esc, fmt, status} from './dom.js';

function activityRow(run) {
  const id = String(run.id || '').trim();
  if (!id) return '';
  const state = String(run.state || run.status || 'unknown');
  return `<li class="home-activity-row" data-home-activity-row>
    <div class="home-activity-main"><a href="#run/${encodeURIComponent(id)}" class="home-activity-id">${esc(id)}</a><span class="home-activity-project">${esc(run.project_id || '—')}</span></div>
    <div class="home-activity-state">${status(state)}</div>
    <time class="home-activity-time" datetime="${esc(run.updated_at || run.created_at || '')}">${esc(fmt(run.updated_at || run.created_at))}</time>
  </li>`;
}

export async function loadHomeActivity(project) {
  const target = document.querySelector('#home-activity');
  if (!target) return;
  if (!config.token) {
    target.className = 'home-activity';
    target.innerHTML = '<div class="home-activity-empty"><strong>Connect a server to see activity.</strong><p>Recent runs stay hidden until this tab has an authenticated session.</p><button class="button" data-action="open-connection">Connect server</button></div>';
    return;
  }
  if (!project) {
    target.className = 'home-activity';
    target.innerHTML = '<div class="home-activity-empty"><strong>Choose a project to see activity.</strong><p>The run trail stays scoped to the active project.</p><a href="#projects">Open projects</a></div>';
    return;
  }
  target.setAttribute('aria-busy', 'true');
  try {
    const data = await get(`/v1/jobs?project=${encodeURIComponent(project)}`);
    if (!target.isConnected) return;
    const rows = (Array.isArray(data.items) ? data.items : []).slice(0, 5).map(activityRow).filter(Boolean);
    target.className = 'home-activity';
    target.innerHTML = rows.length
      ? `<ol class="home-activity-list">${rows.join('')}</ol>`
      : '<div class="home-activity-empty"><strong>No recent runs in this project.</strong><p>Start a governed operation, then follow its evidence here.</p><a href="#data">Open Data Engineering</a></div>';
  } catch (error) {
    if (!target.isConnected) return;
    target.className = 'home-activity home-activity-error';
    target.innerHTML = `<div class="home-activity-empty"><strong>Live activity is unavailable.</strong><p>${esc(error.message)}</p><a href="#runs">Open the run trail</a></div>`;
  } finally {
    if (target.isConnected) target.removeAttribute('aria-busy');
  }
}
