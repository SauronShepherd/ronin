# Ronin Public v1 implementation status

**Status authority:** `docs/product/PUBLIC_V1_SCOPE.md` defines the product/release target.  
**Machine-readable ledger:** `docs/product/public-v1-status.json`.  
**Observed source head:** `b7e861f11a1399553fba0292f2b86760cc04d747` (2026-09-13).  
**Release status:** **INCOMPLETE**.

This document records implementation state only. It does not claim test execution, legal review, human decisions, release qualification or operational evidence that does not exist.

## Status vocabulary

- **implemented** — the stated foundation/path exists in source and is not known here to require another feature to perform its narrow claimed role;
- **partial** — meaningful source implementation exists, but the mandatory Public v1 family lacks an end-to-end supported path;
- **missing** — no supported implementation path exists for the mandatory capability;
- **blocked** — work/evidence cannot be truthfully completed under a current external or maintainer-controlled prerequisite;
- **human decision** — a maintainer/product/security/legal decision must be made rather than invented by implementation;
- **qualification pending** — implementation exists but current exact-head execution/release evidence does not.

## Repository-grounded capability snapshot

| Capability | Status | Current source truth |
| --- | --- | --- |
| Durable execution foundation | implemented | Job/Run/Attempt, SQLite durability, leases/heartbeat/fencing/reclaim/resume, cancellation, evidence, local/container worker, HTTP/CLI/SDK foundation |
| Workspace/project/source control | partial | workspace/project persistence, project manifest/Git identity, environment/deployment bindings; full Public v1 APIs/UI/membership remain |
| Connectors/ingestion | partial | connection/discovery/checkpoint contracts and governed local CSV/JSONL path; remote connector matrix remains |
| Lakehouse/SQL | missing | no supported Parquet/Iceberg/Delta + SQL engine path |
| Data Engineering Studio | partial | notebook/pipeline execution foundations exist; authoring APIs and Web Studio remain |
| Durable DAG scheduler | partial | durable snapshots/task runs, fenced attempts/retries/dependencies, deterministic task→Job planning, execution outbox/reconciliation, deployment-aware controller, timezone-aware durable cron, durable event inbox/delivery, cancellation, timeout enforcement, snapshot-safe bounded backfill, shared resource pools, generation-fenced leader authority, leader-guarded cron/event/backfill/controller services, bounded and continuous daemon orchestration, and group backfill cancellation exist; branching/notifications, broad operator execution, public scheduler APIs/UI, process/signal/deployment wiring and PostgreSQL multi-node HA qualification remain |
| Catalog/lineage | partial | governed assets/revisions and declared/observed lineage persistence plus explicit selected-subgraph Bundle export/planning/atomic import exist; search/glossary/classification/OpenLineage/complete asset integration remain |
| Ontology/KG | partial | object/property/link/action schema and persistence exist; instance resolution/query/materialization/actions remain |
| Graph intelligence/RQL | missing | no supported parser/planner/runtime/provider path |
| Data quality/contracts | partial | definitions/results/persistence exist; execution/gating/alerts remain |
| AI/ML/MLOps | partial | experiment/run/model/evaluation provenance exists; training/features/interop/inference/serving remain |
| GenAI/RAG/agents | partial | provider/prompt/vector/RAG/tool/agent contracts/persistence exist; runtime/evals/tool execution/cost remain |
| Semantic models/dashboards | missing | no supported compiler/metrics/dashboard runtime |
| Streaming/real-time | missing | no supported processor/checkpoint/window/table-sink path |
| Observability/alerts/FinOps | partial | execution evidence and container resource observation exist; unified telemetry/alerts/costs/budgets remain |
| Multi-user security/audit | partial | typed grants, bearer auth, transport policy, secret resolver and append-only audit foundation exist; OIDC/users/groups/service identities/role administration/full instrumentation remain |
| Local/Compose/Kubernetes | partial | local and Compose foundation exist; Kubernetes/Helm and production metadata/object-store profile remain |
| Ronin Bundle | partial | deterministic verified archive IO, semantic inventory, native project/connection round-trips with explicit runtime/secret remapping, atomic multi-object project+connection commit, and explicit catalog asset/revision/lineage selected-subgraph export/planning/atomic commit exist; workflow/quality/ontology/ML/GenAI/data/semantic assets, PostgreSQL adapters, certification and public surfaces remain |
| Fabric migration | missing | no certified adapter |
| Databricks migration | missing | no certified adapter |
| Palantir Foundry/AIP migration | missing | no certified adapter |
| Dataiku DSS migration | missing | no certified adapter |
| Web Studio | missing | no current web application tree |
| Public v1 release qualification | blocked | active Actions/current exact-head qualification absent; main remains unprotected |

## Public v1 source work merged in the current construction sequence

