# Ronin v0.1 construction plan

_Last synchronized: 2026-09-11 from base `3e69c2a084260126f7eb87cbfbbe4bedcd77df2e` with the storage evidence-layer collapse in this change. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

Ronin remains capability-ordered rather than calendar-ordered. Each autonomous run selects at most one coherent implementation slice and revalidates against current `main`, open Builder work, canonical handoffs, and frozen v0.1 scope.

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` are one canonical planning pair. Whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially, both files must be updated from the same observed repository state.

## Current validation mode

GitHub Actions and automated tests are intentionally disabled by maintainer policy. Previous workflow definitions remain under `.github/workflows-disabled/`. Autonomous work performs static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning only. Security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints, but no new CI/test/acceptance evidence may be claimed.

A complementary local audit dated 2026-09-11 reported six failing tests, format/lint drift, low indirect coverage in `grants.py`, stale acceptance skips, orphaned qualification tooling and a concrete storage-layer regression. Those execution-derived observations remain useful diagnostic evidence, but this plan does not adopt that audit's CI/test phases as current requirements because the maintainer has explicitly kept Ronin in code-only mode. The storage regression was independently confirmed in source and is resolved by the current collapse slice.

The last authoritative automated acceptance baseline remains **13/15**, with historical gaps `01` and `12`. Product code for both capabilities exists; code-only implementation does not automatically change the qualified result.

## Current position

The MVP durable local execution spine is implemented: Job -> Run -> Attempt lifecycle, SQLite/in-memory storage, bounded async composition, immutable resume identity, Docker worker execution/recovery, fencing/cancellation, authenticated HTTP job control, OpenAPI, `pyronin`, operator CLI, typed scoped grants, public portable evidence, strict-alpha public compatibility, project-scoped HTTP authorization, production image/Compose, explicit bearer transport/bind policy, real readiness, corrected Git dirty identity, observed cgroup CPU/memory evidence, exact-artifact qualification tooling and the canonical JSON v1 foundation.

Canonical JSON work has advanced through #190/#193/#194/#195: shared codec, independent Go checker, resume identity, worker identity, project manifest, notebook and IR all use the common boundary. Remaining #56 work is concentrated in kernel/session, HTTP request/idempotency parsing/identity, durable parameter parsing, grants and remaining core serializers plus complete boundary goldens.

#95 is no longer a missing implementation tool: `tools/artifact_qualification.py` provides the code mechanics for build-once, external install and artifact identity. Real artifact qualification/publish evidence remains outstanding. #115 likewise has production cgroup observation code; real-Docker/overhead evidence remains outstanding.

#99 is closed: the immutable Job/Run/Attempt lifecycle, lease/retry rules and storage-neutral `JobStore` Protocol are already present in `studio_orchestrator` and consumed by storage/worker code.

## Phase A — foundation

**Complete.** Deterministic domain/runtime/notebook/kernel contracts and architecture boundaries are present.

## Phase B — durable worker execution and resume

**Complete for the MVP spine.** Replacement Attempts remain in the same logical Run and preserve exact cell-reuse plus `attempt_id` provenance.

## Phase C — HTTP/API/SDK contract

**Functionally complete in code; automated qualification deferred.** Authenticated job control, typed project/action grants, evidence, pagination/cursors, OpenAPI, `pyronin`, compatibility rules and secure bearer transport are implemented.

## Phase D — operator CLI and Git identity

**Functionally complete in code under current policy.** Installed command routing and Git identity hardening are present; automated regression proof remains deferred.

## Phase E — production image, Compose and zero-to-demo

**Functionally complete in code; automated qualification deferred.**

The repository contains one production Ronin image and supported `compose.yaml` topology with durable local SQLite/artifact/evidence storage, explicit server health dependency, host loopback publication, worker-only Docker socket authority, immutable local image-ID resolution, read-only checkout access, narrowly scoped Git safe-directory configuration, non-root product execution, crash-path worker `restart: "no"`, and a no-Docker-authority CLI helper.

Compose uses `RONIN_BIND_POLICY=container-internal` for private bridge communication. This is an explicit topology declaration, not encryption and not a generic remote-HTTP permission. The host-facing port remains loopback-only; supported remote authenticated access terminates HTTPS externally.

The <60 s healthy and <10 min zero-to-demo budgets remain implementation targets, not newly measured evidence while tests/CI are disabled.

## Phase F — architecture/canonical hardening

### F1 — storage evidence adapter collapse

**Code-complete in this change under static review; automated regression proof deferred.**

The schema-v3 evidence extension had reintroduced concrete subclasses outside the canonical storage adapters. The current implementation restores the #164 architecture invariant:

```text
SQLite:
  _SqliteLifecycleStore
    -> fenced_sqlite.SqliteJobStore  # exported concrete adapter

Memory:
  memory.InMemoryJobStore
    -> paged_store.InMemoryJobStore  # exported concrete adapter
