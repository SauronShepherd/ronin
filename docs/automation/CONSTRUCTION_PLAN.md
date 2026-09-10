# Ronin v0.1 construction plan

_Last synchronized: 2026-09-10 from product/state baseline `33f1d57134c6356af43ae6d5eb5bc8fd17ad5813`; the planning correction was published as `a12789dd8aa883a096057ef7267257609de43852`. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

Ronin remains capability-ordered rather than calendar-ordered. Each autonomous run selects at most one coherent slice, revalidates against current `main`, open Builder work, handoffs and exact-SHA qualification, and preserves all release gates.

**Planning synchronization rule.** `BACKLOG.md` and `CONSTRUCTION_PLAN.md` are one canonical planning pair. Whenever acceptance truth, completed capabilities, or the critical path changes materially, both files must be updated from the same observed repository state in one coherent planning slice. If they disagree, autonomous product selection stops until the drift is reconciled.

**Release-acceptance invariant.** Docker Qualification is the authoritative capable context for the frozen journey. Current acceptance is **13/15 live** with exactly `01` (production image/Compose) and `12` (public evidence) intentionally skipped. Docker Qualification enforces this exact named allowance and stale/new skips fail closed. Final release remains strict: all fifteen required step names must execute and pass with zero skips, xfails, failures, errors, missing, unexpected, renamed or duplicated outcomes.

**Current exact-main evidence.** Planning publication `a12789dd8aa883a096057ef7267257609de43852` is green for CI run `34437517162`, Security qualification `34437517194`, Docker Qualification `34437517131`, and Release qualification `34437517122`. This does not replace the still-missing scheduled/manual full-clean proof required by #166/#167/#163.

## Current position on 2026-09-10

The MVP-critical durable local execution and operator spine is substantially implemented:

- pure Job -> Run -> Attempt lifecycle and storage-neutral contracts;
- in-memory and SQLite `JobStore` adapters with conformance/fencing qualification;
- bounded async store/artifact composition;
- immutable per-cell execution/resume identity and explicit artifact verification;
- sequential checkpoint-before-next-cell execution;
- real-Docker worker execution, process crash, production-TTL reclaim and replacement Attempt resume with exact valid-cell reuse;
- fail-closed lease fencing, heartbeat ownership and cancellation behavior;
- authenticated HTTP submit/list/status/events/cancel with bounded keyset pagination and Run-global event projection;
- version-controlled OpenAPI 3.1 and `pyronin` support for the implemented public job-control boundary;
- supported CLI `doctor`, `validate`, `plan`, `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel`;
- prompt in-flight cancellation and container cleanup;
- SQLite public-adapter collapse/internal lifecycle helper cleanup and retirement of the transitional SQLite coverage baseline.

The old statement that only seven frozen steps are live is obsolete. The only two frozen acceptance gaps on current main are step `01` and step `12`.

PR #159 (`feat: expose portable durable evidence`) closed without merge. It is not landed behavior and is not an active blocker. A fresh #53 slice may proceed once earlier critical-path planning/qualification requirements are satisfied.

PR #170 structurally repaired nightly verifier self-contamination by moving verifier state outside `GITHUB_WORKSPACE`. The code repair is landed; authoritative scheduled/manual full-clean validation remains pending and must not be inferred from push-green.

B1 / #48 canonical planning synchronization is complete in implementation: PR #174 merged as `a12789dd8aa883a096057ef7267257609de43852` and all four mandatory push workflows for that exact main SHA are green. This follow-up removes #48 from the selectable critical path and records the explicit synchronization rule required by its acceptance criteria.

## Phase A — completed foundation

**Status. Complete.** Deterministic core/project/runtime/notebook/kernel contracts, architecture/quality gates, durable lifecycle, storage adapters, execution evidence and local Docker execution foundations are present. Do not reselect this work absent regression.

## Phase B — durable worker execution and resume

**Status. Complete for the current MVP execution spine.** Real OS-process crash + real Docker qualification proves same-Run replacement Attempt recovery with exact valid-cell reuse and execution of only the remaining cells. Resume validity depends on immutable identity plus artifact verification; a successful rerun alone is not accepted as proof. Attempt provenance remains part of the durable evidence model.

**Invariant.** Prefer durable-state assertions over fragile wall-clock assertions wherever state can prove the property.

## Phase C — bounded HTTP control plane and SDK contract

**Status. Substantially implemented, with two contract slices still important.** Existing public routes cover submit/list/status/events/cancel over the durable execution service, and OpenAPI/SDK coverage exists for them. Public evidence does not yet exist. Typed least-privilege scope semantics also remain missing.

Remaining ordered work:

1. #52 typed scoped grants before authorization behavior expands/fossilizes;
2. #53 bounded public portable evidence across HTTP/OpenAPI/CLI/SDK, activating frozen step 12;
3. #54 remaining error/evolution/drift compatibility rules after #52/#53 settle.

HTTP/server implementation types must never become canonical domain/storage contracts. Do not introduce a worker -> server dependency inversion.

## Phase D — operator CLI and Git revision identity

**Status. D1 is complete except `ronin evidence`.** `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel` are on main. The `evidence` subcommand remains intentionally coupled to #53 because its backing public evidence contract is absent.

