# Ronin Public v1 scope

**Status:** normative product contract for the first public release  
**Supersedes for release gating:** `V01_SCOPE.md`  
**Does not erase:** the v0.1 execution foundation; that work becomes the execution/control-plane substrate of the larger platform.

## 1. Release principle

Ronin MUST NOT present a first public product release as complete until it is a coherent, self-hostable Data + AI operating platform rather than only a durable notebook runner.

The first public release is **Ronin Public v1**. The existing `0.1.0a*` line is an engineering alpha and foundation milestone, not the product-completeness gate.

Public v1 is intended to let a team migrate a representative project away from Microsoft Fabric, Databricks, Palantir Foundry/AIP, or Dataiku DSS, operate that project in Ronin without a mandatory dependency on the source vendor, and export the portable parts again through documented adapters.

Ronin does not promise fictional byte-for-byte compatibility with every proprietary feature of those products. It promises a documented migration profile, explicit loss reporting, no silent semantic downgrade, and an open canonical representation for the supported intersection.

## 2. Product identity

Ronin is a professional, free, open-source and self-hostable **Data + AI OS platform**.

It combines in one product:

1. workspaces, projects, repositories, environments and secrets;
2. data connections, ingestion and lakehouse assets;
3. SQL, notebooks and code execution;
4. a DAG planner/scheduler and event-driven automation;
5. catalog, lineage, governance, ontology and knowledge graph;
6. data quality and contracts;
7. AI/ML experimentation, registry, evaluation and serving;
8. GenAI/RAG/agent development and evaluation;
9. graph intelligence and provider-neutral graph execution;
10. semantic models, metrics and dashboards;
11. real-time/streaming data processing and triggers;
12. observability, alerts, budgets and FinOps;
13. migration/import/export adapters for major data/AI platforms;
14. CLI, HTTP API, Python SDK and a web Studio over the same contracts.

## 3. Existing foundation retained

The current durable execution foundation remains useful and MUST be preserved where compatible:

- Job -> Run -> Attempt durable lifecycle;
- idempotency, leases, heartbeat, reclaim and resume;
- project-scoped authenticated HTTP control plane;
- CLI and `pyronin`;
- portable evidence and canonical identity formats;
- Docker worker execution;
- repository revision identity;
- typed grants and fail-closed transport policy.

These are platform primitives, not the finished product.

## 4. Mandatory Public v1 capability families

### P1 — Workspace, project and source control

Public v1 MUST provide:

- multi-project workspaces;
- Git-backed project source with explicit revision identity;
- project export/import through the Ronin Bundle format;
- environment/profile selection;
- secrets by reference, never embedded in project artifacts;
- project-scoped permissions and audit events;
- reproducible development and deployment manifests.

### P2 — Data connections and ingestion

Public v1 MUST provide:

- file/object-store ingestion;
- JDBC/SQL source ingestion;
- HTTP/API source ingestion;
- batch copy/sync;
- incremental ingestion using cursor/watermark semantics;
- connector contracts that expose schema, capabilities and lineage;
- credential references separated from portable project definitions;
- explicit unsupported/partial connector behavior.

A minimum connector matrix is required for PostgreSQL, generic JDBC, S3-compatible object storage, Azure-compatible object storage, local files and HTTP/REST.

### P3 — Lakehouse and SQL

Public v1 MUST provide a vendor-neutral data layer using open formats where possible:

- Parquet read/write;
- Iceberg support;
- Delta Lake interoperability profile sufficient for Fabric/Databricks migration cases;
- managed and external table metadata;
- SQL query execution through a pluggable engine contract;
- table/view lifecycle;
- schema evolution policy;
- partitioning and snapshot metadata;
- zero-copy/external-location references where practical.

### P4 — Data Engineering Studio

Public v1 MUST provide:

- notebook editing/execution;
- SQL editor;
- code task execution;
- visual or declarative pipeline graph;
- reusable transforms;
- parameterized runs;
- artifact/evidence view;
- lineage from inputs through outputs.

