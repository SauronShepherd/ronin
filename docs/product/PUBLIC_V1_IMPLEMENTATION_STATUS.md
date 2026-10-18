# Ronin Public v1 implementation status

**Status authority:** `docs/product/PUBLIC_V1_SCOPE.md` defines the product/release target.  
**Machine-readable ledger:** `docs/product/public-v1-status.json`.  
**Capability matrix:** [`PUBLIC_V1_CAPABILITY_MATRIX.md`](PUBLIC_V1_CAPABILITY_MATRIX.md).
**Architecture decisions:** [`docs/architecture/PUBLIC_V1_ADRS.md`](../architecture/PUBLIC_V1_ADRS.md).
**Observed workspace snapshot:** 2026-10-18. The tracked source is based on
`main@2abc6ac`; untracked qualification output directories are not release
evidence.
**Observed source head:** `2abc6ac3495ae3aa61a406f6f8c5be3e3478b796` (2026-10-18).
**Release status:** **INCOMPLETE**.

**Verified release progress:** **0% (0/14 P1–P14 capability families are
release-qualified).** A family counts only after its mandatory Public v1
journey and applicable provider, security and exact-head evidence are complete.
All 14 remain partial; this is a release-completion metric, not a measure of
code already implemented.

This document records implementation state only. It does not claim test execution, legal review, human decisions, release qualification or operational evidence that does not exist.

## Reading this snapshot

The source tree is the authority for implementation presence. The status ledger
is intentionally conservative: a capability is `partial` until its mandatory
Public v1 path is complete end to end. Historical CI/evidence files retain the
candidate SHA they were generated for and are not promoted to current-head
evidence.

## Exact-head qualification snapshot

On the prior `main@58876c2a759fdb2d6dd93ba354ca6b5ce75ffbff` snapshot
(2026-10-17), GitHub reported success for [CI](https://github.com/SauronShepherd/ronin/actions/runs/39029783787)
(Python 3.11/3.12), [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783816),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783792),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783786),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783791)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39029783794).
Docker included PostgreSQL storage coverage, real container qualification, and
strict frozen v0.1 acceptance (15 passed, zero skips/failures/errors). CI's
`mutation` job was skipped; skipped is not pass. This is exact-head automation
evidence only. The Public v1 release remains **INCOMPLETE**, and product
qualification remains **blocked** by incomplete capability journeys and
external/human-owned evidence.

On the prior `main@41a2024fde3de508d29c2fc3f9960b611f075edd` snapshot,
GitHub reported success for CI, Docker, Web, Security, Release and Status
consistency. The prior `main@fa8cc731f4af11120328b25aa207cb39897503d5`
snapshot also passed [CI](https://github.com/SauronShepherd/ronin/actions/runs/39034134947),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134890),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134789),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034135001),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134870)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39034134902).
Docker passed PostgreSQL storage coverage, real container qualification, and
strict frozen v0.1 acceptance. PR #396's isolated dispatcher termination test
passed the scheduler/API suite (151 tests), Ruff, and local image qualification
(21 passed; strict acceptance 15/15). This candidate additionally implements
the first PostgreSQL run/task snapshot store; its real PostgreSQL Docker
integration passed 3/3 with 95% adapter coverage, plus Ruff, architecture and
mypy. Standard CI excludes this PostgreSQL-only module from its no-service
coverage gate; Docker runs the full per-file coverage gate against PostgreSQL.
The snapshot store
does not implement dispatch, fencing, events, backfills or task evidence, and
does not exercise daemon shutdown/restart or close the broader Public v1 paths.

The prior `main@46f98056b9c501a374fe0f33a1548110f3cbf17f` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39035748927),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39035748910),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39035748905),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39035748879),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39035748917),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39035748936).
The merged PR #397 exact commit `b1b4574d336b1d16cd4b2975e0f996563a8042a1`
and PR #398 exact commit `53f4cc8d6c827e0caa6a8624dff3543d1d6dd4ed`
passed CI (Python 3.11/3.12), Docker, Web, Security, Release, Status
consistency, quality, dependencies and negative gates. Docker passed
PostgreSQL storage coverage, real container qualification, and strict frozen
v0.1 acceptance; `mutation` was skipped.