```

Details:

1. schema-v3 `availability` and `unavailable_reason` persistence now lives in `fenced_sqlite.SqliteJobStore`;
2. the per-Run bound `MAX_EVIDENCE_REFS_PER_RUN=100` is shared from `studio_storage.limits`;
3. SQLite checks the bound inside the same `BEGIN IMMEDIATE` transaction and rolls back the attempted write on overflow;
4. the exported SQLite class retains the existing fail-closed legacy-call overload/normalization surface and active lease fencing;
5. `evidence_sqlite.py` is only a compatibility re-export;
6. the canonical paged in-memory adapter owns the same evidence bound;
7. `evidence_memory.py` is only a compatibility re-export;
8. `studio_storage.__init__` exports the canonical classes directly.

Existing lifecycle storage still owns migration/read primitives, WAL and `synchronous=FULL`; paging and thread-local SQLite connection reuse remain unchanged. No test was edited to accept the previously layered state.

### F2 — finish #56 canonical JSON

This is now the next code-critical phase:

1. `studio_kernel/session.py`: canonicalize authorization/event bytes and duplicate/nonfinite ledger parsing;
2. `studio_server/http.py`: canonicalize `_request_identity` and reject duplicate/nonfinite request JSON before identity construction; keep `_write_json` as presentation JSON;
3. `studio_orchestrator/lifecycle.py`: canonical decoder for `Job.parameters_json` validation;
4. `studio_core/grants.py`: route Requirement/GrantSet/AuthorizationEvidence JSON through shared codec;
5. `studio_core/operators.py` and `diagnostics.py`: route canonical catalog serializers through shared codec;
6. audit remaining direct `json.dumps/json.loads` call sites and classify identity vs presentation/cursor/tooling;
7. extend canonical goldens for project, notebook, IR, cell execution, HTTP request identity, kernel events and grants;
8. preserve valid v1 bytes, including the documented finite-float and `-0.0` compatibility boundary.

### F3 — #22 residual architecture reconciliation

After #56, reconcile only remaining current-source defects: duplicate exact edges, operator-aware target-port cardinality and concrete secret-bearing producer surfaces. Do not reopen already-landed durable/auth/evidence/transport work.

## Phase G — security, supply-chain and release implementation

### #58 exact transitive license/NOTICE

The fail-closed tooling exists. Remaining honest implementation work before real evidence is available is to make the PEP 517 `build-system.requires` and release-only tool surfaces explicit rather than pretending they belong to `requirements-dev.lock`.

Exact `third_party/licenses-v1.json`, per-package `license-policy-v1.json`, NOTICE/attribution conclusions and approval rationales require a real exact environment plus human/legal review. Do not fabricate them.

### #95 exact artifact identity

Implementation mechanics already exist. Do not reimplement them. The remaining release claim requires execution against a real candidate and binding that artifact identity to #58 evidence.

### Human/project surface

After the code-critical items above, prioritize:

- #72 + #70: contributor-facing governance, CONTRIBUTING, Code of Conduct and templates;
- #71: docs landing, canonical first-run and troubleshooting;
- #73: release runbook and change communication;
- #45: SECURITY only after the maintainer selects and verifies a real private reporting channel.

## Phase H — decisions and release gates

#50 requires a written architecture decision before implementation: capability namespaces/value families, explicit ambiguity semantics, unknown-version behavior, selection evidence and dispatch-time binding. Do not add a second v0.1 runtime merely to satisfy it.

#63 remains a release-time repository-administration gate: protect `main` and semantic release refs before `v0.1.0`, no later than 2026-11-01.

#57 remains a qualification gate, not a feature slice. If and only if the maintainer explicitly restores automated verification, remove stale step-01/step-12 skips and obtain strict exact-SHA 15/15 evidence without weakening the frozen contract.

## Deferred verification/evidence track

While code-only mode is active, do not select these as implementation blockers:

- #47 mutation expansion;
- #60 Docker qualification bootstrap pin plus its runtime proof;
- #69 retained benchmark evidence;
- #102 release-tool coverage;
- #163 scheduled full qualification;
- #166 verifier same-mode evidence;
- #167 HTTP contention same-mode evidence;
- #115 real-Docker collection-overhead proof;
- #95 real candidate qualification/publish proof;
- #57 strict 15/15.

Their requirements remain preserved for any future verification phase; no thresholds or acceptance semantics may be weakened simply because enforcement is paused.

## Post-v0.1

#59 open-table/data-platform work remains frozen until v0.1 ships and the E3 freeze is explicitly lifted.

#62 language-neutral runner protocol is post-v0.1 and should be treated as already directionally decided by ADR-V01-009: define a versioned language-neutral process boundary before any remote/non-Python runner. It does not justify current runner breadth.

## Current critical path

One coherent Builder slice at a time:

1. **#56 canonical JSON completion** — kernel/session -> HTTP request/idempotency -> durable parameters/grants -> remaining core serializers/goldens.
2. **#22 residual architecture reconciliation** — duplicate exact edges, operator-aware target-port cardinality and concrete secret-bearing producers.
3. **#58 deterministic license/build-tool surface** — then exact inventory/legal review only where real evidence exists.
4. **#70/#72/#71/#73 public contributor/docs/release surface**, with #45 gated on a verified private reporting route.
5. **#50 decision record**, followed by compatible pure-core work only if justified.
6. **#57 qualification** only after an explicit policy change restoring verification.

## Architecture and scope guardrails

Canonical contracts stay capability-driven and vendor-neutral. Static bearer auth remains the v0.1 mechanism; typed scopes are required, enterprise auth is not. Evidence identity is storage-neutral and public payloads exclude backend locators. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. Do not add OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry or OpenLineage unless scope explicitly changes.

Existing implementation constraints remain: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing; fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% when coverage execution is restored.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, merge decisions are based on current-main freshness plus complete static diff/code review. Do not use GitHub Actions or automated tests, and do not claim runtime qualification that was not executed.
