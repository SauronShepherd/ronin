# Ronin UI maturity scorecard

This scorecard turns the Public v1 UI ambition into reviewable acceptance criteria. It is a product-quality gate, not a claim that the current release is ready. A Studio may be called **mature** only when every applicable criterion has candidate-bound evidence.

## Product bar

Ronin should feel like one operating surface for governed data work: a user can understand the active boundary, choose a safe next action, inspect evidence, and recover from an error without learning the API. The visual language may remain original, but the interaction bar should be comparable to Databricks, Dataiku, Palantir and Fabric in clarity, density, keyboard support and operational honesty.

## Per-Studio acceptance criteria

| Area | Acceptance criterion | Evidence required |
| --- | --- | --- |
| Orientation | The page states what the Studio is for, its active workspace/project context and the next safe action above the fold. | Candidate screenshot at 1440x900 and 390x844; no invented live telemetry. |
| Progressive disclosure | The primary path is visible first; advanced parameters, destructive actions and raw JSON are behind an explicit secondary surface. | DOM review plus focused journey test. |
| Context safety | Workspace, project, environment, revision and runtime remain visible or recoverable while navigating within the Studio. | Context propagation test and mobile review. |
| Evidence | Every result exposes state, scope, identity and a useful empty/error state; successful output can be traced to its request or revision. | API/UI journey with mocked and negative responses. |
| Recovery | A failed request explains what happened, preserves entered intent where safe and gives a bounded retry or correction path. | Forced 4xx/5xx browser journey. |
| Density | Tables, forms and code output remain readable without horizontal overflow; long identifiers truncate with an accessible full value. | 320, 390, 768 and 1440 viewport matrix. |
| Accessibility | Keyboard navigation, focus restoration, labels, dialog semantics and status announcements work without a pointer. | Axe scan plus keyboard journey. |
| Performance | Initial shell and Studio assets stay inside the tracked request/byte budget; no route emits unexpected resource failures. | `studio_web_audit`, budget check and route traversal. |
| Destructive boundaries | Mutations are explicit, authenticated and confirmation-gated when irreversible; read-only previews never imply execution. | API contract tests and UI action review. |

## Release scoring

Score each applicable row as `green`, `yellow` or `red` for the exact candidate SHA. A Studio is `green` only with no red rows and no more than one yellow row, and only after human visual review. The Public v1 release remains `NO-GO` while any mandatory Studio is below green or while provider, legal, security, rollback or governance gates remain open.

The scorecard is deliberately stricter than a passing browser suite: automated tests prove behavior, while the visual and product rows require a candidate-bound human decision.

## Current iteration baseline

The 2026-11-11 candidate has automated evidence for the shell, context propagation into Data Engineering, command palette, mobile navigation clearance, long-identifier discoverability, SQL progressive disclosure, local SQL and QueryFlux tabular result previews, Catalog context inheritance, QueryFlux capability disclosure, Connections operation disclosure, Alerts decision and state-table disclosure, Semantic metric/join table disclosure, Quality response disclosure, Project Studio revision history/comparison, exact-head Chromium assembled from three bounded receipts (`59 + 69 + 47 = 175 passed`, `33 explicit skips`, `0 failed`) plus focused Data Engineering/Platform receipts (`32 passed`), updated QueryFlux/context receipt (`8 passed`), Connections receipt (`5 passed`), Alerts receipt (`3 passed`), Semantic receipt (`5 passed`) and the Python suite (`4511 passed, 77 skipped, 0 failed`). It does **not** yet have a green score for every Public v1 Studio, nor the human/product, provider, legal, security, rollback and governance approvals. Those remain explicit release blockers in `docs/product/public-v1-status.json` and `docs/product/RELEASE_DECISION_CHECKLIST_2026-11-03.md`.

## Next review order

1. Project and Data Engineering: bind revision, compare, run and evidence flows to one visible context.
2. QueryFlux, Catalog and Quality: make governed search, explainability, quality state and promotion decisions legible without raw API knowledge.
3. Scheduler, Streaming and Migration: make recovery, lag, replay and promotion boundaries visible before an operator acts.
4. ML, Semantic, Graph and Cloud: preserve provenance and safe-preview semantics across the richer authoring surfaces.
5. Repeat the full viewport, accessibility, negative-path and human visual pass on every mandatory Studio before any release decision changes.

## Candidate evidence snapshot — 2026-11-11

| Surface | Automated evidence | Current product score |
| --- | --- | --- |
| Shell, navigation and responsive layout | Chromium global `164 passed / 33 explicit skips / 0 failed`; route traversal, keyboard, Axe and viewport matrix green; web audit `0` failures | Yellow — human visual sign-off still open |
| Workspace / Project | Workspace retry `3/3`; context, revision history and comparison journeys green | Yellow — provider/source-control qualification absent |
| Environment | `5/5`, including 503 → retry, authoring, reversible governance and serious/critical Axe clean | Yellow — runtime/provider qualification absent |
| Scheduler | `3/3`, including durable operations, backfill and delivery retry | Yellow — live worker/HA qualification absent |
| Catalog / Quality / QueryFlux / Synthetic | Focused journeys green; global Chromium green | Yellow — end-to-end family qualification and real provider evidence absent |
| Migration / ML / Semantic / Graph / Cloud / Streaming | Route and focused tests green where available | Yellow/red — external runtime, portability, security and human review gates remain |

The snapshot is a candidate-bound product review, not a release score. No
surface is promoted to green until the applicable human visual review and
provider/security/rollback gates are accepted; the release ledger therefore
remains `NO-GO / 0 of 13`.
