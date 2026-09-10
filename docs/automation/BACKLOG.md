# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

_Last synchronized: 2026-09-10 against `33f1d57134c6356af43ae6d5eb5bc8fd17ad5813`._

## Current v0.1 truth

Ronin already has the durable local execution spine, real-Docker worker execution/recovery, authenticated HTTP control-plane paths, OpenAPI 3.1, the `pyronin` SDK, and the supported operator CLI commands `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel`.

Docker Qualification is the authoritative capable environment for frozen acceptance. Current frozen acceptance is **13/15 live** with exactly two intentional skips:

- `01` — production image + supported Compose topology is not implemented yet;
- `12` — public portable evidence retrieval is not implemented yet.

The exact Docker Qualification allowance is therefore `01,12`, and the allowance remains a ratchet: newly skipped live steps and stale allowances both fail qualification. Strict release remains unchanged at 15/15 with an empty allowance.

The current exact-main push qualification on `33f1d57134c6356af43ae6d5eb5bc8fd17ad5813` is green for CI run `34431357861`, Security qualification `34431357908`, Docker Qualification `34431358031`, and Release qualification `34431357884`.

## Completed foundation carried into v0.1

Do not reselect already-landed foundation, durable lifecycle, C0 pagination/event semantics, or bounded-composition work unless a regression or changed contract reopens it.

Completed capabilities include:

- pure Job -> Run -> Attempt lifecycle and storage-neutral `JobStore` contracts;
- in-memory and SQLite adapters with shared conformance/fencing qualification;
- bounded async store/artifact composition;
- per-cell immutable resume identity and artifact verification;
- sequential checkpoint-before-next-cell execution;
- production-lease crash/reclaim/replacement Attempt behavior with exact cell reuse;
- fail-closed lease fencing, heartbeat ownership and cancellation semantics;
- real-Docker local worker execution and container cleanup qualification;
- authenticated submit/list/status/events/cancel HTTP paths with bounded keyset pagination;
- OpenAPI 3.1 and `pyronin` coverage for the implemented public job-control surface;
- HTTP-independent CLI `doctor`, `validate`, `plan` plus network/operator commands `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel`;
- prompt in-flight cancellation/container cleanup;
- the SQLite public-adapter collapse, internal lifecycle helper, and retirement of the transitional SQLite per-file coverage baseline.

PR #159 (`feat: expose portable durable evidence`) is **closed without merge**. It is not current behavior, is not an active dependency, and must not block a fresh #53 implementation.

PR #170 landed the nightly-verifier structural fix by moving verifier state outside `GITHUB_WORKSPACE`. That repair is present on main, but fresh scheduled/manual full-clean evidence is still required before #166/#167/#163 can be considered satisfied.

## Current critical path

Select one coherent slice at a time. Do not start product work while this canonical planning state is known to be stale.

