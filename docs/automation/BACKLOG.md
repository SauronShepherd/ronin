# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

## Completed foundation carried into v0.1

E0/E1 already provide deterministic core/project/runtime/operator/diagnostic/notebook/kernel contracts, restart-safe single-writer execution evidence, hardened and real-engine-qualified Docker execution, async execution ports, 100% line/branch coverage on the original gated packages, and repository secret/dependency qualification. `docs/automation/PROGRESS.md` retains the historical publication record; dated progress supplements may record later qualification milestones without rewriting that long-form history.

Week 1 is complete on current main. PRs #105-#116 closed the runner reap/truncation, Docker resource-limit, tested-isolation, runtime-version, async-sink, redacted failure-context, core property/performance, SDK retry/transport, and repository-URI secret-boundary work. Do not reimplement those slices.

## Durable execution spine status

The Week-2 storage foundation is already on `main`: pure Job -> Run -> Attempt lifecycle and `JobStore`, SQLite plus in-memory adapters/migrations, shared conformance and concurrent fencing qualification, immutable per-cell resume identity, and the bounded async `JobStore` composition boundary. The closed #91 contract must not be selected again.

PR #128 completed the first Week-3 control-plane composition increment: server submit/status/cancel plus worker reclaim/claim/heartbeat route through the bounded async durable-store facade. PR #131 then fenced worker-originated event/result/evidence/terminal writes by active Attempt lease, and PR #132 added safe worker project/runtime preparation plus transitive execution identities. Do not select those slices again.

The durable worker now has the first per-cell execution/restart seam: sequential execution checkpoints content-addressed evidence and the cell result before advancing; cancellation is polled between cells; heartbeat ownership loss is fail closed; heartbeat tasks are cancelled and awaited; replacement Attempts reuse only identity-matching cells whose artifact is explicitly verified; corrupt deterministic artifacts are repaired only by a valid re-execution. Blocking JobStore and artifact operations use bounded async facades rather than an event-loop thread or unbounded executor queue.

The local worker runtime composition is now wired through the same durable spine. PR #135 made the canonical demo valid for clean per-cell containers and qualified the complete five-cell demo through `LocalWorkerRuntime -> SQLite -> DockerContainerKernelExecutor` with the real Docker command path, including durable terminal state and cell-result evidence. PR #137 added the continuous worker poll loop with interruptible idle waits, signal-driven shutdown, unique Attempt/lease identities per poll, Attempt-limit continuity, and immediate fenced abandonment of an active claim on graceful shutdown. The process-crash qualification that follows proves the missing abrupt-failure path: a separate worker process executes three real-Docker cells and checkpoints them, is killed non-gracefully before the fourth Docker launch, the real 30-second lease expires, and a replacement process reclaims the same Run, reuses exactly those three verified cells, executes only the remaining two, and reaches one successful terminal result. This advances #57 but does not complete the frozen fifteen-step product journey or the HTTP/SDK/operator/Compose surfaces.

#125 is now complete when combined across its landed qualification slices: bounded async store/artifact structure, real SQLite/local-artifact contention, real authenticated HTTP POST/GET p95 budgets under bounded SQLite contention, and final `LocalWorkerRuntime` heartbeat/reclaim/artifact call-site qualification at the unchanged production 30-second lease and 10-second heartbeat settings. Do not select #125 again unless a regression or changed acceptance criterion reopens it.

Current critical-path work now moves beyond the contention prerequisite. Select one coherent slice at a time in this order:

1. **#54 — HTTP/OpenAPI/SDK contract.** Continue the frozen `/v1/jobs` surface over `DurableExecutionService`. Keep HTTP framework/model types at the boundary and preserve the canonical vendor-neutral domain. The implementation may use the standard library or a pinned framework, but the OpenAPI contract, SDK behavior and route coverage must be executable and drift-tested.
2. **CLI / local operator surface.** Implement `serve`, `worker`, `doctor`, `validate`, `plan`, `submit`, `status`, `logs`, `evidence`, and `cancel`; enable the `ronin` console entry point only when `studio_cli:main` is real and tested.
3. **Production image + Compose.** Promote the qualified probe assumptions into the real image/topology, including non-root execution, Docker socket GID handling, read-only workspace identity, durable data volume, health dependency, sibling-container execution and `restart: "no"` for crash-acceptance workers.
4. **#53 — portable evidence references.** Unify kernel/storage/API evidence identity before the external evidence representation hardens.
5. **#57 — complete the frozen fifteen-step v0.1 journey.** Activate acceptance steps incrementally as their capabilities land; strict release qualification remains fail closed and is not replaced by progress telemetry. Keep #57 open until the whole frozen journey, including API/SDK/idempotency/logs/evidence/cancel/Compose/operator steps, actually executes and passes.
6. **Release qualification and publication.** Only after all fifteen acceptance steps execute and pass, run the full release-quality perimeter, enable required release protections, bump versions consistently, tag, publish immutable artifacts, and smoke the published artifacts by digest/version.

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
- Clean per-cell execution containers must not make notebook correctness depend on container-local transient state surviving across cells; the canonical v0.1 demo is now deliberately self-contained per cell.
- Process-crash qualification must preserve the production lease TTL rather than shorten it merely to make CI faster.

### Environment proof required before production Compose

