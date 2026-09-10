# Ronin v0.1 construction plan

_Last synchronized: 2026-09-10 after #57 frozen-journey reconciliation under code-only validation. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

Ronin remains capability-ordered rather than calendar-ordered. Each autonomous run selects at most one coherent implementation slice and revalidates against current `main`, open Builder work, canonical handoffs, and frozen v0.1 scope.

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` are one canonical planning pair. Whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially, both files must be updated from the same observed repository state.

## Current validation mode

GitHub Actions and automated tests are intentionally disabled by maintainer policy. Previous workflow definitions remain under `.github/workflows-disabled/`. Autonomous work performs static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning only. Security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints, but no new CI/test/acceptance evidence may be claimed.

The last automated baseline remains **13/15**, with historical gaps `01` and `12`. Code-only implementation does not automatically change that qualified result.

## Current position

The MVP durable local execution spine is implemented: Job -> Run -> Attempt lifecycle, SQLite/in-memory storage, bounded async composition, immutable resume identity, Docker worker execution/recovery, fencing/cancellation, authenticated HTTP job control, OpenAPI, `pyronin`, operator CLI, typed scoped grants, public portable evidence, strict-alpha public compatibility, project-scoped HTTP authorization, and the supported production image/Compose topology for frozen step 01.

#52, #53, #54, and #161 are functionally complete under code-only validation. Automated drift/conformance, authorization and Compose qualification remain deferred, so the authoritative acceptance baseline remains 13/15.

#57 has been reconciled as the frozen-journey umbrella: product code for all historical missing surfaces is present, but the issue remains open/BLOCKED until strict automated qualification can prove the full journey on an exact SHA. It must not be used to justify duplicate feature implementation while the current no-tests/no-CI policy remains active.

## Phase A — foundation

**Complete.** Deterministic domain/runtime/notebook/kernel contracts and architecture boundaries are present.

## Phase B — durable worker execution and resume

**Complete for the MVP spine.** Replacement Attempts remain in the same logical Run and preserve exact cell-reuse plus `attempt_id` provenance.

## Phase C — HTTP/API/SDK contract

**Status: functionally complete in code; automated qualification deferred.**

Completed:

- #52 provider-neutral typed scoped grants, bearer-scope mapping and kernel pre-effect authorization decisions;
- #53 durable/public portable evidence with `available`, `missing`, `tombstoned`, `unavailable`, locator privacy, authenticated HTTP, OpenAPI, CLI and `pyronin` surfaces;
- #54 strict-alpha API/SDK compatibility: closed response objects and semantic enums, open error-code vocabulary inside a normalized closed envelope, opaque bounded cursors, canonical Instant validation, and documented alpha/beta/stable evolution rules;
- #161 project-scoped HTTP authorization using the #52 grant model, including list filtering, direct Job-ID visibility checks, evidence authorization, pre-effect submit/cancel checks, and removal of the token-only server-constructor bypass.

HTTP/server types remain adapters, never canonical lifecycle/storage models. No worker -> server dependency inversion is allowed.

## Phase D — operator CLI and Git identity

**D1 functionally complete in code**, including installed `ronin evidence`. #123 remains separate correctness work for executable-bit identity of untracked files.

## Phase E — production image, Compose and zero-to-demo

**Functionally complete in code; automated qualification deferred.**

The repository now contains one production Ronin image and supported `compose.yaml` topology with:

- durable local SQLite/artifact/evidence storage on one named volume;
- explicit server health dependency without a new public `/v1` route;
- HTTP published only on host loopback by default;
- Docker socket authority only on the worker;
- immutable local image-ID resolution before worker cell execution;
- read-only checkout access with narrowly scoped Git safe-directory configuration;
- product processes dropped to UID/GID `65532:65532` after bounded permission setup;
- crash-path worker `restart: "no"`;
- a no-Docker-authority CLI helper profile and documented quickstart.

The <60 s healthy and <10 min zero-to-demo budgets remain implementation targets, not newly measured evidence while tests/CI are disabled.

## Phase F — acceptance completion

**Last automated baseline: 13/15.** Historical gaps remain `01` and `12` until qualification is restored.

Code contains both step-01 Compose and step-12 public evidence capabilities plus the #54 compatibility and #161 scoped-authorization contracts. `tests/e2e/test_v01_journey.py` still carries stale historical skip markers for 01/12; under maintainer policy those tests are not being edited or executed in code-only slices. Do not call the project qualified 14/15 or 15/15 while automated qualification is disabled.

#57 is therefore a blocked qualification gate, not the next implementation slice.

## Phase G — security, non-functional and release work

The next bounded implementation slice is **#162 remote bearer transport confidentiality**. Authenticated clients must reject remote plaintext HTTP by default, loopback HTTP must remain supported, and `ronin serve` must require an explicit insecure-development override before plaintext non-loopback binding. The built-in server must not claim TLS support; supported secure remote access relies on an external TLS terminator/reverse proxy. The existing Compose topology must remain usable by explicitly opting its private bridge bind into the local-container insecure mode while retaining host loopback publication.

After #162, prioritize **#123 untracked executable-bit identity**. Then proceed through actionable release preparation such as #58/#95/#73 under code-only policy. #63 remains blocked on repository administration/release timing; #45 remains blocked on the maintainer selecting and verifying a private reporting channel. Evidence-only #166/#167/#163 remain deferred while CI/tests are disabled.

Existing implementation constraints remain: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing; fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% when coverage execution is restored.

## Phase H — release candidate and v0.1.0

**Not started.** Feature implementation alone is not release qualification. Automated acceptance, exact installed-artifact checks, immutable image identity, security/license/process blockers, version synchronization and ref protection must be satisfied before publication.

## Current critical path

One coherent Builder slice at a time:

1. **#162 remote bearer transport confidentiality** — secure defaults for authenticated HTTP and explicit non-loopback plaintext opt-in, preserving Compose local operation.
2. **#123 untracked executable-bit identity** — close the remaining known local Git dirty-identity correctness gap.
3. **Release blockers/publication preparation** — actionable portions of #58/#95/#73 and related release work; do not select human/admin/evidence-only blockers as implementation slices.
4. **#57 frozen-journey qualification** — revisit only after the maintainer explicitly restores automated tests/qualification; then remove stale acceptance skips and obtain strict exact-SHA 15/15 evidence without weakening the frozen contract.

## Architecture and scope guardrails

Canonical contracts stay capability-driven and vendor-neutral. Static bearer auth remains the v0.1 mechanism; typed scopes are required, enterprise auth is not. Evidence identity is storage-neutral and public payloads exclude backend locators. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. Do not add OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry or OpenLineage unless scope explicitly changes.

The built-in HTTP server remains a local/plaintext implementation boundary. Remote authenticated use is HTTPS-by-default through an external TLS terminator; no server framework or TLS stack becomes canonical merely to satisfy transport policy.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, merge decisions are based on current-main freshness plus complete static diff/code review. Do not use GitHub Actions or automated tests, and do not claim runtime qualification that was not executed.
