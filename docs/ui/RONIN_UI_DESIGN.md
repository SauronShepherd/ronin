# RONIN UI/UX Design Specification

**Status:** living product-design document — repository-verified
**Revision:** 3
**Run date:** 2026-09-18
**Repository:** `SauronShepherd/ronin`
**Review baseline:** `5b33e10554ece861d69b6bd564562672c98e38a8`

> The requested `SauronShepherd/roninand` URL is not the active repository. The connected GitHub installation exposes `SauronShepherd/ronin`, which is the repository reviewed and updated here.

## 0. Product rule

Ronin Studio should feel like one compact operating environment for Data + AI work:

**Choose an outcome → gather resources → define meaning → build logic → validate → understand placement → run/deploy → observe → iterate.**

KISS rules:

- intent before platform taxonomy;
- one obvious primary action per page;
- logical meaning before physical/runtime placement;
- AUTO placement by default, with “Why this placement?” available;
- no silent downgrade or hidden cross-provider retry;
- raw evidence one click away, but never the default interpretation;
- secrets by reference;
- vendor colors only in bounded provider badges;
- accessible structured alternatives for canvas/drag interactions;
- incremental evolution from the existing static Studio rather than a required big-bang rewrite.

## 1. Current Studio audit

### Verified source

Current Web Studio is the static surface under `web/`:

- `web/index.html`
- `web/studio.css`
- `web/studio.js`
- `web/README.md`

It currently provides:

- top-bar API URL + bearer token connection;
- Runs / Evidence / Logs / SQL navigation;
- project + state run filters, Apply/Clear, current scope, cursor pagination and Refresh;
- run detail with Status / Events / Evidence rendered as formatted JSON;
- cancellation using a browser confirmation;
- project-scoped read-only SQL;
- API URL in `localStorage`, bearer token only in `sessionStorage`;
- a 15-second browser request timeout.

Server-side static files remain allowlisted. Server authorization remains authoritative.

### Screenshot evidence

A real Chromium capture was attempted against exact locally served verified Studio HTML/CSS. Chromium returned `ERR_BLOCKED_BY_ADMINISTRATOR`, so **no browser screenshot is claimed**. `mockups/current-studio-source-reconstruction.svg` is explicitly a source-grounded reconstruction, not a screenshot.

### Preserve / change

| Current behavior | Decision |
|---|---|
| Runs list | Keep and generalize into Observe / Runs |
| Project/state filters + Clear + scope | Keep |
| Cursor pagination | Keep as proven baseline; do not replace with speculative infinite scrolling |
| Evidence/events/logs | Keep, but move into contextual Run Detail tabs |
| SQL | Keep, later promote into Build / Notebooks & SQL |
| API/token form in permanent top bar | Demote into local Session/Connection setup |
| Raw JSON as default detail | Move behind Raw |
| Dark-only theme | Add explicit light/dark semantic tokens |
| Gold used as state | Use semantic state colors + text/icon |
| Generic clickable run cards | Use semantic table rows/links |
| Browser confirm | Replace with accessible product dialog |

## 2. North-star IA

Global shell:

**Work**
- Home
- Data
- Build
- Catalog
- AI
- Deploy
- Observe

**Workspace**
- Projects
- Admin

First-class routes inside those groups:

- **Data:** Connections, Ingestion, Lakehouse, Streams
- **Build:** Pipelines, Notebooks, SQL, Graph Query, Semantic Models, Dashboards
- **Catalog:** Assets, Lineage, Quality, Ontology, Knowledge Graph
- **AI:** AI/ML Lab, Experiments, Features, Models, GenAI, Prompts, RAG, Agents
- **Deploy:** Endpoints, Services, Workflow Deployments, Environments, Runtime Profiles
- **Observe:** Runs, Monitoring, Alerts, Cost Control
- **Admin:** Access, Identities, Secrets, Policies, Audit, Settings

Persistent context:

**Workspace → Project → Environment/Profile → Asset / Run**

Project switching is global because repository, runtime, policy, lineage, cost and observability attach to project identity.

## 3. Design system

Use `docs/product/BRAND_V1.md` as the visual contract.

Primary brown scale:

| Token | Hex |
|---|---|
| brown-950 | #241A16 |
| brown-900 | #35251D |
| brown-800 | #503020 |
| brown-700 | #604030 |
| brown-600 | #705040 |
| brown-500 | #806050 |
| brown-400 | #A47A5A |
| brown-300 | #C9A383 |
| brown-200 | #E3C8AD |
| brown-100 | #F2E3D2 |
| brown-50 | #FAF5EE |

Gold/amber: `#B96800 #D88000 #F0A010 #F0B010 #F0C020`.
Neutrals: `#111111 #202020 #303030 #F0E0D0 #FFF9F2 #FFFFFF`.

Semantic status remains separate: green success, amber/yellow warning, red error/destructive, blue information/running, gray unknown. Never rely on color alone.

Core components: `AppShell`, `ProjectSwitcher`, `GlobalCommandPalette`, `CreateRouter`, `StatusChip`, `ProviderBadge`, `DecisionEvidence`, `UniversalAssetRow`, `DataTable`, `TreeExplorer`, `WizardStepper`, `CodeEditorShell`, `ResultGrid`, `GraphCanvas` + `GraphStructuredEditor`, `RunTimeline`, `EvidenceViewer`, `MetricCard`, `CostAttribution`, `InlineDiagnostic`, `DestructiveReviewDialog`.

## 4. Screen map

### Home
**Job:** resume useful work, start an outcome, resolve attention.
**Layout:** outcome prompt → Continue → Needs attention → compact operations strip.
**Primary:** Plan build.
**Objects:** drafts, deployments, failed/blocked runs, stale connections, quality/budget alerts.
**Guidance:** action-oriented summaries. Avoid dashboard clutter.
**Accessibility/responsive:** semantic links; cards stack.

### Create
**Job:** convert intent into the smallest valid set of resources.
**Entry:** global + Create, empty states, contextual “create from”.
**Flow:** Inputs → Definition → Validation → Runtime/placement if needed → Review → Create/deploy.
**Guidance:** defaults first; Advanced collapsed. Never silently deploy generated plans.

### Projects
**Job:** bind project code and runtime intent.
**Tabs:** Overview / Code / Runtime / Members / Settings.
**Validation:** repository identity and runtime capability checks are separate.
**Guidance:** requested vs resolved runtime, with exact compatibility evidence.
**Error:** no silent runtime downgrade.

### Data / Connections
**Job:** connect/discover data safely.
**Flow:** connector → secret reference → endpoint/config → test → discover → save.
**States:** healthy/degraded/unavailable/unverified/disabled.
**Guidance:** exact/partial/unsupported capability behavior.
**Secrets:** references only.

### Data / Ingestion, Lakehouse, Streams
**Job:** move/reference data with explicit freshness/checkpoint behavior.
**Validation:** schema, cursor/watermark, sink policy, permissions.
**Advanced:** partitions, snapshots, checkpoint internals.
**Error:** schema drift/checkpoint conflict preserves last useful state.

### Build / Pipelines
**Job:** assemble repeatable DAG work.
**Layout:** DAG + canonical task list + inspector.
**Validation:** cycles, params, permissions, runtime capability.
**Accessibility:** every drag operation has list/form equivalent.

### Build / Notebooks & SQL
**Job:** build/explore logic in governed context.
**Layout:** asset explorer + editor + results/evidence + context.
**Results:** table first; Raw secondary.
**Error:** preserve source and last successful results.

### Catalog
**Job:** find trusted resources and understand ownership, quality and lineage.
**Filters:** type, owner, tag, classification, quality, project.
**Asset detail:** Overview / Lineage / Quality / Usage / History.
**Unknown:** missing lineage/quality is Unknown, not healthy.

### Ontology / Knowledge Graph / Graph Intelligence
Keep four layers distinct:
1. Catalog asset
2. Logical ontology/graph model
3. Physical binding
4. Execution placement

Model tabs: Model / Bindings / Lineage / Usage / History.
Provider incompatibility does not invalidate logical semantics.
Graph canvas always has a structured editor equivalent.

### Semantic Models / Dashboards
**Job:** define reusable dimensions/measures and simple governed views.
**Guidance:** show semantic definition + compiled query.
**Accessibility:** charts have tabular equivalent.