The prior `main@2a7d0c9ef697d3de131f04d0973b49bfb2e1c780` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39036976451),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39036976461),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39036976408),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39036976428),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39036976444),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39036976413).
The prior `main@e3ca935055968460ba4a0cc3063617c42383b45f` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39039830705),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39039830679),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39039830690),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39039830694),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39039830715),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39039830750).
The prior `main@586801468a6b1cdc0f28d72d0da585ceb3ca2fd1` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39041024109),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39041024090),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39041024085),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39041024151),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39041024086),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39041024136).
The prior `main@209991ab4b67a1d1cdb85057432e80bda1c2bfdd`, including the
squash merge of PR #401, passed [CI](https://github.com/SauronShepherd/ronin/actions/runs/39047807894),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39047807872),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39047807911),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39047807769),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39047807778),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39047807882).
PR #402 added PostgreSQL task-attempt claims, lease heartbeat/fencing,
expiry reclaim/retry, terminal completion and resource-pool capacity. Its exact
head passed Python 3.11/3.12, PostgreSQL-backed storage coverage and Docker
qualification; `mutation` was skipped. The squash commit is
`main@0ccb5fdd68b8849f860c7ffe9ef2526e4ec9b3e4`; on `main@ef0d107`, exact-head
Status consistency and Security passed, with CI, Docker, Web and Release
running. PR #404 added the PostgreSQL schema-4 execution
outbox with lease-fenced writes, idempotent intent replay, expired-attempt
protection and terminal reconciliation; its required CI, Docker (7m45s),
`ledgers`, Security, dependencies and remaining checks passed. `mutation` was
skipped. PostgreSQL event delivery, backfills and task-evidence stores remain
incomplete, and the scheduler HTTP routes stay unavailable for that profile.
PostgreSQL snapshots, replay-safe branch decisions and generation-fenced
leadership persist in main. The real PostgreSQL integration passed 4 tests
with 87% leadership-adapter coverage, including repeat execution against the
same database. The local scheduler/workflow suite passed 115 tests. Ruff,
formatting, architecture, focused mypy for the adapter, and status generator
checks passed. The repository-wide mypy command reports three existing
unused-ignore errors in unrelated files. Standard CI
excludes PostgreSQL-only adapters from its no-service coverage gate; Docker
runs the full per-file coverage gate against PostgreSQL. PostgreSQL scheduler
HTTP routes remain unavailable until task execution state and the remaining
scheduler stores are qualified.

The audit for PR #401 found that a branch decision arriving after task completion
could overwrite the terminal task state. The fix rejects late decisions in both
SQLite and PostgreSQL under their transaction locks, increments SQLite
`row_version` for a persisted decision, and tests that a rejected update leaves
state and version unchanged. CI and Docker passed on code candidate
`a5ae71629589b5d722c4ba29c50492661fe94728`; Docker passed PostgreSQL storage
coverage, real container qualification, and strict v0.1 acceptance. The 0% release
progress remains unchanged because P5 and all other mandatory capability families
remain partial.

The PostgreSQL task-attempt implementation passed real PostgreSQL integration
in Docker: 14 focused tests passed and focused line coverage reached 81%.
PR #404 added the PostgreSQL execution intent outbox and terminal reconciliation.
PRs #406–#414 now provide PostgreSQL event delivery, backfills, task evidence,
schedule cursors/fires and the workflow/schedule HTTP adapter. P5 remains partial
because full daemon/controller recovery, operator conformance and notification
provider qualification remain incomplete.

The current workspace includes the implementation families listed in the
package inventory (`studio_ai_studio`, `studio_cloud`, `studio_data_engineering`,
`studio_migration`, `studio_ml`, `studio_streaming`, `studio_synthetic_data`,
and the shared runtime/storage/server packages). It also includes the current
ML, migration, Cloud Studio, PostgreSQL and synthetic-data contracts under
`docs/`; those documents describe implemented slices and remaining boundaries,
not Public v1 completion.

## Historical local verification (prior snapshot)

