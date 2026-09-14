# Ronin Public v1 implementation status

**Status authority:** `docs/product/PUBLIC_V1_SCOPE.md` defines the product/release target.  
**Machine-readable ledger:** `docs/product/public-v1-status.json`.  
**Observed source head:** `2f334c0f07ac023b0378bcdac6c6e5bc25150842` (2026-09-13).  
**Status observed:** 2026-09-14 05:55 Europe/Madrid.  
**Release status:** **INCOMPLETE**.

This document records merged implementation state only. It does not claim test execution, legal review, human decisions, release qualification or operational evidence that does not exist. Open PRs are called out separately and are not counted as landed capability.

## Status vocabulary

- **implemented** — the stated foundation/path exists in merged source and is not known here to require another feature to perform its narrow claimed role;
- **partial** — meaningful merged source implementation exists, but the mandatory Public v1 family lacks an end-to-end supported path;
- **missing** — no supported merged implementation path exists for the mandatory capability;
- **blocked** — work/evidence cannot be truthfully completed under a current external or maintainer-controlled prerequisite;
- **human decision** — a maintainer/product/security/legal decision must be made rather than invented by implementation;
- **qualification pending** — implementation exists but current exact-head execution/release evidence does not.

## Repository-grounded capability snapshot

| Capability | Status | Current merged source truth |
| --- | --- | --- |
| Durable execution foundation | implemented | Job/Run/Attempt, SQLite durability, leases/heartbeat/fencing/reclaim/resume, cancellation, evidence, local/container worker, HTTP/CLI/SDK foundation |
| Workspace/project/source control | partial | workspace/project persistence, project manifest/Git identity, environment/deployment bindings and PostgreSQL core metadata adapter exist; complete Public v1 APIs/UI/source-control lifecycle and membership administration remain |
| Connectors/ingestion | partial | governed local CSV/JSONL foundations plus executable bounded HTTP JSON and PostgreSQL discovery/read connectors exist; incremental cursor/CDC, writes, JDBC/object-store breadth and public surfaces remain |
| Lakehouse/SQL | partial | Parquet read/write/inspection, governed Parquet catalog integration, DuckDB reference SQL, and optional Delta Lake/Iceberg adapters exist; schema/partition evolution, maintenance, remote credential wiring, cross-engine interoperability and server APIs remain |
| Data Engineering Studio | partial | notebook/pipeline execution foundations exist; authoring CRUD APIs, SQL/notebook/pipeline public surfaces and Web Studio remain |
| Durable DAG scheduler | partial | durable snapshots/task runs, fenced attempts/retries/dependencies, task→Job planning, execution outbox/reconciliation, deployment-aware controller, cron/events, cancellation/timeouts, bounded backfill, pools, leader fencing and daemon orchestration exist; branching/notifications, broad operator execution, public scheduler APIs/UI, deployment wiring and PostgreSQL multi-node HA qualification remain |
| Catalog/lineage | partial | governed assets/revisions and declared/observed lineage persistence plus selected-subgraph Bundle export/planning/atomic import exist; search/glossary/classification/OpenLineage and complete asset integration remain |
| Ontology/KG | partial | object/property/link/action schema and persistence exist; instance resolution/query/materialization/actions remain |
| Graph intelligence/RQL | missing | no supported parser/planner/runtime/provider path |
| Data quality/contracts | partial | durable contracts/results plus built-in null/unique/range/domain/row-count/freshness evaluation and optional blocking gate exist; referential/custom execution, scheduler/alert integration and public surfaces remain |
| AI/ML/MLOps | partial | experiment/run/model provenance plus executable deterministic tabular classification/regression training, metrics, content-addressed artifact registration, digest-checked local inference and evaluation foundations exist; features, distributed training, MLflow interoperability, promotion, batch jobs and serving remain; executable-pickle hardening is open work and not counted as landed |
| GenAI/RAG/agents | partial | provider-neutral runtime contracts, bounded OpenAI-compatible HTTP execution, SQLite vector retrieval, RAG execution and bounded declared-tool agent loop exist; production vector backends, richer provider APIs, evaluation and distributed execution remain |
| Semantic models/dashboards | partial | canonical semantic model/metric/dashboard contracts, safe SQL compilation, semantic query execution and dashboard tile execution exist; persistence/catalog registration, joins/time grains/advanced semantics and Web Studio rendering remain |
| Streaming/real-time | partial | source/sink/checkpoint contracts, SQLite checkpoint CAS, sink-before-checkpoint micro-batch execution, replay-safe Parquet sink and optional Kafka JSON source exist; windows/watermarks/stateful aggregation, table/Kafka sinks, scheduler bridge and UI remain |
| Observability/alerts/FinOps | partial | normalized metrics/events, SQLite telemetry, alert rule/state engine, notification intents, usage/rate-card/cost/budget policy evaluation and actual-vs-estimate provenance exist; OpenTelemetry exporters, notification adapters, forecasting/anomaly detection, enforcement and public surfaces remain |
| Multi-user security/audit | partial | stable user/service principals, groups/memberships, workspace roles, deny-by-default RBAC, actor context, OIDC JWT validation and authorization→append-only-audit bridge exist in merged source; public HTTP/CLI adoption, admin provisioning, PostgreSQL identity/audit persistence, network discovery and broader instrumentation remain; RBAC hardening is open work and not counted as landed |
| Local/Compose/Kubernetes | partial | local/container/Compose foundation and a PostgreSQL adapter for workspace/project/environment/connection/catalog metadata exist; shared job/scheduler/security stores, object storage, Kubernetes/Helm, backup/restore and HA qualification remain |
| Ronin Bundle | partial | deterministic verified archive IO, native project/connection round-trips, atomic multi-object project+connection commit, selected catalog subgraph round-trip, and workflow+schedules portability exist; quality/ontology/ML/GenAI/data/semantic assets, PostgreSQL commit adapters, certification and public surfaces remain |
| Fabric migration | missing | no certified adapter |
| Databricks migration | missing | no certified adapter |
| Palantir Foundry/AIP migration | missing | no certified adapter |
| Dataiku DSS migration | missing | no certified adapter |
| Web Studio | missing | no current web application tree |
| Public v1 release qualification | blocked | active GitHub Actions/current exact-head qualification remain absent; main remains unprotected and human/security/legal gates remain |

