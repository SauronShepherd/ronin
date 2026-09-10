# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

_Last synchronized: 2026-09-10 for the #161 scoped HTTP authorization implementation under code-only validation mode._

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` must be updated together from the same observed repository state whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially. If the two files disagree, autonomous product selection stops until the drift is reconciled.

## Current validation mode

GitHub Actions are intentionally disabled to avoid consuming Actions credits. Previous workflow definitions are retained under `.github/workflows-disabled/` only as historical/restart material.

Until the maintainer explicitly changes this policy, autonomous Builder work does not wait for, trigger, rerun, or require CI; does not execute automated tests; validates through static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning; and does not claim green CI or passing tests for new changes. Existing security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints.

Evidence-only handoffs #166/#167/#163 remain open/deferred and do not block implementation while this mode is active.

## Current v0.1 truth

The last automated qualification before CI was disabled remains **13/15 live**, with exact historical gaps `01` (production image + supported Compose topology) and `12` (public portable evidence retrieval). Code-only work does not alter that qualified baseline automatically.

Supported code now contains the durable local execution spine, authenticated and project-scoped HTTP job control, OpenAPI 3.1, `pyronin`, operator CLI, typed scoped grants (#52), public portable evidence (#53), strict-alpha API/SDK compatibility (#54), and route-level typed grant enforcement (#161). Step 12 is functionally present but **not yet re-qualified** under the disabled-test policy.

B1 / #48 is complete. #52, #53, #54, and #161 are functionally complete in code-only mode. Automated drift/conformance qualification remains deferred. PR #159 remains closed without merge and is only historical reuse evidence.

## #161 scoped HTTP authorization implementation

The current slice applies the existing #52 grant model without redesigning it:

- the canonical `RoninHTTPServer` requires a non-empty `GrantSet`; the former token-only internal constructor path is removed;
- project-scoped route requirements are `list`, `read`, `events`, `evidence:read`, `cancel`, and both `submit` + `execute` for submission;
- direct Job-ID operations resolve the Job's `project_id` before authorization and return the same `404 job_not_found` result for absent and cross-project Jobs;
- explicit list project filters fail closed when unauthorized; unfiltered pages contain only Jobs visible to the bearer grant while preserving the storage cursor;
- authorization is checked before cancellation/submission side effects;
- OpenAPI publishes the route requirements using `x-ronin-required-project-actions` and keeps HTTP status authoritative;
- CLI and `pyronin` continue to send only the bearer credential and cannot widen authority with client-selected scopes.

No automated authorization tests or CI qualification were executed under the current maintainer policy.

## Current critical path

Select one coherent slice at a time.

1. **Production image + Compose — acceptance step 01 implementation.** Preserve durable SQLite, server health dependency, bounded Docker authority, sibling-container execution, non-root operation where practical, and explicit crash-worker `restart: "no"`.
2. **#57 — frozen journey completion in code.** Keep open until all fifteen capabilities are implemented; automated 15/15 release qualification remains separately deferred while CI/tests are disabled.
3. **Release blockers/publication.** Address #58, #95, #63, #45 and other release-critical work before immutable publication.

Security/correctness slices such as #162 and #123 remain important and may be selected when they do not displace an earlier dependency-critical implementation slice.

## D1 operator status

D1 is functionally complete in code: `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, `cancel`, and installed `ronin evidence` are present. Automated qualification remains paused.

## Worker execution invariants

Every remaining worker/runtime slice must preserve checkpoint-before-next-cell persistence, lease fencing, fail-closed heartbeat ownership, prompt cancellation, immutable resume identity plus verified artifact availability/digest, same-Run replacement Attempts, exact reused-cell and `attempt_id` provenance, bounded async store/artifact facades, and production lease TTL semantics.

## Public-boundary and architecture invariants

Canonical contracts remain capability-driven and vendor-neutral. Do not introduce worker -> server dependency inversion. Physical evidence/storage locators are not canonical public identity. Static bearer auth remains the v0.1 mechanism; typed least-privilege scopes are required. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. No OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry, or OpenLineage unless scope is explicitly revised.

## Quality and release invariants

These remain implementation constraints while automated enforcement is paused: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing and fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% once coverage execution is restored; and exact installed-artifact plus immutable Docker-digest qualification before release.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, implementation may merge after static review of the complete diff against current `main`. Do not run or wait for GitHub Actions/tests, and do not claim runtime/qualification evidence that was not actually produced.
