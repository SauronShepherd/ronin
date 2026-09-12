# Ronin Public v1 implementation roadmap

**Status:** implementation roadmap for the first complete public release

This roadmap replaces the earlier assumption that a durable notebook runner is sufficient for the first public version. The current execution/control-plane work is retained as foundation work.

## 1. Delivery model

Public v1 is delivered in waves. A wave is not complete because files exist; each wave must have an end-to-end operator journey, documented contracts and migration implications.

Tests/CI policy may temporarily limit qualification evidence, but the product gate itself does not shrink.

## 2. Wave A — Foundation normalization

Goal: turn the current alpha execution spine into reusable platform infrastructure.

Required work:

- finish source/static hygiene and current alpha contract reconciliation;
- formalize workspace/project identifiers above the current project-only model;
- introduce production metadata-store abstraction while retaining SQLite local mode;
- define audit event model;
- define notification adapter contract;
- define durable resource/evidence model shared by pipelines, data, ML and agents;
- define plugin/adapter discovery and capability model;
- preserve canonical JSON identity and existing durable/fencing invariants.

Exit: current notebook workload still works, but its lifecycle types are no longer narrowly tied to the old MVP assumptions.

## 3. Wave B — Canonical portable project and migration kernel

Goal: make Ronin itself portable before importing other platforms.

Required work:

- implement versioned Ronin Bundle schema;
- bundle import/export;
- migration report schema with exact/translated/partial/passthrough/unsupported/manual-decision statuses;
- connection/secret/runtime remapping manifest;
- deterministic asset IDs;
- package project source + metadata without secrets;
- lossless Ronin -> Ronin round-trip.

Then implement vendor discovery/import in this order:

1. Databricks;
2. Microsoft Fabric;
3. Dataiku DSS;
4. Palantir Foundry/AIP.

The order is implementation convenience, not product priority.

Exit: each importer can inventory a representative project and generate a complete migration report even before every object type is executable.

## 4. Wave C — Data platform core

Goal: support real data workloads independently of a source vendor.

Required work:

- connection registry;
- local files;
- S3-compatible storage;
- Azure-compatible object storage;
- PostgreSQL;
- generic JDBC adapter;
- HTTP/REST connector;
- copy/sync ingestion;
- watermark/cursor incremental ingestion;
- Parquet;
- Iceberg;
- Delta interoperability profile;
- managed/external tables;
- SQL engine SPI and first supported SQL engine;
- schema evolution and snapshot metadata;
- lineage emission for reads/writes/transforms.

Exit: a migrated data-engineering project can ingest, transform, query and persist datasets without its original vendor.

## 5. Wave D — Planner, scheduler and Data Engineering Studio

Goal: provide Airflow-class orchestration as an integrated Ronin capability.

Required work:

- durable DAG definition;
- task dependency model;
- cron/time schedule;
- API/manual/event triggers;
- retries/timeouts;
- backfill;
- branching/conditionals;
- task parameters;
- resource pools/concurrency limits;
- cancellation;
- restart-safe scheduler state;
- task/run history;
- notification hooks;
- visual/declarative pipeline editor;
- notebook and SQL task integration;
- reusable transform nodes.

Exit: representative Fabric pipeline, Databricks Job and Dataiku Scenario migrations run on the Ronin scheduler with explicit translation reports.

## 6. Wave E — Catalog, lineage, ontology and knowledge graph

Goal: create the semantic backbone of the platform.

Required work:

- persistent catalog service;
- asset type registry;
- ownership/tags/classification;
- searchable metadata;
- lineage graph;
- glossary/business terms;
- object types;
- properties;
- link types;
- interfaces;
- governed action/function contracts;
- object-instance materialization/reference policies;
- ontology mapping from data assets;
- knowledge-graph query API;
- integrate the original RQL/Graph Intelligence design as a provider-neutral graph-query subsystem;
- ontology and lineage explorer in the web Studio.

Exit: a Palantir-style ontology fixture can be represented, linked to governed data and queried without losing its declared object/link semantics.

## 7. Wave F — Data quality and semantic analytics

Goal: make datasets and metrics governable and consumable.

Required work:

- schema/data contracts;
- freshness/null/uniqueness/range/domain rules;
- custom SQL/Python quality checks;
- severity/blocking policy;
- quality status in catalog/lineage;
- semantic models;
- dimensions/relationships;
- reusable measures/metrics;
- dashboard definitions;
- basic charts/tables/filters/drill;
- exportable declarative definitions.

Exit: migrated Fabric semantic-model/report cases and Dataiku metrics/checks have useful Ronin equivalents with explicit unsupported visual semantics.

## 8. Wave G — AI/ML Lab and MLOps

Goal: provide a complete practical ML lifecycle.

Required work:

- experiment/run tracking;
- parameters/metrics/artifacts;
- dataset snapshot lineage;
- notebook/script training;
- visual baseline tabular training;
- reusable feature assets;
- model registry/version/alias/state;
- MLflow import/export;
- model evaluation/comparison;
- drift/performance hooks;
- batch inference;
- pluggable HTTP serving;
- deployment state and telemetry;
- lineage data -> experiment -> model -> deployment;
- AI/ML Lab web surface.

Exit: a Dataiku visual-ML fixture and a Databricks MLflow fixture can be imported, evaluated and operated in Ronin for the certified subset.

## 9. Wave H — GenAI/RAG/agents

