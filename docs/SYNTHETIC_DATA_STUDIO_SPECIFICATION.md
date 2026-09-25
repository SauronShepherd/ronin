# Synthetic Data Studio

## Functional, Architecture, and Technical Specification

**Product:** Ronin Synthetic Data Studio  
**Plugin ID:** `com.ronin.synthetic-data-studio`  
**Scope:** Ronin Community, local-first and offline  
**External integrations:** Ronin Pro only  
**Status:** Complete for the documented Community scope

## 1. Product definition

Synthetic Data Studio generates deterministic synthetic relational data from
declarative plans and governs the resulting artifacts in a local Ronin catalog.
It combines generation, validation, privacy evidence, catalog registration,
revisions, lineage, export, asynchronous jobs, and a Studio UI.

The Community module must operate without external credentials, DNS, HTTP
connections, or remote catalog services. SQLite is the reference local store.

### Goals

- Generate reproducible test fixtures from safe JSON plans.
- Enforce bounded tables, columns, and rows before generation.
- Validate schema, row count, nullability, primary keys, and foreign keys.
- Make privacy limitations explicit rather than claiming automatic anonymity.
- Publish generated outputs as local governed assets.
- Track revisions, content/schema digests, and lineage.
- Support Ronin, Unity Catalog-style, and Polaris-style local namespaces.
- Provide synchronous and bounded asynchronous execution with cancellation.
- Expose all local capabilities through a permissioned HTTP API and UI.

### Non-goals

Community does not connect to Databricks, Snowflake, AWS Glue, or remote
catalogs; manage external secrets; provide distributed orchestration; or claim
that synthetic data is automatically anonymous. Those are separate Pro
capabilities.

## 2. Plugin contract

```text
id:             com.ronin.synthetic-data-studio
name:           Synthetic Data Studio
version:        0.1.0
plugin_api:     1.0
host_requires:  >=1,<2
permissions:    synthetic:read
                synthetic:write
                synthetic:execute
capabilities:   synthetic-data-studio.plan.v1
                synthetic-data-studio.generate.v1
                synthetic-data-studio.validate.v1
                synthetic-data-studio.export.v1
                synthetic-data-studio.jobs.v1
```

The plugin registers routes and permissions through Ronin's contribution
registry. The host remains the authentication and authorization boundary.

## 3. Architecture

```text
Studio UI
  -> SyntheticDataStudioPlugin (routes, limits, permissions, health)
      -> GovernStudioService (runs, validation, export, idempotency)
      -> LocalGenerationJobs (executor, SQLite jobs, claims, leases)
      -> Synthetic engine (pure deterministic generation and evidence)
      -> SqliteCatalogStore (assets, revisions, namespaces, lineage)
      -> Artifact store (exported content and digests)
```

### Components

| Component | Responsibility |
|---|---|
| `engine.py` | Pure generation, profiling, validation, privacy assessment, exporter contracts |
| `application.py` | Run lifecycle, idempotency, durable run persistence, export orchestration |
| `plugin.py` | Public manifest, HTTP routes, payload decoding, limits and health |
| `async_generation.py` | Bounded jobs, cancellation, SQLite state, claims and heartbeat |
| `local_catalogs.py` | Provider profiles and namespace resolution |
| `publication.py` | Converts generated output into catalog asset/revision/lineage |
| `studio_storage.catalog` | SQLite catalog persistence and migrations |
| `synthetic-data-studio.js` | UI generation, catalog, lineage, revisions and export |

The engine must not perform network I/O or mutate catalog state. Publication is
an explicit application boundary after generation and validation.

## 4. Domain model

### Column

```python
ColumnSpec(
    name: str,
    kind: str = "string",
    nullable: bool = True,
    null_rate: float = 0.0,
    values: tuple[str, ...] = (),
    minimum: int = 0,
    maximum: int = 100,
)
```

Built-in kinds are `string`, `integer`, `number`, `boolean`, `email`, `uuid`,
and `date`. Explicit values override generated values. Nullability and null
rate are bounded by the plan parser.

### Table and relationship

```python
TableSpec(name, columns, primary_key=None, rows=0)
ForeignKey(child_table, child_column, parent_table, parent_column)
```

Names are non-empty and unique within scope. Primary keys must reference a
declared column. Parents are generated before child foreign keys are resolved.

### Run, result, asset, revision, lineage

