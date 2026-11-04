import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testRoot = path.dirname(fileURLToPath(import.meta.url));
const markerPath = path.join(testRoot, 'node_modules', '.ronin-test-lock.sha256');
const statusFlag = process.argv.indexOf('--status-file');
const statusPath = statusFlag >= 0 ? process.argv[statusFlag + 1] : null;
const packageHash = createHash('sha256').update(readFileSync(path.join(testRoot, 'package.json'))).digest('hex');
const lockHash = createHash('sha256').update(readFileSync(path.join(testRoot, 'package-lock.json'))).digest('hex');
const fingerprint = createHash('sha256').update(`${lockHash}:${packageHash}`).digest('hex');
const bundledNpmCli = process.env.npm_execpath || path.join(path.dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npm-cli.js');
const npmCommand = process.platform === 'win32' && existsSync(bundledNpmCli) ? process.execPath : 'npm';
const npmPrefixArgs = npmCommand === process.execPath ? [bundledNpmCli] : [];
const lockRoot = path.join(os.tmpdir(), 'ronin-test-dependency-locks');
mkdirSync(lockRoot, { recursive: true });
const checkoutKey = createHash('sha256').update(testRoot).digest('hex');
const lockPath = path.join(lockRoot, `${checkoutKey}.lock`);

function runNpm(args, { quiet = false } = {}) {
  const result = spawnSync(npmCommand, [...npmPrefixArgs, ...args], {
    cwd: testRoot,
    encoding: 'utf8',
    stdio: quiet ? 'ignore' : 'inherit',
  });
  if (result.error) throw result.error;
  return result.status ?? 1;
}

async function acquireCheckoutLock() {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    try {
      const descriptor = openSync(lockPath, 'wx');
      writeFileSync(descriptor, `${process.pid}\n`, 'utf8');
      return () => {
        closeSync(descriptor);
        unlinkSync(lockPath);
      };
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      let owner = 0;
      try { owner = Number.parseInt(readFileSync(lockPath, 'utf8').trim(), 10); } catch { }
      let alive = false;
      if (Number.isInteger(owner) && owner > 0) {
        try { process.kill(owner, 0); alive = true; } catch (probeError) { alive = probeError.code === 'EPERM'; }
      }
      if (!alive) {
        try { unlinkSync(lockPath); } catch (removeError) { if (removeError.code !== 'ENOENT') throw removeError; }
        continue;
      }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
  }
  throw new Error(`Timed out waiting for the web-test dependency lock: ${lockPath}`);
}

const releaseLock = await acquireCheckoutLock();
try {
  let dependencyCache = 'miss';
  if (existsSync(markerPath) && readFileSync(markerPath, 'utf8').trim() === fingerprint) {
    dependencyCache = runNpm(['ls', '--depth=0'], { quiet: true }) === 0 ? 'hit' : 'miss';
  }

  if (dependencyCache === 'miss') {
    if (runNpm(['ci']) !== 0) throw new Error('npm ci failed for the locked web-test dependencies.');
    if (runNpm(['ls', '--depth=0'], { quiet: true }) !== 0) {
      throw new Error('The installed web-test dependency tree does not satisfy package.json.');
    }
    writeFileSync(markerPath, `${fingerprint}\n`, 'utf8');
  }

  const { chromium } = await import('@playwright/test');
  let browser = 'hit';
  if (!existsSync(chromium.executablePath())) {
    browser = 'installed';
    if (runNpm(['exec', '--', 'playwright', 'install', 'chromium']) !== 0) {
      throw new Error('Could not install the Playwright Chromium browser.');
    }
  }

  const status = { schemaVersion: 1, dependencyCache, fingerprint, chromium: browser };
  if (statusPath) writeFileSync(path.resolve(statusPath), `${JSON.stringify(status, null, 2)}\n`, 'utf8');
  process.stdout.write(`Web test dependencies: ${dependencyCache.toUpperCase()} [${fingerprint.slice(0, 12)}]; Chromium: ${browser}.\n`);
} finally {
  releaseLock();
}