These local results were recorded against the prior source snapshot
`dfdb1045de2e997caa191ba81a8ec640c1dd04bd`, not the observed candidate above.
The full `python -m pytest -q` verification produced **2266 passed, 15 skipped**
with zero failures or errors. The skips are
environment-gated Docker/PostgreSQL/Spark/provider qualification checks, not
test failures.
The latest focused contract verification produced **144 passed**.
Additional evidence recorded for that snapshot includes Docker qualification
(21 historical CI checks plus 5 current real-Docker tests), real PostgreSQL integration (11 passed), the installed-wheel
browser smoke (no console/request/CSP failures), installed-wheel accessibility
(no violations at 320/768/1440 px), and four credential-free migration fixture
certifications. These checks do not constitute current-head or Public v1 release qualification.

That snapshot's local checks additionally passed Ruff format/lint across all 881
Python files, the public import smoke for 32 packages, 11 Data Engineering
async tests, and installed-wheel plus installed-sdist Studio Chromium and
accessibility qualification (zero console/request/CSP, axe, or layout failures).

Mutation evidence is retained as a historical, frozen record in
`docs/quality/MUTATION_CAMPAIGN_FINAL.md`. Recurring mutation qualification is
retired by product decision and is not a release or implementation blocker.
Current product readiness is determined by ordinary unit, integration, contract,
and end-to-end verification plus the capability matrix; temporary mutation
workspaces and generated reports are not release evidence.

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
| Workspace/project/source control | partial | workspace/project persistence, authenticated create/read/update/archive workspace and project lifecycles with idempotency, audit and active-project filtering, project manifest, reproducible secret-free deployment manifest with canonical identity, Git identity, environment/deployment bindings, Studio and SDK journeys covering project creation, environment binding, Bundle export/archive, audited/idempotent governed pipeline execution and project-scoped permission inspection; full Public v1 APIs/UI and membership remain |
| Connectors/ingestion | partial | connection/discovery/checkpoint contracts, governed local CSV/JSONL, bounded HTTP/PostgreSQL, S3-compatible including Apache Ozone, Azure Blob and JDBC profiles, public capability/plan/preview/checkpoint-health API, Studio actions and SDK parity; production driver qualification and broader incremental coverage remain |
| Lakehouse/SQL | partial | bounded Arrow/Parquet open-data and streaming publication paths, provider-neutral SQL/table contracts, optional local DuckDB engine with bounded relation lifecycle, shared query lifecycle adapter, provider-neutral query-engine contracts/discovery/local transport/Trino HTTP transport, QueryFlux discovery and QueryFlux-to-Trino lifecycle adapters, bounded project-scoped fail-closed read-only SQL HTTP adapter/route, and optional Iceberg/Delta adapters exist; external QueryFlux and remote/catalog qualification, full format features, and broader SQL service remain |
| Data Engineering Studio | partial | notebook/pipeline execution foundations, durable SQL editor revisions/history/bounded export, parameter schemas, pipeline revision comparison/archive, and an authenticated pipeline-revision-to-workflow-run creation route with deterministic idempotency exist; worker/evidence lineage, complete CRUD and complete Web Studio remain |
| Durable DAG scheduler | partial | durable snapshots/task runs, fenced attempts/retries/dependencies, deterministic task→Job planning, execution outbox/reconciliation, deployment-aware controller, timezone-aware durable cron, durable event inbox/delivery, cancellation, timeout enforcement, snapshot-safe bounded backfill, shared resource pools, generation-fenced leader authority, leader-guarded cron/event/backfill/controller services, bounded and continuous daemon orchestration, graceful SIGINT/SIGTERM daemon entrypoint with fenced lease release, group backfill cancellation, fail-closed conditional branches with idempotent persisted decisions/skipped task state, authenticated schedule/event-trigger list/read/replace and event-ingest routes, Scheduler Studio authoring for schedules, event triggers, workflow runs, deliveries and backfills, durable scheduler adapters for notebook, SQL, Python-code, Data Engineering pipeline, quality-gate, connector-sync, graph-query, notification, semantic-refresh, ML and GenAI nodes, optional leader-cycle notification dispatch, bounded SMTP/HTTPS webhook notification adapters, and durable retry/error recording exist; SQLite store-reopen/outbox replay/reconciliation and PostgreSQL task-evidence plus process-kill dispatch/replay/reconciliation have focused test evidence, while full daemon/controller recovery, notification-provider qualification and broader operator conformance remain |
| Catalog/lineage | partial | governed asset CRUD/revisions, versioned sensitivity/ownership, glossary authoring, bounded search, lineage HTTP navigation, OpenLineage export/HTTP transport and selected-subgraph Bundle portability exist; event certification and complete asset integration remain |
| Ontology/KG | partial | object/property/link/action schema and persistence, instance materialization, link resolution, bounded graph queries and authorized actions exist; durable replay and public interfaces remain |
| Graph intelligence/RQL | partial | bounded read-only RQL SELECT filtering, one-hop typed traversal, and typed property joins over materialized KnowledgeGraph views exist; planning, provider execution and public API exposure remain |
| Data quality/contracts | partial | versioned definitions/results, all built-in checks, injected SQL/Python/referential checks, quality gates, scheduler release enforcement, quality-to-common-alert transition evaluation, authenticated contract read/replace and run/history/state APIs, pyronin SDK parity including contract authoring, and Quality Studio contract authoring, validation, dry-run, evidence/history and blocking-policy controls exist; provider qualification remains |
| AI/ML/MLOps | partial | experiment/run/model/evaluation provenance, deterministic tabular training, digest-verified inference, champion serving resolution, deterministic trial comparison, bounded numeric drift summaries, explicit feature-level threshold assessments, versioned feature definitions with dataset snapshots, workspace-scoped HTTP routes and pyronin SDK parity exist; broader feature engineering, algorithms, MLflow and network serving remain |
| GenAI/RAG/agents | partial | provider/prompt/vector/RAG/tool/agent contracts, OpenAI-compatible runtime, deterministic retrieval, bounded agents, deterministic per-example RAG scoring, aggregate reports, telemetry callbacks and GenAI definition Bundle export/import exist; judge-provider evaluation and production qualification remain |
| Semantic models/dashboards | partial | safe semantic contracts, canonical persistence, parameterized metric compiler, calculated metrics, SQL metric runtime, bounded declared-column two-model JOIN execution, dashboard CRUD/execution, Studio and native semantic Bundle round-trips exist; multi-join planning, export/import API qualification and production surfaces remain |
| Streaming/real-time | partial | Kafka polling, durable CAS checkpoints, micro-batch processing, Parquet sinks, event-time windows, stream tables, scheduler integration and bounded health/lag projection including unseen partitions exist; production qualification remains |
| Observability/alerts/FinOps | partial | durable metrics/events, threshold alerts, SMTP/webhook notification adapters, durable delivery intents with retry/backoff, Prometheus export, instrumentation, usage pricing, actual-versus-estimated costs, non-ledger forecasts, anomaly hooks and budget gates exist; authenticated alert-rule/evaluation APIs, SDK parity, fail-closed alert operation validation and the Monitoring & Alerts Studio route are covered by static and Playwright smoke evidence; broader service adoption and production qualification remain |
| Multi-user security/audit | partial | typed grants, bearer auth, transport policy, fail-closed classification-aware policy actions, secret resolver with injected external backends, OIDC users/groups/service identities, authenticated principal/group reads and role-binding administration with SQLite/PostgreSQL parity, public SDK parity, broad fail-closed mutation audit and append-only audit foundation exist; external provider qualification and production certification remain |
| Local/Compose/Kubernetes | partial | local/Compose foundation, PostgreSQL metadata healthcheck, PostgreSQL JobStore adapter wired to the server, single-node real-PostgreSQL lifecycle qualification, SQLite backup/restore with path-bound artifact-tree manifests, PostgreSQL dump backup with checksum sidecar verification, S3 artifacts with retry/corruption checks, Kubernetes Job submit/status/cancel/log adapter, constrained single-replica Helm chart, and forward-only upgrade/failure recovery runbooks exist; PostgreSQL scheduler event-delivery, backfill, task-evidence and durable timeout intent/finalization methods exist, while the Compose profile still does not mount scheduler HTTP routes pending full conformance qualification. General production HA is outside the Public v1 contract. |
| Ronin Bundle | partial | deterministic verified archive IO, project/connection/catalog/workflow/schedule/quality/ontology/semantic inventories, workflow/schedule export and verified planning, atomic SQLite/PostgreSQL workflow commits, plus GenAI definitions and ML experiment/run/registered-model metadata export/import exist; ML artifacts/data assets, broader PostgreSQL Bundle adapters, certification and public surfaces remain |
| Fabric migration | qualification pending | deterministic fixture discovery and fail-closed notebook-item translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Databricks migration | qualification pending | deterministic fixture discovery and fail-closed notebook-job translation with dependency/schedule mapping and CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Palantir Foundry/AIP migration | qualification pending | deterministic fixture discovery and fail-closed Python-function translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Dataiku DSS migration | qualification pending | deterministic fixture discovery and fail-closed Python/SQL recipe translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Web Studio | partial | authenticated static Studio shell supports job/evidence/event workflows, project-scoped read-only SQL, project/environment/Bundle/governed-pipeline journeys, resource-scoped project permission inspection and a Monitoring & Alerts route; 77 Playwright route/accessibility/history/domain-journey checks pass; authoring editors, domain workflows and complete Public v1 journeys remain |
| Public v1 release qualification | blocked | exact-head CI, security, Docker and release-packaging workflows are active; release qualification now generates and verifies candidate-bound SBOM/provenance evidence for wheel and sdist artifacts, alongside installed Studio smoke and accessibility checks; main is protected with required PR approval, strict checks and no force-push/deletion; Public v1 remains blocked by incomplete mandatory product capabilities, provider certification and legal/release decisions |

