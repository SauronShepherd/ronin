# Ronin v0.1 construction plan

_Last synchronized: 2026-09-07. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

The v0.1 plan remains eight weeks, but execution is ahead of the original calendar in the durable-execution spine. Planning therefore uses capability order rather than waiting for nominal week boundaries. Each autonomous run still selects at most one coherent slice, revalidates against current `main`, and preserves all release gates.

**Release-acceptance invariant.** Ordinary PR/main CI may run the frozen journey as explicitly named non-blocking telemetry while capabilities are still landing. The Docker-capable qualification is the authoritative execution context for the real worker crash/reclaim/resume steps. Release/tag publication consumes exact-SHA evidence from that capable qualification rather than re-running the journey in an environment where required steps are structurally skipped. Docker qualification may carry only an exact named skip allowance matching the current skipped-step set; the allowance must shrink as capabilities become live. Final release qualification remains strict: all fifteen frozen required step names must execute and pass with zero skips, xfails, failures, errors, missing, unexpected, renamed or duplicated outcomes.

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
- real OS-process crash qualification: after three real-Docker cells are durably checkpointed, a separate worker process is killed non-gracefully, the production 30-second lease expires, and a replacement process reclaims the same Run, reuses exactly the three valid checkpoints and executes only the remaining two cells;
- #125 bounded-contention qualification at final server and worker call sites;
- release acceptance truth unified around exact-SHA Docker-capable JUnit/provenance plus an exact skip ratchet;
- C0 storage pagination contracts: stable newest-first keyset job pagination, defensive opaque cursors, bounded Run-event keyset reads, and dense Run-global event projection across replacement Attempts without changing canonical `(attempt_id, sequence)` storage identity.

The process-crash evidence advances #57 but does not complete it. The frozen fifteen-step journey still depends on the remaining HTTP/SDK, CLI/operator, portable evidence, Compose and supported cancellation surfaces. Current acceptance remains four live steps (6-9) and eleven explicitly skipped steps.

## Phase A — completed foundation

**Objective.** Establish deterministic core/project/runtime/operator/diagnostic/notebook/kernel contracts, quality/architecture gates, durable lifecycle semantics and storage adapters.

**Status.** Complete on current `main` for the MVP-critical foundation. Historical details remain in `docs/automation/PROGRESS.md` and dated qualification supplements.

## Phase B — durable worker execution and resume

**Objective.** Execute one durable local Run through worker claim, heartbeat, fenced per-cell persistence, lease expiry, replacement Attempt and record-level resume.

**Status.** Core execution is implemented and qualified through real OS-process death plus real Docker execution. Worker-originated writes are fenced; successful cells checkpoint before the next cell; corrupt/missing artifacts are not reused; cancellation and lease loss fail closed; graceful daemon shutdown and abrupt process death have separate qualification paths; abrupt-death qualification preserves the production 30-second lease TTL. Bounded-contention qualification proves the production worker runtime keeps renewing durable leases while selected SQLite/artifact operations occupy bounded workers and that replacement resume remains live while artifact verification is contended.

**Remaining Phase-B/product-journey work.** Wire these proven capabilities through the supported operator journey as surrounding surfaces land, and keep #57 open until the frozen acceptance sequence itself executes end-to-end.

## Phase C0 — storage contracts before public list/events

**Objective.** Make the storage/API boundary unambiguous before remaining public endpoints freeze broken pagination or event-coordinate behavior.

**Status. Complete in this construction sequence.** The storage-neutral port now exposes bounded Run-event pages. Canonical durable event identity remains `(attempt_id, sequence)`, while the public/service-ready projection assigns dense Run-global sequence numbers in `(attempt.ordinal, sequence)` order. `since`/`next_since` is an opaque versioned keyset cursor bound to the Run; malformed, oversized, schema-drifted and cross-Run cursors fail closed. Job listing now uses newest-first keyset pagination over `(created_at DESC, job_id DESC)`, with opaque cursors bound to the active project/state filters. SQLite queries no longer use OFFSET for these public-facing pagination contracts, and in-memory/SQLite adapters share conformance tests for inserts between pages, timestamp ties, replacement Attempts, empty polling and resumed polling. The bounded async store facade exposes the same event-page operation.

**Exit criteria.** Satisfied by the C0 qualification: replacement-Attempt events have one stable Run-global coordinate system at the service boundary; polling is bounded and does not materialize prior history; list pagination remains stable under concurrent newer inserts; cursor parsing is fail closed. Public HTTP routes are deliberately still absent and remain Phase C work.

Do not select C0 again unless a regression or changed contract reopens it.

## Phase C — bounded HTTP control plane and SDK contract

**Objective.** Make durable jobs remotely controllable through one bounded authenticated API whose executable OpenAPI contract matches `pyronin`.

**Pull requests.** Continue #54 with the frozen `/v1/jobs` submit/status/list/cancel/events surface over `DurableExecutionService`; add bearer-token authorization; add OpenAPI golden/route coverage tests; align `pyronin` schemas/errors/retry behavior. Existing submit/status routes and contention p95 budgets are already qualified. C0 is now available as the storage contract for list/events. Defer the public evidence representation until #53 freezes portable evidence identity.

