# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

## Completed foundation carried into v0.1

E0/E1 already provide deterministic core/project/runtime/operator/diagnostic/notebook/kernel contracts, restart-safe single-writer execution evidence, hardened and real-engine-qualified Docker execution, async execution ports, 100% line/branch coverage on the original gated packages, and repository secret/dependency qualification. `docs/automation/PROGRESS.md` retains the historical publication record; dated progress supplements may record later qualification milestones without rewriting that long-form history.

Week 1 is complete on current main. PRs #105-#116 closed the runner reap/truncation, Docker resource-limit, tested-isolation, runtime-version, async-sink, redacted failure-context, core property/performance, SDK retry/transport, and repository-URI secret-boundary work. Do not reimplement those slices.

## Durable execution spine status

The Week-2 storage foundation is already on `main`: pure Job -> Run -> Attempt lifecycle and `JobStore`, SQLite plus in-memory adapters/migrations, shared conformance and concurrent fencing qualification, immutable per-cell resume identity, and the bounded async `JobStore` composition boundary. The closed #91 contract must not be selected again.

PR #128 completed the first Week-3 control-plane composition increment: server submit/status/cancel plus worker reclaim/claim/heartbeat route through the bounded async durable-store facade. PR #131 then fenced worker-originated event/result/evidence/terminal writes by active Attempt lease, and PR #132 added safe worker project/runtime preparation plus transitive execution identities. Do not select those slices again.

The durable worker has the per-cell execution/restart seam: sequential execution checkpoints content-addressed evidence and the cell result before advancing; cancellation is polled between cells; heartbeat ownership loss is fail closed; heartbeat tasks are cancelled and awaited; replacement Attempts reuse only identity-matching cells whose artifact is explicitly verified; corrupt deterministic artifacts are repaired only by valid re-execution. Blocking JobStore and artifact operations use bounded async facades rather than an event-loop thread or unbounded executor queue.

The local worker runtime composition is wired through the same durable spine. PR #135 made the canonical demo valid for clean per-cell containers and qualified the complete five-cell demo through `LocalWorkerRuntime -> SQLite -> DockerContainerKernelExecutor`. PR #137 added the continuous worker poll loop. Process-crash qualification proves a separate worker process can execute three real-Docker cells, die non-gracefully, preserve the production 30-second lease, and be replaced by a worker that reclaims the same Run, reuses exactly three verified cells, executes the remaining two, and reaches one terminal success.

#125 is complete across bounded async structure, real SQLite/local-artifact contention, authenticated HTTP POST/GET p95 budgets under bounded contention, and final `LocalWorkerRuntime` heartbeat/reclaim/artifact qualification at the unchanged production lease/heartbeat settings. Do not select #125 again unless regression or changed acceptance criteria reopen it.

## Acceptance truth, C0 storage and D0 CLI status

Release acceptance truth is unified: Docker Qualification is the authoritative capable environment for steps 6-9, emits exact-SHA JUnit/provenance, and enforces an exact named skip allowance. The allowance is a ratchet: newly skipped live steps and stale allowances both fail. Strict release remains unchanged at 15/15 with an empty allowance.

C0 storage contracts are complete in this construction sequence. Canonical durable event identity remains `(attempt_id, sequence)`, while bounded service-ready pages expose dense Run-global sequence ordered by `(attempt.ordinal, sequence)`. Event polling uses opaque versioned Run-bound keyset cursors, avoiding historical materialization and OFFSET. Job listing uses newest-first keyset pagination over `(created_at DESC, job_id DESC)` with defensive opaque cursors bound to active filters. In-memory and SQLite adapters share qualification for concurrent inserts, timestamp ties, replacement Attempts, empty polling, resumed polling, malformed cursors and cross-Run rejection.

D0 is also complete on current main: the supported `ronin` console entry point provides HTTP-independent `doctor`, `validate`, and `plan`, and frozen acceptance steps 2-4 are live. Current frozen acceptance is therefore seven live steps (2,3,4,6,7,8,9) and eight exact skips (1,5,10,11,12,13,14,15).