1. **#48 — canonical planning synchronization.** Keep this backlog, `CONSTRUCTION_PLAN.md`, and public status wording aligned to current main before selecting new product work. This item is complete only after the synchronized change is merged and exact-main qualification is green.
2. **#166/#167/#163 — scheduled/manual full-clean proof.** Obtain a post-#170 workflow-dispatch or scheduled CI run that executes the full `make check` path. Push-green is not equivalent evidence. Do not change production code merely to manufacture this proof.
3. **#52 — typed scoped grants.** Define the versioned vendor-neutral grant/requirement contract and deterministic deny-by-default matching before externally relied-on authorization behavior expands. Do not introduce OIDC, enterprise RBAC, OPA or provider IAM into the canonical model.
4. **#53 — public portable evidence + acceptance step 12.** Expose storage-neutral evidence through the supported HTTP/OpenAPI/CLI/SDK boundary, keep physical locators private, add real SQLite/HTTP conformance, activate step 12, and shrink the Docker allowance from `01,12` to `01` in the same coherent change.
5. **#54 — remaining API/SDK compatibility rules.** Finish error/evolution/drift conformance after the #52/#53 semantics settle.
6. **Production image + Compose — acceptance step 01.** Promote the qualified Docker assumptions into the supported product topology: production image, durable SQLite volume, server health dependency, sibling-container execution, Docker authority only where required, non-root operation where practical, and explicit crash-worker `restart: "no"`.
7. **#57 — strict frozen journey completion.** Keep open until all fifteen required steps execute and pass in authoritative qualification with no skip/xfail/failure/error/missing/unexpected outcome.
8. **Release blockers and publication.** Close exact dependency/license/NOTICE policy (#58), installed-wheel clean qualification (#95), required repository/ref protection (#63), security-reporting policy after the human channel decision (#45), and other release-critical work before immutable publication.

Security quick wins such as #162, #123, #95 and #60 remain important, but they do not outrank an unresolved earlier critical-path blocker unless current main/CI evidence changes the ordering.

## D1 operator status

D1 is no longer a general network/operator CLI implementation block. `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel` are already landed. The only missing v0.1 operator subcommand in this family is `ronin evidence`, which belongs with #53 because its backing public evidence contract does not exist yet.

Local Git revision capture is also implemented, but #123 remains open for executable-bit correctness in untracked dirty identity. Treat that as a bounded correctness slice, not a reason to reimplement D1.

## Worker execution invariants

Every remaining worker/runtime slice must preserve all of these:

- Persist successful cell result/evidence before the next cell starts; end-of-run batching is not resume-safe.
- Every worker-originated durable write is fenced by the active Attempt lease.
- Heartbeat ownership loss is fail closed: cancel active execution and do not complete the Attempt.
- Cancellation must not wait for all remaining cells and in-flight container cleanup must remain qualified.
- Resume requires immutable cell identity plus verified artifact availability/digest.
- Replacement Attempts reuse the same logical Run and must not replay valid completed cells.
- Resume evidence must prove exact reused-cell identity and provenance by `attempt_id`; a simple successful rerun is insufficient.
- Blocking durable-store and artifact operations remain behind bounded async facades.
- Process-crash qualification preserves the production lease TTL rather than shortening it for CI.
- Prefer durable-state assertions over fragile wall-clock assertions when the required property can be proven from state.

## Public-boundary and architecture invariants

- Domain contracts remain capability-driven and vendor-neutral; engines, clouds, catalogs, formats, model providers, runtimes and execution stay behind adapters/SPIs/protocols.
- Do not introduce a worker -> server dependency inversion; HTTP/server types remain boundary concerns, not canonical domain/storage models.
- Physical evidence/storage locators are not canonical public identity.
- Static bearer authentication remains the v0.1 auth mechanism; typed least-privilege scopes are required, but OIDC and enterprise multi-user RBAC remain out of scope.
- No generic skip allowances: any allowed skip must be exact by step and reason and qualification must fail on any new or stale skip.

## Quality and release invariants

Do not weaken gates to make CI green.

- POST p95 <100 ms and GET p95 <30 ms remain unchanged.
- SQLite WAL + `synchronous=FULL` durability and fencing are non-negotiable.
- VCS capture remains fail closed.
- T1 (`studio_core`, `studio_notebook`, `studio_orchestrator`) = 100% line and branch coverage.
- T2 = 90%.
- T3 = 75%.
- Every `studio_storage` file = 80% minimum.
- Publication must qualify the exact `pyronin` wheel outside the checkout and must use immutable Docker image identity/digests.
- Merge requires exact-head PR CI evidence; release claims require exact-main post-merge evidence.

## Frozen until v0.1 ships

The following remain out of scope unless `docs/product/V01_SCOPE.md` is explicitly revised: ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product deployment, enterprise RBAC, OPA, brokers, OpenTelemetry, OpenLineage, and broad vendor-adapter expansion.

Do not introduce FastAPI, Pydantic, SQLAlchemy or other framework choices into canonical contracts merely to accelerate the v0.1 boundary work.

## Operational invariant

After every publication to `main`, inspect mandatory GitHub Actions for the exact published SHA. If an increment cannot safely be made green, do not force the merge or weaken the gate; record the exact blocker and next safe step instead.