**Framework decision.** Framework choice is an implementation detail, not a domain decision. Framework/model types stay outside canonical domain packages.

**Exit criteria.** Acceptance steps for submit/status/idempotency/events/cancel/SDK become live against the real supported server/operator path; every documented route is exercised; bounded request latency and secure token transport defaults are qualified; API composition does not execute blocking durable storage on an event-loop thread. Evidence remains blocked until #53.

## Phase D0 — HTTP-independent CLI foundation

**Objective.** Provide the first supported `ronin` entry point using already-landed local capabilities without waiting for the entire HTTP block.

**Status. Current next slice.** Implement and test `studio_cli:main`, enable the console entry point, and land `doctor`, `validate`, and `plan`. `validate` consumes existing project/notebook/runtime validation; `plan` consumes existing dependency levels; `doctor` reports the bounded local environment checks required by the frozen journey.

**Exit criteria.** Frozen acceptance steps 2, 3 and 4 are live through the supported CLI path with no HTTP/store/Docker dependency introduced merely to activate them.

## Phase D1 — network/operator CLI and local Git revision capture

**Objective.** Expose the supported job workflow through `ronin` and bind execution to a reproducible local checkout revision.

**Pull requests.** Complete Git revision/dirty identity qualification, including executable-bit correctness; add `serve`, `worker`, `submit`, `status`, `logs`, `evidence`, and `cancel` after their backing contracts exist. The evidence command lands only after #53 and the evidence API representation are stable.

**Exit criteria.** CLI portions of the job journey are live; Git qualification covers detached HEAD, ref movement, dirty digest, executable-bit changes, path safety and credential exclusion.

## Phase E — production image, Compose and zero-to-demo quickstart

**Objective.** Deliver one reproducible OCI image and a documented local startup path that reaches the demo journey from zero.

**Pull requests.** Promote proven probe-image assumptions into the production Dockerfile; build/install Ronin and `pyronin`; run non-root; preserve Docker socket GID handling and read-only workspace identity; add durable data volume, server health dependency, worker topology, immutable base-image identity, clean-room install smoke and quickstart.

**Exit criteria.** `docker compose up -d` is healthy under the product budget; quickstart completes on a clean host; image runs server and worker without privileged web/control-plane Docker access; crash-acceptance worker uses explicit `restart: "no"`.

## Phase F — incremental acceptance activation

**Objective.** Turn skips live as soon as dependencies exist while making regression-to-skip fail closed in Docker Qualification.

**Activation order.**

1. `doctor`, `validate`, `plan` after D0.
2. Compose health after Phase E.
3. submit/status/idempotency/SDK after the supported Phase C/D1 path.
4. logs/evidence after Run-global event ordering and #53 portable evidence references are real.
5. execute/crash/reclaim/resume through the supported product journey while preserving already-qualified Phase-B semantics.
6. cancel cleanup once cancellation/container cleanup are exercised through the supported operator path.

**Exit criteria.** Every activation removes that step from the exact Docker skip allowance in the same change. A newly skipped previously-live step or stale allowance fails qualification. Strict release ultimately reports all fifteen required steps live and passed.

## Phase G — non-functional and release qualification

**Objective.** Qualify the exact implementation against product budgets and trust requirements rather than inferring readiness from unit tests.

**Status.** #125 contention qualification is complete. Continue qualifying remaining product budgets as supported surfaces land: compose health, RSS, full `make check`, security/secret/vulnerability/license qualification, deterministic demo/evidence output and targeted recovery cases. Release-gating tooling remains release-critical and must meet #102 coverage expectations.

## Phase H — release candidate and v0.1.0

**Objective.** Stabilize only: documentation, clean-room verification, compatibility checks, release notes and immutable publication.

**Status. Not started.** Tag/publish only after strict 15/15 acceptance, remaining P0/P1 release blockers, immutable image/package provenance, version synchronization and required process protections are resolved.

## Current critical path

Acceptance truth wiring and C0 storage contracts are complete and are no longer selectable unless regression reopens them. The current ordering is:

1. D0 local CLI (`doctor`, `validate`, `plan`, console entry point);
2. #54 list/cancel/events + executable OpenAPI/SDK contract using the completed C0 pagination/event semantics;
3. #53 portable evidence identity before `/evidence` ships;
4. #54 evidence completion plus D1 network/operator CLI;
5. production image/Compose;
6. incremental completion of the frozen fifteen-step journey with the Docker allowance shrinking to empty;
7. remaining non-functional/security/release blockers and immutable publication.

#125 is complete and is no longer an eligible critical-path slice unless its acceptance criteria change or a regression reopens it. This ordering does not authorize parallel Builder PRs: each autonomous run must finish/reconcile its own prior work before selecting the next slice.

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

E3-E10 remain frozen until v0.1 ships: data engineering, streaming/reliability, catalog/governance/BI, data science/MLOps, GenAI/RAG, agents, enterprise operations and ecosystem/maturity work are not eligible autonomous slices before the v0.1 release.
