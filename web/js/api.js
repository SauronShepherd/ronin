const sameOrigin = location.origin;
const apiUrlKey = 'ronin.api';
const sessionTokenKey = 'ronin.session';

function normalizeBase(value) {
  const base = value.trim() || sameOrigin;
  let parsed;
  try {
    parsed = new URL(base, sameOrigin);
  } catch {
    throw new TypeError('Enter a valid Ronin API URL.');
  }
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new TypeError('The Ronin API URL must use HTTP or HTTPS and cannot contain credentials.');
  }
  if (parsed.search || parsed.hash) {
    throw new TypeError('The Ronin API URL cannot contain a query string or fragment.');
  }
  return parsed.href.replace(/\/$/, '');
}

function storedBase() {
  const legacySessionBase = sessionStorage.getItem(apiUrlKey);
  const base = localStorage.getItem(apiUrlKey) || legacySessionBase || sameOrigin;
  try {
    const normalizedBase = normalizeBase(base);
    if (legacySessionBase) {
      if (!localStorage.getItem(apiUrlKey)) localStorage.setItem(apiUrlKey, normalizedBase);
      sessionStorage.removeItem(apiUrlKey);
    }
    return normalizedBase;
  } catch {
    localStorage.removeItem(apiUrlKey);
    sessionStorage.removeItem(apiUrlKey);
    sessionStorage.removeItem(sessionTokenKey);
    return sameOrigin;
  }
}

export const config = {
  base: storedBase(),
  token: sessionStorage.getItem(sessionTokenKey) || '',
};

export function setConfig(base, token) {
  const normalizedBase = normalizeBase(base || '');
  const normalizedToken = typeof token === 'string' ? token.trim() : '';
  config.base = normalizedBase;
  config.token = normalizedToken;
  if (normalizedBase === sameOrigin) localStorage.removeItem(apiUrlKey);
  else localStorage.setItem(apiUrlKey, normalizedBase);
  if (normalizedToken) sessionStorage.setItem(sessionTokenKey, normalizedToken);
  else sessionStorage.removeItem(sessionTokenKey);
}

export async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('Accept', 'application/json');
  if (config.token) headers.set('Authorization', `Bearer ${config.token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  let response;
  try {
    response = await fetch(`${config.base}${path}`, { ...options, headers });
  } catch (error) {
    if (options.signal?.aborted || error?.name === 'AbortError') throw error;
    throw new Error(`Unable to reach the control plane. Check the API URL and network connection. ${error.message}`);
  }
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text };
  }
  if (!response.ok) {
    const rawMessage = data?.error?.message || data?.message;
    const isHtml = typeof rawMessage === 'string' && /<(?:!doctype|html|body)\b/i.test(rawMessage);
    const message = isHtml
      ? `The Ronin API is not available at ${config.base}. Start the API server or set its URL in the connection controls.`
      : (rawMessage || `Request failed (${response.status})`);
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

export const get = (path) => request(path);
export const post = (path, body, options = {}) => request(path, {
  method: 'POST', body: JSON.stringify(body || {}), ...options, headers: { ...(options.headers || {}) },
});
export const put = (path, body, options = {}) => request(path, {
  method: 'PUT', body: JSON.stringify(body || {}), ...options, headers: { ...(options.headers || {}) },
});
export const patch = (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body || {}) });
export const del = (path, options = {}) => request(path, {
  method: 'DELETE', ...options, headers: { ...(options.headers || {}) },
});
