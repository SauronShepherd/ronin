# Ronin v0.1 construction plan

_Last synchronized: 2026-09-12 from base `0ab5f116ecda79a9590dff4244f6b6c55443b82d` after the current source-hygiene implementation slices. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

Ronin remains capability-ordered rather than calendar-ordered. Each autonomous run selects at most one coherent implementation slice and revalidates against current `main`, open Builder work, canonical handoffs, and frozen v0.1 scope.

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` are one canonical planning pair. Whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially, both files must be updated from the same observed repository state.

## Current validation mode

GitHub Actions and automated tests are intentionally disabled by maintainer policy. Previous workflow definitions remain under `.github/workflows-disabled/`. Autonomous work performs static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning only. Security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints, but no new CI/test/acceptance evidence may be claimed.

A complementary local audit dated 2026-09-11 reported six failing tests, format/lint drift, low indirect coverage in `grants.py`, stale acceptance skips, orphaned qualification tooling and a concrete storage-layer regression. Those execution-derived observations remain useful diagnostic evidence, but this plan does not adopt that audit's CI/test phases as current requirements because the maintainer has explicitly kept Ronin in code-only mode. The storage regression was independently confirmed in source and resolved by #197.

The last authoritative automated acceptance baseline remains **13/15**, with historical gaps `01` and `12`. Product code for both capabilities exists; code-only implementation does not automatically change the qualified result.

## Current position

The MVP durable local execution spine is implemented: Job -> Run -> Attempt lifecycle, SQLite/in-memory storage, bounded async composition, immutable resume identity, Docker worker execution/recovery, fencing/cancellation, authenticated HTTP job control, OpenAPI, `pyronin`, operator CLI, typed scoped grants, public portable evidence, strict-alpha public compatibility, project-scoped HTTP authorization, production image/Compose, explicit bearer transport/bind policy, real readiness, corrected Git dirty identity, observed cgroup CPU/memory evidence, exact-artifact qualification tooling and the canonical JSON v1 foundation.

Canonical JSON v1 implementation for the MVP is source-complete. HTTP request/idempotency parsing and identity, durable job parameters, grants, operator/diagnostic catalogs, kernel/session evidence, the canonical boundary registry/goldens and the checker target all use the shared boundary. #56 is closed; valid v1 bytes remain frozen compatibility input.

Graph hardening for #200 is implemented: exact duplicate edges and operator-aware target-port cardinality fail closed with stable `RONIN-OP-008..010` diagnostics. The #22 residual audit has not produced another concrete secret-bearing source that justifies speculative hardening.

The deterministic #58 source surface is implemented, including fail-closed build-system/release-tool dependency modeling. Exact inventory, legal review, NOTICE/attribution decisions and candidate evidence remain dependent on a real exact environment plus human review.

The public contributor/docs/release implementation is substantially complete: CONTRIBUTING, docs landing/first-run/troubleshooting, issue/PR templates, release runbook and changelog have landed; #71, #72 and #73 are closed. #70 retains only human/project remainder where a real reporting route or genuinely suitable starter work exists.

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

**Complete in code.**

PR #197 restored the #164 single-public-adapter invariant. Later source-hygiene work removed the dead `evidence_sqlite.py` and `evidence_memory.py` compatibility reexports after confirming no consumers. The canonical fenced SQLite and paged in-memory adapters remain the only public storage implementations, preserving lease fencing, paging, schema-v3 availability semantics, WAL/`synchronous=FULL`, thread-local connection reuse and the max-100 evidence-ref bound.

### F2 — #56 canonical JSON

**Source-complete; automated qualification deferred.**

- HTTP request bodies parse through the canonical decoder, rejecting duplicate members and non-finite values before identity construction.
- HTTP request/idempotency identity bytes use the shared canonical encoder; response `_write_json` remains presentation JSON by design.
- `Job.parameters_json` validation uses the canonical decoder.
- grants and authorization evidence use canonical JSON serialization.
- operator and diagnostic catalog serializers use the shared boundary.
- kernel authorization/event evidence and durable ledger parsing use the same codec.
- the canonical registry, complete boundary goldens and checker target are present.
- valid v1 payload bytes, including the documented finite-float and `-0.0` compatibility boundary, remain unchanged.

#56 is closed. Do not reopen it for cosmetic JSON unification.

### F3 — graph/cardinality and #22 residual reconciliation

**Source-complete for reproduced defects.**

Exact duplicate graph edges are rejected and operator-aware target-port cardinality is validated with stable `RONIN-OP-008..010` diagnostics. The residual #22 audit found no additional concrete secret-producing surface that warrants speculative hardening. Future changes require new source evidence, not umbrella-driven filler.

### F4 — source hygiene

The individually reproduced I0 lint findings have source fixes or have been revalidated as current no-ops: E501, I001, S603, S104, PT011, PT018, PT006, UP022, SIM102, RET501 and PTH201. Dead storage compatibility reexports are removed.

The global I0 DoD is **not yet demonstrated**. The original audit reported 15 files requiring `ruff format`, but did not enumerate them. The current execution environment cannot obtain a GitHub checkout, so neither `ruff format --check` nor repository-wide `ruff check` has been executed against current `main`. Do not manufacture formatter edits or claim a clean global pass without executable current-tree evidence.

## Phase G — security, supply-chain and release implementation

### #58 exact transitive license/NOTICE

**Deterministic source mechanics complete; evidence/human review outstanding.**

The implementation models the resolved dependency graph plus explicit PEP 517 build-system and release-tool surfaces fail closed. Exact `third_party/licenses-v1.json`, package review policy, NOTICE/attribution conclusions and approval rationales require a real exact environment plus human/legal review. Do not fabricate them.

### #95 exact artifact identity

Implementation mechanics already exist. Do not reimplement them. The remaining release claim requires execution against a real candidate and binding that artifact identity to #58 evidence.

### Human/project surface

The contributor/docs/release code and content surfaces have landed. Remaining legitimate work is human/project dependent:

- #70: use only a real owned conduct-reporting route; add starter issues only when genuinely suitable work exists;
- #45: publish `SECURITY.md` only after the maintainer selects and verifies a real private reporting channel.

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

One coherent Builder slice at a time, with no filler work:

1. **I0 repository-wide Ruff proof** only when an executable current checkout is available; address only real residual findings.
2. **#58/#95 exact evidence** in a real exact environment with human/legal review.
3. **#70 human/project remainder** only where a verified reporting route or genuinely suitable starter task exists.
4. **#45 private reporting-channel decision** before `SECURITY.md`.
5. **#50 architecture decision**, followed by compatible pure-core work only if the recorded ADR requires it.
6. **#57 qualification** only after an explicit policy change restoring verification.
7. **Repository administration** such as branch/ref protection and physical cleanup where connector/admin capabilities are required.

No further #56, #200, contributor-docs, release-docs or deterministic #58 source expansion should be selected merely because historical planning text once listed it.

## Architecture and scope guardrails

Canonical contracts stay capability-driven and vendor-neutral. Static bearer auth remains the v0.1 mechanism; typed scopes are required, enterprise auth is not. Evidence identity is storage-neutral and public payloads exclude backend locators. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. Do not add OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry or OpenLineage unless scope explicitly changes.

Existing implementation constraints remain: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing; fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% when coverage execution is restored.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, merge decisions are based on current-main freshness plus complete static diff/code review. Do not use GitHub Actions or automated tests, and do not claim runtime qualification that was not executed.
