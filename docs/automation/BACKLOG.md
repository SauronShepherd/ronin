# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

_Last synchronized: 2026-09-11 from base `3e69c2a084260126f7eb87cbfbbe4bedcd77df2e` with the storage evidence-layer collapse in this change._

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` must be updated together from the same observed repository state whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially. If the two files disagree, autonomous product selection stops until the drift is reconciled.

## Current validation mode

GitHub Actions are intentionally disabled to avoid consuming Actions credits. Previous workflow definitions remain under `.github/workflows-disabled/` only as historical/restart material.

Until the maintainer explicitly changes this policy, autonomous Builder work does not wait for, trigger, rerun, or require CI; does not execute automated tests; validates through static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning; and does not claim green CI or passing tests for new changes. Existing security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints.

The complementary 2026-09-11 audit reported six failing tests, lint/format drift and a storage-layer regression from its own local execution. Those observations remain diagnostic evidence, but they do not change the repository's current code-only operating policy or create permission to run tests/CI. The storage-layer finding was independently confirmed in source and is resolved by the current collapse slice.

Evidence-only handoffs #166/#167/#163 remain open/deferred and do not block implementation while this mode is active. Test/CI-centric #47/#60/#102 likewise remain deferred under this policy.

## Current v0.1 truth

The last automated qualification before CI was disabled remains **13/15 live**, with historical gaps `01` (production image + supported Compose topology) and `12` (public portable evidence retrieval). Both capabilities are now implemented in product code, but code-only work does not alter that qualified baseline automatically.

Supported code contains the durable local execution spine, authenticated and project-scoped HTTP job control, OpenAPI 3.1, `pyronin`, operator CLI, typed scoped grants, public portable evidence, strict-alpha API/SDK compatibility, route-level typed grant enforcement, production image + Compose, explicit bearer transport/bind policy, real readiness, corrected Git dirty identity, artifact qualification tooling, observed cgroup CPU/memory evidence, and the shared canonical JSON v1 boundary.

Canonical JSON v1 has landed through #190/#193/#194/#195 for the shared codec, independent Go checker, resume identity, worker identity, project manifests, notebooks and IR. #56 remains open because kernel/session, public HTTP request/idempotency identity, durable parameter parsing, grants and remaining core identity serializers still require migration and boundary goldens.

#57 remains open/BLOCKED as a qualification gate. The acceptance harness still carries stale historical step-01/step-12 skip markers, and no 15/15 claim is permitted until automated qualification is explicitly restored and executed.

## Storage evidence adapter architecture

The schema-v3 public-evidence extension had reintroduced concrete `evidence_sqlite.SqliteJobStore` and `evidence_memory.InMemoryJobStore` subclasses after #164 established a single-public-adapter invariant.

The current collapse restores that invariant:

- `studio_storage.SqliteJobStore` is exported directly from `fenced_sqlite.SqliteJobStore`;
- schema-v3 evidence availability/unavailable fields and the per-Run bound live in that canonical fenced SQLite adapter;
- `evidence_sqlite.py` is a compatibility re-export rather than another concrete class;
- `studio_storage.InMemoryJobStore` is exported directly from `paged_store.InMemoryJobStore`;
- the same per-Run evidence bound lives in the canonical paged in-memory adapter;
- `evidence_memory.py` is a compatibility re-export;
- the shared bound is defined in storage-neutral `studio_storage.limits`.

This preserves lease fencing, `BEGIN IMMEDIATE`, thread-local SQLite connection reuse, keyset paging, schema-v3 availability semantics, WAL/`synchronous=FULL` through the existing lifecycle store, and the max-100 evidence-ref contract without relaxing the existing regression guards.

## Production image + Compose implementation

The supported local container path provides one digest-pinned Ronin image, durable `/var/lib/ronin` storage, server health gating, host loopback publication, worker-only Docker socket authority, immutable local image-ID resolution, read-only checkout access, narrowly scoped Git safe-directory handling, non-root product execution, worker `restart: "no"`, and a bundled CLI helper.

The supported Compose topology uses the explicit `RONIN_BIND_POLICY=container-internal` declaration for private bridge communication. This declaration is not encryption and is not a generic remote-HTTP permission; the host-facing port remains bound to `127.0.0.1`. Supported remote authenticated access terminates HTTPS externally.

No automated Compose/runtime qualification is claimed under current policy.

## Current critical path

Select one coherent slice at a time.

1. **#56 — finish canonical JSON identity boundaries.** Migrate kernel/session, HTTP request/idempotency input, durable `parameters_json`, grants and remaining core serializers; add complete boundary goldens while preserving valid v1 bytes.
2. **#22 — residual architecture reconciliation.** After #56, handle duplicate exact edges, operator-aware target-port cardinality and concrete secret-bearing producers without reopening already-completed durable/auth/evidence work.
3. **#58 — exact transitive license/NOTICE evidence.** Tooling exists; remaining deterministic code work is explicit build-system/release-tool exception modeling. Exact inventory/policy/NOTICE conclusions require a real resolved environment and human review; never fabricate them.
4. **#70/#72/#71/#73 — contributor/governance/docs/release surface.** Governance decision is already recorded; publish truthful contributor-facing policy, docs index, troubleshooting, first-run and release/change communication. #45 security policy remains blocked on a verified private reporting channel.
5. **#50 — runtime capability namespace/ambiguity decision.** Decision record first; do not add a second v0.1 runtime.
6. **#57 — qualification gate.** Revisit only if the maintainer explicitly restores automated verification.

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
