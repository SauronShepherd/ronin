# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

## Completed foundation carried into v0.1

E0/E1 already provide deterministic core/project/runtime/operator/diagnostic/notebook/kernel contracts, restart-safe single-writer execution evidence, hardened and real-engine-qualified Docker execution, async execution ports, 100% line/branch coverage on the original gated packages, and repository secret/dependency qualification. `docs/automation/PROGRESS.md` retains the detailed publication history.

Week 1 is complete on current main. PRs #105-#116 closed the runner reap/truncation, Docker resource-limit, tested-isolation, runtime-version, async-sink, redacted failure-context, core property/performance, SDK retry/transport, and repository-URI secret-boundary work. Do not reimplement those slices.

## Next — Week 2 durable execution spine

Select these items in dependency order. The environment proof may run in parallel because it claims only infrastructure files.

1. **#99 / 49a — pure Job -> Run -> Attempt lifecycle and `JobStore` Protocol.** `studio_orchestrator` remains pure; concurrency primitives do not enter this package. Crash reclaim replaces an abandoned Attempt within the same Run, outside ordinary retry budget; `max_runs=1`, attempt cap 10.
2. **#100 / 49b — SQLite `JobStore` and migrations.** `studio_storage` owns both `SqliteJobStore` and the concurrent `InMemoryJobStore` reference adapter. Enforce WAL, `foreign_keys=ON`, `synchronous=FULL`, `busy_timeout=5000`, durable idempotency, lease fencing and reclaim.
3. **#101 / 49c — store conformance and concurrent claim qualification.** Run one parameterized contract suite against both adapters and prove one-winner claiming under bounded contention.
4. **#91 — immutable per-cell resume identity.** Persist results after every cell and reuse only when the frozen Run identity and referenced artifact digests still verify.
5. **#57 — accelerated vertical v0.1 path.** As the storage contract stabilizes, compose worker, API, CLI and Docker/Compose in parallel domains and turn acceptance steps live incrementally rather than in one final batch.

### Environment proof required before production Compose

The Docker-host assumptions must be proved early on GitHub-hosted Linux runners: supplementary Docker socket GID, cross-uid read-only Git workspace, server health dependency, sibling-container launch, identical absolute workspace path, and explicit `restart: "no"` for the crash-acceptance worker. Execution containers receive source through stdin and return output through stdout/stderr; they do not inherit worker-internal mounts.

### Contract corrections carried into implementation

- Storage event identity is `(attempt_id, sequence)`; the API exposes a dense Run-global sequence ordered by `(attempt.ordinal, sequence)`.
- Cancelling an unclaimed pending Run terminalizes Job and Run transactionally without waiting for a worker.
- Replaying an idempotency key is a pure read after creation, including for failed/cancelled Jobs; a new Run requires a new key.
- Exhausting ten crash-replacement Attempts fails with `failure_code="attempt_limit_exceeded"`, distinct from notebook/cell failure.

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

| Trigger | Automatic cut |
|---|---|
| Fri 18 Sep: `JobStore` fails its contract suite | `RetryPolicy.max_runs = 1` fixed. No retries in v0.1. |
| Sun 27 Sep: local end-to-end does not resume | v0.1 re-runs the whole run after a crash. Documented limitation. |
| Sun 4 Oct: HTTP not green | Drop cursor pagination, `/evidence`, and scopes. Single token. |
| Sun 11 Oct: CLI not green | Ship server + SDK + `serve`/`worker`/`doctor` only. |
| Fri 16 Oct: packaging not green | Dockerfile only, no Compose. Document `docker run`. |
| Mon 19 Oct: anything behind | Week 7 becomes buffer. Ship without chaos tests, never without the acceptance journey. |

Never cut the fifteen-step acceptance journey, a green `make check`, or the requirement to ship with no known secrets or vulnerabilities. A release/tag workflow may report progress separately, but it must not publish v0.1 artifacts unless strict acceptance proves all fifteen required steps executed and passed.

## Operational invariant

After every publication to `main`, inspect mandatory GitHub Actions for the exact published SHA. If the increment cannot safely be made green, revert it rather than weakening a gate.
