# Ronin v0.1 construction plan

_Last synchronized: 2026-09-10 after disabling GitHub Actions and switching autonomous work to code-only validation. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

Ronin remains capability-ordered rather than calendar-ordered. Each autonomous run selects at most one coherent implementation slice and revalidates against current `main`, open Builder work, canonical handoffs, and frozen v0.1 scope.

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` are one canonical planning pair. Whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially, both files must be updated from the same observed repository state in one coherent planning slice.

## Current validation mode

GitHub Actions CI and qualification workflows are intentionally disabled because Actions credits are unavailable. The previous workflow definitions are retained under `.github/workflows-disabled/` for future restoration.

Until the maintainer explicitly changes this mode:

- do not trigger, wait for, rerun, or require GitHub Actions;
- do not run automated tests in autonomous cycles;
- perform only static code inspection, dependency/contract tracing, schema/API consistency review, and code-level checks;
- preserve existing security, durability, performance, architecture, coverage, and acceptance constraints in implementation;
- never claim new CI/test/acceptance evidence when none was executed.

The last automated baseline before disabling CI was 13/15 frozen acceptance with exact gaps `01` (Compose) and `12` (public evidence). New code-only work does not automatically change that qualified baseline.

## Current position on 2026-09-10

The MVP-critical durable local execution and operator spine is substantially implemented:

- pure Job -> Run -> Attempt lifecycle and storage-neutral contracts;
- in-memory and SQLite `JobStore` adapters;
- bounded async store/artifact composition;
- immutable per-cell execution/resume identity and artifact verification;
- sequential checkpoint-before-next-cell execution;
- Docker worker execution, crash/reclaim/replacement Attempt semantics and exact valid-cell reuse;
- lease fencing, heartbeat ownership and cancellation behavior;
- authenticated HTTP submit/list/status/events/cancel with bounded keyset pagination and Run-global event projection;
- version-controlled OpenAPI 3.1 and `pyronin` support for the implemented public job-control boundary;
- supported CLI `doctor`, `validate`, `plan`, `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel`;
- prompt in-flight cancellation and container cleanup;
- SQLite public-adapter collapse/internal lifecycle helper cleanup.

B1 / #48 canonical planning synchronization is complete and no longer on the selectable path.

PR #159 remains closed without merge; it is not landed behavior and does not block #53.

## Phase A — completed foundation

**Status: complete.** Deterministic core/project/runtime/notebook/kernel contracts, architecture boundaries, durable lifecycle, storage adapters, execution evidence and local Docker foundations are present. Do not reselect absent a real regression.

## Phase B — durable worker execution and resume

**Status: complete for the current MVP execution spine.** Resume remains based on immutable identity plus artifact verification. Replacement Attempts stay in the same logical Run and must preserve `attempt_id` provenance for reused cells.

## Phase C — bounded HTTP control plane and SDK contract

**Status: substantially implemented.** Remaining ordered implementation work:

1. **#52 typed scoped grants** before authorization behavior expands or hardens accidental semantics;
2. **#53 public portable evidence** across HTTP/OpenAPI/CLI/SDK, with storage locators kept private;
3. **#54 compatibility/evolution completion** after #52/#53 semantics settle.

HTTP/server implementation types must never become canonical domain/storage contracts. Do not introduce a worker -> server dependency inversion.

## Phase D — operator CLI and Git revision identity

**Status: D1 complete except `ronin evidence`.** The evidence command belongs with #53.

#123 remains a separate bounded correctness issue for executable-bit handling in untracked dirty identity.

## Phase E — production image, Compose and zero-to-demo quickstart

**Status: not implemented.** Frozen step 01 remains an implementation gap.

The supported topology must preserve:

- one production OCI image;
- durable local SQLite data volume;
- server health dependency;
- no unnecessary Docker authority in the control plane;
- worker sibling-container launch capability only where required;
- read-only workspace identity assumptions;
- non-root operation where practical;
- crash-acceptance worker `restart: "no"`;
- <60 s health target and <10 min zero-to-demo target.

## Phase F — acceptance completion

**Last automated baseline: 13/15.** Exact historical gaps are `01` and `12`.

Under code-only validation mode:

- implement #53 so step 12 is functionally present, but do not call it qualified 14/15 until automated validation is restored;
- implement production image/Compose so step 01 is functionally present, but do not call it qualified 15/15 until automated validation is restored;
- preserve the semantics of all thirteen already-qualified steps in code.

## Phase G — non-functional and release work

Implementation/policy work still open includes:

- #162 remote bearer HTTPS-by-default;
- #123 untracked executable-bit Git identity;
- #95 installed `pyronin` artifact qualification logic;
- #60 immutable Docker bootstrap identity;
- #58 exact transitive license/NOTICE policy;
- #102 release-tool coverage configuration for when tests are restored;
- #63 `main`/release-ref protection before release;
- #45 security-reporting policy after the private channel decision.

Evidence-only handoffs #166/#167/#163 are deferred while CI/tests are disabled. They remain valid records but no longer block implementation ordering.

Existing implementation constraints remain unchanged: POST p95 <100 ms, GET p95 <30 ms, SQLite WAL + `synchronous=FULL`, fencing, fail-closed VCS capture, T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% when coverage execution is restored.

## Phase H — release candidate and v0.1.0

**Status: not started.** Do not publish `v0.1.0` merely because code implementation reaches feature completeness. Automated qualification, exact installed-artifact checks, immutable image identity, security/license/process blockers, version synchronization and ref protections must be restored/satisfied before release publication.

## Current critical path

One coherent Builder slice at a time:

1. **#52 typed scoped grants** — versioned, language-neutral, vendor-neutral, deterministic deny-by-default grant/requirement model and migration path; no OIDC/RBAC/OPA/provider IAM in core.
2. **#53 public portable evidence** — bounded authenticated HTTP/OpenAPI/CLI/SDK representation with locator privacy and durable availability semantics.
3. **#54 compatibility/evolution completion** — normalize errors and compatibility policy after #52/#53 settle.
4. **Production image + Compose** — implement frozen step 01 topology.
5. **#57 code-complete frozen journey** — keep open until all fifteen capabilities exist in supported code paths; qualification remains a separate deferred concern while CI/tests are off.
6. **Release blockers/publication preparation** — #58/#95/#63/#45 and other release-critical items.

Deferred evidence track while code-only mode is active:

- **#166/#167/#163 scheduled/manual full-clean proof.** Do not spend Builder iterations attempting to satisfy these until the maintainer restores automated qualification.

## Architecture and scope guardrails

- Canonical domain remains capability-driven and vendor-neutral.
- Static bearer auth remains the v0.1 mechanism; typed scopes are required, enterprise auth is not.
- Do not add OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry or OpenLineage unless scope explicitly changes.
- No generic weakening of security, durability, performance, architecture, or acceptance semantics merely because tests are disabled.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, merge decisions are based on current-main freshness plus complete static diff/code review. Do not use GitHub Actions or automated tests, and do not claim runtime qualification that was not executed.
