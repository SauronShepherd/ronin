# Ronin Studio UI decisions

These decisions implement the recommendations in the build plan and are the
contract for subsequent UI work.

| ID | Decision | Resolution |
|---|---|---|
| D1 | Information architecture | Use the prototype's flat primary navigation with grouped child surfaces. Backend-backed routes are active; unsupported capabilities remain visible as disabled planned surfaces. |
| D2 | Theme | Light canvas with dark rail. Gold is reserved for dark-rail branding and is not used for focus or body controls where its measured contrast is insufficient. |
| D3 | CORS | Do not add CORS. Studio is served by the control plane's own origin; cross-origin configuration is not part of the product path. |
| D4 | Iconography | Use inline SVG icons with adjacent accessible labels. Unicode glyphs are not part of the rendered production icon system. |
| D5 | Initial scope | Runs, run detail, Workspaces/Projects, Workflows, SQL and Governance/Access are connected to published APIs. Catalog, Data, Graphs, AI, Deployments and Environments remain explicit disabled placeholders until their contracts/capabilities exist. |

Security and data invariants remain authoritative: the server owns
authorization; bearer tokens are session-only; cursors remain opaque; secrets
are references only; physical evidence locators are never rendered; and no
screen may present invented provider or connector data.

Unavailable navigation surfaces are intentionally rendered as visibly planned
and `aria-disabled`; they remain discoverable without presenting mock data as
live capability.
