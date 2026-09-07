# Ronin v0.1 construction plan

_Last synchronized: 2026-09-07. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

The v0.1 plan remains eight weeks, but execution is ahead of the original calendar in the durable-execution spine. Planning therefore uses capability order rather than waiting for nominal week boundaries. Each autonomous run still selects at most one coherent slice, revalidates against current `main`, and preserves all release gates.

**Release-acceptance invariant.** Ordinary PR/main CI may run the frozen journey as explicitly named non-blocking telemetry while capabilities are still landing. The Docker-capable qualification is the authoritative execution context for the real worker crash/reclaim/resume steps. Release/tag publication must consume exact-SHA evidence from that capable qualification rather than re-run the journey in an environment where required steps are structurally skipped. Docker qualification may carry only an exact named skip allowance matching the current skipped-step set; the allowance must shrink as capabilities become live. Final release qualification remains strict: all fifteen frozen required step names must execute and pass with zero skips, xfails, failures, errors, missing, unexpected, renamed or duplicated outcomes.

## Current position on 2026-09-07

The repository now has the durable local execution spine required to move through control-plane qualification:

- pure Job -> Run -> Attempt lifecycle and canonical `Instant` semantics;
- in-memory and SQLite `JobStore` adapters with shared conformance/fencing tests;
- immutable per-cell resume identity and explicit artifact verification;
- bounded async JobStore and artifact-store composition;
- `DurableExecutionService` for submit/status/cancel plus worker reclaim/claim/heartbeat and fenced worker writes;
- safe local project/runtime preparation with exact immutable execution-image identity;
- sequential per-cell checkpoint-before-next execution with cancellation polling, heartbeat fail-closed behavior and verified resume;
- `LocalWorkerRuntime` composition over SQLite, local durable stores and the real Docker executor;
- a deterministic canonical demo that succeeds across clean per-cell containers through the real Docker command path;
- a continuous worker lifecycle with unique poll identities, signal-aware graceful shutdown and Attempt-limit continuity;
- real OS-process crash qualification: after three real-Docker cells are durably checkpointed, a separate worker process is killed non-gracefully, the production 30-second lease is allowed to expire, and a replacement process reclaims the same Run, reuses exactly the three valid checkpoints and executes only the remaining two cells;
- #125 bounded-contention qualification at final server and worker call sites: authenticated HTTP POST/GET meet their published p95 budgets under bounded SQLite contention, while `LocalWorkerRuntime` proves durable lease renewal and reclaim/resume continue through real SQLite and local-artifact contention at the unchanged 30-second lease / 10-second heartbeat settings.

The process-crash evidence advances #57 but does not complete it. The frozen fifteen-step journey still depends on the remaining HTTP/SDK, CLI/operator, portable evidence, Compose and supported cancellation surfaces.

A release-path review at `78d483c` exposed a structural acceptance split: Docker Qualification can execute steps 6-9 but historically used an unconditional progress-only gate, while prerelease strict acceptance re-ran the journey without the Docker qualification context and therefore saw those required steps skipped. The acceptance-truth wiring is now the first release-critical prerequisite: one exact-SHA Docker-capable evidence source, a ratcheting exact skip allowance during development, and unchanged strict 15/15 publication semantics.

## Phase A — completed foundation

**Objective.** Establish deterministic core/project/runtime/operator/diagnostic/notebook/kernel contracts, quality/architecture gates, durable lifecycle semantics and storage adapters.

**Status.** Complete on current `main` for the MVP-critical foundation. Historical details remain in `docs/automation/PROGRESS.md` and dated qualification supplements.

## Phase B — durable worker execution and resume

**Objective.** Execute one durable local Run through worker claim, heartbeat, fenced per-cell persistence, lease expiry, replacement Attempt and record-level resume.

**Status.** The core execution seam is implemented and qualified through a real OS-process death plus real Docker execution. Worker-originated durable writes are fenced; successful cells checkpoint before the next cell; corrupt/missing artifacts are not reused; cancellation and lease loss fail closed; the canonical demo is clean-container safe; graceful daemon shutdown and abrupt process death have separate qualification paths; abrupt-death qualification preserves the production 30-second lease TTL. Bounded-contention qualification now also proves the production worker runtime keeps renewing durable leases while selected SQLite/artifact operations occupy bounded workers and that replacement resume remains live while artifact verification is contended.

**Remaining Phase-B/product-journey work.** Wire these proven capabilities through the supported operator journey as the surrounding surfaces land, and keep #57 open until the frozen acceptance sequence itself executes end-to-end. The dedicated Docker qualification already proves executor cancellation/timeout cleanup leaves no residual execution container, but the product-level cancel step still requires the supported control-plane/operator path.

**Exit criteria.** A kill/restart test proves completed reusable cells are not replayed; terminal state remains unique/monotonic; lost or expired leases cannot continue writing; heartbeat tasks are always cancelled/awaited; no residual execution container remains after cancellation/failure. The first four properties are now directly qualified through the composed runtime; product-level cancellation remains tied to later API/operator activation.