### AI/ML Lab
**Job:** train, compare, evaluate, register.
**Lineage:** data → run → model → deployment.
**Advanced:** params/artifacts/runtime snapshot.

### GenAI Lab
**Job:** build/evaluate prompts, retrieval and agents.
**Validation:** secret refs, tool permissions, knowledge source, token/cost policy.
**Evidence:** retrieved context/tool calls visible; trace values redacted by default.

### Deploy
**Job:** make a validated asset operable in a supported reference/development profile.
**Review:** artifact/version, runtime, environment, permissions, limits, telemetry.
**Honesty:** do not imply unsupported production guarantees.

### Observe
Runs / Monitoring & Alerts / Cost Control. Revision 3 deep dive below.

### Admin
People & identities / Roles & grants / Secrets / Policies / Audit / Settings.
Fail closed; secrets are reference metadata only.

## 5. Deep dive #1 — Create / New

Two entry modes:

1. **Describe an outcome** — Ronin proposes a build plan for explicit user approval.
2. **Choose a starting point** — expert resource shortcuts.

Quick starts: Connect data, Ingest/sync, Pipeline, Notebook, SQL, Ontology/KG, Graph Query, Train/evaluate model, RAG/Agent, Semantic Model/Dashboard, Deployment, Import/Migrate.

Generated plans never silently persist or deploy resources.

## 6. Deep dive #2 — Graph / KG / bindings

Logical semantics and execution placement remain separate.

Binding cards show:
- name/provider badge;
- Ready/Stale/Unverified/Unavailable/Disabled;
- freshness summary;
- locality/movement summary;
- last validation.

Expanded mapping reveals physical tables/labels/properties, safe backend version and secret reference ID.

Graph Query uses `Validate & run` as primary action and a small placement pill such as `AUTO · Native Spark`.

“Why this placement?” uses a shared candidate table: support, binding/freshness, movement, selection/rejection reason. Planning rejection is normal eligibility evidence, not runtime failure.

## 7. Deep dive #3 — Observe / Runs / Evidence / Logs / Metrics / Cost

This revision focuses here because it maps directly onto today’s working Studio APIs.

### 7.1 Runs list

Use a **table**, not large cards, for operational density.

Default columns:
- State
- Run / Resource
- Runtime/placement when available
- Started
- Duration
- Evidence/attention

Target filters:
- text search
- state
- workload type
- time range
- optional asset/runtime under More

Keep current project/state filtering + cursor pagination as the first implementation slice. Do not invent unavailable fields.

Attention strip is conditional: failures needing review, blocked/waiting work, incomplete evidence, budget/quality impact.

Rows are semantic links and fully keyboard focusable. State uses icon + text + semantic color.

### 7.2 Run detail

Header answers:
- what resource/workload;
- run ID;
- state/type;
- start/end/duration;
- project;
- resolved runtime/provider when available;
- revision;
- output summary;
- cost classification/value when available.

Tabs:

**Summary / Tasks / Events / Evidence / Logs / Metrics / Cost / Raw**

Unsupported tabs are capability-driven; they are not populated with invented data.

### 7.3 Summary

Order:
1. state/failure summary;
2. run timeline;
3. evidence-health checklist;
4. task summary;
5. normalized key metrics;
6. next action.

### 7.4 Events

Structured timeline first: timestamp, event type, actor/system, safe summary, related task/resource. Raw canonical event expands per row.

Events are durable lifecycle evidence and stay distinct from diagnostic logs.

### 7.5 Evidence

Group by question:

**Identity & reproducibility**
- project
- repository commit/dirty identity
- runtime snapshot
- redacted parameter/config identity
- image/dependency identity when available

**Inputs & outputs**
- asset revisions/snapshots
- outputs/artifacts
- rows/bytes/checksums where supported
- lineage links

**Validation/governance**
- quality gates
- capability decisions
- policy decisions
- migration classification/report when relevant

**Execution**
- attempts
- result/failure code
- engine/provider detail
- metric/log pointers

Raw evidence stays available.

### 7.6 Logs

Task/source selector where applicable, search/severity if backend supports it, timestamps/source labels, visible redaction status. Do not merge logs with events.

