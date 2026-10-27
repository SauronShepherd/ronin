const sameOrigin = location.origin;
const apiUrlKey = 'ronin.api';
const sessionTokenKey = 'ronin.session';

function isLoopback(hostname) {
  return hostname === 'localhost' || hostname.endsWith('.localhost') || hostname === '[::1]' || /^127(?:\.\d{1,3}){3}$/.test(hostname);
}

function normalizeServerAddress(value, token = '') {
  let address;
  try {
    address = new URL(value || sameOrigin, sameOrigin);
  } catch {
    throw new Error('Enter a valid HTTP or HTTPS server address.');
  }
  if (!['http:', 'https:'].includes(address.protocol) || address.username || address.password || address.search || address.hash) {
    throw new Error('Use an HTTP or HTTPS server address without a username, password, query, or fragment.');
  }
  if (token && address.protocol === 'http:' && !isLoopback(address.hostname)) {
    throw new Error('Access keys require HTTPS. Plain HTTP is allowed only on this computer (localhost).');
  }
  return address.toString().replace(/\/+$/, '');
}

function storedBase() {
  const legacySessionBase = sessionStorage.getItem(apiUrlKey);
  const savedBase = localStorage.getItem(apiUrlKey) || legacySessionBase || sameOrigin;
  try {
    const normalizedBase = normalizeServerAddress(savedBase, sessionStorage.getItem(sessionTokenKey) || '');
    if (legacySessionBase) {
      if (!localStorage.getItem(apiUrlKey) && normalizedBase !== sameOrigin) localStorage.setItem(apiUrlKey, normalizedBase);
      sessionStorage.removeItem(apiUrlKey);
    }
    if (normalizedBase === sameOrigin) localStorage.removeItem(apiUrlKey);
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
  const nextToken = typeof token === 'string' ? token.trim() : '';
  const nextBase = normalizeServerAddress(base, nextToken);
  config.base = nextBase;
  config.token = nextToken;
  if (nextBase === sameOrigin) localStorage.removeItem(apiUrlKey);
  else localStorage.setItem(apiUrlKey, nextBase);
  sessionStorage.removeItem(apiUrlKey);
  if (nextToken) sessionStorage.setItem(sessionTokenKey, nextToken);
  else sessionStorage.removeItem(sessionTokenKey);
}

export async function request(path, options = {}) {
  const base = normalizeServerAddress(config.base, config.token);
  const headers = new Headers(options.headers || {});
  headers.set('Accept', 'application/json');
  if (config.token) headers.set('Authorization', `Bearer ${config.token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  let response;
  try {
    response = await fetch(`${base}${path}`, { ...options, headers });
  } catch (error) {
    if (options.signal?.aborted || error?.name === 'AbortError') throw error;
    throw new Error(`Unable to reach the Ronin server. Check its address and your network connection. ${error.message}`);
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
      ? `The Ronin server is not available at ${base}. Start the server or use the address provided by your administrator.`
      : rawMessage || `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

export const get = (path) => request(path);
export const post = (path, body, options = {}) => request(path, {
  method: 'POST',
  body: JSON.stringify(body || {}),
  ...options,
  headers: { ...(options.headers || {}) },
});
export const put = (path, body, options = {}) => request(path, {
  method: 'PUT',
  body: JSON.stringify(body || {}),
  ...options,
  headers: { ...(options.headers || {}) },
});
export const patch = (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body || {}) });
export const del = (path, options = {}) => request(path, {
  method: 'DELETE',
  ...options,
  headers: { ...(options.headers || {}) },
});
