# Ronin Public v1 implementation status

**Status authority:** `docs/product/PUBLIC_V1_SCOPE.md` defines the product/release target.  
**Machine-readable ledger:** `docs/product/public-v1-status.json`.  
**Observed source head:** `f16a2129d1d07efae0bd778884f50f4bbf62f590` (2026-09-13).  
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
| Catalog/lineage | partial | governed assets/revisions and declared/observed lineage exist; search/glossary/classification/interoperability remain |
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
| Ronin Bundle | partial | canonical manifest/migration semantics, deterministic verified archive IO, semantic inventory for native projects, bounded verified import planning, explicit runtime binding resolution, create/no-op/collision classification and atomic project+environment-binding commit exist; broader asset inventory/import, native round-trip certification and public surfaces remain |
| Fabric migration | missing | no certified adapter |
| Databricks migration | missing | no certified adapter |
| Palantir Foundry/AIP migration | missing | no certified adapter |
| Dataiku DSS migration | missing | no certified adapter |
| Web Studio | missing | no current web application tree |
| Public v1 release qualification | blocked | active Actions/current exact-head qualification absent; main remains unprotected |

## Public v1 source work merged in the current construction sequence

PRs **#242–#280** moved Public v1 from planning into source implementation. Later scheduler slices include deterministic task→Job identity/linking (#259), durable execution outbox/reconciliation (#260), deployment-aware controller (#262), timezone-aware cron firing (#263), durable event inbox/delivery (#264), cancellation propagation (#265), timeout enforcement (#267), snapshot-safe bounded backfill (#268), shared resource pools (#270), durable scheduler leader fencing (#271), leader guarding across cron/event/backfill services (#273), bounded leader-owning daemon orchestration (#274), continuous daemon loop/shutdown semantics (#275), and parent-first group backfill cancellation (#276). Native Bundle portability then added project semantic inventory/export (#278), bounded verified import planning with create/no-op/collision classification (#279), and explicit runtime remapping plus one-transaction project/environment-binding commit (#280). PR #266 made Public v1 the active construction authority while preserving the historical v0.1 planning files verbatim.

These merges do **not** imply that their parent capability families are complete. The scheduler still lacks broad task adapters, branching/skipped semantics, durable notifications, public scheduler APIs/UI, production process/signal/deployment wiring and PostgreSQL multi-node HA qualification. Service-level leader checks occur immediately before cron/event/backfill mutations but are not one transaction with every underlying write; deterministic identities/idempotency remain the race backstop. Bundle support is currently lossless only for the narrow native project-manifest path represented in source; connections, catalog/workflow/quality/ontology/ML/GenAI and later data/semantic assets are not yet covered by the same inventory/import transaction. Storage ports do not constitute a PostgreSQL backend.

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
3. Extend native Ronin Bundle semantic inventory/import beyond `ProjectManifest` to connections and other executable canonical assets, preserving explicit binding requests and atomic staged commit; certify Ronin-native lossless round-trip before vendor profiles.
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
