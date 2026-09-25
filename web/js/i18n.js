// Source locale for Ronin Studio. IDs are stable API/UI contracts; copy is replaceable.
const messages = Object.freeze({
  "app.name": "RONIN Studio",
  "app.controlPlane": "Control plane",
  "nav.home": "Overview",
  "nav.runs": "Runs",
  "nav.workspaces": "Workspaces",
  "nav.migration": "Migration Studio",
  "nav.synthetic": "Synthetic Data Studio",
  "nav.mlstudio": "Machine Learning Studio",
  "nav.workflows": "Workflows",
  "nav.sql": "SQL",
  "nav.access": "Governance · Access",
  "nav.catalog": "Catalog",
  "nav.data": "Data",
  "nav.graphs": "Graphs",
  "nav.ai": "AI",
  "nav.deployments": "Deployments",
  "nav.environments": "Environments",
  "nav.settings": "Settings",
  "nav.performance": "Performance Studio",
  "nav.debugger": "Debugger",
  "nav.cloud": "Cloud Studio",
  "nav.planned": "planned",
  "command.open": "Open command menu",
  "command.search": "Search commands…",
  "command.help": "↑↓ to navigate · Enter to open · Esc to close",
  "command.empty": "No commands found.",
  "common.toggleNavigation": "Toggle navigation",
  "common.skipToContent": "Skip to content",
  "common.connect": "Connect",
});

const pseudoChars = Object.freeze({a: "à", e: "ë", i: "ï", o: "õ", u: "ü", A: "Ȧ", E: "Ë", I: "Ï", O: "Õ", U: "Ü"});

// Deterministic pseudo-locale used by UI tests to expose clipping and missing copy.
export function pseudoLocale(value) {
  const expanded = String(value).replace(/[aeiouAEIOU]/g, character => pseudoChars[character] || character);
  return `[${expanded}··]`;
}

export function t(id, values = {}) {
  const template = messages[id];
  if (template === undefined) {
    if (globalThis.__RONIN_I18N_STRICT__) throw new Error(`Missing message: ${id}`);
    return id;
  }
  const rendered = template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? `{${key}}`));
  return globalThis.__RONIN_PSEUDO_LOCALE__ ? pseudoLocale(rendered) : rendered;
}

export function pseudoT(id, values = {}) {
  const previous = globalThis.__RONIN_PSEUDO_LOCALE__;
  globalThis.__RONIN_PSEUDO_LOCALE__ = true;
  try { return t(id, values); } finally { globalThis.__RONIN_PSEUDO_LOCALE__ = previous; }
}

export function hasMessage(id) {
  return Object.prototype.hasOwnProperty.call(messages, id);
}

export function messageIds() {
  return Object.freeze(Object.keys(messages));
}