## Public v1 source work merged in the current construction sequence

PRs **#242–#288** moved Public v1 from planning into source implementation. Scheduler foundations include deterministic task→Job identity/linking (#259), execution outbox/reconciliation (#260), deployment-aware controller (#262), cron/events (#263/#264), cancellation/timeouts (#265/#267), snapshot-safe backfill (#268), pools (#270), leader fencing (#271/#273), daemon orchestration (#274/#275), and group backfill cancellation (#276). Native Bundle portability added project semantic inventory/export (#278), project import planning (#279), runtime remapping plus atomic project/environment-binding commit (#280), connection round-trip with explicit secret-reference remapping (#282), deterministic dependency-ordered multi-object staging (#283), atomic project+connection commit (#285), explicit selected catalog subgraph export/planning (#287), and atomic catalog asset/revision/lineage commit (#288). PR #266 made Public v1 the active construction authority while preserving the historical v0.1 planning files verbatim.

These merges do **not** imply that their parent capability families are complete. Scheduler branching/skipped semantics, durable notification dispatch, public APIs/Studio authoring, and process/signal wiring now exist; daemon restart recovery and broader operator/provider qualification remain. PostgreSQL now persists workflow/task snapshots, branch decisions, leader fencing, task-attempt leases and execution intents with terminal reconciliation, durable event delivery, snapshot-safe backfills, and workspace-scoped task-evidence lookup. A focused PostgreSQL process-kill test covers dispatcher replay and scheduler reconciliation; full daemon/controller recovery and scheduler conformance remain unqualified, so scheduler HTTP routes remain unavailable on that backend. Bundle support now covers project, connection, workflow/schedule, quality contracts, ontology definitions, semantic models/dashboards, and an explicitly selected catalog subgraph; ML/GenAI/data assets remain outside it. Catalog export intentionally does not invent whole-catalog revision discovery because the current catalog port does not expose it. PostgreSQL does not yet implement the Bundle atomic commit ports.

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

