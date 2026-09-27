# Data Enginerring Studio

## Scope

Data Enginerring Studio is Ronin's data-engineering plugin for designing,
validating, previewing, debugging, and executing local data pipelines. The
canonical pipeline representation is provider-neutral. A single pipeline can
be compiled for local preview, Spark Connect, or Spark Declarative Pipelines
(SDP Studio) without changing the authored pipeline.

The exact user-facing product name is **Data Enginerring Studio**. The spelling
is preserved for compatibility with the existing Ronin product surface.

## Architecture

The plugin boundary is `studio_data_engineering`. Its contracts cover:

- canonical pipeline IR and deterministic compilation;
- bounded local fixture preview;
- Spark Connect through `SparkSession.builder.remote`;
- SDP Studio project import and provider integration;
- immutable revisions and SQLite compilation records;
- durable run planning and execution bridging;
- SHA-256 evidence artifacts and observed lineage;
- IDE cell/session state and debugger breakpoints;
- runtime qualification and external-provider diagnostics.

The HTTP routes are:

| Method | Route | Purpose |
|---|---|---|
| GET | `/v1/data-engineering/health` | Readiness and provider state |
| GET | `/v1/data-engineering/runtimes` | Runtime capabilities |
| POST | `/v1/data-engineering/pipelines/validate` | Compile and validate IR |
| POST | `/v1/data-engineering/pipelines/preview` | Execute bounded local preview |
| POST | `/v1/data-engineering/pipelines/runs` | Create a durable run plan |
| POST | `/v1/data-engineering/sdp/import` | Import an SDP project losslessly |

The control plane maps `data-engineering:read` to `project.read`,
`data-engineering:write` to `project.write`, and
`data-engineering:execute` to `scheduler.write`. Studio assets are served by
Ronin under `/studio/` and can share the API origin.

## Runtime portability

Validation produces an IR digest, runtime, node/edge counts, and diagnostics.
A provider may reject an unsupported construct, but it must not silently alter
the authored IR.

- `local-preview` executes bounded fixture data deterministically.
- `spark-connect` sends SQL to an external Spark Connect endpoint and returns
  bounded rows plus endpoint and execution evidence.
- `spark-sdp` delegates declarative compilation to SDP Studio while preserving
  Ronin identity, source digests, artifacts, and execution governance.

## Persistence and evidence

Revisions are content-addressed and optimistic-concurrency protected.
Compilation reports and outbox records are transactional. Execution evidence
is stored with SHA-256 metadata. A stale lease token cannot write evidence.
Lineage retains the execution reference and can be exported as OpenLineage
observations.

## IDE and debugging

IDE cells retain authored source, prepared execution, outputs, diagnostics,
breakpoints, and execution state. Runtime adapters supply execution while the
Studio preserves cell and pipeline identity across preview and durable runs.

## Qualification gates

1. Module tests, Ruff, and bytecode compilation pass.
2. Ronin HTTP serves Studio assets and dispatches plugin routes.
3. Browser E2E executes Validate, Preview, and Submit against Ronin HTTP.
4. A real Spark Connect server executes `select 1` and persists evidence.
5. The official SDP Studio CLI validates an imported project and reports
   `Pipeline model is valid.`.
6. Durable execution, outbox, fencing, evidence, and lineage tests pass.

The optional JSON-stdio SDP adapter is an additional provider contract; it is
not a substitute for qualification against the official SDP Studio CLI.

## Source documents

The Spanish proposal and historical analysis remain available for traceability:

- `PROPUESTA_PLUGIN_DATA_ENGINEERING_RONIN.md`
- `PROPUESTA_DATA_ENGINERRING_STUDIO_DETALLADA.md`
- `BUILD_PLAN_DATA_ENGINERRING_STUDIO.md`
- `AUDITORIA_SDP_STUDIO_DATA_ENGINERRING.md`

This document is the English implementation reference. The English release
gate is maintained in `DATA_ENGINERRING_STUDIO_RELEASE_CHECKLIST_EN.md`.
