# Ronin Public v1 implementation status

**Status authority:** `docs/product/PUBLIC_V1_SCOPE.md` defines the product/release target.  
**Machine-readable ledger:** `docs/product/public-v1-status.json`.  
**Capability matrix:** [`PUBLIC_V1_CAPABILITY_MATRIX.md`](PUBLIC_V1_CAPABILITY_MATRIX.md).
**Architecture decisions:** [`docs/architecture/PUBLIC_V1_ADRS.md`](../architecture/PUBLIC_V1_ADRS.md).
**Observed workspace snapshot:** 2026-09-22. The checkout has no Git commit yet
(`master` is an empty branch), so there is no valid source SHA for this snapshot.
**Observed source head:** `2d69761220d1b1c90e40a5bb0bfbec737f9670e9` (2026-09-24).
Historical ledger value only; this SHA is qualification context and must not be
used as the identity of the current implementation.
**Release status:** **INCOMPLETE**.

This document records implementation state only. It does not claim test execution, legal review, human decisions, release qualification or operational evidence that does not exist.

## Reading this snapshot

The source tree is the authority for implementation presence. The status ledger
is intentionally conservative: a capability is `partial` until its mandatory
Public v1 path is complete end to end. Historical CI/evidence files retain the
candidate SHA they were generated for. They are not current-head evidence for
this uncommitted workspace.

The current workspace includes the implementation families listed in the
package inventory (`studio_ai_studio`, `studio_cloud`, `studio_data_engineering`,
`studio_migration`, `studio_ml`, `studio_streaming`, `studio_synthetic_data`,
and the shared runtime/storage/server packages). It also includes the current
ML, migration, Cloud Studio, PostgreSQL and synthetic-data contracts under
`docs/`; those documents describe implemented slices and remaining boundaries,
not Public v1 completion.

## Local verification on this snapshot