**Cut line.** Sunday 27 September remains the planning checkpoint. A prerelease may document whole-run replay as a limitation only if a future regression reopens this capability; final v0.1 remains governed by the frozen acceptance contract unless product scope is explicitly revised.

## Phase C0 — storage contracts before public list/events

**Objective.** Make the storage/API boundary unambiguous before remaining public endpoints freeze broken pagination or event-coordinate behavior.

**Pull requests.** Preserve canonical storage event identity as `(attempt_id, sequence)` while exposing a dense Run-global projection ordered by `(attempt.ordinal, sequence)` with bounded reads and explicit `since`/`next_since`. Replace `list_jobs` UUID ordering plus OFFSET with stable newest-first keyset pagination over `(created_at DESC, job_id DESC)` and fail-closed cursor parsing. Keep equivalent adapter behavior where the `JobStore` contract requires it.

**Exit criteria.** Events across replacement Attempts have one stable Run-global coordinate system at the service/API boundary; polling never requires an unbounded historical materialization; list pagination remains stable under concurrent inserts; malformed cursors become normalized boundary errors rather than 500s.

## Phase C — bounded HTTP control plane and SDK contract

**Objective.** Make durable jobs remotely controllable through one bounded authenticated API whose executable OpenAPI contract matches `pyronin`.

**Pull requests.** After C0, continue #54 with the frozen `/v1/jobs` submit/status/list/cancel/events surface over `DurableExecutionService`; add bearer-token authorization; add OpenAPI golden/route coverage tests; align `pyronin` schemas/errors/retry behavior. The existing submit/status routes and their contention p95 budgets are already qualified; do not reimplement them. Defer the public evidence representation until #53 freezes portable evidence identity.

**Framework decision.** Framework choice is an implementation detail, not a domain decision. A standard-library HTTP server is acceptable if it satisfies the same route/auth/OpenAPI/SDK/error/qualification contract; a pinned FastAPI/Pydantic stack is also acceptable if dependency-lock, typing, architecture and image costs remain justified. In either case, framework/model types stay outside canonical domain packages.

**Exit criteria.** Acceptance steps for submit/status/idempotency/events/cancel/SDK are live against the real server as their supported operator paths land; every documented route is exercised by tests; bounded request latency and secure token transport defaults are qualified; the API never calls synchronous durable storage directly from an event-loop thread. Evidence remains blocked until #53.

**Cut line.** Sunday 4 October: cut optional pagination breadth first. Do not silently delete frozen acceptance behavior without an explicit product-scope decision.

## Phase D0 — HTTP-independent CLI foundation

**Objective.** Provide the first supported `ronin` entry point using already-landed local capabilities without waiting for the entire HTTP block.

**Pull requests.** Implement and test `studio_cli:main`, enable the console entry point, and land `doctor`, `validate`, and `plan`. `validate` consumes existing project/notebook/runtime validation; `plan` consumes existing dependency levels; `doctor` reports the bounded local environment checks required by the frozen journey.

**Exit criteria.** Frozen acceptance steps 2, 3 and 4 are live through the supported CLI path with no HTTP/store/Docker dependency introduced merely to activate them.

## Phase D1 — network/operator CLI and local Git revision capture

**Objective.** Expose the supported job workflow through `ronin` and bind execution to a reproducible local checkout revision.

**Pull requests.** Complete Git revision/dirty identity qualification, including executable-bit correctness; add `serve`, `worker`, `submit`, `status`, `logs`, `evidence`, and `cancel` after their backing contracts exist. The evidence command lands only after #53 and the evidence API representation are stable.

**Exit criteria.** CLI portions of the job journey are live; Git qualification covers detached HEAD, ref movement, dirty digest, executable-bit changes, path safety and credential exclusion.

**Cut line.** Sunday 11 October: a prerelease may reduce CLI breadth, but final v0.1 remains governed by `V01_SCOPE.md` unless scope is explicitly revised.

## Phase E — production image, Compose and zero-to-demo quickstart

**Objective.** Deliver one reproducible OCI image and a documented local startup path that reaches the demo journey from zero.

**Pull requests.** Promote the proven probe-image assumptions into the production Dockerfile; build/install Ronin and `pyronin`; run non-root; preserve Docker socket GID handling and read-only workspace identity; add durable data volume, server health dependency, worker topology, immutable base-image identity, clean-room install smoke and quickstart.

**Exit criteria.** `docker compose up -d` is healthy under the product budget; quickstart completes on a clean host; image runs server and worker without privileged web/control-plane Docker access; crash-acceptance worker uses explicit `restart: "no"`.

**Cut line.** Friday 16 October: a prerelease may document `docker run`; final v0.1 still requires the frozen packaging acceptance behavior unless scope is explicitly revised.

## Phase F — incremental acceptance activation