The Docker-host assumptions must be proved on GitHub-hosted Linux runners: supplementary Docker socket GID, cross-uid read-only Git workspace, server health dependency, sibling-container launch, identical absolute workspace path, and explicit `restart: "no"` for the crash-acceptance worker. Execution containers receive source through stdin and return output through stdout/stderr; they do not inherit worker-internal mounts.

### Contract corrections carried into implementation

- Storage event identity is `(attempt_id, sequence)`; the API exposes a dense Run-global sequence ordered by `(attempt.ordinal, sequence)`.
- Cancelling an unclaimed pending Run terminalizes Job and Run transactionally without waiting for a worker.
- Replaying an idempotency key is a pure read after creation, including for failed/cancelled Jobs; a new Run requires a new key.
- Exhausting ten crash-replacement Attempts fails with `failure_code="attempt_limit_exceeded"`, distinct from notebook/cell failure.
- Blocking durable store calls never execute directly on an asyncio event-loop thread; bounded admission/backpressure is part of composition rather than canonical storage semantics.
- `CellExecutionIdentity` and artifact verification are canonical; worker integration consumes that contract rather than inventing a second resume key.
- A successful heartbeat is not authorization for a later unfenced write: the durable write itself must revalidate current lease ownership atomically.
- A corrupt content-addressed artifact is never reused; deterministic re-execution may atomically repair the expected digest before a new durable checkpoint is recorded.

## Acceptance activation order

Acceptance should be activated incrementally instead of replacing all skips in one change:

1. Compose health once the production image/topology is real.
2. `doctor`, `validate`, `plan` once the CLI surface is real.
3. submit/status/idempotency/SDK once HTTP + OpenAPI + SDK are real.
4. logs/evidence once run-global event ordering and portable evidence output are real.
5. execute/crash/reclaim/resume once the process-level durable worker path is wired into the frozen product journey.
6. cancel cleanup once worker cancellation and container cleanup are qualified through the supported operator path.

The strict release gate remains the final authority: every frozen step must execute and pass with zero skipped/xfail/failed/error/missing/unexpected outcomes.

## Frozen until v0.1 ships (2026-11-01)

Items below are out of scope by decision, not by omission. See `docs/product/V01_SCOPE.md` section 3. Do not select work from this section before v0.1 is tagged.

- **E3 — Data engineering platform:** remote connectors/ingestion, codegen/source maps, pipeline scheduling, SQL/warehouse/federation, lakehouse/open-table integration and broad Git collaboration.
- **E4 — Streaming and data reliability:** streaming runtimes, checkpointing, event-time semantics, quality engines, data observability and SLAs/SLOs.
- **E5 — Catalog, governance and semantic/BI:** asset catalog, lineage graph, glossary/ontology, policy/search, semantic models, governed metrics, dashboards/reporting.
- **E6 — Data science and MLOps:** experiment systems, feature store, AutoML/HPO, model registry, serving, drift/quality monitoring and distributed training.
- **E7 — GenAI/RAG:** model/provider gateway, prompt versioning, evaluation suites, knowledge/retrieval/vector/hybrid search, safety hooks and token/cost accounting.
- **E8 — Agents:** agent runtime, tool schemas, approvals, multi-agent graphs, durable replay/resume, agent evaluation and per-step evidence/cost.
- **E9 — Enterprise operations:** Postgres/multi-node/HA, multi-tenancy, advanced RBAC/audit/compliance, DR, advanced FinOps, Kubernetes scale and air-gap lifecycle.
- **E10 — Ecosystem and maturity:** stable plugin marketplace, broad compatibility matrix, additional proprietary adapters, advanced optimization/recommendation systems and community-governance maturity work.

## Automatic cut lines

The original calendar cut lines remain release-policy guardrails, but they do not authorize weakening strict acceptance. If a capability is cut from a prerelease, it must be explicitly documented as a limitation and the artifact must not be represented as the completed v0.1 MVP.

| Trigger | Automatic cut |
|---|---|
| Fri 18 Sep: `JobStore` fails its contract suite | `RetryPolicy.max_runs = 1` fixed. No retries in v0.1. |
| Sun 27 Sep: local end-to-end does not resume | A prerelease may document whole-run replay as a limitation; final v0.1 still requires the frozen acceptance contract unless product scope is explicitly revised. |
| Sun 4 Oct: HTTP not green | Drop cursor pagination first; do not silently remove frozen acceptance endpoints without an explicit scope decision. |
| Sun 11 Oct: CLI not green | A prerelease may ship server + SDK + minimal operational commands; final v0.1 remains governed by `V01_SCOPE.md`. |
| Fri 16 Oct: packaging not green | A prerelease may document `docker run`; final v0.1 still requires the frozen Compose acceptance step unless scope is explicitly revised. |
| Mon 19 Oct: anything behind | Week 7 becomes buffer. Cut optional chaos breadth before trust, durability, security or acceptance evidence. |

Never cut the fifteen-step final v0.1 acceptance journey, a green `make check`, or the requirement to ship with no known secrets or vulnerabilities without an explicit product-scope decision. A release/tag workflow may report progress separately, but it must not publish v0.1 artifacts unless strict acceptance proves all fifteen required steps executed and passed.

## Operational invariant

After every publication to `main`, inspect mandatory GitHub Actions for the exact published SHA. If the increment cannot safely be made green, revert it rather than weakening a gate.