On Windows, `python -m pytest -x -q` produced **1982 passed, 20
skipped**. Docker, PostgreSQL, Spark, symlink and POSIX-specific checks were
skipped where their prerequisites were unavailable. No release qualification is
claimed.

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
| Workspace/project/source control | partial | workspace/project persistence, authenticated create/read/update/archive workspace and project lifecycles with idempotency, audit and active-project filtering, project manifest, reproducible secret-free deployment manifest with canonical identity, Git identity, environment/deployment bindings; full Public v1 APIs/UI/membership remain |
| Connectors/ingestion | partial | connection/discovery/checkpoint contracts, governed local CSV/JSONL, bounded HTTP/PostgreSQL, S3-compatible including Apache Ozone, Azure Blob and JDBC profiles, public capability/plan/preview/checkpoint-health API, Studio actions and SDK parity; production driver qualification and broader incremental coverage remain |
| Lakehouse/SQL | partial | bounded Arrow/Parquet open-data and streaming publication paths, provider-neutral SQL/table contracts, optional local DuckDB engine with bounded relation lifecycle, shared query lifecycle adapter, provider-neutral query-engine contracts/discovery/local transport/Trino HTTP transport, bounded project-scoped fail-closed read-only SQL HTTP adapter/route, and optional Iceberg/Delta adapters exist; QueryFlux and remote/catalog qualification, full format features, and broader SQL service remain |
| Data Engineering Studio | partial | notebook/pipeline execution foundations, durable SQL editor revisions/history/bounded export, parameter schemas, pipeline revision comparison/archive, and an authenticated pipeline-revision-to-workflow-run creation route with deterministic idempotency exist; worker/evidence lineage, complete CRUD and complete Web Studio remain |
| Durable DAG scheduler | partial | durable snapshots/task runs, fenced attempts/retries/dependencies, deterministic task→Job planning, execution outbox/reconciliation, deployment-aware controller, timezone-aware durable cron, durable event inbox/delivery, cancellation, timeout enforcement, snapshot-safe bounded backfill, shared resource pools, generation-fenced leader authority, leader-guarded cron/event/backfill/controller services, bounded and continuous daemon orchestration, graceful SIGINT/SIGTERM daemon entrypoint with fenced lease release, group backfill cancellation, fail-closed conditional branches with idempotent persisted decisions/skipped task state, authenticated schedule/event-trigger list/read/replace and event-ingest routes, Scheduler Studio authoring for schedules, event triggers, workflow runs, deliveries and backfills, durable scheduler adapters for notebook, SQL, Python-code, Data Engineering pipeline, quality-gate, connector-sync, graph-query, notification, semantic-refresh, ML and GenAI nodes, optional leader-cycle notification dispatch, bounded SMTP/HTTPS webhook notification adapters, and durable retry/error recording exist; broader operator execution, notification provider qualification, crash-restart/deployment qualification and PostgreSQL multi-node HA qualification remain |
| Catalog/lineage | partial | governed asset CRUD/revisions, versioned sensitivity/ownership, glossary authoring, bounded search, lineage HTTP navigation, OpenLineage export/HTTP transport and selected-subgraph Bundle portability exist; event certification and complete asset integration remain |
| Ontology/KG | partial | object/property/link/action schema and persistence, instance materialization, link resolution, bounded graph queries and authorized actions exist; durable replay and public interfaces remain |
| Graph intelligence/RQL | partial | bounded read-only RQL SELECT filtering, one-hop typed traversal, and typed property joins over materialized KnowledgeGraph views exist; planning, provider execution and public API exposure remain |
| Data quality/contracts | partial | versioned definitions/results, all built-in checks, injected SQL/Python/referential checks, quality gates, scheduler release enforcement, quality-to-common-alert transition evaluation, authenticated alert rule-list/evaluation APIs, and pyronin SDK parity exist; alert UI and provider qualification remain |
| AI/ML/MLOps | partial | experiment/run/model/evaluation provenance, deterministic tabular training, digest-verified inference, champion serving resolution, deterministic trial comparison, bounded numeric drift summaries, explicit feature-level threshold assessments, versioned feature definitions with dataset snapshots, workspace-scoped HTTP routes and pyronin SDK parity exist; broader feature engineering, algorithms, MLflow and network serving remain |
| GenAI/RAG/agents | partial | provider/prompt/vector/RAG/tool/agent contracts, OpenAI-compatible runtime, deterministic retrieval, bounded agents, deterministic per-example RAG scoring, aggregate reports, telemetry callbacks and GenAI definition Bundle export/import exist; judge-provider evaluation and production qualification remain |
| Semantic models/dashboards | partial | safe semantic contracts, canonical persistence, parameterized metric compiler, calculated metrics, SQL metric runtime, bounded declared-column two-model JOIN execution, dashboard CRUD/execution, Studio and native semantic Bundle round-trips exist; multi-join planning, export/import API qualification and production surfaces remain |
| Streaming/real-time | partial | Kafka polling, durable CAS checkpoints, micro-batch processing, Parquet sinks, event-time windows, stream tables, scheduler integration and bounded health/lag projection including unseen partitions exist; production qualification remains |
| Observability/alerts/FinOps | partial | durable metrics/events, threshold alerts, SMTP/webhook notification adapters, durable delivery intents with retry/backoff, Prometheus export, instrumentation, usage pricing, actual-versus-estimated costs, non-ledger forecasts, anomaly hooks and budget gates exist; authenticated alert-rule/evaluation APIs, SDK parity and the Monitoring & Alerts Studio route are covered by static and Playwright smoke evidence; broader service adoption and production qualification remain |
| Multi-user security/audit | partial | typed grants, bearer auth, transport policy, fail-closed classification-aware policy actions, secret resolver with injected external backends, OIDC users/groups/service identities, authenticated principal/group reads and role-binding administration with SQLite/PostgreSQL parity, public SDK parity, broad fail-closed mutation audit and append-only audit foundation exist; external provider qualification and production certification remain |
| Local/Compose/Kubernetes | partial | local/Compose foundation, PostgreSQL metadata healthcheck, PostgreSQL JobStore adapter wired to the server, single-node real-PostgreSQL lifecycle qualification, SQLite backup/restore with path-bound artifact-tree manifests, PostgreSQL dump backup with checksum sidecar verification, S3 artifacts with retry/corruption checks, Kubernetes Job submit/status/cancel/log adapter, constrained single-replica Helm chart, and forward-only upgrade/failure recovery runbooks exist; PostgreSQL HA, multi-node and production qualification remain |
| Ronin Bundle | partial | deterministic verified archive IO, project/connection/catalog/workflow/schedule/quality/ontology/semantic inventories, export, verified planning and atomic commits, plus GenAI definitions and ML experiment/run/registered-model metadata export/import exist; ML artifacts/data assets, PostgreSQL adapters, certification and public surfaces remain |
| Fabric migration | qualification pending | deterministic fixture discovery and fail-closed notebook-item translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Databricks migration | qualification pending | deterministic fixture discovery and fail-closed notebook-job translation with dependency/schedule mapping and CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Palantir Foundry/AIP migration | qualification pending | deterministic fixture discovery and fail-closed Python-function translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Dataiku DSS migration | qualification pending | deterministic fixture discovery and fail-closed Python/SQL recipe translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Web Studio | partial | authenticated static Studio shell supports job/evidence/event workflows, project-scoped read-only SQL and a Monitoring & Alerts route; 77 Playwright route/accessibility/history/domain-journey checks pass; authoring editors, domain workflows and complete Public v1 journeys remain |
| Public v1 release qualification | blocked | exact-head CI, security, Docker and release-packaging workflows are active; release qualification now generates and verifies candidate-bound SBOM/provenance evidence for wheel and sdist artifacts, alongside installed Studio smoke and accessibility checks; main is protected with required PR approval, strict checks and no force-push/deletion; Public v1 remains blocked by incomplete mandatory product capabilities, provider certification and legal/release decisions |

