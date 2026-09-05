# Ronin v0.1 construction plan

_Last synchronized: 2026-09-05. Scope authority: `docs/product/V01_SCOPE.md`. Target release: 2026-11-01._

The v0.1 plan is eight weeks. Each week has one objective, an explicit pull-request sequence, measurable exit criteria, and a pre-decided cut line. Work outside the frozen v0.1 scope does not enter these weeks.

## Week 1 — 7–13 September: close review defects and prepare durable-execution contracts

**Objective.** Remove the known trust/performance defects that would contaminate durable orchestration, while landing the package/gate/quality scaffolding needed for E2 work.

**Pull requests.** Execute PR-01 through PR-12 from `BACKLOG.md`: cancellation terminal evidence; runner reap/truncation; Docker limits; isolation qualification default; quality perimeter; tier gates/lock; runtime redaction/version comparison; architecture `os` closure; core performance indexes; async event sink; T1 properties; SDK resilience.

**Exit criteria.** All twelve Week-1 proving tests pass or the corresponding issue is explicitly carried with a documented blocker; `make check` is green from the hash-locked environment; no open P0 defect is unowned.

**Cut line.** Friday 18 September: if `JobStore` fails its contract suite, fix `RetryPolicy.max_runs = 1`; retries are out of v0.1.

## Week 2 — 14–20 September: transactional Job → Run → Attempt storage

**Objective.** Define the pure lifecycle/state-machine and prove a SQLite adapter against it.

**Pull requests.** Add pure lifecycle IDs/states/transitions and `JobStore` protocol in `studio_orchestrator`; add SQLite schema/migrations, WAL/FULL/foreign-key/busy-timeout setup, idempotency uniqueness and store conformance suite in `studio_storage`; add cursor-safe storage queries needed by the future API.

**Exit criteria.** Transactional create/read/update, idempotency and unique `(attempt_id, sequence)` behavior are proven under concurrent access; no clock/random/database I/O enters pure packages; migration tests pass from an empty database.

**Cut line.** The 18 September retry cut above applies automatically if the store contract is not green.

## Week 3 — 21–27 September: worker leases, crash reclamation and per-cell resume

**Objective.** Execute one durable local run through worker claim, heartbeat, lease expiry, attempt replacement and record-level resume.

**Pull requests.** Add lease/heartbeat/reclaim transitions; worker loop; durable cell-result persistence; resume selection from succeeded cell records; crash/restart integration test with the demo notebook and real Docker qualification boundary.

**Exit criteria.** Kill/restart test proves a new attempt resumes at cell 4 without re-running cells 1–3; terminal state is unique/monotonic; no residual container remains after cancellation/failure.

**Cut line.** Sunday 27 September: if local end-to-end does not resume, v0.1 re-runs the whole run after a crash and documents that limitation.

## Week 4 — 28 September–4 October: HTTP control plane and SDK contract

**Objective.** Make durable jobs remotely controllable through one bounded authenticated API whose OpenAPI contract matches `pyronin`.

**Pull requests.** Add exact-pinned FastAPI/uvicorn/pydantic in `studio_server`; bearer-token scope model; `/v1/jobs` submit/status/list/cancel/events/evidence endpoints; OpenAPI golden/contract tests; align `pyronin` schemas/errors/retry behavior.

**Exit criteria.** Acceptance steps 5 and 10–15 are live against the real server; bounded request/response/error behavior and secure token transport defaults are tested; SDK contract tests consume generated OpenAPI.

**Cut line.** Sunday 4 October: if HTTP is not green, drop cursor pagination, `/evidence`, and scopes; keep one token and the core job endpoints.

## Week 5 — 5–11 October: CLI and local Git revision capture

**Objective.** Expose the supported local workflow through `ronin` and bind execution to a reproducible local checkout revision.

**Pull requests.** Add `studio_vcs` commit + dirty digest capture; add CLI composition and `serve`, `worker`, `validate`, `plan`, `submit`, `status`, `logs`, `evidence`, `cancel`, `doctor`; enable the console entry point; document per-cell record-level resume limitations.

**Exit criteria.** Acceptance steps 2–4 and CLI portions of 5, 10–14 are live; Git qualification covers detached HEAD, ref movement, dirty digest, path safety and credential exclusion.

**Cut line.** Sunday 11 October: if CLI is not green, ship server + SDK + `serve`/`worker`/`doctor` only.