- **License/NOTICE/attribution and release approval:** tooling may inventory facts; maintainers/legal review own conclusions.
- **Provider certifications:** real vendor qualification still needs authorized environments and credentials; fixture-only migration evidence is not certification.
- **#102:** `main` enforces a 90% line floor on 11 release-decision modules: strict v0.1 acceptance gate (94%), exact-candidate release aggregator (100%), artifact identity (96%), installed-artifact qualification (96%), release evidence (91%), evidence emission (100%), artifact qualification (96%), license qualification (97%), SBOM generation (96%), supply-chain evidence (97%), and mutation policy (97%). The explicit module list and threshold are enforced by `coverage-release-gates`; the finding stays open for review of future decision modules.
- **#63:** current GitHub API evidence shows protected `main` with eight required checks, admin enforcement, no force pushes or deletion, and an active `v*` tag ruleset. Reconcile the open issue's checklist with this evidence before claiming the issue is fully satisfied.
- **#199, #57, #96, #202:** automated qualification is active and exact-head runs pass on the recorded candidate. The strict 15-step Docker/release gate for #96 landed in #389; keep the broader journey and product/provider/legal criteria open.
- **Mutation:** the campaign is permanently frozen and the score gate retired by product decision. Do not rerun; reopen only through a new explicit product decision and campaign plan.

