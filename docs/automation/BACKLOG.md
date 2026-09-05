# Autonomous build backlog

This backlog is deliberately narrow for v0.1. Selection must be revalidated against current `main`, open Builder work, canonical automation handoffs, and the scope authority in `docs/product/V01_SCOPE.md`.

## Completed foundation carried into v0.1

E0/E1 already provide deterministic core/project/runtime/operator/diagnostic/notebook/kernel contracts, restart-safe single-writer execution evidence, hardened and real-engine-qualified Docker execution, async execution ports, 100% line/branch coverage on the original gated packages, and repository secret/dependency qualification. `docs/automation/PROGRESS.md` retains the detailed publication history.

The P1 analyst handoffs #68 and #94 identified the same remaining false-negative edge in pull-request secret qualification: an intermediate candidate commit could introduce a detector-triggering value and later remove it before the final tree scan. PR #97 hardens the existing qualification by scanning the protected base history, the complete pull-request candidate range, and the current tree, with temporary multi-commit negative and clean conformance repositories. This security correction is additive and does not change the frozen Week-1 product queue below.

## Next

Exactly these twelve Week-1 items are selectable. Do not select work outside this list until it is rewritten by a later approved phase/week transition.

1. **PR-01 — N1: terminal evidence on task cancellation.** Proving test: `tests/test_kernel_session_task_cancellation.py::test_task_cancellation_terminalizes_durable_attempt_and_propagates`. Current main already contains the fix; retain as completed evidence and do not reimplement.
2. **PR-02 — N3/N2: reap in `finally`; keep prefix on truncation.** Proving tests: `tests/test_runners.py::test_broken_stdin_reaps_process` and `tests/test_runners.py::test_truncation_keeps_prefix`.
3. **PR-03 — N8: `--memory-swap`, `--ulimit`; require memory unit.** Proving test: `tests/integration/test_docker_container_executor_real.py::test_real_docker_memory_swap_capped`.
4. **PR-04 — N4: default minimum qualification `tested`; wire real evidence.** Proving test: `tests/test_kernel_session.py::test_declared_isolation_rejected_by_default`.
5. **PR-05 — N5/Q6: quality perimeter includes `packages` and `docker`.** Proving command: `make check` with those paths present in format/lint/type/test configuration. Phase 7 prepares most of this item.
6. **PR-06 — ADR-V01-003: tiered coverage, nightly mutation, Python 3.12 matrix, lockfile.** Proving evidence: CI green in the new shape. Phase 7 prepares most of this item.
7. **PR-07 — B8/B6: redacted exception message; PEP 440 comparator.** Proving test: `tests/test_runtime_profiles.py::test_databricks_lts_version_resolves`.
8. **PR-08 — N11: remove the pure-domain `os` exemption and update the matrix.** Proving test: `tests/test_architecture_contracts.py::test_gate_rejects_low_level_os_calls`. Phase 6 delivers this item.
9. **PR-09 — Performance: port index, `bisect` without rebuild, catalog indexes.** Proving suite: `tests/perf/test_budgets.py`.
10. **PR-10 — N10: async event sink protocol.** Proving test: `tests/test_kernel_session.py::test_sink_does_not_block_loop`.
11. **PR-11 — T1 property tests: round-trip, strict JSON, identity, determinism.** Proving evidence: four named invariant/property tests pass under the T1 gate.
12. **PR-12 — N6/N7/N12: SDK structured errors, pooling, backoff, token guard.** Proving test: `packages/pyronin/tests/test_client.py::test_client_retries_with_backoff`.

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

Never cut the fifteen-step acceptance journey, a green `make check`, or the requirement to ship with no known secrets or vulnerabilities.

## Operational invariant

After every publication to `main`, inspect mandatory GitHub Actions for the exact published SHA. If the increment cannot safely be made green, revert it rather than weakening a gate.