The web Studio is a first-class product surface. CLI/API-only operation remains supported for automation.

### P5 — Planner and scheduler

Ronin MUST include an Airflow-class orchestration surface without requiring Airflow as the product control plane.

Required semantics:

- DAG tasks and dependencies;
- cron/time schedules;
- event/manual/API triggers;
- retries and retry policy;
- timeouts;
- backfills;
- conditional branches;
- parameter passing;
- concurrency limits;
- queues/pools or equivalent resource classes;
- cancellation;
- run history;
- task-level evidence;
- failure notifications;
- deterministic scheduler state persisted durably.

### P6 — Catalog, lineage, ontology and knowledge graph

Public v1 MUST include a persistent semantic catalog, not only a session graph catalog.

It MUST represent:

- datasets/tables/views/files/streams;
- notebooks, SQL queries, pipelines and tasks;
- models, experiments, features and endpoints;
- dashboards and semantic models;
- users/service identities and ownership metadata;
- object types, properties, interfaces and relationships;
- lineage edges between assets;
- business glossary terms/tags/classifications;
- policy and quality status.

The ontology layer defines real-world object types and link types. The knowledge graph materializes or virtually resolves object instances and relationships from governed data sources.

Ronin Graph Intelligence/RQL becomes one query/execution subsystem over this semantic foundation rather than the entire product.

### P7 — Data quality and contracts

Required:

- schema contracts;
- null/uniqueness/range/domain checks;
- custom SQL/Python checks;
- freshness checks;
- run-level quality evidence;
- severity and blocking policy;
- quality state visible in catalog and lineage;
- alert integration.

### P8 — AI/ML Lab Studio

Public v1 MUST provide a usable AI/ML lifecycle:

- experiments and runs;
- parameter/metric/artifact tracking;
- notebook and script training;
- visual baseline training workflow for tabular ML;
- dataset/snapshot binding;
- feature definitions and reusable feature assets;
- model registry with versions/stages/aliases;
- MLflow model import/export interoperability;
- model evaluation and comparison;
- drift/performance evaluation hooks;
- batch inference;
- HTTP serving contract or pluggable serving adapter;
- lineage from data -> run -> model -> deployment.

### P9 — GenAI, RAG and agents

Because the product claims Data + AI platform scope, Public v1 MUST include a bounded but real GenAI surface:

- model/provider registry;
- prompt assets and versions;
- embeddings and vector-index abstraction;
- retrieval pipeline;
- RAG evaluation datasets and metrics;
- tool/function registry;
- agent/workflow execution with explicit permissions;
- token/latency/cost telemetry;
- no secret values in traces by default.

### P10 — Semantic models, metrics and dashboards

Public v1 MUST include:

- reusable measures/metrics;
- dimensions and relationships;
- semantic model versioning;
- SQL-backed exploration;
- dashboard definitions;
- basic charts, tables, filters and drill behavior;
- exportable declarative definitions.

The goal is portability and operational usefulness, not pixel-perfect Power BI compatibility.

### P11 — Real-time and streaming

Required minimum:

- stream/source contract;
- event ingestion;
- checkpointed processing;
- windowed transformation primitives;
- stream-to-table sink;
- event-triggered workflows;
- real-time health and lag metrics.

### P12 — Observability, Alerts and FinOps Control Center

Public v1 MUST expose one control center for platform operations and cost governance.

Required telemetry:

- job/task status and duration;
- failures/retries/cancellations;
- CPU/memory/storage/network evidence when available;
- rows/bytes processed;
- model serving/request metrics;
- GenAI token usage;
- scheduler queue/lag;
- connector freshness/lag;
- quality failures;
- estimated and actual cost records where a provider exposes price/usage data.

Required controls:

- alert rules with thresholds and state transitions;
- notification adapter contract;
- budgets by workspace/project/team/tag;
- cost allocation tags;
- anomaly hooks;
- expensive-run/resource views;
- cost forecast hook;
- policy actions such as warn, block new work, or require approval.

### P13 — Security and governance

Public v1 MUST provide:

- OIDC/OAuth2-compatible authentication for multi-user deployments;
- project/workspace RBAC or typed-grant equivalent with named roles;
- service identities;
- secret resolver abstraction;
- audit log;
- data sensitivity/classification metadata;
- transport security policy;
- redaction rules;
- least-privilege execution;
- private vulnerability-reporting channel before release;
- dependency/license/SBOM/provenance release evidence.

### P14 — Deployment and operations

Required supported deployment profiles:

1. local developer mode;
2. Docker/Compose single-host reference deployment;
3. Kubernetes reference deployment for multi-user/server operation.

SQLite MAY remain for local development. Public multi-user server deployment MUST have a production metadata-store profile with transactional concurrency suitable for multiple workers.

## 5. Migration and portability requirement

The first public release MUST implement the migration contract in `PLATFORM_PORTABILITY_V1.md` for certified profiles of:

- Microsoft Fabric;
- Databricks;
- Palantir Foundry/AIP;
- Dataiku DSS.

A migration is not considered successful merely because files were copied. The imported project must be inspectable, executable for the certified subset, schedulable, observable, governed and exportable through Ronin's canonical bundle.

## 6. Web Studio requirement

The first public release MUST ship a coherent web Studio with at least these top-level areas:

- Home / Projects;
- Data;
- Pipelines;
- Notebooks / SQL;
- Catalog;
- Ontology / Knowledge Graph;
- AI/ML Lab;
- GenAI Lab;
- Models / Deployments;
- Dashboards;
- Monitoring & Alerts;
- Cost Control;
- Administration.

All UI mutations MUST be representable through documented backend APIs. The UI is not a second semantic implementation.

## 7. Brand contract

Ronin's primary identity is **brown**, with gold/amber accents and charcoal/ivory neutrals. See `BRAND_V1.md`.

The UI MUST NOT use red, green or blue as the dominant brand color. Those colors remain available for semantic status indications where appropriate.

## 8. Public release gate

Ronin Public v1 may be declared only when all of the following are true:

- P1-P14 each have an end-to-end supported path;
- the web Studio exposes the mandatory product surfaces;
- the canonical Ronin Bundle round-trips without losing Ronin-native semantics;
- each certified vendor migration profile has golden fixtures and migration reports with no undisclosed loss;
- the four vendor profiles can be imported into Ronin and run through their published acceptance journeys;
- security, audit, secrets and multi-user authorization are enabled in the server profile;
- monitoring, alerts and cost records are visible for scheduled workloads;
- the scheduler survives process restart without corrupting run state;
- lakehouse/SQL, ML, ontology/KG, dashboards and streaming have working reference journeys;
- a clean install from release artifacts succeeds without source-tree leakage;
- license/SBOM/provenance evidence is complete;
- a private security reporting path exists and is tested;
- documentation clearly distinguishes exact, translated, partial, passthrough and unsupported migration behavior;
- release evidence is generated from the exact candidate commit.

There is no percentage shortcut for this gate. Missing a mandatory capability family means Public v1 is not complete.

## 9. What remains allowed before Public v1

Before Public v1, the repository may publish source code, design documents, development snapshots or alpha packages, but they MUST be labeled as incomplete engineering artifacts and MUST NOT be marketed as the completed Data + AI OS.

## 10. Relationship to the original graph specification

The original Spark/RQL property-graph specification remains valuable as the design contract for Ronin's Graph Intelligence subsystem:

- provider-neutral graph semantics;
- Native Spark reference execution;
- GraphFrames/Neo4j/PuppyGraph provider model;
- graph catalog/binding concepts;
- explainability and differential semantics.

Public v1 expands the product around that subsystem rather than replacing its semantic goals.