**Objective.** Turn skips live as soon as their dependencies exist instead of waiting for one large end-stage change, while making regression-to-skip fail closed in Docker Qualification.

**Activation order.**

1. `doctor`, `validate`, `plan` after D0.
2. Compose health after Phase E.
3. submit/status/idempotency/SDK after the supported Phase C/D1 path.
4. logs/evidence after Run-global event ordering and #53 portable evidence references are real.
5. execute/crash/reclaim/resume through the supported product journey while preserving the already-qualified Phase-B worker semantics.
6. cancel cleanup once worker cancellation/container cleanup are exercised through the supported operator path.

**Exit criteria.** Every activation removes that step from the exact Docker skip allowance in the same change. A newly skipped previously-live step or a stale allowance fails qualification. The strict release gate ultimately reports all fifteen required steps live and passed with zero skipped/xfail/failed/error/missing/unexpected outcomes.

## Phase G — non-functional and release qualification

**Objective.** Qualify the exact implementation against the product budgets and trust requirements rather than inferring readiness from unit tests.

**Pull requests.** #125 contention qualification is complete. Continue qualifying remaining product budgets as supported surfaces land: compose health, RSS, full `make check`, security/secret/vulnerability/license qualification, deterministic demo/evidence output and targeted recovery cases. Release-gating tooling itself remains release-critical code and must be brought under the required coverage perimeter under #102.

**Exit criteria.** All product budgets in `V01_SCOPE.md` are evidenced on exact SHAs; no known secret or vulnerability ships; no release gate is weakened to achieve green.

## Phase H — release candidate and v0.1.0

**Objective.** Stabilize only: documentation, clean-room verification, compatibility checks, release notes and immutable publication.

**Pull requests.** Fix release-blocking defects only; finalize quickstart/limitations/security docs; verify Python 3.11/3.12 and supported Docker path; synchronize package/version metadata; ensure tested image identity is immutable before qualification; close release-gate coverage and license/NOTICE debt; enable required `main`/tag protections or record the governing exception; tag and publish only after strict acceptance and every other release gate is green.

**Exit criteria.** Clean hash-locked `make check`; exact-SHA Docker-capable evidence proves all fifteen required acceptance steps execute and pass; acceptance allowance is empty; demo regenerates deterministically; release artifacts have immutable provenance; zero Builder-owned PRs remain open at tagging time; no P0/P1 release blocker remains.

**Cut line.** No feature substitution. Defer optional surfaces rather than weakening trust, reproducibility, durability, acceptance or security gates.

## Current critical path

The current ordering is:

1. acceptance truth wiring: exact-SHA Docker-capable evidence + exact skip ratchet + unchanged strict release gate;
2. C0 storage contracts for Run-global events and stable keyset job pagination;
3. D0 local CLI (`doctor`, `validate`, `plan`, entry point);
4. #54 list/cancel/events + OpenAPI/SDK contract after C0;
5. #53 portable evidence identity before `/evidence` ships;
6. #54 evidence completion plus D1 network/operator CLI;
7. production image/Compose;
8. incremental completion of the frozen fifteen-step journey with the Docker allowance shrinking to empty;
9. remaining non-functional/security/release blockers and immutable publication.

#125 is complete and is no longer an eligible critical-path slice unless its acceptance criteria change or a regression reopens it. This ordering supersedes the prior #54-first sequence because acceptance truth is a release-structural prerequisite, C0 must land before public list/events contracts freeze storage defects, and D0 does not depend on HTTP. It does not authorize parallel Builder PRs: each autonomous run must finish/reconcile its own prior work before selecting the next slice.

## Pre-decided calendar checkpoints

| Trigger | Planning response |
|---|---|
| Fri 18 Sep: `JobStore` contract regresses | Freeze retries at one Run and fix storage before adding surfaces. |
| Sun 27 Sep: local end-to-end does not resume | Prerelease may document whole-run replay; final v0.1 scope remains unchanged unless explicitly revised. |
| Sun 4 Oct: HTTP not green | Cut optional pagination breadth before required job-control behavior. |
| Sun 11 Oct: CLI not green | Cut optional CLI breadth in prerelease before weakening core server/worker behavior. |
| Fri 16 Oct: packaging not green | Use `docker run` for prerelease if necessary; do not misrepresent final v0.1 acceptance. |
| Mon 19 Oct: anything behind | Consume buffer and cut optional chaos breadth first. |

**Never cut without an explicit product-scope revision:** the final fifteen-step v0.1 acceptance journey, a green `make check`, durability/trust invariants, or shipping with known secrets/vulnerabilities.

## Post-v0.1 horizon, not scheduled

E3–E10 remain frozen until v0.1 ships: data engineering, streaming/reliability, catalog/governance/BI, data science/MLOps, GenAI/RAG, agents, enterprise operations and ecosystem/maturity work are not eligible autonomous slices before the v0.1 release.