## Updated critical path

1. Keep this ledger and the active construction plan synchronized with repository truth.
2. Qualify PostgreSQL scheduler event, backfill and task-evidence adapters together; qualify end-to-end outbox dispatch/restart recovery, operator conformance and notification delivery in the supported local/Compose profiles. Task-evidence linkage now has focused Docker integration coverage. Do not claim production HA.
3. Extend native Bundle support to the next executable canonical metadata family, preferring workflow/pipeline persistence if its canonical snapshot/store contracts preserve identity without deployment locators; then quality/ontology/ML/GenAI as their contracts permit.
4. Complete store ports for remaining domains; then implement PostgreSQL adapters and an S3-compatible artifact store without changing logical references.
5. Implement the first open data path: Arrow/Parquet + reference open table profile + reference SQL engine, with catalog/lineage/quality hooks.
6. Complete remote connectors and safe incremental checkpoint execution.
7. Expand the Public v1 API and begin Web Studio against documented/generated clients.
8. Complete quality runtime, ontology/KG actions/query, RQL, ML, GenAI, semantic/dashboard, streaming, observability/alerts/FinOps and multi-user identity.
9. Add Kubernetes/Helm after the server metadata/object-store/identity profile is real.
10. Build the four vendor migration profiles only against executable canonical target capabilities and certify them with exhaustive migration reports.
11. Continue #102 coverage work: `coverage-release-gates` now applies a 90% line floor to the strict gate, exact-candidate aggregator, artifact identity, release evidence/emission, installed-artifact evidence, artifact/license qualification, SBOM generation, supply-chain evidence, and mutation-policy parser. Review future release-decision modules against this explicit list.
12. Maintain exact-candidate qualification; the strict Docker/release acceptance gate must pass on its exact candidate. Public v1 remains incomplete until every mandatory family has its supported end-to-end path and the human-owned evidence is approved.

## Reconciliación de PostgreSQL scheduler (2026-10-17)

Los PR #406 y #407 añadieron entrega durable de eventos y backfills PostgreSQL, respectivamente. #407 corrigió además la carrera de cancelación al crear workflows. El candidato `8edb47807fc4ce9db23067fd5a933c95d821a8c9` pasó CI 3.11/3.12 y Docker qualification; la integración local con PostgreSQL 16 pasó 10 pruebas del adaptador de backfills (88% de cobertura de ramas), más 27 pruebas SQLite/scheduler relacionadas. El merge actual es `main@418ab8be9604c12d84e2825ec2b925cf865d39b7`. En la observación de reconciliación, CI, Web, Security, Release y Status consistency exact-head de `main` pasaron; Docker qualification seguía en ejecución. Después, `read_task_evidence(workspace_id, attempt_id)` quedó implementado para resolver evidencia del Job asociado al intent durable con aislamiento por workspace, y la prueba de integración de outbox/evidencia/reconciliación pasó en PostgreSQL 16. Esta evidencia no cierra P5 ni cambia el progreso release-qualified de 0% (0/14): faltan recuperación end-to-end del dispatcher y conformance integral de operador/notificaciones.

### Estado reconciliado tras PR #411 (2026-10-17)

