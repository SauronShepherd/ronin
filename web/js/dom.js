export const esc=(value)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
export const fmt=(value)=>value?new Date(value).toLocaleString(): '—';
export const json=(value)=>JSON.stringify(value,null,2);
export function page(title,eyebrow,actions=''){return `<div class="page-header"><div><p class="eyebrow">${esc(eyebrow)}</p><h1 tabindex="-1" id="view-title">${esc(title)}</h1></div><div class="page-actions">${actions}</div></div>`}
export function status(value){const v=String(value||'unknown').toLowerCase();const tone=['succeeded','completed','active'].includes(v)?'green':['running','queued','pending'].includes(v)?'blue':['failed','cancelled','error'].includes(v)?'red':'amber';return `<span class="status ${tone}">${esc(value||'Unknown')}</span>`}