A run stores `run_id`, plan fingerprint, lifecycle status, result, validation,
errors, and artifacts. A result contains generated tables, warnings, state, and
fingerprint. A catalog asset has identity, kind, name, tags, classifications,
and properties. A revision records a version, schema digest, content digest,
and generation metadata. A lineage edge connects source and target revisions
with operation, mode, execution reference, and deterministic digest.

## 5. Generation semantics

1. Decode a JSON-compatible plan; executable code is never accepted.
2. Validate shape and resource limits.
3. Compute a stable normalized plan fingerprint.
4. Initialize a seeded, non-cryptographic random generator.
5. Generate parent tables and primary keys.
6. Generate child tables.
7. Resolve declared foreign keys from generated parent values.
8. Attach warnings for source-sample-assisted generation or skipped relations.
9. Return a `GenerationResult`; publication is explicit.

The same normalized plan and seed produce the same result. The RNG is not for
passwords, tokens, secrets, or security decisions.

## 6. Validation and privacy

`ValidationReport` contains `passed`, `checks`, `errors`, and deterministic
`evidence_id`. Required checks are:

```text
schema
row_count
nullability
primary_key_uniqueness
foreign_key_integrity
privacy_disclaimer
```

Validation fails for missing tables, schema mismatch, incorrect row counts,
nullability violations, duplicate primary keys, or broken foreign keys.

`PrivacyAssessment` contains:

```json
{
  "status": "not_assessed | no_exact_matches_observed | review_required",
  "generated_rows": 0,
  "exact_row_matches": 0,
  "warnings": []
}
```

With a bounded `source_sample`, rows are canonicalized and exact matches are
counted. This is evidence only; it does not assess linkage, inference,
distributional disclosure, k-anonymity, l-diversity, t-closeness, or DP.

## 7. HTTP API

All routes are under `/v1/synthetic-data-studio` and return JSON.

```text
GET  /formats
GET  /health
POST /plans
POST /generate
POST /validate
GET  /runs
GET  /runs/{run_id}
POST /generate/async
GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel
POST /export
GET  /catalog/providers
POST /catalog/resolve
GET  /catalog/namespaces
POST /catalog/namespaces
GET  /catalog/assets
GET  /catalog/assets/{asset_id}
GET  /catalog/assets/{asset_id}/revisions
GET  /catalog/assets/{asset_id}/lineage?version=...
```

### Generation request

```json
{
  "plan": {
    "seed": 42,
    "tables": [{
      "name": "customers",
      "rows": 10,
      "primary_key": "id",
      "columns": [
        {"name": "id", "kind": "integer", "nullable": false},
        {"name": "email", "kind": "email", "nullable": false}
      ]
    }]
  },
  "source_sample": {}
}
```

The response contains `status`, `run_id`, `planFingerprint`, tables, warnings,
validation, privacy, and error fields.

### Async job request/response

`POST /generate/async` returns `job_id`, `run_id`, `status`, and contract
`synthetic-data-studio/jobs/v1`. Polling returns `queued`, `running`,
`completed`, `failed`, or `cancelled`. Terminal cancellation is idempotent.

### Export request

```json
{"run_id":"run-id", "format_id":"jsonl", "table":"customers"}
```

The response includes content and, when configured, artifact storage reference,
digest, byte size, and media type.

## 8. Catalog and namespace architecture

Catalog migration 001 creates `catalog_assets`,
`catalog_asset_revisions`, and `lineage_edges`. Migration 002 creates:

```text
catalog_namespace_bindings(
  workspace_id, provider_id, identifier, namespace_json,
  created_at, updated_at
)
```

Namespace registration is idempotent by workspace/provider/identifier.

Local provider profiles are:

```text
ronin-sqlite:          workspace.namespace.asset
unity-catalog-local:   catalog.schema.table
polaris-local:         catalog.namespace.table
```

The Unity and Polaris profiles define local namespace semantics only; they do
not create clients, credentials, or outgoing connections.

Publishing a synthetic result creates a synthetic-tagged asset, an immutable
revision with SHA-256 schema/content digests, and lineage from the declared
source revision. Conflicting identity collisions are rejected.

## 9. Jobs, leases, and persistence

When `SDS_JOBS_DB` is configured, `synthetic_jobs` stores:

```text
job_id, run_id, plan_json, status, error,
lease_owner, lease_epoch, lease_expires_at
```

An atomic update claiming `status='queued'` assigns owner and increments the
epoch. The lease duration is 60 seconds and a heartbeat renews it every 10
seconds. A new facade may reclaim an expired running job; an active job cannot
be claimed by another owner. Terminal jobs are not re-executed.