### 7.7 Metrics

Normalize cross-platform metrics first:
- duration
- rows/bytes
- CPU/memory/storage/network if available
- retries
- queue/lag
- serving metrics
- GenAI tokens/latency
- streaming lag

Provider-native metrics live under Provider details/Raw.

### 7.8 Cost

Always classify as **Actual / Estimated / Unknown / N/A**.
Unknown is never rendered as 0.
Show attribution tags, top drivers and budget impact when supported.

### 7.9 Raw

Safe canonical JSON for status/events/evidence/errors. Selecting Raw never disables redaction.

### 7.10 Failure card

Must include:
- readable title;
- stable code;
- affected step/resource;
- timestamp;
- safe detail/source span when available;
- one clear next action;
- run/diagnostic ID.

Users should not search JSON to understand the primary failure.

### 7.11 Cancellation

Replace browser confirm with `DestructiveReviewDialog`.

Explain object, current state and consequence. “Keep running” is default; “Request cancellation” is destructive. Show `Cancelling` until a terminal state confirms outcome.

### 7.12 Loading/refresh

- initial load: skeleton/spinner + label;
- refresh: retain existing data;
- failed refresh: retain last data + stale banner;
- empty: explain active filters and offer Clear;
- permission denied: identify evidence class safely;
- backend unavailable: distinguish from empty.

### 7.13 Live behavior

Terminal runs do not auto-refresh.
Running detail may poll modestly or use future event streaming, with last-updated time.
Runs list stays manual Refresh by default; optional auto-refresh may be session-scoped.
Avoid high-frequency background polling.

### 7.14 Accessibility

- proper table headers + row links;
- text/icon + color states;
- textual timeline equivalent;
- WAI-ARIA tabs;
- polite live-state announcements;
- charts backed by tables;
- focus-managed destructive dialog;
- Raw/log panes scroll internally rather than causing page-level horizontal overflow.

### 7.15 Evidence completeness

Do **not** invent a percentage. Use named states:

- Repository identity — Complete / Missing / N/A
- Runtime snapshot — Complete / Missing / N/A
- Inputs/outputs — Complete / Partial / N/A
- Quality/policy — Passed / Blocked / N/A
- Cost — Actual / Estimated / Unknown / N/A

### 7.16 KISS rejects

Rejected:
- Evidence and Logs as permanent top-level nav;
- giant run-card inventories;
- provider-specific run layouts;
- raw JSON as default;
- missing cost represented as zero;
- automatic cross-provider retry after execution failure;
- fake “evidence completeness” scores;
- replacing proven cursor pagination with speculative infinite scroll.

## 8. Shared explainability grammar

Use the same component for runtime resolution, graph provider selection, connector support, migration translation, quality/policy gating and cost policy:

**Decision → Why → Alternatives → Exact evidence**

`DecisionEvidence` shows a plain-language result and 1–2 reasons first, with exact normalized evidence under disclosure.

## 9. Key journeys

### Ingest + pipeline
Create → connection → schema discovery → incremental ingestion → checkpoint validation → governed table → quality → pipeline/schedule → runtime review → run → Observe → lineage.

### Graph Intelligence
Catalog datasets → logical relationship model → semantic validation → bindings → Graph Query → validate → Explain placement → run → DataFrame result → Observe evidence.

### Train + serve model
Dataset snapshot → experiment → runtime compatibility → train/evaluate → compare/register → deploy reference endpoint → Observe metrics/cost → lineage.

### RAG/agent
Model/provider → governed knowledge → retrieval → prompt → tools/permissions → evaluation → token/cost evidence → deploy → Observe.

### Diagnose failure
Home attention → Run Summary → affected task → structured evidence/event → logs only if needed → edit source/config → explicit rerun → compare evidence.

## 10. Interaction rules

Every async view distinguishes loading, refresh, success, empty, degraded, permission denied, unavailable and validation error.

Structured errors show stable code, affected resource/field, source span where available, safe details, action and copyable diagnostic ID.

Tables are for operational density/comparison. Cards are for onboarding/resume/attention. Raw JSON is expert evidence, not default interpretation.

Missing freshness, telemetry, cost or capability is Unknown/Unverified — never silently healthy/current/zero.