Git revision capture is present. #123 remains a separate bounded correctness item: executable-vs-non-executable mode of untracked files must affect dirty identity while preserving fail-closed path/symlink/special-file handling.

## Phase E — production image, Compose and zero-to-demo quickstart

**Status. Not yet implemented; frozen step 01 remains skipped.**

The supported product topology must preserve the already-qualified boundaries:

- one production OCI image containing the installed product;
- durable local SQLite data volume;
- server health dependency;
- server/control-plane does not receive unnecessary Docker authority;
- worker can launch sibling execution containers with explicit Docker socket GID handling where required;
- read-only workspace identity and identical absolute workspace path assumptions remain explicit;
- non-root operation where practical;
- crash-acceptance worker uses explicit `restart: "no"`;
- health is reached within the v0.1 <60 s budget;
- zero-to-demo quickstart stays under ten minutes on a clean supported host.

## Phase F — acceptance completion

**Status. 13/15 live.** Exact intentional skips are `01,12`.

Activation rule:

- #53 activates step 12 and shrinks Docker Qualification allowance from `01,12` to `01` in the same coherent change;
- production image/Compose activates step 01 and shrinks the allowance from `01` to empty;
- all thirteen already-live steps must remain live throughout. Any regression-to-skip fails qualification.

Strict release remains the final authority: all fifteen steps execute and pass with zero skips/xfails/failures/errors/missing/unexpected outcomes.

## Phase G — non-functional and release qualification

**Current open release/trust work includes:**

- #166/#167/#163: scheduled/manual full-clean proof after #170/#168; do not close from push-green;
- #162: secure default for bearer transport over remote HTTP;
- #123: untracked executable-bit identity correctness;
- #95: qualify installed `pyronin` wheel outside the checkout;
- #60: pin Docker qualification bootstrap image by immutable digest;
- #58: exact transitive license inventory + fail-closed policy + evidence-based NOTICE decision;
- #102: measure release-gating tools under coverage;
- #63: enforce `main`/release-ref protection before v0.1.0 and no later than the recorded gate date;
- #45: security reporting/advisory policy after a human chooses/verifies the private reporting channel.

Quality budgets and durability constraints are not negotiable: POST p95 <100 ms, GET p95 <30 ms, WAL + `synchronous=FULL`, fencing, fail-closed VCS capture, T1 100%, T2 90%, T3 75%, and every `studio_storage` file >=80%.

## Phase H — release candidate and v0.1.0

**Status. Not started.** Tag/publish only after strict 15/15 acceptance, exact-main post-merge qualification, clean installed-artifact tests, immutable image identity, license/security/process blockers, version synchronization and required ref protections are satisfied.

Publication must qualify the exact wheel outside the checkout and must reference Docker images by immutable digest. Do not publish from a source-tree-only test path.

## Current critical path

One coherent Builder slice at a time:

1. **#166/#167/#163 scheduled/manual full-clean proof** — obtain same-mode evidence for the repaired verifier/contention path; if red, that failure becomes the next blocker.
2. **#52 typed scoped grants** — versioned, language-neutral, vendor-neutral, deny-by-default model and migration path; no OIDC/RBAC/OPA/provider IAM in core.
3. **#53 public portable evidence + step 12** — bounded authenticated HTTP/OpenAPI/CLI/SDK representation, physical locator privacy, real SQLite/HTTP conformance, allowance -> `01`.
4. **#54 compatibility/evolution completion** — complete error/additive/unknown/drift policy after #52/#53 contracts settle.
5. **Production image + Compose + step 01** — supported topology and allowance -> empty.
6. **#57 strict 15/15 completion** — keep open until authoritative Docker/release evidence proves the full frozen journey.
7. **Release blockers/publication** — #58/#95/#63/#45 and remaining release-critical items, then immutable tag/artifacts and published smoke.

Security/process quick wins may be taken only when they do not displace an earlier unresolved critical-path blocker or create parallel implementation PRs.

## Architecture and scope guardrails

- Canonical domain remains capability-driven and vendor-neutral; engines, clouds, catalogs, formats, model providers, runtimes and execution stay behind adapters/SPIs/protocols.
- Static bearer auth remains the v0.1 mechanism; typed scopes are required, enterprise auth is not.
- Do not add OIDC, enterprise RBAC, OPA, FastAPI, Pydantic, SQLAlchemy, Postgres, Kubernetes product deployment, brokers, OpenTelemetry or OpenLineage unless `V01_SCOPE.md`/current planning explicitly changes with evidence.
- No generic skip allowances. Allowed skips are exact by step/reason and stale allowances fail.
- Do not weaken security, coverage, durability, qualification or performance budgets to get green.

## Frozen until v0.1 ships

Ingestion/CDC breadth, SQL/lakehouse breadth, streaming, catalog/semantic BI, MLOps, GenAI/RAG, agents, Postgres/multi-node/HA, Kubernetes product scale, enterprise authorization and broad vendor integrations remain out of scope until the v0.1 freeze is explicitly lifted.

## Operational invariant

Before merge, require exact-head PR CI for the actual PR SHA and reread main. After merge, verify the mandatory workflows for the exact resulting main SHA. If a required safe operation cannot complete because CI or permissions are unavailable, record the exact blocker and next step; never invent green evidence or force the merge.
