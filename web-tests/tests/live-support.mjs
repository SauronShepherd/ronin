import fs from 'node:fs/promises';
import path from 'node:path';

const apiBase = process.env.RONIN_LIVE_API_URL;
const jobsApiBase = process.env.RONIN_LIVE_JOBS_API_URL;
const token = process.env.RONIN_LIVE_API_TOKEN;
const trafficOutput = process.env.RONIN_LIVE_API_TRAFFIC_OUTPUT;
let traffic = [];
let trafficReady;
let trafficWrite = Promise.resolve();

function initializeTraffic() {
  if (!trafficReady) {
    trafficReady = (async () => {
      if (!trafficOutput) return;
      try {
        traffic = JSON.parse(await fs.readFile(trafficOutput, 'utf8'));
        if (!Array.isArray(traffic)) throw new Error('API traffic evidence must be a JSON array');
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
        traffic = [];
      }
    })();
  }
  return trafficReady;
}

export async function flushLiveTraffic() {
  await initializeTraffic();
  await trafficWrite;
}

async function recordTraffic(call) {
  await initializeTraffic();
  traffic.push(call);
  if (!trafficOutput) return;
  trafficWrite = trafficWrite.then(async () => {
    await fs.mkdir(path.dirname(path.resolve(trafficOutput)), { recursive: true });
    await fs.writeFile(trafficOutput, `${JSON.stringify(traffic, null, 2)}\n`, 'utf8');
  });
  await trafficWrite;
}

export function installLiveApiProxy(page, expectedToken = token) {
  const calls = [];
  page.route('**/v1/**', async route => {
    const requestStartedAt = performance.now();
    const request = route.request();
    const requestUrl = new URL(request.url());
    const jobsSurface = requestUrl.pathname === '/v1/jobs' ||
      requestUrl.pathname.startsWith('/v1/jobs/') ||
      requestUrl.pathname.includes('/migration/sessions');
    const surfaceBase = jobsSurface ? jobsApiBase : apiBase;
    const upstreamUrl = new URL(`${requestUrl.pathname}${requestUrl.search}`, `${surfaceBase}/`);
    const requestHeaders = await request.allHeaders();
    const authorization = Object.entries(requestHeaders)
      .find(([name]) => name.toLowerCase() === 'authorization')?.[1];
    const authorizationValue = authorization?.replace(/^Bearer\s+/i, '');
    const headers = new Headers();
    for (const name of ['accept', 'authorization', 'content-type', 'idempotency-key', 'if-match', 'if-none-match']) {
      const value = Object.entries(requestHeaders)
        .find(([headerName]) => headerName.toLowerCase() === name)?.[1];
      if (value) headers.set(name, value);
    }
    const method = request.method();
    const timeoutMs = requestUrl.pathname.startsWith('/v1/ml-studio/labs/') &&
      requestUrl.pathname.endsWith('/search') ? 90_000 : 15_000;
    let upstream;
    try {
      upstream = await fetch(upstreamUrl, {
        method,
        headers,
        body: ['GET', 'HEAD'].includes(method) ? undefined : await request.postDataBuffer(),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      const call = {
        method,
        path: requestUrl.pathname,
        status: 0,
        outcome: 'ERROR',
        duration_ms: Math.max(0, Math.round(performance.now() - requestStartedAt)),
        authorization: authorization ? 'present' : 'missing',
        authorizationKind: authorizationValue === expectedToken ? 'expected' : authorizationValue ? 'other' : 'missing',
        network_error: true,
      };
      calls.push(call);
      await recordTraffic(call);
      await route.abort();
      return;
    }
    const call = {
      method,
      path: requestUrl.pathname,
      status: upstream.status,
      surface: jobsSurface ? 'jobs' : 'control-plane',
      outcome: upstream.status >= 500 ? 'ERROR' : upstream.status >= 400 ? 'WARN' : 'OK',
      authorization: authorization ? 'present' : 'missing',
      authorizationKind: authorizationValue === expectedToken ? 'expected' : authorizationValue ? 'other' : 'missing',
      requestId: upstream.headers.get('x-ronin-request-id') || undefined,
    };
    calls.push(call);
    const body = await upstream.text();
    call.duration_ms = Math.max(0, Math.round(performance.now() - requestStartedAt));
    if (upstream.status >= 400) {
      try {
        const errorPayload = JSON.parse(body);
        const code = errorPayload.code ?? errorPayload.error?.code;
        if (typeof code === 'string' && /^[a-z0-9_]{1,80}$/i.test(code)) call.errorCode = code;
      } catch {
        // Keep only known-safe machine-readable error codes in test evidence.
      }
    }
    await recordTraffic(call);
    const contentType = upstream.headers.get('content-type') || 'application/json';
    await route.fulfill({ status: upstream.status, contentType, body });
  });
  return calls;
}

export async function connectLiveStudio(page, tokenToUse = token) {
  await page.goto('./#home');
  await page.locator('#rail .nav-item').first().waitFor({ state: 'visible' });
  await page.getByRole('button', { name: 'Server connection' }).click();
  await page.locator('#api-url').fill('');
  await page.locator('#api-token').fill(tokenToUse);
  await page.getByRole('button', { name: 'Save connection', exact: true }).click();
  // The toast is intentionally transient and can disappear before a long live
  // page settles. Assert the durable effects of the save instead.
  await page.locator('#connection-dialog').waitFor({ state: 'hidden' });
  await page.waitForFunction(expected => sessionStorage.getItem('ronin.session') === expected, tokenToUse);
  await page.evaluate(
    workspace => sessionStorage.setItem('ronin.workspace', workspace),
    process.env.RONIN_LIVE_WORKSPACE,
  );
}

export function liveConfigurationReady() {
  return Boolean(
    apiBase &&
      /^https?:\/\//i.test(apiBase) &&
      jobsApiBase &&
      /^https?:\/\//i.test(jobsApiBase) &&
      token &&
      process.env.RONIN_LIVE_WORKSPACE &&
      (process.env.RONIN_LIVE_REQUIRE_POSTGRES === '0' || process.env.RONIN_LIVE_PG_PORT) &&
      process.env.RONIN_STUDIO_E2E_URL &&
      trafficOutput,
  );
}

export function assertLiveConfiguration() {
  const required = [
    'RONIN_LIVE_API_URL',
    'RONIN_LIVE_JOBS_API_URL',
    'RONIN_LIVE_API_TOKEN',
    'RONIN_LIVE_WORKSPACE',
    'RONIN_STUDIO_E2E_URL',
    'RONIN_LIVE_API_TRAFFIC_OUTPUT',
  ];
  if (process.env.RONIN_LIVE_REQUIRE_POSTGRES !== '0') required.push('RONIN_LIVE_PG_PORT');
  const missing = required.filter(name => !process.env[name]);
  if (missing.length) {
    throw new Error(`Missing live API configuration: ${missing.join(', ')}`);
  }
}