PRs **#242–#288** moved Public v1 from planning into source implementation. Scheduler foundations include deterministic task→Job identity/linking (#259), execution outbox/reconciliation (#260), deployment-aware controller (#262), cron/events (#263/#264), cancellation/timeouts (#265/#267), snapshot-safe backfill (#268), pools (#270), leader fencing (#271/#273), daemon orchestration (#274/#275), and group backfill cancellation (#276). Native Bundle portability added project semantic inventory/export (#278), project import planning (#279), runtime remapping plus atomic project/environment-binding commit (#280), connection round-trip with explicit secret-reference remapping (#282), deterministic dependency-ordered multi-object staging (#283), atomic project+connection commit (#285), explicit selected catalog subgraph export/planning (#287), and atomic catalog asset/revision/lineage commit (#288). PR #266 made Public v1 the active construction authority while preserving the historical v0.1 planning files verbatim.

These merges do **not** imply that their parent capability families are complete. The scheduler still lacks broad task adapters, branching/skipped semantics, durable notifications, public scheduler APIs/UI, production process/signal/deployment wiring and PostgreSQL multi-node HA qualification. Bundle support now covers project, connection, and an explicitly selected catalog subgraph, but workflow/quality/ontology/ML/GenAI and later data/semantic assets remain outside it. Catalog export intentionally does not invent whole-catalog revision discovery because the current catalog port does not expose it. PostgreSQL does not yet implement the Bundle atomic commit ports. Storage ports do not constitute a PostgreSQL backend.

## Invariants that remain mandatory

1. **Canonical identity:** semantic IDs use versioned canonical contracts; physical locators, credentials and ephemeral worker state do not silently enter logical identity.
2. **Durability:** logical retries do not duplicate Job/Run meaning; state transitions are persisted before dependent completion claims.
3. **Fencing:** stale workers/controllers cannot commit authoritative state after lease loss.
4. **Checkpoint safety:** ingestion/stream checkpoints advance only after governed output commit.
5. **Secrets:** portable state stores references only; resolution happens at an authorized execution/deployment edge.
6. **Storage portability:** SQLite remains a supported local adapter while production backends must preserve the same service semantics.
7. **Security:** authorization is typed and resource-scoped; unsupported constraints fail closed; UI never replaces server-side enforcement.
8. **Migration honesty:** every source object is classified as exact, translated, partial, passthrough, unsupported or manual-decision; nothing is silently dropped or upgraded semantically.
9. **Evidence honesty:** implementation presence is not CI/release qualification, and historical evidence is not current-head evidence.

## Human-decision / blocked work

- **#50:** runtime capability namespace/value/ambiguity and dispatch-time binding semantics.
- **#62:** language-neutral runner protocol family and compatibility semantics.
- **#45:** choose and verify a real private vulnerability reporting path before publishing a security policy that points to it.
- **License/NOTICE/attribution:** tooling may inventory facts; maintainers/legal review own conclusions.
- **#199 and dependent release issues:** automated qualification is currently disabled and must not be silently re-enabled or treated as executed evidence.
- **#63:** repository/ref protection is an administrative release-gate action after required checks are restored.

## Updated critical path

1. Keep this ledger and the active construction plan synchronized with repository truth.
2. Finish scheduler broad task adapters, branching/notifications, public scheduler APIs/UI, process/deployment wiring and PostgreSQL HA semantics/qualification.
3. Extend native Bundle support to the next executable canonical metadata family, preferring workflow/pipeline persistence if its canonical snapshot/store contracts preserve identity without deployment locators; then quality/ontology/ML/GenAI as their contracts permit.
4. Complete store ports for remaining domains; then implement PostgreSQL adapters and an S3-compatible artifact store without changing logical references.
5. Implement the first open data path: Arrow/Parquet + reference open table profile + reference SQL engine, with catalog/lineage/quality hooks.
6. Complete remote connectors and safe incremental checkpoint execution.
7. Expand the Public v1 API and begin Web Studio against documented/generated clients.
8. Complete quality runtime, ontology/KG actions/query, RQL, ML, GenAI, semantic/dashboard, streaming, observability/alerts/FinOps and multi-user identity.
9. Add Kubernetes/Helm after the server metadata/object-store/identity profile is real.
10. Build the four vendor migration profiles only against executable canonical target capabilities and certify them with exhaustive migration reports.
11. Restore and run exact-candidate qualification only when authorized; Public v1 remains incomplete until every mandatory family has its supported end-to-end path.

## Historical v0.1 planning documents

The earlier v0.1 construction plan and backlog are preserved verbatim under `docs/automation/history/`. They remain useful evidence for the execution foundation and historical qualification baseline, but they are not current feature-selection authority. Active `docs/automation/CONSTRUCTION_PLAN.md` and `BACKLOG.md` derive scope from `PUBLIC_V1_SCOPE.md` rather than the superseded v0.1 feature freeze.