The default in-memory mode is suitable for ephemeral sessions. SQLite is the
required mode for restart recovery. Distributed multi-node coordination still
belongs to Ronin's durable worker infrastructure.

## 10. Exporters

Exporters implement:

```python
class Exporter(Protocol):
    format_id: str
    def export(self, table: SyntheticTable) -> str: ...
```

Reference formats include `csv` and `jsonl`. Optional providers expose
availability and missing dependencies. Unknown formats fail explicitly.

## 11. UI specification

`web/js/synthetic-data-studio.js` owns the `#synthetic` route and renders:

- JSON plan editor and Generate action;
- generated result and evidence output;
- table/format selectors and Export action;
- local-only provider indicator;
- provider profile badges;
- catalog search by ID, name, tag, or classification;
- asset list with lineage and revision actions;
- recent runs;
- explicit privacy disclaimer and Community/Pro boundary.

Server values are HTML-escaped. The module waits for DOM readiness and does not
allow the legacy shell renderer to overwrite the page. API failures render as
messages rather than uncaught exceptions.

## 12. Security and limits

```text
synthetic:read     read catalog, runs, jobs, formats
synthetic:write    create plans and namespaces
synthetic:execute  generate, export, cancel
```

Default limits:

```text
SDS_MAX_ROWS_PER_RUN=100000
SDS_MAX_TABLES_PER_PLAN=100
SDS_MAX_COLUMNS_PER_TABLE=2000
SDS_JOBS_DB=<SQLite path, optional>
```

Community has no external network requirement. Backups must include SQLite and
artifact storage as one logical snapshot. The host maps plugin permissions to
workspace/project grants.

## 13. Operational behavior

Health reports service and catalog readiness. Missing catalog is degraded, not
silently treated as governed or privacy-safe. Invalid plans fail before data
generation. Failed and cancelled jobs remain observable. Export artifacts are
content-addressed. Namespace and catalog writes are idempotent where specified.

## 14. Community/Pro boundary

| Capability | Community | Pro |
|---|---:|---:|
| Local generation | Yes | Yes |
| Local SQLite catalog | Yes | Yes |
| Unity/Polaris local profiles | Yes | Yes |
| Local lineage and revisions | Yes | Yes |
| Databricks sync | No | Optional |
| Snowflake sync | No | Optional |
| Glue sync | No | Optional |
| External secrets | No | Optional |
| Enterprise policy/audit | No | Optional |
| Multi-node orchestration | No | Optional |

Pro connectors must be separate capabilities with explicit secret handling,
audit, retries, circuit breakers, cursors, and provider-specific policies.

## 15. Testing and acceptance

Unit tests cover deterministic generation, profiles, validation, privacy,
exporters, and namespace resolution. Integration tests cover plugin routes,
limits, health, SQLite runs, publication, revisions, lineage, migrations,
jobs, cancellation, and real HTTP behavior. Chromium smoke tests verify that
the form, catalog search, and module load without JavaScript errors.

Acceptance requires:

1. manifest and routes load through Ronin;
2. plans are bounded and deterministic;
3. offline generation, validation, export, and publication work;
4. privacy output never claims automatic anonymity;
5. jobs expose state, cancellation, claims, leases, and heartbeat;
6. migrations are repeatable and idempotent;
7. revisions and lineage have stable digests;
8. UI renders without errors;
9. module tests, HTTP tests, browser smoke checks, and architecture gate pass;
10. operations and Community/Pro boundaries are documented.

Authoritative evidence is maintained in:

```text
docs/SYNTHETIC_DATA_STUDIO_COMPLETION_AUDIT.md
docs/SYNTHETIC_DATA_STUDIO_OPERATIONS.md
```

## 16. Source map

```text
python/studio_synthetic_data/engine.py
python/studio_synthetic_data/application.py
python/studio_synthetic_data/plugin.py
python/studio_synthetic_data/async_generation.py
python/studio_synthetic_data/local_catalogs.py
python/studio_synthetic_data/publication.py
python/studio_storage/catalog.py
python/studio_storage/migrations/catalog_001.sql
python/studio_storage/migrations/catalog_002.sql
web/js/synthetic-data-studio.js
docs/SYNTHETIC_DATA_STUDIO_OPERATIONS.md
docs/SYNTHETIC_DATA_STUDIO_COMPLETION_AUDIT.md
```
