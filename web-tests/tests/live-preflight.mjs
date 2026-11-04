import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertLiveConfiguration } from './live-support.mjs';

assertLiveConfiguration();

const apiUrl = new URL(process.env.RONIN_LIVE_API_URL);
const browserUrl = new URL(process.env.RONIN_STUDIO_E2E_URL);
if (!['http:', 'https:'].includes(apiUrl.protocol) || !['http:', 'https:'].includes(browserUrl.protocol)) {
  throw new Error('Live API and Studio URLs must use HTTP or HTTPS.');
}
if (process.env.RONIN_LIVE_REQUIRE_POSTGRES !== '0') {
  const port = Number(process.env.RONIN_LIVE_PG_PORT);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('RONIN_LIVE_PG_PORT must be a valid TCP port.');
  }
}

for (const name of [
  'PLAYWRIGHT_OUTPUT_DIR',
  'PLAYWRIGHT_HTML_OUTPUT_DIR',
  'PLAYWRIGHT_JUNIT_OUTPUT_FILE',
]) {
  if (!process.env[name]) throw new Error(`${name} must point to this run's external evidence directory.`);
}

const trafficOutput = path.resolve(process.env.RONIN_LIVE_API_TRAFFIC_OUTPUT);
if (fs.existsSync(trafficOutput)) {
  throw new Error(`API traffic evidence already exists; use a unique run path: ${trafficOutput}`);
}
const checkoutRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
for (const name of [
  'RONIN_LIVE_API_TRAFFIC_OUTPUT',
  'PLAYWRIGHT_OUTPUT_DIR',
  'PLAYWRIGHT_HTML_OUTPUT_DIR',
  'PLAYWRIGHT_JUNIT_OUTPUT_FILE',
]) {
  const resolved = path.resolve(process.env[name]);
  const relative = path.relative(checkoutRoot, resolved);
  if (!relative.startsWith('..') && !path.isAbsolute(relative)) {
    throw new Error(`${name} must be outside the repository: ${resolved}`);
  }
}