`main@39c83b4490328fc0be44a7f4e7f30c4870615491` integra el vínculo PostgreSQL workspace-scoped de workflow con proyecto y entorno (`WorkflowDeploymentBinding`) por medio de migración 6→7. El PR #410 pasó CI 3.11/3.12, Security, Release, Status consistency, Web y Docker (**7m15s**); su primer job Docker expuso una mejora del adaptador `postgres_core.py` hasta 37,61%, así que el ratchet se elevó de 32,00% a ese valor medido.

El PR #411 integra migraciones PostgreSQL 7→9 para solicitudes persistentes de timeout y estado cancelado de intentos. Las funciones compartidas consultan la autoridad de dispatch y las solicitudes PostgreSQL; la detección es repetible, el timeout se reconcilia a retry/fallo, y si el workflow está cancelándose, la finalización conserva el estado cancelado. CI 3.11/3.12 y Docker qualification pasaron; Docker completó la cobertura PostgreSQL, pruebas Docker reales y aceptación estricta en **7m25s**. La cobertura medida de `scheduler_timeout.py` llegó a 68,78%, por lo que su baseline subió a 66,70% manteniendo el ratchet de 2,1 puntos. El merge squash es `main@dacd3ffbecef029a77fdfa6ef09cc45bea232f2c`; CI, Docker (**6m57s**), Web, Security, Release y Status consistency exact-head también pasaron.

El PR [#412](https://github.com/SauronShepherd/ronin/pull/412) delega a PostgreSQL el cambio durable de workflow a `cancelling`, la cancelación de tareas sin intent, el retiro de intents aún no enviados y la reconciliación de Jobs cancelados. La autoridad de cancelación se persiste antes de esperar bloqueos de tareas. Sus 17 pruebas PostgreSQL pasaron en Docker/PostgreSQL 16 con 82% de cobertura del adaptador; CI 3.11/3.12 y Docker qualification completa (**8m14s**) también pasaron. El squash quedó en `main@897e04a3b6c4219d82ed70d13a126c27a97cff4c`; CI, Docker, Web, Security, Release y Status consistency exact-head de main pasaron.

El PR [#414](https://github.com/SauronShepherd/ronin/pull/414) añadió migración PostgreSQL 9→10 con cursores monotónicos y ledger idempotente de schedule fires, implementación del contrato HTTP completo y montaje condicionado de rutas workflow/schedule en Compose. PostgreSQL 16 en Docker pasó **19 pruebas**, incluida una ruta HTTP real, y el módulo nuevo obtuvo 100% de cobertura de líneas y ramas. El PR pasó CI 3.11/3.12 y Docker qualification (**7m54s**); quedó integrado en `main@98e79db96ef45cfca6c3678c59475d5f74d024b6`. CI, Docker, Web, Security, Release y Status consistency exact-head de esa base pasaron. Las rutas generales workflow/schedule están disponibles cuando el backend expone todas las operaciones del contrato.

El PR [#415](https://github.com/SauronShepherd/ronin/pull/415) añadió takeover del `SchedulerDaemon` sobre stores PostgreSQL aislados: tras expirar el lease anterior, la instancia nueva adquiere generación 2 y vuelve a leer el cursor/fire persistente sin duplicarlo. PostgreSQL 16 en Docker pasó **20 tests** del módulo completo y CI 3.11/3.12 más Docker qualification (**6m37s**) pasaron antes del merge `main@2abc6ac3495ae3aa61a406f6f8c5be3e3478b796`. Los checks post-merge CI, Web, Security, Release y Status consistency están verdes; Docker qualification sigue en ejecución. El test cubre takeover/replay de schedule, no recovery del controller.

El candidato `codex/daemon-notification-lease-renewal` mueve la entrega síncrona de notificaciones fuera del event loop y renueva el lease durante proveedores lentos. La regresión verifica que un contender no obtiene liderazgo cuando el dispatcher excede el lease inicial. El módulo de daemon pasa **9 tests**; con PostgreSQL 16 en Docker pasan **29 tests** de daemon y scheduler. Ruff, formato, mypy y `git diff --check` también pasan. No se han cualificado endpoints SMTP/HTTPS reales ni la entrega completa a través de caída abrupta; P5 sigue parcial y el progreso release-qualified permanece en **0% (0/14)**.