## Public v1 source work merged after the previous status snapshot

PRs **#290–#301** are merged into the observed main head and materially change the capability snapshot:

- **#290** — workflow and schedule Bundle portability;
- **#291** — Parquet plus DuckDB reference open data/SQL path;
- **#292** — executable HTTP JSON and PostgreSQL connectors;
- **#293** — Delta Lake and Apache Iceberg open-table adapters;
- **#294** — PostgreSQL core metadata backend;
- **#295** — executable built-in data-quality runtime and blocking gate;
- **#296** — semantic metrics and dashboard query runtime;
- **#297** — executable tabular ML training/inference;
- **#298** — executable GenAI/RAG/agent runtime;
- **#299** — durable micro-batch streaming runtime;
- **#300** — observability, alert and FinOps runtime;
- **#301** — multi-user principals/groups/OIDC/workspace RBAC and authorization-audit bridge.

These merges make those families real source capabilities, but they do **not** complete their Public v1 end-to-end paths. Public APIs, Web Studio, broader persistence/server profiles, interoperability, migration certification and exact-head execution evidence remain incomplete.

## Open hardening and follow-up work is not merged source truth

A substantial hardening queue is open after the 2026-09-13 audit. It includes store-authoritative RBAC membership (#302/#303/#305), ML split feasibility (#306/#307/#309), authorization-aware Job pagination (#310/#317/#319), SQLite RBAC database integrity (#311/#312/#314), stale generated packaging metadata (#315/#316), HTTP request/service deadlines (#320/#321/#323), OIDC HTTP/CLI/admin/server-profile follow-ups (#324 onward), PostgreSQL identity/audit adapters, and removal of executable pickle model artifacts (#353/#354/#356).

Those PRs are intentionally **not** reflected as landed capability in the table above until merged. Their source tests are likewise not current exact-head qualification evidence.

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

1. Keep this ledger and the construction plan synchronized with merged repository truth; never count open PRs as landed.
2. Convert existing domain/runtime capabilities into application services and supported public APIs, beginning with workspace/project/security, scheduler and executable data/AI paths.
3. Complete the multi-user server profile: store-authoritative RBAC, OIDC HTTP/CLI adoption, admin provisioning, shared PostgreSQL identity/audit persistence, broader audit instrumentation and production secret boundaries.
4. Expand the Public v1 API and build Web Studio against documented/generated clients rather than private in-process calls.
5. Finish connector incrementality/CDC, lakehouse lifecycle/interoperability, scheduler branching/notifications/operator breadth and PostgreSQL HA semantics.
6. Extend native Bundle coverage to quality/ontology/ML/GenAI/data/semantic families and add PostgreSQL commit adapters plus certification evidence.
7. Complete ontology/KG actions/query and RQL, then close advanced ML/GenAI/semantic/streaming/observability gaps already exposed by the first executable runtimes.
8. Add an S3-compatible artifact/object-store profile and Kubernetes/Helm only after shared metadata/security/job/scheduler semantics are real.
9. Build and certify the four vendor migration profiles only against executable canonical target capabilities, with exhaustive migration reports.
10. Restore and run exact-candidate qualification only when authorized; Public v1 remains incomplete until every mandatory family has its supported end-to-end path and release evidence.

## Historical v0.1 planning documents

The earlier v0.1 construction plan and backlog are preserved verbatim under `docs/automation/history/`. They remain useful evidence for the execution foundation and historical qualification baseline, but they are not current feature-selection authority. Active `docs/automation/CONSTRUCTION_PLAN.md` and `BACKLOG.md` derive scope from `PUBLIC_V1_SCOPE.md` rather than the superseded v0.1 feature freeze.
