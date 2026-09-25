const keys = Object.freeze(['workspace', 'project', 'environment', 'revision', 'runtime', 'dataset', 'run', 'compare']);

function clean(value) {
  if (value === undefined || value === null || value === '') return null;
  const text = String(value).trim();
  if (!text || text.length > 256 || /[\u0000-\u001f\u007f]/.test(text)) {
    throw new TypeError('studio context values must be bounded printable text');
  }
  return text;
}

export function createStudioContext(values = {}) {
  const result = {};
  for (const key of keys) {
    const value = clean(values[key]);
    if (value !== null) result[key] = value;
  }
  return Object.freeze(result);
}

export function encodeStudioContext(values) {
  const context = createStudioContext(values);
  const query = new URLSearchParams();
  for (const key of keys) if (context[key]) query.set(key, context[key]);
  return query.toString();
}

export function decodeStudioContext(search) {
  const query = new URLSearchParams(search || '');
  const values = {};
  for (const key of keys) {
    const value = query.get(key);
    if (value !== null) values[key] = value;
  }
  return createStudioContext(values);
}

export function studioContextKeys() {
  return keys;
}
