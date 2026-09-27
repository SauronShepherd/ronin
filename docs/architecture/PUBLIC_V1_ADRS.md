# Public v1 architecture decisions

This document records the minimum decisions required by DOC-003 of the
current build plan. These are architecture and evidence boundaries; they do
not turn an incomplete capability into a release-qualified one.

## ADR-PV1-001 — Query-engine contract and optional QueryFlux provider

**Status:** accepted.

Ronin exposes a provider-neutral query-engine contract for discovery,
submit/poll/cancel, bounded result retrieval and normalized failure states.
DuckDB is the local reference engine. QueryFlux is an optional provider
selected through explicit configuration and capability discovery; it is never
silently substituted for the local engine and `not_configured` is distinct from
`qualified`. A provider must preserve project scope, read-only policy, row and
resource bounds, cancellation, and evidence digests. QueryFlux qualification
requires an operator-supplied real endpoint or command and candidate-bound
evidence.

## ADR-PV1-002 — Capability namespace and dispatch binding

**Status:** accepted pending maintainer confirmation of the public value set.

Capabilities are namespaced, versioned values (for example,
`ronin.query-engine/v1`) and are compared as structured values, not arbitrary
strings. Discovery records the provider, version, constraints and evidence
source. Dispatch binds a selected capability at execution time, rechecks the
required constraints immediately before execution, and fails closed on an
unknown namespace, unsupported version, ambiguity or stale binding. A
capability declaration is not proof of provider qualification.

## ADR-PV1-003 — Release evidence aggregation

**Status:** accepted.

Each evidence item must identify the exact source SHA, artifact/image identity,
environment fingerprint, command, status, start/end time and relevant digest.
The aggregate verifier accepts only required gates with the exact candidate
identity, valid schema, fresh timestamps, and no skip, missing, xfail, error or
unexpected result. Product capability status is an independent input: a green
test gate cannot override a `partial`, `blocked` or `qualification_pending`
mandatory capability. Historical evidence is retained as context and cannot
be promoted by copying or relabeling it.

## ADR-PV1-004 — Publication channel policy

**Status:** accepted.

Publication is allowed only from one immutable, exact candidate. Wheel, sdist,
container image, SBOM, provenance and release notes must refer to the same
source SHA and artifact digests already qualified. Publication does not rebuild
or mutate artifacts. Tag and branch protection, private vulnerability
reporting, legal/NOTICE review and maintainer authorization remain external
release gates; automation must fail closed when their evidence is absent.

## ADR-PV1-005 — Browser qualification architecture

**Status:** accepted.

Browser qualification is layered: installed-package smoke verifies packaged
assets and runtime/browser errors; Playwright journeys verify authenticated
routes and domain behavior; axe-based checks verify the supported viewport
matrix; headed mode is a diagnostic mode, not a stronger release gate. Server
authorization remains authoritative and browser checks cannot replace API
negative tests. Visual regression is not claimed until reference artifacts,
review policy and a reproducible baseline are defined.

## ADR-PV1-006 — Bundle family portability

**Status:** accepted.

Bundle inventories contain canonical logical intent, dependencies, binding
requests and verified payload digests. Physical locations, credentials,
ephemeral scheduler state and provider-specific runtime locators are excluded
unless represented as explicit remappable bindings. Import is planned and
validated before an atomic commit; conflicts fail closed. A family is
certified only after export → clean-target import → reference journey →
re-export produces a semantic inventory match. Fixture-only round-trips are
implementation evidence, not full Public v1 certification.

## Decision ownership

The public capability namespace/value set and any change to release gates are
maintainer-owned decisions. Implementation may preserve conservative behavior
and report ambiguity, but must not invent a value or silently weaken a gate.