## Public v1 source work merged in the current construction sequence

PRs **#242–#288** moved Public v1 from planning into source implementation. Scheduler foundations include deterministic task→Job identity/linking (#259), execution outbox/reconciliation (#260), deployment-aware controller (#262), cron/events (#263/#264), cancellation/timeouts (#265/#267), snapshot-safe backfill (#268), pools (#270), leader fencing (#271/#273), daemon orchestration (#274/#275), and group backfill cancellation (#276). Native Bundle portability added project semantic inventory/export (#278), project import planning (#279), runtime remapping plus atomic project/environment-binding commit (#280), connection round-trip with explicit secret-reference remapping (#282), deterministic dependency-ordered multi-object staging (#283), atomic project+connection commit (#285), explicit selected catalog subgraph export/planning (#287), and atomic catalog asset/revision/lineage commit (#288). PR #266 made Public v1 the active construction authority while preserving the historical v0.1 planning files verbatim.

These merges do **not** imply that their parent capability families are complete. The scheduler still lacks broad task adapters, branching/skipped semantics, durable notification integration, public scheduler APIs/UI, production process/signal/deployment wiring and PostgreSQL multi-node HA qualification. Bundle support now covers project, connection, workflow/schedule, quality contracts, ontology definitions, semantic models/dashboards, and an explicitly selected catalog subgraph; ML/GenAI/data assets remain outside it. Catalog export intentionally does not invent whole-catalog revision discovery because the current catalog port does not expose it. PostgreSQL does not yet implement the Bundle atomic commit ports.

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
- **#199 and dependent release issues:** automated qualification is active; each claim must still identify the exact candidate SHA, and green automation does not replace product, provider, legal or administrative release evidence.
- **#63:** repository/ref protection remains an administrative release-gate action even though the required checks are now restored.

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
