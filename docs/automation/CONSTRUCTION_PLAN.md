# Ronin v0.1 construction plan

_Last synchronized: 2026-09-12 from base `ce830f966164d884f8b830a60be83b305f32b6e9` after source-hygiene work through PR #229. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

Ronin remains capability-ordered rather than calendar-ordered. Each autonomous run selects at most one coherent implementation slice and revalidates against current `main`, open Builder work, canonical handoffs, and frozen v0.1 scope.

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` are one canonical planning pair. Whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially, both files must be updated from the same observed repository state.

## Current validation mode

GitHub Actions and automated tests remain intentionally disabled by maintainer policy. Previous workflow definitions remain under `.github/workflows-disabled/`. Autonomous work performs static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning only. Security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints, but no new CI/test/acceptance evidence may be claimed.

The last authoritative automated acceptance baseline remains **13/15**, with historical gaps `01` and `12`. Product code for both capabilities now exists; code-only implementation does not automatically change the qualified result.

## Current position

The MVP durable local execution spine is implemented: Job -> Run -> Attempt lifecycle, SQLite/in-memory storage, bounded async composition, immutable resume identity, Docker worker execution/recovery, fencing/cancellation, authenticated HTTP job control, OpenAPI, `pyronin`, operator CLI, typed scoped grants, public portable evidence, strict-alpha public compatibility, project-scoped HTTP authorization, production image/Compose, explicit bearer transport/bind policy, readiness, Git dirty identity, observed cgroup CPU/memory evidence and artifact-qualification mechanics.

Canonical JSON v1 implementation is complete in scope. #56 is closed. The shared canonical codec now covers HTTP request/idempotency identity, durable `Job.parameters_json`, grants and authorization evidence, operator/diagnostic catalogs, project manifests, notebooks, IR and kernel event/authorization payloads. Boundary goldens are published and valid v1 identity bytes remain unchanged.

#200 duplicate-edge and target-port-cardinality implementation is complete with stable `RONIN-OP-008` through `RONIN-OP-010` diagnostics.

#22 has no remaining concrete secret-producing source gap identified by current inspection. Do not reopen secret hardening without a specific current producer surface.

The old storage compatibility reexports `evidence_sqlite.py` and `evidence_memory.py` were removed by #211 after current-tree consumer checks found no callers.

## Phase A — foundation

**Complete.** Deterministic domain/runtime/notebook/kernel contracts and architecture boundaries are present.

## Phase B — durable worker execution and resume

**Complete for the MVP spine.** Replacement Attempts remain in the same logical Run and preserve exact cell-reuse plus `attempt_id` provenance.

## Phase C — HTTP/API/SDK contract

**Functionally complete in code; automated qualification deferred.** Authenticated job control, typed project/action grants, canonical request identity, evidence, pagination/cursors, OpenAPI, `pyronin`, compatibility rules and secure bearer transport are implemented.

## Phase D — operator CLI and Git identity

**Functionally complete in code under current policy.** Installed command routing, canonical parameter handling and Git identity hardening are present; automated regression proof remains deferred.

## Phase E — production image, Compose and zero-to-demo

**Functionally complete in code; automated qualification deferred.**

The repository contains one production Ronin image and supported `compose.yaml` topology with durable local SQLite/artifact/evidence storage, explicit server health dependency, host loopback publication, worker-only Docker socket authority, immutable local image-ID resolution, read-only checkout access, narrowly scoped Git safe-directory configuration, non-root product execution, crash-path worker `restart: "no"`, and a no-Docker-authority CLI helper.

Compose uses `RONIN_BIND_POLICY=container-internal` for private bridge communication. This is an explicit topology declaration, not encryption and not a generic remote-HTTP permission. Supported remote authenticated access terminates HTTPS externally.

The <60 s healthy and <10 min zero-to-demo budgets remain implementation targets, not newly measured evidence while tests/CI are disabled.

## Phase F — architecture and canonical hardening

### F1 — storage evidence adapter collapse

**Complete in code.** #197 restored the canonical storage adapter invariant and #211 then removed the now-unused compatibility reexport modules. Lease fencing, paging, schema-v3 availability semantics, WAL/`synchronous=FULL`, thread-local connection reuse and the max-100 evidence-ref bound remain unchanged.

### F2 — #56 canonical JSON

**Complete in scope.**

- HTTP inbound JSON uses the canonical decoder and request/idempotency identity uses canonical bytes;
- `Job.parameters_json` validation uses the canonical boundary;
- Requirement, GrantSet and AuthorizationEvidence canonical serialization use the shared codec;
- operator and diagnostic catalog serializers use the shared codec;
- project, notebook, IR, kernel event, grant-set and HTTP identity boundary goldens are present;
- response/presentation JSON remains presentation JSON rather than being migrated for aesthetics;
- valid v1 bytes, including the documented finite-float and `-0.0` compatibility boundary, remain preserved.

### F3 — #22 / #200 residual architecture reconciliation

**Complete for identified source defects.** Exact duplicate edges and operator-aware target-port cardinality are enforced. Current secret-bearing producer inspection has not identified an additional concrete source gap.

### F4 — source hygiene (I0)

**Targeted historical lint findings complete; global proof still unavailable.**

Landed source-hygiene corrections include dead reexport removal; `UP022`, `SIM102`, `RET501`, `PTH201`, `S104`, both `S603`, both `PT011`, `PT018`, `PT006`; and the reproduced `E501` findings across production, tooling and the mechanically permitted test files.

PR #229 identifies the historical `SIM102` exactly in `tools/license_qualification.py::locked_graph`: the nested blank/comment handling was flattened while preserving the same fail-closed interruption error and skip behavior. All 38 historical Ruff lint findings from the 2026-09-12 audit now have traceable resolutions.

The active execution environment cannot obtain a current checkout from GitHub and does not have the pinned Ruff 0.16.6 binary locally available, so a full current `ruff check python tests tools packages docker` and `ruff format --check python tests tools packages docker` have not been demonstrated. The historical audit reported 15 files needing formatter changes but did not preserve their filenames. Do not claim I0 globally clean until equivalent exact evidence exists.

## Phase G — security, supply-chain and release implementation

### #58 exact transitive license/NOTICE

Deterministic source implementation is present. `tools/dependency_surfaces.py` models build-system and release/qualification tool dependencies, and license qualification fails closed on unsupported/unpinned/conflicting dependency forms.

Exact `third_party/licenses-v1.json`, per-package policy decisions, NOTICE/attribution conclusions and approval rationales require a real exact environment plus human/legal review. Do not fabricate them.

### #95 exact artifact identity

Implementation mechanics already exist. The remaining release claim requires execution against a real candidate and binding that exact artifact identity to #58 evidence.

### Contributor and governance surface

PR #204 landed CONTRIBUTING, docs landing, changelog, release runbook and issue/PR templates. #71, #72 and #73 are closed.

#70 remains human-blocked only where a real owned Code-of-Conduct reporting route or genuinely suitable starter tasks are required. Do not invent either.

#45 remains blocked until the maintainer selects and verifies a real private vulnerability-reporting channel. Do not add `SECURITY.md` before that route exists.

## Phase H — decisions and release gates

#50 remains `NEEDS_DECISION`. Capability namespaces/value families, ambiguity semantics, unknown-version behavior, selection evidence and dispatch-time binding require a current architecture decision before implementation. Do not add a second v0.1 runtime merely to create implementation work.

#63 remains repository-administration work: branch/tag protection and physical merged-ref cleanup are not source implementation. The active connector does not expose safe branch-ref deletion; record that limitation rather than claiming cleanup.

#57 remains a qualification gate, not a feature slice. Revisit strict 15/15 only if the maintainer explicitly restores automated verification.

## Deferred verification/evidence track

While code-only mode is active, do not select these as implementation blockers: tests, coverage, mutation, stale acceptance skips, benchmarks, CI/workflows/GitHub Actions, provenance/secret scanning as CI, repository-reference administration, or candidate/legal evidence that requires an unavailable exact environment.

This includes #47, #57, #60 where its value is workflow qualification, #63 admin, #95 candidate execution/publishing evidence, #102, #115 real-Docker proof, #123 regression tests, #163/#166/#167, #199, #201, #202, and release/provenance workflow items #43/#44/#94/#96. #59 and #62 remain post-v0.1.

## Current critical path

One coherent Builder slice at a time:

1. **I0 source hygiene:** obtain executable current-tree evidence using pinned Ruff 0.16.6; fix only reproduced findings and do not claim global clean status without that evidence.
2. **Planning consistency:** keep `BACKLOG.md` and this construction plan synchronized with observed `main`.
3. **#58 / #95 exact evidence:** proceed only with a real exact environment and required human/legal decisions; source implementation is already present.
4. **#70 / #45 reporting channels:** proceed only after real owned routes are available.
5. **#50 architecture decision:** implement only after a current ADR/decision exists.
6. **#57 qualification:** revisit only after an explicit policy change restoring verification.

If current repository truth shows no additional in-scope source implementation beyond I0 diagnostics that cannot be reproduced, the remaining work is evidence, tests/CI, administration or human decision work; do not manufacture another product slice.

## Architecture and scope guardrails

Canonical contracts stay capability-driven and vendor-neutral. Static bearer auth remains the v0.1 mechanism; typed scopes are required, enterprise auth is not. Evidence identity is storage-neutral and public payloads exclude backend locators. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. Do not add OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry or OpenLineage unless scope explicitly changes.

Existing implementation constraints remain: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing; fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% when coverage execution is restored.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, merge decisions are based on current-main freshness plus complete static diff/code review. Do not use GitHub Actions or automated tests, and do not claim runtime qualification that was not executed.