Goal: satisfy the AI platform claim beyond classical ML.

Required work:

- model/provider registry;
- prompt/version assets;
- embedding provider abstraction;
- vector-index abstraction;
- retrieval pipelines;
- RAG evaluation datasets and metrics;
- tool/function registry;
- agent/workflow execution;
- permission-aware tools;
- trace redaction;
- token/latency/cost telemetry;
- GenAI Lab web surface.

Exit: one local/open model path and one external-provider adapter execute the same bounded RAG/agent reference journey.

## 10. Wave I — Streaming and real-time

Goal: support event-driven workloads rather than batch only.

Required work:

- stream connector contract;
- event ingestion;
- checkpoint model;
- windowed transforms;
- stream-to-table sink;
- event-triggered DAG execution;
- lag/health telemetry;
- integration with alerts.

Exit: a stream can be ingested, transformed, persisted, monitored and used to trigger a workflow after restart without checkpoint corruption.

## 11. Wave J — Monitoring, alerts and FinOps

Goal: provide a unified operational and cost-control center.

Required work:

- telemetry normalization across jobs/tasks/connectors/ML/GenAI/streaming;
- metrics and log/evidence views;
- alert rule engine;
- alert state transitions/deduplication;
- notification adapters;
- workspace/project/team/tag budgets;
- cost allocation;
- provider usage ingestion;
- estimated-cost model for local/self-hosted compute;
- anomaly and forecast hooks;
- warn/block/approval policy actions;
- expensive-run and resource attribution views;
- Monitoring & Alerts UI;
- Cost Control UI.

Exit: scheduled workloads expose health, failure alerts, resource attribution and budget state in one place.

## 12. Wave K — Multi-user security and server deployment

Goal: make the system safe for organizational use.

Required work:

- OIDC/OAuth2-compatible authentication;
- users/groups/service identities;
- workspace/project roles and typed grants;
- authorization enforcement across APIs and scheduler;
- audit log;
- secret backend adapters;
- security classifications/policy metadata;
- production metadata store;
- multiple workers;
- Kubernetes reference deployment;
- backup/restore/migration procedures;
- private vulnerability reporting channel before release.

Exit: multi-user reference deployment survives restart/worker loss and preserves authorization/audit invariants.

## 13. Wave L — Web Studio integration

The web Studio is developed incrementally with prior waves, but Public v1 cannot ship until the product is coherent end to end.

Mandatory top-level navigation:

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

All first-party UI uses `BRAND_V1.md` and the Ronin Brown design tokens.

## 14. Wave M — Vendor certification

Run the complete portability fixtures from `PLATFORM_PORTABILITY_V1.md`.

Required profiles:

### Databricks

- bundle/workspace assets;
- notebook;
- lakehouse table;
- job DAG + schedule;
- Unity Catalog metadata/lineage subset;
- MLflow experiment/model;
- SQL/dashboard artifact where publicly retrievable.

### Microsoft Fabric

- workspace item definitions;
- notebook;
- lakehouse/warehouse asset;
- pipeline;
- semantic model;
- report/dashboard definition where portable;
- real-time/streaming artifact for certified subset.

### Dataiku DSS

- project bundle;
- Flow datasets/recipes;
- Scenario + trigger;
- visual recipe;
- code recipe/notebook;
- ML model/evaluation;
- metrics/checks.

### Palantir Foundry/AIP

- datasets;
- pipeline/build artifact where exportable;
- ontology object/property/link/interface subset;
- action/function-shaped portable artifact;
- analytical or AI consumer.

Exit: every source object is classified, supported assets run, and no undisclosed loss exists.

## 15. Wave N — Release hardening

Only after the product waves exist:

- exact-head conformance;
- migration golden fixtures;
- clean installation;
- performance/resource qualification;
- backup/restore qualification;
- security qualification;
- license review;
- SBOM;
- provenance;
- release runbook;
- upgrade/migration path;
- API compatibility review;
- docs and examples;
- vulnerability reporting verification.

## 16. Priority rules

When choosing work, use this order:

1. preserve durable/canonical invariants already implemented;
2. implement canonical Ronin asset models before vendor adapters;
3. implement executable platform capability before UI polish;
4. import/export must report loss before claiming compatibility;
5. prefer open formats/protocols over vendor emulation;
6. no secret material in portable assets;
7. no silent fallback that changes semantics;
8. one backend API contract shared by UI, CLI and SDK;
9. do not add a new subsystem without catalog/lineage/observability hooks;
10. do not mark Public v1 complete while any P1-P14 family in `PUBLIC_V1_SCOPE.md` lacks an end-to-end path.

## 17. Immediate next implementation sequence

The next concrete implementation sequence after this contract is merged is:

1. Ronin Bundle model + deterministic manifest;
2. asset/migration status model and report;
3. workspace abstraction above projects;
4. connection/secret remapping model;
5. persistent catalog asset core + lineage edges;
6. DAG/scheduler domain model leveraging existing Job/Run/Attempt durability;
7. first Databricks discovery/import slice;
8. first Fabric discovery/import slice;
9. first Dataiku project/Flow discovery slice;
10. first Palantir ontology discovery/mapping slice;
11. data connectors/lakehouse/SQL execution path;
12. web Studio shell using Ronin Brown tokens.

This sequence deliberately turns existing infrastructure into a migration-capable platform before expanding into ML/GenAI and advanced UI surfaces.
