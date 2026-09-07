# Ronin v0.1 construction plan

_Last synchronized: 2026-09-07. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

The v0.1 plan remains eight weeks, but execution is ahead of the original calendar in the durable-execution spine. Planning therefore uses capability order rather than waiting for nominal week boundaries. Each autonomous run still selects at most one coherent slice, revalidates against current `main`, and preserves all release gates.

**Release-acceptance invariant.** Ordinary PR/main CI may run the frozen journey as explicitly named non-blocking progress telemetry while capabilities are still landing. A release/tag publication gate is different: it must verify the exact fifteen frozen required step names and fail closed if any step is skipped, xfailed, failed, errored, deselected/missing, renamed/unexpected, duplicated, or otherwise not executed. Machine-readable live/passed/skipped/xfail/missing counts are evidence; a normal pytest exit code alone is not release acceptance evidence.

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

The process-crash evidence advances #57 but does not complete it. The frozen fifteen-step journey still depends on the remaining HTTP/SDK, CLI/operator, portable evidence, Compose and supported cancellation surfaces; normal progress telemetry must not be represented as release acceptance.

HTTP, CLI and packaging remain adjacent integration surfaces, but autonomous execution stays serial: they are not opened in parallel merely because they are technically independent.

## Phase A — completed foundation

**Objective.** Establish deterministic core/project/runtime/operator/diagnostic/notebook/kernel contracts, quality/architecture gates, durable lifecycle semantics and storage adapters.

**Status.** Complete on current `main` for the MVP-critical foundation. Historical details remain in `docs/automation/PROGRESS.md` and dated qualification supplements.

## Phase B — durable worker execution and resume

**Objective.** Execute one durable local Run through worker claim, heartbeat, fenced per-cell persistence, lease expiry, replacement Attempt and record-level resume.

**Status.** The core execution seam is implemented and qualified through a real OS-process death plus real Docker execution. Worker-originated durable writes are fenced; successful cells checkpoint before the next cell; corrupt/missing artifacts are not reused; cancellation and lease loss fail closed; the canonical demo is clean-container safe; graceful daemon shutdown and abrupt process death have separate qualification paths; abrupt-death qualification preserves the production 30-second lease TTL. Bounded-contention qualification now also proves the production worker runtime keeps renewing durable leases while selected SQLite/artifact operations occupy bounded workers and that replacement resume remains live while artifact verification is contended.

**Remaining Phase-B/product-journey work.** Wire these proven capabilities through the supported operator journey as the surrounding surfaces land, and keep #57 open until the frozen acceptance sequence itself executes end-to-end. The dedicated Docker qualification already proves executor cancellation/timeout cleanup leaves no residual execution container, but the product-level cancel step still requires the supported control-plane/operator path.

**Exit criteria.** A kill/restart test proves completed reusable cells are not replayed; terminal state remains unique/monotonic; lost or expired leases cannot continue writing; heartbeat tasks are always cancelled/awaited; no residual execution container remains after cancellation/failure. The first four properties are now directly qualified through the composed runtime; product-level cancellation remains tied to later API/operator activation.

**Cut line.** Sunday 27 September remains the planning checkpoint. A prerelease may document whole-run replay as a limitation only if a future regression reopens this capability; final v0.1 remains governed by the frozen acceptance contract unless product scope is explicitly revised.

## Phase C — bounded HTTP control plane and SDK contract

**Objective.** Make durable jobs remotely controllable through one bounded authenticated API whose executable OpenAPI contract matches `pyronin`.

**Pull requests.** Continue #54 with the frozen `/v1/jobs` submit/status/list/cancel/events/evidence surface over `DurableExecutionService`; add bearer-token authorization; define/verify dense Run-global event numbering across attempts; add OpenAPI golden/route coverage tests; align `pyronin` schemas/errors/retry behavior. The existing submit/status routes and their contention p95 budgets are already qualified; do not reimplement them.

**Framework decision.** Framework choice is an implementation detail, not a domain decision. A standard-library HTTP server is acceptable if it satisfies the same route/auth/OpenAPI/SDK/error/qualification contract; a pinned FastAPI/Pydantic stack is also acceptable if dependency-lock, typing, architecture and image costs remain justified. In either case, framework/model types stay outside canonical domain packages.

**Exit criteria.** Acceptance steps for submit/status/idempotency/logs/evidence/cancel/SDK are live against the real server; every documented route is exercised by tests; bounded request latency and secure token transport defaults are qualified; the API never calls synchronous durable storage directly from an event-loop thread.

**Cut line.** Sunday 4 October: cut optional pagination breadth first. Do not silently delete frozen acceptance behavior without an explicit product-scope decision.