Do not select acceptance-truth wiring, C0, D0, or #125 again unless a regression or changed contract reopens them.

## Current critical path

Select one coherent slice at a time in this order:

1. **#54 — remaining HTTP/OpenAPI/SDK contract.** Continue the frozen `/v1/jobs` surface over `DurableExecutionService` using the completed C0 semantics. The current C1 increment adds stable list/cancel plus executable OpenAPI/SDK coverage. The next #54 increment is Run-global events, with #52 considered before authorization semantics are frozen. Keep framework/model types at the boundary and preserve the vendor-neutral domain.
2. **#53 — portable evidence references before `/evidence`.** Unify kernel/storage/API evidence identity before the public evidence endpoint hardens that representation.
3. **#54 evidence completion + D1 operator surface.** Expose evidence only after #53, finish SDK drift/error/retry alignment, then implement `serve`, `worker`, `submit`, `status`, `logs`, `evidence`, and `cancel` over supported product paths, including remaining Git revision/dirty identity qualification.
4. **Production image + Compose.** Promote qualified probe assumptions into the real image/topology, including non-root execution, Docker socket GID handling, read-only workspace identity, durable data volume, health dependency, sibling-container execution and explicit `restart: "no"` for crash-acceptance workers.
5. **#57 — complete the frozen fifteen-step v0.1 journey.** Activate acceptance steps incrementally as capabilities land; keep #57 open until the entire frozen journey executes and passes in the authoritative qualification context.
6. **Release blockers and publication.** Close remaining trust/process blockers, empty the acceptance skip allowance, require strict 15/15 exact-SHA evidence, enable required release protections, bump versions consistently, tag, publish immutable artifacts, and smoke published artifacts by digest/version.

### Worker execution invariants

Every remaining worker/runtime slice must preserve all of these:

- Persist successful cell result/evidence before the next cell starts; end-of-run batching is not resume-safe.
- Every worker-originated durable write is fenced by the active Attempt lease; stale or expired workers must fail before mutating events, results, evidence or terminal state.
- Heartbeat ownership loss is fail closed: cancel active execution and do not complete the attempt.
- Cancellation is checked between cells and must not wait for all remaining cells.
- Heartbeat tasks are always cancelled and awaited on exit.
- Resume requires both matching immutable cell identity and verified artifact availability/digest.
- Attempt replacement reuses the same logical Run and must not replay valid completed cells.
- Blocking durable-store and artifact operations remain outside the event-loop thread with bounded admission/backpressure.
- Clean per-cell execution containers must not make notebook correctness depend on container-local transient state surviving across cells.
- Process-crash qualification preserves the production lease TTL rather than shortening it for CI.

### Environment proof required before production Compose

The Docker-host assumptions must be proved on GitHub-hosted Linux runners: supplementary Docker socket GID, cross-uid read-only Git workspace, server health dependency, sibling-container launch, identical absolute workspace path, and explicit `restart: "no"` for the crash-acceptance worker. Execution containers receive source through stdin and return output through stdout/stderr; they do not inherit worker-internal mounts.

### Contract corrections carried into implementation

- Storage event identity is `(attempt_id, sequence)`; the service/API projection exposes dense Run-global sequence ordered by `(attempt.ordinal, sequence)`.
- Event polling is bounded and keyset-based with opaque Run-bound `since`/`next_since` cursors.
- Job listing is stable newest-first keyset pagination over `(created_at DESC, job_id DESC)`; public pagination must not regress to UUID ordering or OFFSET.
- Cancelling an unclaimed pending Run terminalizes Job and Run transactionally without waiting for a worker.
- Replaying an idempotency key is a pure read after creation, including failed/cancelled Jobs; a new Run requires a new key.
- Exhausting ten crash-replacement Attempts fails with `failure_code="attempt_limit_exceeded"`, distinct from notebook/cell failure.
- Blocking durable store calls never execute directly on an asyncio event-loop thread; bounded admission/backpressure belongs to composition rather than canonical storage semantics.
- `CellExecutionIdentity` and artifact verification are canonical; worker integration consumes that contract rather than inventing a second resume key.
- A successful heartbeat is not authorization for a later unfenced write: the durable write itself revalidates current lease ownership atomically.
- A corrupt content-addressed artifact is never reused; deterministic re-execution may atomically repair the expected digest before a new durable checkpoint is recorded.