## Week 6 — 12–18 October: packaging, image, Compose and zero-to-demo quickstart

**Objective.** Deliver one reproducible OCI image and a documented local startup path that reaches the demo journey from zero.

**Pull requests.** Add production Dockerfile, image healthcheck, Compose topology, immutable base-image identity, clean-room install smoke, quickstart and release artifact provenance inputs.

**Exit criteria.** `docker compose up -d` is healthy under 60 seconds; quickstart completes under ten minutes on a clean host; image runs server and worker without privileged web/control-plane Docker access.

**Cut line.** Friday 16 October: if packaging is not green, ship Dockerfile only, no Compose, and document `docker run`.

## Week 7 — 19–25 October: acceptance, security, performance and buffer

**Objective.** Turn every remaining skipped acceptance step green and qualify release budgets/trust properties.

**Pull requests.** Activate all e2e steps; add non-functional budget tests; security/secret/vulnerability/license qualification; release provenance/SBOM; targeted chaos/recovery tests only after the acceptance journey is green.

**Exit criteria.** Fifteen acceptance steps pass; p95/event/health/RSS/`make check` budgets meet `V01_SCOPE.md`; no known secret or vulnerability ships; exact-head release evidence is reproducible.

**Cut line.** Monday 19 October: any earlier slippage consumes Week 7 as buffer. Ship without chaos tests if necessary, never without the acceptance journey.

## Week 8 — 26 October–1 November: release candidate and v0.1.0

**Objective.** Stabilize only: documentation, clean-room verification, compatibility checks, release notes, immutable release publication.

**Pull requests.** Fix release-blocking defects only; finalize quickstart/limitations/security docs; verify Python 3.11/3.12 and supported Docker path; tag and publish v0.1.0 after all gates are green.

**Exit criteria.** Clean hash-locked `make check`; all fifteen e2e steps pass; demo regenerates byte-for-byte; release artifacts have immutable provenance; `main` and release-tag protection is active; no P0/P1 release blocker remains.

**Cut line.** No feature substitution. Defer optional surfaces rather than weakening trust, reproducibility, acceptance, or security gates.

## Pre-decided automatic cuts

| Trigger | Automatic cut |
|---|---|
| Fri 18 Sep: `JobStore` fails its contract suite | `RetryPolicy.max_runs = 1` fixed. No retries in v0.1. |
| Sun 27 Sep: local end-to-end does not resume | v0.1 re-runs the whole run after a crash. Documented limitation. |
| Sun 4 Oct: HTTP not green | Drop cursor pagination, `/evidence`, and scopes. Single token. |
| Sun 11 Oct: CLI not green | Ship server + SDK + `serve`/`worker`/`doctor` only. |
| Fri 16 Oct: packaging not green | Dockerfile only, no Compose. Document `docker run`. |
| Mon 19 Oct: anything behind | Week 7 is consumed as buffer. Ship without chaos tests, never without the acceptance journey. |

**Never cut:** the fifteen-step acceptance journey, a green `make check`, and shipping with no known secrets or vulnerabilities.

## Post-v0.1 horizon, not scheduled

The former E3–E10 roadmap remains a product horizon only and is intentionally unscheduled until v0.1 is tagged.

- **E3 — Data engineering:** ingestion/connectors, codegen/source maps, pipelines, SQL, lakehouse, Git collaboration.
- **E4 — Streaming and reliability:** streaming runtimes, checkpoints, data quality/observability and SLAs/SLOs.
- **E5 — Catalog/governance/semantic BI:** catalog, lineage, glossary/ontology, policy/search, semantic models, metrics and reporting.
- **E6 — Data science/MLOps:** experiments, features, AutoML/HPO, registry, serving, monitoring and distributed training.
- **E7 — GenAI/RAG:** AI gateway, prompt/version/evaluation systems, retrieval/indexing, safety and token/cost evidence.
- **E8 — Agents:** `AgentRuntime` SPI, tools, scoped permissions, approvals, durable replay/resume, evaluation and multi-agent graphs.
- **E9 — Enterprise operations:** HA/DR, multi-tenancy, compliance, advanced FinOps, Kubernetes scale and air-gap qualification.
- **E10 — Ecosystem/maturity:** stable APIs/SDKs, plugins, compatibility matrix, reproducible releases, governance and benchmark-led optimization.

These are frozen by `BACKLOG.md`; autonomous work must not select them before v0.1 ships.
