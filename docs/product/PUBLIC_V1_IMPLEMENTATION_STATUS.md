# Ronin Public v1 implementation status

**Status authority:** `docs/product/PUBLIC_V1_SCOPE.md` defines the product/release target.  
**Machine-readable ledger:** `docs/product/public-v1-status.json`.  
**Observed source head:** `69ee645e7b6fe90bf218a6a019595d382424fcf8` (2026-09-13).  
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
| Durable DAG scheduler | partial | durable snapshots/task runs, fenced attempts/retries/dependencies, deterministic task→Job planning, execution outbox/reconciliation, deployment-aware controller, timezone-aware durable cron firing, durable event inbox/delivery and durable cancellation propagation exist; backfill, pools, timeout enforcement, leadership and broad operator execution remain |
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
| Ronin Bundle | partial | canonical manifest/migration semantics and deterministic verified archive IO exist; complete inventory/import binding workflow remains |
| Fabric migration | missing | no certified adapter |
| Databricks migration | missing | no certified adapter |
| Palantir Foundry/AIP migration | missing | no certified adapter |
| Dataiku DSS migration | missing | no certified adapter |
| Web Studio | missing | no current web application tree |
| Public v1 release qualification | blocked | active Actions/current exact-head qualification absent; main remains unprotected |

## Public v1 source work merged in the current construction sequence

PRs **#242–#265** moved Public v1 from planning into source implementation. The later slices include deterministic verified Bundle IO (#255), deployment-local secret resolution (#256), provider-neutral metadata store ports (#257), environments/deployment bindings (#258), deterministic scheduler task→Job identity/linking (#259), the durable scheduler execution outbox/reconciliation path (#260), deployment-aware scheduler controller (#262), durable timezone-aware cron firing (#263), durable scheduler event inbox/delivery (#264), and durable scheduler cancellation propagation (#265).

These merges do **not** imply that their parent capability families are complete. In particular, the scheduler still lacks backfill, resource pools, timeout enforcement, leader fencing and a broad task adapter matrix; Bundle support still lacks complete project inventory/import binding resolution; storage ports do not constitute a PostgreSQL backend.

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
2. Finish scheduler semantics already supported by current contracts: timeout enforcement, pools, backfill, broader operator adapters, branching/notifications and leader fencing.
3. Complete native Ronin Bundle project inventory/import transaction and binding resolution.
4. Complete store ports for remaining domains; then implement PostgreSQL adapters and an S3-compatible artifact store without changing logical references.
5. Implement the first open data path: Arrow/Parquet + reference open table profile + reference SQL engine, with catalog/lineage/quality hooks.
6. Complete remote connectors and safe incremental checkpoint execution.
7. Expand the Public v1 API and begin Web Studio against documented/generated clients.
8. Complete quality runtime, ontology/KG actions/query, RQL, ML, GenAI, semantic/dashboard, streaming, observability/alerts/FinOps and multi-user identity.
9. Add Kubernetes/Helm after the server metadata/object-store/identity profile is real.
10. Build the four vendor migration profiles only against executable canonical target capabilities and certify them with exhaustive migration reports.
11. Restore and run exact-candidate qualification only when authorized; Public v1 remains incomplete until every mandatory family has its supported end-to-end path.

## Historical v0.1 planning documents

The earlier v0.1 construction plan and backlog are preserved verbatim under `docs/automation/history/`. They remain useful evidence for the execution foundation and historical qualification baseline, but they are not current feature-selection authority. Active `docs/automation/CONSTRUCTION_PLAN.md` and `BACKLOG.md` now derive scope from `PUBLIC_V1_SCOPE.md` rather than the superseded v0.1 feature freeze.
