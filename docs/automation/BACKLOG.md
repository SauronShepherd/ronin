# Ronin Public v1 autonomous build backlog

_Last synchronized: 2026-09-13 from main `69ee645e7b6fe90bf218a6a019595d382424fcf8` after PR #265. Scope authority: `docs/product/PUBLIC_V1_SCOPE.md`._

This backlog is the active implementation-selection surface for Public v1. The previous narrow v0.1 backlog is preserved verbatim at `docs/automation/history/V01_BACKLOG.md` and is historical evidence only.

## Selection rules

- Revalidate current `main`, open PRs/issues, tree and normative product contracts before selecting work.
- Select one coherent implementation slice with explicit dependencies and compatibility impact.
- Preserve canonical identity, durability, fencing, checkpoint, secret, storage, authorization and compatibility invariants.
- Do not select blocked qualification, repository administration, credentials, legal conclusions or human architecture/security decisions as if they were ordinary implementation tasks.
- Do not claim tests, CI, benchmarks, release evidence or migration certification that were not actually executed.
- Public v1 remains incomplete while any mandatory capability family lacks an end-to-end supported path.

## P0 — planning truth

- Keep `PUBLIC_V1_IMPLEMENTATION_STATUS.md`, `public-v1-status.json`, this backlog and `CONSTRUCTION_PLAN.md` synchronized with current main.
- Treat old v0.1 freeze statements as historical, not as current feature-selection authority.

## P5 — scheduler next

- Timeout enforcement using existing TaskPolicy timeout plus linked Job cancellation.
- Durable resource pools and workspace/project/workflow concurrency accounting.
- Deterministic backfill requests that do not mutate normal schedule cursors.
- Broader task execution adapters: SQL, connector sync, quality, code, ML, GenAI, graph/RQL, semantic refresh and notifications.
- Explicit branching/skipped semantics if required by the final scheduler contract.
- Durable failure notifications.
- Continuous scheduler daemon and database-backed leader fencing/HA.

Cancellation propagation landed in PR #265 and should be preserved as the reference cancellation boundary: scheduler state first, stale attempt fencing, unpublished intent retirement, existing Job cancellation and terminal reconciliation.

## Portability

- Complete Ronin Bundle semantic inventory/export.
- Add import planning, deterministic identity mapping, collision detection, staged mutation, binding resolution and atomic commit.
- Certify Ronin-native Bundle round-trip before vendor profiles.

## Data plane

- Arrow/Parquet interchange.
- Reference open table lifecycle using Iceberg; documented Delta compatibility subset.
- SQL engine protocol and local reference engine.
- PostgreSQL, JDBC, S3-compatible, Azure-compatible and HTTP connectors.
- Fenced/CAS incremental checkpoints committed after governed output.

## Engineering and governance

- Data Engineering Studio backend assets and scheduler-backed execution.
- Catalog search/glossary/ownership/classification/OpenLineage.
- Quality rule execution and blocking/nonblocking enforcement.
- Public-v1 route modularization and generated-client Web Studio foundation.

## Semantic/AI/runtime families

- Ontology interfaces, instances, links and governed actions.
- Freeze RQL v1 grammar/AST; native graph executor and provider conformance.
- Semantic models, reusable metrics and dashboards.
- ML features/training/tracking/MLflow/inference/serving.
- GenAI providers, embeddings/vector stores, RAG/evaluation/agents/tool execution.
- Streaming sources/windows/sinks/checkpoints and scheduler-event integration.

## Operations/security/deployment

- OpenTelemetry-compatible telemetry normalization.
- Alert state engine, webhook/SMTP notification adapters.
- FinOps usage/cost records, budgets and policies with actual-vs-estimate provenance.
- OIDC users/groups/service identities mapped to typed grants; classification-aware governance and full audit.
- Remaining store ports, PostgreSQL adapters and S3-compatible ArtifactStore.
- Server Compose profile, Kubernetes/Helm, scheduler HA and backup/restore.

## Migration profiles

Implement only after the relevant canonical target capability executes end to end:

- Microsoft Fabric.
- Databricks.
- Dataiku DSS.
- Palantir Foundry/AIP, especially after ontology/action runtime is real.

Every migration profile must inventory read-only, classify every source object exactly once, translate honestly, emit binding requests instead of credentials, execute its certified subset in Ronin and export/reimport through Ronin Bundle.

## Blocked / human-owned

- #199 automated qualification and dependent exact-candidate release evidence.
- #45 private vulnerability-reporting route.
- #50 runtime capability namespace/value/ambiguity semantics.
- #62 language-neutral runner protocol.
- License/NOTICE/attribution approval.
- #63 branch/ref protection administration.
- Vendor credentials.

## Definition of ready for merge

A code-only slice may be reviewed and merged under current repository policy when current-main freshness, architecture/contract compatibility, security/durability implications and complete static diff review are satisfactory. Committed tests are source coverage, not executed evidence while automation remains disabled. Any slice whose correctness materially depends on unavailable execution evidence must state that limitation rather than fabricating a pass claim.
