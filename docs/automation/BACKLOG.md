# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

_Last synchronized: 2026-09-12 from base `0ab5f116ecda79a9590dff4244f6b6c55443b82d` after the current source-hygiene implementation slices._

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` must be updated together from the same observed repository state whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially. If the two files disagree, autonomous product selection stops until the drift is reconciled.

## Current validation mode

GitHub Actions are intentionally disabled to avoid consuming Actions credits. Previous workflow definitions remain under `.github/workflows-disabled/` only as historical/restart material.

Until the maintainer explicitly changes this policy, autonomous Builder work does not wait for, trigger, rerun, or require CI; does not execute automated tests; validates through static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning; and does not claim green CI or passing tests for new changes. Existing security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints.

The complementary 2026-09-11 audit reported six failing tests, lint/format drift and a storage-layer regression from its own local execution. Those observations remain diagnostic evidence, but they do not change the repository's current code-only operating policy or create permission to run tests/CI. The storage-layer finding was independently confirmed in source and resolved by #197.

Evidence-only handoffs #166/#167/#163 remain open/deferred and do not block implementation while this mode is active. Test/CI-centric #47/#60/#102 likewise remain deferred under this policy.

## Current v0.1 truth

The last automated qualification before CI was disabled remains **13/15 live**, with historical gaps `01` (production image + supported Compose topology) and `12` (public portable evidence retrieval). Both capabilities are now implemented in product code, but code-only work does not alter that qualified baseline automatically.

Supported code contains the durable local execution spine, authenticated and project-scoped HTTP job control, OpenAPI 3.1, `pyronin`, operator CLI, typed scoped grants, public portable evidence, strict-alpha API/SDK compatibility, route-level typed grant enforcement, production image + Compose, explicit bearer transport/bind policy, real readiness, corrected Git dirty identity, artifact qualification tooling, observed cgroup CPU/memory evidence, and the shared canonical JSON v1 boundary.

Canonical JSON v1 implementation for the MVP is source-complete: public HTTP request/idempotency parsing and identity use the shared codec; durable job parameters, grants, operator/diagnostic catalogs and kernel/session evidence use the same boundary; the canonical registry/goldens and checker target are present. #56 is closed. Valid v1 bytes remain the compatibility invariant.

Exact duplicate graph edges and operator target-port cardinality fail closed with the stable operator diagnostics required by #200; that implementation is complete. The #22 residual audit has not identified another concrete secret-producing source that justifies speculative hardening.

#57 remains open/BLOCKED as a qualification gate. The acceptance harness still carries stale historical step-01/step-12 skip markers, and no 15/15 claim is permitted until automated qualification is explicitly restored and executed.

## Storage evidence adapter architecture

PR #197 restored the #164 single-public-adapter invariant. Subsequent source-hygiene work removed the dead `evidence_sqlite.py` and `evidence_memory.py` compatibility reexports after confirming no consumers.

The canonical adapters remain:

- `studio_storage.SqliteJobStore` from `fenced_sqlite.SqliteJobStore`;
- `studio_storage.InMemoryJobStore` from `paged_store.InMemoryJobStore`;
- the shared evidence bound in storage-neutral `studio_storage.limits`.

This preserves lease fencing, `BEGIN IMMEDIATE`, thread-local SQLite connection reuse, keyset paging, schema-v3 availability semantics, WAL/`synchronous=FULL` through the existing lifecycle store, and the max-100 evidence-ref contract.

## Production image + Compose implementation

The supported local container path provides one digest-pinned Ronin image, durable `/var/lib/ronin` storage, server health gating, host loopback publication, worker-only Docker socket authority, immutable local image-ID resolution, read-only checkout access, narrowly scoped Git safe-directory handling, non-root product execution, worker `restart: "no"`, and a bundled CLI helper.

The supported Compose topology uses the explicit `RONIN_BIND_POLICY=container-internal` declaration for private bridge communication. This declaration is not encryption and is not a generic remote-HTTP permission; the host-facing port remains bound to `127.0.0.1`. Supported remote authenticated access terminates HTTPS externally.

No automated Compose/runtime qualification is claimed under current policy.

## Current source-hygiene state

The reproduced I0 lint findings have been addressed individually in source or revalidated as current no-ops: E501, I001, S603, S104, PT011, PT018, PT006, UP022, SIM102, RET501 and PTH201. Dead storage compatibility reexports are removed.

A repository-wide `ruff check` and `ruff format --check` are **not** claimed. The active execution environment cannot obtain a GitHub checkout, and the original format audit identified 15 files without enumerating them. Do not manufacture a formatter diff or claim a clean global pass without executable current-tree evidence.

## License/release evidence state

The deterministic #58 source implementation is present, including fail-closed dependency/build-system/release-tool surface modeling and exact-evidence validation mechanics.

What remains is evidence and human review, not source invention: an exact resolved package inventory, package-by-package legal decisions, NOTICE/attribution conclusions, and candidate-artifact binding require a real exact environment plus human/legal review. Never fabricate those artifacts or decisions.

## Contributor/docs/release surface

CONTRIBUTING, the docs landing/first-run/troubleshooting surface, issue/PR templates, release runbook, changelog, and contributor-facing governance material have landed. #71, #72 and #73 are closed.

#70 remains only where a real conduct-reporting route or genuinely suitable starter work requires human/project input. #45 remains blocked on a verified private vulnerability-reporting channel; do not publish `SECURITY.md` with an invented destination.

## Current critical path

Select one coherent slice at a time and do not create filler work.

1. **I0 global source-hygiene proof.** Only when an executable current checkout exists, run the plan's repository-wide Ruff format/check commands and address any real residual findings. Until then, do not claim the global DoD.
2. **#58/#95 exact evidence.** Requires a real exact environment and human/legal review; source mechanics are already implemented.
3. **#70 human/project remainder.** Add only a verified conduct-reporting route and genuinely suitable starter work if they actually exist.
4. **#45 security reporting decision.** `SECURITY.md` only after a verified private channel exists.
5. **#50 capability semantics decision.** No implementation until the maintainer records the current namespace/value/ambiguity/binding ADR decision.
6. **#57 qualification gate.** Revisit only if the maintainer explicitly restores automated verification.
7. **Repository administration.** Branch/ref protection and physical cleanup requiring unavailable admin/ref-delete capabilities remain administrative, not product implementation.

#95 artifact-qualification mechanics and #115 observed-resource implementation are substantially complete in code and remain open for real evidence. #63 remains a release-time repository-administration gate. #59 and #62 remain post-v0.1. #99 is closed because the Job/Run/Attempt domain and `JobStore` Protocol already exist.

## Worker execution invariants

Every remaining worker/runtime slice must preserve checkpoint-before-next-cell persistence, lease fencing, fail-closed heartbeat ownership, prompt cancellation, immutable resume identity plus verified artifact availability/digest, same-Run replacement Attempts, exact reused-cell and `attempt_id` provenance, bounded async store/artifact facades, and production lease TTL semantics.

## Public-boundary and architecture invariants

Canonical contracts remain capability-driven and vendor-neutral. Do not introduce worker -> server dependency inversion. Physical evidence/storage locators are not canonical public identity. Static bearer auth remains the v0.1 mechanism; typed least-privilege scopes are required. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. No OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry, or OpenLineage unless scope is explicitly revised.

## Quality and release invariants

These remain implementation constraints while automated enforcement is paused: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing and fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% once coverage execution is restored; exact installed-artifact plus immutable Docker-digest qualification before release.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, implementation may merge after current-main freshness checks plus complete static diff/code review. Do not run or wait for GitHub Actions/tests, and do not claim runtime/qualification evidence that was not actually produced.