## Phase D — CLI and local Git revision capture

**Objective.** Expose the supported local workflow through `ronin` and bind execution to a reproducible local checkout revision.

**Pull requests.** Complete Git revision/dirty identity qualification, including executable-bit correctness; implement `studio_cli:main`; add `serve`, `worker`, `validate`, `plan`, `submit`, `status`, `logs`, `evidence`, `cancel`, `doctor`; enable the console entry point only after the symbol and commands are tested.

**Exit criteria.** Acceptance steps 2–4 and CLI portions of the job journey are live; Git qualification covers detached HEAD, ref movement, dirty digest, executable-bit changes, path safety and credential exclusion.

**Cut line.** Sunday 11 October: a prerelease may reduce CLI breadth, but final v0.1 remains governed by `V01_SCOPE.md` unless scope is explicitly revised.

## Phase E — production image, Compose and zero-to-demo quickstart

**Objective.** Deliver one reproducible OCI image and a documented local startup path that reaches the demo journey from zero.

**Pull requests.** Promote the proven probe-image assumptions into the production Dockerfile; build/install Ronin and `pyronin`; run non-root; preserve Docker socket GID handling and read-only workspace identity; add durable data volume, server health dependency, worker topology, immutable base-image identity, clean-room install smoke and quickstart.

**Exit criteria.** `docker compose up -d` is healthy under the product budget; quickstart completes on a clean host; image runs server and worker without privileged web/control-plane Docker access; crash-acceptance worker uses explicit `restart: "no"`.

**Cut line.** Friday 16 October: a prerelease may document `docker run`; final v0.1 still requires the frozen packaging acceptance behavior unless scope is explicitly revised.

## Phase F — incremental acceptance activation

**Objective.** Turn skips live as soon as their dependencies exist instead of waiting for one large end-stage change.

**Activation order.**

1. Compose health after Phase E.
2. `doctor`, `validate`, `plan` after Phase D.
3. submit/status/idempotency/SDK after Phase C.
4. logs/evidence after run-global event ordering and portable evidence references are real.
5. execute/crash/reclaim/resume once the Phase-B worker capabilities are wired through the supported journey.
6. cancel cleanup once worker cancellation/container cleanup are exercised through the supported operator path.

**Exit criteria.** The progress workflow reports increasing live counts without redefining step names. The strict release gate ultimately reports all fifteen required steps live and passed with zero skipped/xfail/failed/error/missing/unexpected outcomes.

## Phase G — non-functional and release qualification

**Objective.** Qualify the exact implementation against the product budgets and trust requirements rather than inferring readiness from unit tests.

**Pull requests.** #125 contention qualification is complete. Continue qualifying the remaining product budgets as their supported surfaces land: compose health, RSS, full `make check`, security/secret/vulnerability/license qualification, deterministic demo/evidence output and targeted recovery cases.

**Exit criteria.** All product budgets in `V01_SCOPE.md` are evidenced on exact SHAs; no known secret or vulnerability ships; no release gate is weakened to achieve green.

## Phase H — release candidate and v0.1.0

**Objective.** Stabilize only: documentation, clean-room verification, compatibility checks, release notes and immutable publication.

**Pull requests.** Fix release-blocking defects only; finalize quickstart/limitations/security docs; verify Python 3.11/3.12 and supported Docker path; synchronize package/version metadata; ensure the tested image is the image published; enable required `main`/tag protections or record the governing exception; tag and publish only after strict acceptance and every other release gate is green.

**Exit criteria.** Clean hash-locked `make check`; all fifteen required acceptance steps execute and pass; demo regenerates deterministically; release artifacts have immutable provenance; zero Builder-owned PRs remain open at tagging time; no P0/P1 release blocker remains.

**Cut line.** No feature substitution. Defer optional surfaces rather than weakening trust, reproducibility, durability, acceptance or security gates.

## Current critical path

The current ordering is:

1. #54 HTTP/OpenAPI/SDK;
2. CLI/operator surface plus remaining Git qualification;
3. production image/Compose;
4. #53 portable evidence representation before the external API hardens it;
5. incremental completion of the frozen fifteen-step acceptance journey, including the already-proven crash/reclaim semantics through the supported product path;
6. full non-functional/security/release qualification and publication.

#125 is complete and is no longer an eligible critical-path slice unless its acceptance criteria change or a regression reopens it. This ordering supersedes stale handoff bodies that still describe already-landed storage, fencing, worker-loop, process-crash or contention prerequisites as missing. It does not authorize parallel Builder PRs: each autonomous run must finish/reconcile its own prior work before selecting the next slice.

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