## Acceptance activation order

Acceptance should be activated incrementally instead of replacing all skips in one change:

1. `doctor`, `validate`, `plan` once D0 is real — complete.
2. Compose health once the production image/topology is real.
3. submit/status/idempotency/SDK once the supported HTTP + OpenAPI + SDK + operator path is real.
4. logs/evidence once Run-global event ordering and portable evidence output are real.
5. execute/crash/reclaim/resume through the supported product journey, preserving already-qualified worker semantics.
6. cancel cleanup once worker cancellation and container cleanup are qualified through the supported operator path.

The exact skip allowance in Docker Qualification must shrink whenever one of these steps becomes live. Strict release remains the final authority: every frozen step executes and passes with zero skipped/xfail/failed/error/missing/unexpected outcomes.

## Frozen until v0.1 ships (2026-11-01)

Items below are out of scope by decision, not omission. See `docs/product/V01_SCOPE.md` section 3. Do not select work from this section before v0.1 is tagged.

- **E3 — Data engineering platform:** remote connectors/ingestion, codegen/source maps, pipeline scheduling, SQL/warehouse/federation, lakehouse/open-table integration and broad Git collaboration.
- **E4 — Streaming and data reliability:** streaming runtimes, checkpointing, event-time semantics, quality engines, data observability and SLAs/SLOs.
- **E5 — Catalog, governance and semantic/BI:** asset catalog, lineage graph, glossary/ontology, policy/search, semantic models, governed metrics, dashboards/reporting.
- **E6 — Data science and MLOps:** experiment systems, feature store, AutoML/HPO, model registry, serving, drift/quality monitoring and distributed training.
- **E7 — GenAI/RAG:** model/provider gateway, prompt versioning, evaluation suites, knowledge/retrieval/vector/hybrid search, safety hooks and token/cost accounting.
- **E8 — Agents:** agent runtime, tool schemas, approvals, multi-agent graphs, durable replay/resume, agent evaluation and per-step evidence/cost.
- **E9 — Enterprise operations:** Postgres/multi-node/HA, multi-tenancy, advanced RBAC/audit/compliance, DR, advanced FinOps, Kubernetes scale and air-gap lifecycle.
- **E10 — Ecosystem and maturity:** stable plugin marketplace, broad compatibility matrix, additional proprietary adapters, advanced optimization/recommendation systems and community-governance maturity work.

## Automatic cut lines

The original calendar cut lines remain release-policy guardrails, but they do not authorize weakening strict acceptance.

| Trigger | Automatic cut |
|---|---|
| Fri 18 Sep: `JobStore` fails its contract suite | `RetryPolicy.max_runs = 1` fixed. No retries in v0.1. |
| Sun 27 Sep: local end-to-end does not resume | A prerelease may document whole-run replay as a limitation; final v0.1 still requires frozen acceptance unless scope is explicitly revised. |
| Sun 4 Oct: HTTP not green | Drop optional pagination breadth first; do not silently remove frozen acceptance endpoints. |
| Sun 11 Oct: CLI not green | A prerelease may reduce optional CLI breadth; final v0.1 remains governed by `V01_SCOPE.md`. |
| Fri 16 Oct: packaging not green | A prerelease may document `docker run`; final v0.1 still requires frozen Compose acceptance unless scope is revised. |
| Mon 19 Oct: anything behind | Week 7 becomes buffer. Cut optional chaos breadth before trust, durability, security or acceptance evidence. |

Never cut the fifteen-step final v0.1 acceptance journey, a green `make check`, or the requirement to ship with no known secrets or vulnerabilities without an explicit product-scope decision.

## Operational invariant

After every publication to `main`, inspect mandatory GitHub Actions for the exact published SHA. If an increment cannot safely be made green, revert it rather than weakening a gate.
