# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

_Last synchronized: 2026-09-12 from base `1734e172d3e9d3cc4b87f7587a5a1e2cb1e9172e` after SIM102 planning sync #231._

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` must be updated together from the same observed repository state whenever acceptance truth, completed capabilities, validation mode, or the critical path changes materially. If the two files disagree, autonomous product selection stops until the drift is reconciled.

## Current validation mode

GitHub Actions remain intentionally disabled. Previous workflow definitions stay under `.github/workflows-disabled/` as historical/restart material only.

Until the maintainer explicitly changes this policy, autonomous Builder work does not wait for, trigger, rerun, or require CI; does not execute automated tests; validates through static code inspection, dependency/contract tracing, schema/API consistency review, and code-level reasoning; and does not claim green CI or passing tests for new changes. Existing security, durability, performance, architecture, coverage, and acceptance requirements remain implementation constraints.

The last automated qualification before CI was disabled remains **13/15 live**. Product code for the historical step-01 and step-12 capability gaps now exists, but code-only work does not alter the qualified baseline.

## Current v0.1 truth

The durable local execution spine, authenticated/project-scoped HTTP API, OpenAPI 3.1 contract, `pyronin`, operator CLI, typed scoped grants, public portable evidence, strict-alpha API compatibility, production image/Compose path, bearer transport/bind policy, readiness, Git identity handling, cgroup observation and artifact-qualification mechanics are implemented.

Canonical JSON v1 implementation is complete in scope. #56 is closed and the shared canonical boundary now covers HTTP request/idempotency identity, durable job parameters, grants/authorization evidence, operator and diagnostic catalogs, project manifests, notebooks, IR, kernel authorization/event bytes and the published boundary goldens. Valid v1 identity bytes remain unchanged.

#200 duplicate-edge and target-port-cardinality implementation is complete with stable `RONIN-OP-008` through `RONIN-OP-010` diagnostics.

#22 has no remaining concrete secret-producing source gap identified by current inspection. Existing repository URI credential rejection, grant constraint secret rejection, reproducibility guards and operational redaction remain the supported controls. Do not invent speculative hardening work.

The dead compatibility modules `studio_storage/evidence_sqlite.py` and `studio_storage/evidence_memory.py` were removed by #211 after repository-wide consumer checks found no imports.

## Current source-hygiene status

I0 is the only remaining implementation area with unresolved proof.

Completed source-hygiene work includes:

- dead storage compatibility reexports removed;
- `UP022`, `RET501`, `PTH201`, `S104`, both `S603`, both `PT011`, `PT018`, `PT006` and the reproduced `SIM102` finding addressed without broad suppressions;
- the known historical/current `E501` findings in `studio_cli/network.py`, `studio_orchestrator/store.py`, `studio_kernel/session.py`, `studio_server/http.py`, `studio_core/grants.py`, `tools/license_qualification.py`, `tests/test_readiness.py` and `tests/test_license_qualification.py` mechanically reflowed;
- `tests/test_transport_policy.py` imports were already sorted when rechecked.

The historical `SIM102` was reproduced in `tools/license_qualification.py::locked_graph` and fixed by #229 by flattening the blank/comment continuation guard without changing parser behavior. With that fix, all 38 historical Ruff lint findings from the 2026-09-12 audit have traceable resolutions.

A global current `ruff check python tests tools packages docker` and `ruff format --check python tests tools packages docker` have **not** been demonstrated in the active execution environment because a current checkout cannot be obtained there and the pinned Ruff 0.16.6 binary is not locally available. The historical audit reported 15 files needing formatter changes but did not preserve their filenames. Do not infer a clean global result from the targeted fixes.

## License/release implementation and evidence

#58 deterministic source implementation is present: build-system and release/qualification dependency surfaces are modeled by `tools/dependency_surfaces.py`, and license qualification fails closed on unsupported/unpinned/conflicting dependency forms.

Exact package inventory, license-policy decisions, NOTICE/attribution conclusions and release-candidate evidence still require a real exact environment plus human/legal review. They must not be fabricated.

#95 artifact-qualification mechanics are implemented, but exact candidate execution/publish evidence remains a real-environment task rather than a source-code gap.

## Contributor, governance and release surfaces

PR #204 landed CONTRIBUTING, docs landing material, release runbook, changelog and issue/PR templates; #71, #72 and #73 are closed.

#70 remains human-blocked only where it requires a real owned Code-of-Conduct reporting route or genuinely suitable starter tasks. Do not publish a fake reporting address or manufacture `good first issue` work.

#45 remains blocked until the maintainer selects and verifies a real private vulnerability-reporting channel. Do not add `SECURITY.md` before that route exists.

## Decisions and administration

#50 remains `NEEDS_DECISION`. Capability namespace/value families, ambiguity semantics, unknown-version behavior, selection evidence and dispatch-time binding require a current architecture decision before implementation. Do not add a second v0.1 runtime to create work.

#63 and physical deletion/protection of merged branches/tags are repository-administration work. The current connector does not provide safe branch-ref deletion; record that limitation rather than inventing cleanup evidence.

## Current critical path

Select one coherent slice at a time:

1. **I0 source hygiene:** obtain executable evidence from the current tree with pinned Ruff 0.16.6; fix only reproduced findings and do not claim global clean status without that evidence.
2. **Planning consistency:** keep this file and `CONSTRUCTION_PLAN.md` synchronized with observed `main`.
3. **#58 / #95 exact evidence:** proceed only with a real exact environment and required human/legal decisions; source implementation is already present.
4. **#70 / #45 governance channels:** proceed only after real owned reporting routes exist.
5. **#50 architecture decision:** implementation only after a current ADR/decision exists.
6. **#57 qualification:** revisit only if the maintainer explicitly restores automated verification.

No additional product feature slice is justified merely to keep Builder active.

## Deferred / out-of-scope under the current build plan

The following do not block in-scope implementation completion: tests, coverage, mutation, skipped acceptance cases, benchmarks, CI/workflows/GitHub Actions, provenance/secret scanning as CI gates, release evidence that requires an unavailable exact environment, and repository-reference administration.

This includes #47, #57, #60 where its value is only workflow qualification, #63 admin, #95 candidate execution/publish evidence, #102, #115 real-Docker proof, #123 regression tests, #163/#166/#167, #199, #201, #202, and release/provenance workflow items #43/#44/#94/#96. #59 and #62 remain post-v0.1.

## Worker execution invariants

Every remaining worker/runtime change must preserve checkpoint-before-next-cell persistence, lease fencing, fail-closed heartbeat ownership, prompt cancellation, immutable resume identity plus verified artifact availability/digest, same-Run replacement Attempts, exact reused-cell and `attempt_id` provenance, bounded async store/artifact facades, and production lease TTL semantics.

## Public-boundary and architecture invariants

Canonical contracts remain capability-driven and vendor-neutral. Do not introduce worker -> server dependency inversion. Physical evidence/storage locators are not canonical public identity. Static bearer auth remains the v0.1 mechanism; typed least-privilege scopes are required. Public `/v1` compatibility follows `docs/product/API_COMPATIBILITY_V1.md`. No OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry, or OpenLineage unless scope is explicitly revised.

## Quality and release invariants

These remain implementation constraints while automated enforcement is paused: POST p95 <100 ms; GET p95 <30 ms; SQLite WAL + `synchronous=FULL`; fencing and fail-closed VCS capture; T1 100%, T2 90%, T3 75%, every `studio_storage` file >=80% once coverage execution is restored; exact installed-artifact plus immutable Docker-digest qualification before release.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

While code-only validation mode is active, implementation may merge after current-main freshness checks plus complete static diff/code review. Do not run or wait for GitHub Actions/tests, and do not claim runtime/qualification evidence that was not actually produced.
