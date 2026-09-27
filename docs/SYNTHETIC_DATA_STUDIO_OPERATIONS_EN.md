# Synthetic Data Studio Operations Guide

## Scope

Synthetic Data Studio runs locally in Ronin Community. It does not require
external catalogs, credentials, DNS, or network access. External synchronization
with Databricks, Snowflake, Glue, or remote Unity/Polaris services is a Ronin Pro
capability and is not enabled by Community configuration.

## Configuration

```text
SDS_MAX_ROWS_PER_RUN=100000
SDS_MAX_TABLES_PER_PLAN=100
SDS_MAX_COLUMNS_PER_TABLE=2000
SDS_JOBS_DB=<local SQLite path>
```

`SDS_JOBS_DB` is optional. Without it, jobs are process-local. With it, runs,
job plans, job status, owners, epochs, and lease expiry are persisted.

## Health and readiness

```http
GET /v1/synthetic-data-studio/health
```

The response reports service and catalog readiness. A missing catalog is
`degraded`; it is never interpreted as proof of governance or privacy.

## Generation operations

Synchronous generation:

```http
POST /v1/synthetic-data-studio/generate
```

Asynchronous generation:

```http
POST /v1/synthetic-data-studio/generate/async
GET  /v1/synthetic-data-studio/jobs/{job_id}
POST /v1/synthetic-data-studio/jobs/{job_id}/cancel
```

Jobs transition through `queued`, `running`, `completed`, `failed`, and
`cancelled`. Cancellation is cooperative and terminal cancellation is
idempotent.

## Job durability and leases

When SQLite jobs are enabled, a worker atomically claims a queued job using
`lease_owner` and increments `lease_epoch`. The lease lasts 60 seconds and is
renewed every 10 seconds by a heartbeat. A new facade may reclaim a running job
only after its lease expires. This prevents concurrent execution of an active
job and supports recovery after process failure.

## Catalog operations

Local providers are exposed by:

```http
GET /v1/synthetic-data-studio/catalog/providers
```

Available profiles:

```text
ronin-sqlite
unity-catalog-local
polaris-local
```

Namespace formats are:

```text
Unity Catalog local: catalog.schema.table
Polaris local:       catalog.namespace.table
```

Namespaces are registered and listed through the catalog namespace endpoints.
Assets, revisions, search, and upstream/downstream lineage are local SQLite
operations.

## Export and artifacts

Formats are discovered through `/formats`. The UI only presents formats whose
status is `available`. Export requires a run ID, table name, and format ID.
Configured artifact storage receives content, media type, byte size, and digest.

## Privacy and governance

Synthetic output is not automatically anonymous. Validation covers structural
correctness. The privacy assessment reports exact row reuse when a bounded
source sample is supplied and returns `not_assessed` when no sample exists.
`review_required` must be treated as a governance gate, not as a warning to
ignore.

## Backup and recovery

Back up the SQLite database and artifact storage as one logical snapshot. Restore
both together so run IDs, catalog revisions, lineage, and digests remain valid.
After a process crash, queued jobs are reloaded and expired running leases may
be reclaimed. Active leases are protected by owner and epoch checks.

## Troubleshooting

| Symptom | Action |
|---|---|
| `degraded` catalog health | Verify the configured local catalog store and workspace migration |
| No export controls | Check `/formats` and install the optional format dependency |
| Job remains running | Inspect `lease_expires_at`, owner, and SQLite availability |
| `review_required` privacy | Review exact source-row matches before publication |
| Missing assets | Check workspace ID and catalog migration version |
| External catalog unavailable | Expected in Community; use a Pro connector |

## Release verification

```text
pytest -q tests/test_synthetic_data.py \
  tests/test_synthetic_data_plugin.py \
  tests/test_synthetic_data_async.py \
  tests/test_synthetic_data_publication.py \
  tests/test_synthetic_data_persistence.py \
  tests/test_synthetic_data_public_surface.py \
  tests/integration/test_workspace_project_http_api.py::test_govern_studio_routes_execute_through_real_http_server
node --check web/js/synthetic-data-studio.js
python tools/architecture_gate.py
```

