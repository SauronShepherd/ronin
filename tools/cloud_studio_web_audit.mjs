import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const html = await readFile(new URL('../web/cloud-studio.html', import.meta.url), 'utf8');
const js = await readFile(new URL('../web/cloud-studio.js', import.meta.url), 'utf8');
const requiredIds = ['canvas', 'palette', 'undo', 'redo', 'zoom-in', 'zoom-out', 'layout', 'import', 'export-json', 'validate', 'export', 'name', 'value', 'save'];
const missing = requiredIds.filter((id) => !html.includes(`id="${id}"`));
const requiredFeatures = ['ondrop', 'snapshot', 'JSON.stringify', 'zoom', 'shiftKey', 'onkeydown', 'drawEdges', 'createElementNS', 'import-hcl', '/v1/cloud-studio/import', 'role="application"'];
const missingFeatures = requiredFeatures.filter((feature) => !(html + js).includes(feature));
const syntax = spawnSync(process.execPath, ['--check', fileURLToPath(new URL('../web/cloud-studio.js', import.meta.url))], { encoding: 'utf8' });
if (missing.length || missingFeatures.length || syntax.status !== 0) {
  console.error(JSON.stringify({ missing, missingFeatures, syntax: syntax.stderr }));
  process.exit(1);
}
console.log(JSON.stringify({ ok: true, controls: requiredIds.length, features: requiredFeatures.length }));