## 11. Implementation mapping

### `web/index.html`
Incrementally introduce the new shell/nav while keeping Runs and SQL functioning. Move global Evidence/Logs into Run Detail. Move local API connection UI into Session once replacement exists.

### `web/studio.css`
Map to Brand v1 semantic tokens; add explicit light/dark maps, `:focus-visible`, semantic states. Preserve current simple responsive approach.

### `web/studio.js`
Preserve timeout, session-only token, API URL preference, filters, cursor pagination and permission-specific errors. Refactor API client/render/router boundaries only as needed. Add structured status/events/evidence and accessible cancellation dialog.

### `python/studio_server/http.py`
Preserve fail-closed static allowlist. New assets require deliberate allowlist/bundling changes.

### `python/studio_server/control_plane.py`
Use verified workspace/project/workflow contracts rather than creating browser-only semantics.

### `api/openapi-v1.json` + `tools/route_consistency.py`
Keep UI mutations represented by documented APIs and keep route consistency enforcement.

### `tests/test_studio_static.py`
Extend existing tests rather than replacing them: semantic run links, structured/raw evidence, cancellation dialog path, session-only auth policy and static allowlist.

## 12. Incremental delivery sequence

1. Shell + Brand v1 semantic tokens; current Runs/SQL still work.
2. Observe migration over current job/events/evidence/cancel endpoints.
3. Projects over current workspace/project API.
4. SQL inside proper Build editor shell without inventing writes.
5. Workflow task hierarchy reusing Run Detail.
6. Data/Catalog/domain modules only as supported APIs mature.
7. Graph Explain through shared DecisionEvidence.
8. AI/GenAI/deployment observation reusing Run/Evidence/Metrics/Cost primitives.

## 13. Visual artifacts

- `mockups/current-studio-source-reconstruction.svg` — source reconstruction, **not** a screenshot.
- `mockups/app-shell-v3.svg` — north-star shell.
- `mockups/observe-run-detail.svg` — revision-3 deep-dive design.

## 14. Re-review

Navigation remains compact by grouping mandatory Public v1 areas into Data / Build / Catalog / AI / Deploy / Observe while keeping first-class direct routes.

Terminology:
- Studio = whole web product.
- Notebooks & SQL / Graph Query = authoring.
- Ontology/KG = semantic modeling.
- Providers/runtimes = contextual execution detail.
- Evidence = cross-cutting concept, not global taxonomy.

KISS check for every page:
1. main action obvious in five seconds;
2. normal path works without Advanced;
3. semantics and placement are separate;
4. raw evidence is one disclosure away;
5. no premature choices;
6. no duplicate navigation;
7. errors give a concrete next action.

## 15. Open questions

- Frontend framework remains intentionally undecided.
- Exact bridge between Public v1 ontology object/link types and historical RQL graph descriptors needs an implementation contract.
- Status color values still require automated WCAG contrast verification.
- Run search/type/time filters beyond current project/state need backend support.
- Metrics/cost tabs must be capability-driven; never synthetic.
- Browser screenshots remain blocked by the current Chromium administrator policy.

## 16. Revision log

### Revision 1
Initial north-star IA, Create/New deep dive and provisional design system; repository access was unavailable, so current UI details were deliberately unverified.

### Revision 2
Repository verified as `SauronShepherd/ronin`; current Studio/source/product/brand reviewed; full Public v1 IA and Graph/KG/provider-binding deep dive added.

### Revision 3 — current
- attempted real Chromium QA; navigation was blocked by administrator policy, so no screenshot claim;
- deep-designed Observe/Runs/Evidence/Logs/Metrics/Cost;
- preserved proven current filtering, cursor and auth behavior;
- structured Run Detail replaces “three JSON boxes” while keeping Raw one tab away;
- defined failure/cancel/refresh/responsive/accessibility behavior;
- added actual/estimated/unknown cost semantics;
- re-reviewed KISS and rejected hidden retries, fake completeness scores and provider-specific run layouts.

**Next priority:** Data / Connections / Ingestion — connect → discover → ingest/reference → validate → observe freshness, including secret-reference UX, schema diff, incremental cursor/watermark configuration and zero-copy vs movement explanation.
