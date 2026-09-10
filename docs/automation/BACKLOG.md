# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

_Last synchronized: 2026-09-10 for the #52 typed scoped grants implementation under code-only validation mode._

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` must be updated together from the same observed repository state whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially. If the two files disagree, autonomous product selection stops until the drift is reconciled.

## Current validation mode

GitHub Actions are intentionally disabled to avoid consuming Actions credits. Previous workflow definitions are retained under `.github/workflows-disabled/` only as historical/restart material.

Until the maintainer explicitly changes this policy, autonomous Builder work:

- does not wait for, trigger, rerun, or require CI;
- does not execute automated tests;
- validates by static code inspection, contract/dependency tracing, schema/API consistency review, and code-level reasoning;
- does not claim green CI or passing tests for new changes;
- preserves the existing security, durability, performance, architecture, coverage, and acceptance requirements in implementation even though automated qualification is paused.

Evidence-only handoffs that require scheduled/manual GitHub Actions remain open/deferred and do not block implementation while this mode is active.

## Current v0.1 truth

Ronin already has the durable local execution spine, real-Docker worker execution/recovery, authenticated HTTP control-plane paths, OpenAPI 3.1, the `pyronin` SDK, and the supported operator CLI commands `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel`.

The last automated qualification before CI was disabled established **13/15 live** frozen acceptance with exactly two intentional gaps:

- `01` — production image + supported Compose topology is not implemented yet;
- `12` — public portable evidence retrieval is not implemented yet.

That historical result remains the last automated acceptance baseline. Do not treat later code-only changes as automatically qualified.

B1 / #48 canonical planning synchronization is complete and no longer selectable.

## Completed foundation carried into v0.1

Do not reselect already-landed foundation, durable lifecycle, pagination/event semantics, bounded composition, operator CLI, cancellation, or SQLite-collapse work unless static inspection finds a real regression or changed contract.

Completed capabilities include:

- pure Job -> Run -> Attempt lifecycle and storage-neutral `JobStore` contracts;
- in-memory and SQLite adapters with fencing semantics;
- bounded async store/artifact composition;
- per-cell immutable resume identity and artifact verification;
- sequential checkpoint-before-next-cell execution;
- production-lease crash/reclaim/replacement Attempt behavior with exact cell reuse;
- fail-closed lease ownership/cancellation semantics;
- real-Docker local worker execution path;
- authenticated submit/list/status/events/cancel HTTP paths with bounded keyset pagination;
- OpenAPI 3.1 and `pyronin` support for the implemented public job-control surface;
- CLI `doctor`, `validate`, `plan`, `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel`;
- prompt in-flight cancellation/container cleanup;
- SQLite public-adapter collapse/internal lifecycle helper cleanup.

PR #159 remains closed without merge. It is not landed behavior and must not block a fresh #53 implementation.

## #52 typed scoped grants

The current Builder slice implements the canonical v1 typed grant contract in `studio_core`:

- closed action vocabulary and explicit resource scopes;
- immutable versioned `Grant`, `Requirement`, `Decision`, `GrantSet`, and `AuthorizationEvidence` models;
- bounded constraints with deny-by-default handling for unsupported semantics;
- deterministic matching independent of input order, with ambiguity denied;
- no inferred project/job/run/evidence hierarchy;
- canonical bearer-scope encoding/parsing plus alpha migration from explicit legacy permission strings;
- `KernelDirective.required_grants` alongside the legacy string path, with mixed representations rejected;
- typed kernel authorization evaluated before executor side effects and successful decisions persisted as non-secret durable event evidence;
- `ronin serve` now requires a non-empty canonical `RONIN_TOKEN_SCOPES` grant set associated with the existing static bearer token;
- HTTP route-level enforcement remains intentionally deferred to #161.

Architecture and representation details are recorded in `docs/product/ADR-V01-011-TYPED-GRANTS.md` and `docs/product/AUTHORIZATION_GRANTS_V1.md`.

## Current critical path

Select one coherent slice at a time.

1. **#53 — public portable evidence + acceptance step 12 implementation.** Expose storage-neutral evidence through the supported HTTP/OpenAPI/CLI/SDK boundary and keep physical locators private. Under code-only mode, implement the contract completely but do not claim step 12 automatically qualified until automated validation is restored.
2. **#54 — remaining API/SDK compatibility rules.** Finish error/evolution/drift compatibility after #52/#53 semantics settle.
3. **#161 — enforce scoped HTTP authorization.** Consume the now-canonical #52 typed grants across read/list/events/submit/cancel with project visibility and direct job-ID checks; do not redesign the grant model in the HTTP layer.
4. **Production image + Compose — acceptance step 01 implementation.** Build the supported topology while preserving durable SQLite, server health dependency, bounded Docker authority, sibling-container execution, non-root operation where practical, and explicit crash-worker `restart: "no"`.
5. **#57 — frozen journey completion in code.** Keep open until all fifteen required capabilities are implemented. Automated 15/15 release qualification remains separately deferred while CI/tests are disabled.
6. **Release blockers/publication.** Address implementation/policy blockers such as #58, #95, #63, #45 and related release work before any immutable publication.

Deferred while code-only mode is active:

- **#166/#167/#163** — scheduled/manual full-clean evidence. These remain valid evidence handoffs but are not implementation blockers while GitHub Actions/tests are intentionally disabled.

Security/correctness slices such as #162, #123, #95 and #60 remain important and may be selected when they do not displace an earlier dependency-critical implementation slice.

## D1 operator status

D1 is complete except `ronin evidence`. `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel` are already landed. `ronin evidence` belongs with #53 because its backing public evidence contract does not exist yet.

## Worker execution invariants

Every remaining worker/runtime slice must preserve:

- persist successful cell result/evidence before the next cell starts;
- fence every worker-originated durable write by the active Attempt lease;
- fail closed on heartbeat ownership loss;
- cancellation must not wait for all remaining cells;
- resume requires immutable cell identity plus verified artifact availability/digest;
- replacement Attempts reuse the same logical Run and must not replay valid completed cells;
- resume evidence must retain exact reused-cell identity and `attempt_id` provenance;
- blocking store/artifact operations remain behind bounded async facades;
- production lease TTL semantics are not weakened for convenience.

## Public-boundary and architecture invariants

- Canonical contracts remain capability-driven and vendor-neutral.
- Do not introduce worker -> server dependency inversion.
- Physical evidence/storage locators are not canonical public identity.
- Static bearer auth remains the v0.1 mechanism; typed least-privilege scopes are required.
- No OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry, or OpenLineage unless scope is explicitly revised.

## Quality and release invariants

These requirements remain implementation constraints even while automated enforcement is paused:

- POST p95 <100 ms and GET p95 <30 ms;
- SQLite WAL + `synchronous=FULL`;
- fencing and fail-closed VCS capture;
- T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% when test/coverage execution is eventually restored;
- publication must qualify exact installed artifacts and immutable Docker digests before release.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, implementation may merge after static review of the complete diff against current `main`. Do not run or wait for GitHub Actions/tests, and do not claim runtime/qualification evidence that was not actually produced.
