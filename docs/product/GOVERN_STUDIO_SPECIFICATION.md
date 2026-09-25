# Govern Studio Synthetic Data Plugin

## 1. Document status

| Field | Value |
|---|---|
| Product name | Govern Studio |
| Technical package | `studio_synthetic_data` |
| Plugin id | `com.ronin.synthetic-data-studio` |
| Plugin API | `1.0` |
| Current contract generation | v1 |
| Edition | Community / open source |
| Primary use case | Deterministic, governed synthetic data for local testing |
| Runtime boundary | Ronin plugin host and local HTTP control plane |
| Persistence baseline | SQLite run metadata plus content-addressed artifact storage |

This document is the normative technical specification for the Govern Studio
module. It describes the behavior that a compatible implementation must
provide, the extension points that third-party providers may implement, and the
operational guarantees that the current local-first implementation makes.

Govern Studio generates useful test fixtures. It does not claim that generated
data is anonymous, private, statistically representative, or suitable for
production publication without review.

## 2. Goals and non-goals

### 2.1 Goals

Govern Studio must:

1. Accept an explicit schema-based generation plan.
2. Support multiple tables, primary keys, foreign keys, row counts and seeds.
3. Optionally use a sample to profile bounded distributions and categorical
   values without copying the sample wholesale.
4. Generate deterministic output for the same canonical plan and seed.
5. Preserve referential integrity for declared relationships.
6. Validate generated output independently from generation.
7. Expose lifecycle state, evidence and errors through a plugin contract.
8. Export generated tables through replaceable file and table-format providers.
9. Persist runs, idempotency state and artifact metadata across process restarts.
10. Operate through the Ronin plugin host, HTTP control plane and web UI.
11. Fail closed when an optional writer or provider is unavailable.
12. Be testable without cloud services, databases other than SQLite, or opaque
    model calls.

### 2.2 Non-goals

The v1 module does not:

- provide a formal anonymization or differential-privacy guarantee;
- infer arbitrary business rules from a sample;
- guarantee production-grade statistical fidelity for every distribution;
- connect directly to external databases by default;
- make publication or privacy approval decisions;
- silently enable optional Delta, Iceberg or Hudi writers;
- execute arbitrary user-supplied Python or SQL as part of a plan;
- replace a warehouse, lakehouse, catalog or data-quality platform.

## 3. High-level architecture

```text
                  +-----------------------------+
                  | Ronin Web UI / API client   |
                  +--------------+--------------+
                                 |
                    HTTP + workspace context
                                 |
                  +--------------v--------------+
                  | Ronin Control Plane         |
                  | authentication / authz      |
                  +--------------+--------------+
                                 |
                  +--------------v--------------+
                  | PluginHost                  |
                  | route resolution / audit    |
                  +--------------+--------------+
                                 |
                  +--------------v--------------+
                  | SyntheticDataStudioPlugin   |
                  | handlers / provider surface |
                  +--------------+--------------+
                                 |
                  +--------------v--------------+
                  | GovernStudioService         |
                  | lifecycle / idempotency     |
                  +-----+----------------+------+
                        |                |
             +----------v-----+  +-------v--------+
             | Synthetic engine|  | Run store       |
             | deterministic   |  | memory / SQLite |
             +----------+-----+  +-------+--------+
                        |                |
             +----------v-----+  +-------v--------+
             | Format registry|  | Artifact store  |
             | CSV/JSON/...   |  | content address |
             +----------------+  +----------------+
```

### 3.1 Module boundaries

| Component | Responsibility | Must not own |
|---|---|---|
| `engine.py` | Pure plan, generation, profiling and validation logic | HTTP, SQLite, filesystem side effects |
| `formats.py` | Format manifests, provider contracts and built-ins | Run lifecycle or authorization |
| `application.py` | Run lifecycle, fingerprints, idempotency, persistence port | Browser rendering or HTTP parsing |
| `async_generation.py` | Bounded local job execution and job recovery | Format semantics or policy decisions |
| `plugin.py` | Ronin manifest, routes, request decoding and response contracts | Core generation algorithms |
| `persistence.py` | Compatibility metadata adapter for durable submitted plans | Generated-data semantics |
| `studio_storage.artifacts` | Content-addressed bytes and digest verification | Plan validation |
| `web/js/synthetic-data-studio.js` | Govern Studio UI workflow | Authorization or persistence |
| Ronin control plane | Authentication, workspace authorization and route dispatch | Synthetic data rules |

## 4. Package and plugin identity

The Python package is:

```text
python/studio_synthetic_data/
```

The plugin manifest is:

```json
{
  "id": "com.ronin.synthetic-data-studio",
  "name": "Synthetic Data Studio",
  "version": "0.1.0",
  "plugin_api": "1.0",
  "host_requires": ">=1,<2",
  "edition": "community",
  "capabilities": [
    "synthetic-data-studio.plan.v1",
    "synthetic-data-studio.generate.v1",
    "synthetic-data-studio.validate.v1",
    "synthetic-data-studio.export.v1",
    "synthetic-data-studio.jobs.v1"
  ],
  "permissions": [
    "synthetic:read",
    "synthetic:write",
    "synthetic:execute"
  ]
}
```

Packaging entry points:

```toml
[project.entry-points."ronin.plugins.v1"]
govern_studio = "studio_synthetic_data.plugin:factory"

[project.entry-points."ronin.formats.v1"]
delta = "studio_synthetic_data.formats:delta_provider"
iceberg = "studio_synthetic_data.formats:iceberg_provider"
hudi = "studio_synthetic_data.formats:hudi_provider"
```

The file-format providers CSV, JSON, JSONL and XML are built into the plugin.
Delta, Iceberg and Hudi are optional table-provider manifests. Their entry
points may be discovered even when their writer dependency is not installed;
availability must be reported as unavailable rather than being advertised as
writable.

## 5. Functional workflow

The canonical workflow is:

```text
author plan
    -> create idempotent run
    -> generate deterministic tables
    -> validate generated output
    -> export selected table
    -> persist artifact reference and evidence
    -> inspect or recover run
```

Generation and validation are intentionally separate operations. A successful
generation is not equivalent to a validation approval, and validation is not
equivalent to publication approval.

### 5.1 Plan authoring

A plan contains:

- a non-negative integer seed;
- one or more uniquely named tables;
- columns with supported primitive kinds;
- optional primary keys;
- row counts;
- optional foreign-key relationships;
- optional sample-derived profiles at the application boundary.

Plans must be data, not executable code. JSON decoding must reject malformed
objects before the engine is called.

### 5.2 Run creation

`create_run` validates the idempotency key, calculates the canonical plan
fingerprint and creates a run in `created` state. Repeating the same request
with the same key and equivalent plan returns the existing run. Reusing the key
with a different plan raises an explicit conflict.

### 5.3 Generation

Generation validates that the supplied plan fingerprint matches the run. The
engine generates all requested tables using the plan seed. Repeating generation
for an already generated run is a safe no-op that returns the stored result.

Engine failures transition the run to `failed` and preserve the error message.
Publication-hook failures also transition the run to `failed` and do not claim
successful generation to the caller.

### 5.4 Validation

Validation requires a generated result and a matching plan. It checks:

- expected table names;
- expected columns;
- primary-key uniqueness;
- primary-key non-null behavior;
- declared foreign-key referential integrity;
- deterministic evidence identity.

Passing validation transitions the run to `validated`. A failed validation
transitions it to `failed` with a report containing checks and errors.

### 5.5 Export

Export requires an existing generated result, a known table and a ready format
provider. The exporter serializes one table. If an artifact store is injected,
the plugin writes the bytes to the content-addressed store and returns its
digest and storage reference. The run store records format, table, byte size,
digest and logical storage reference.

An optional table provider that is not installed must fail closed with a clear
provider error. It must never produce a false success response.

## 6. Data model

### 6.1 ColumnSpec

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

Supported kinds:

| Kind | Generation behavior |
|---|---|
| `string` | Deterministic textual values, or declared categories |
| `integer` | Deterministic integer within inclusive range |
| `number` | Deterministic numeric value within range |
| `boolean` | Deterministic boolean |
| `date` | Deterministic date-like value |
| `email` | Deterministic local email value |
| `uuid` | Deterministic UUID-like value |

Validation rules:

- names match `[A-Za-z_][A-Za-z0-9_]*`;
- kinds must be supported;
- `null_rate` is between 0 and 1;
- non-nullable columns cannot have a non-zero null rate;
- declared values are represented as strings at the plan boundary.

### 6.2 TableSpec

```python
TableSpec(
    name: str,
    columns: tuple[ColumnSpec, ...],
    primary_key: str | None = None,
    rows: int = 100,
)
```

Table and column names must be non-empty and unique. A primary key must refer to
one of the table columns. Row counts must be non-negative.

### 6.3 ForeignKey

```python
ForeignKey(
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
)
```

The plan constructor rejects relationships that reference unknown tables. The
validator rejects missing parent values and malformed relationship output.

### 6.4 GenerationPlan

```python
GenerationPlan(
    tables: tuple[TableSpec, ...],
    relationships: tuple[ForeignKey, ...] = (),
    seed: int = 0,
)
```

Table names must be unique. The plan is immutable and hashable by its canonical
serialized representation at the application boundary.

### 6.5 GenerationResult

```python
GenerationResult(
    tables: tuple[SyntheticTable, ...],
    plan_fingerprint: str,
    warnings: tuple[str, ...] = (),
    state: GovernanceState = GovernanceState.GENERATED,
)
```

### 6.6 ValidationReport

```python
ValidationReport(
    passed: bool,
    checks: tuple[str, ...],
    errors: tuple[str, ...] = (),
    evidence_id: str = "",
)
```

### 6.7 GovernRun

```python
GovernRun(
    run_id: str,
    plan_fingerprint: str,
    status: RunStatus,
    result: GenerationResult | None = None,
    validation: ValidationReport | None = None,
    error: str | None = None,
)
```

Run statuses:

```text
created -> generated -> validated
    \-> failed
```

`failed` is terminal for the current attempt. A future retry policy may create a
new attempt while preserving the same logical plan/run identity.

## 7. Canonical fingerprint and idempotency

The fingerprint is the first 16 hexadecimal characters of SHA-256 over sorted,
compact JSON containing every plan field:

```json
{
  "relationships": [],
  "seed": 42,
  "tables": [
    {
      "columns": [
        {
          "kind": "integer",
          "maximum": 100,
          "minimum": 0,
          "name": "id",
          "null_rate": 0.0,
          "nullable": false,
          "values": []
        }
      ],
      "name": "customers",
      "primary_key": "id",
      "rows": 10
    }
  ]
}
```

The run id is `run-<fingerprint>`. The idempotency key is supplied by the
caller and is stored with a unique constraint. A key collision with a different
fingerprint is a client conflict, not a second run.

SQLite creation uses an immediate transaction. If multiple service instances
race on the same key, the losing process reads and returns the durable winner.

## 8. Persistence architecture

### 8.1 Store port

The application depends on a `GovernRunStore` protocol:

```python
put(run, *, idempotency_key, plan) -> None
get(run_id) -> GovernRun
find_by_idempotency(key) -> GovernRun | None
all() -> tuple[GovernRun, ...]
add_artifact(run_id, artifact) -> None
artifacts(run_id) -> tuple[dict, ...]
```

The service is independent of the storage implementation.

### 8.2 In-memory adapter

`InMemoryRunStore` is intended for tests, previews and disposable local
sessions. It provides the same logical contract but has no restart durability.

### 8.3 SQLite adapter

`SqliteRunStore` uses a portable SQLite database with:

```sql
PRAGMA user_version = 1;

CREATE TABLE govern_runs (
  run_id TEXT PRIMARY KEY,
  idempotency_key TEXT UNIQUE NOT NULL,
  plan_json TEXT NOT NULL,
  plan_fingerprint TEXT NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT,
  validation_json TEXT,
  error TEXT
);

CREATE TABLE govern_artifacts (
  run_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  artifact_json TEXT NOT NULL,
  PRIMARY KEY (run_id, sequence),
  FOREIGN KEY (run_id) REFERENCES govern_runs(run_id)
);
```

Opening a database with a version greater than the supported version fails
closed. An unversioned database is initialized as version 1. Run writes and
artifact sequence allocation use `BEGIN IMMEDIATE` and a process-local lock.

### 8.4 Artifact bytes

Run metadata contains references, not a substitute for artifact integrity. The
recommended byte store is `LocalArtifactStore`, which writes:

```text
artifact://sha256/<64-hex-digest>
```

The store verifies the digest after writing and rejects tampered content on
read. The plugin returns:

```json
{
  "storage_ref": "artifact://sha256/…",
  "digest": "…",
  "size_bytes": 1234,
  "media_type": "application/json"
}
```

## 9. Format provider architecture

### 9.1 Manifest

```python
FormatManifest(
    format_id: str,
    family: "file" | "table",
    version: str,
    capabilities: frozenset[str],
    protocol_versions: tuple[str, ...],
    optional_dependencies: tuple[str, ...],
)
```

Format ids match `[a-z][a-z0-9_-]*`.

### 9.2 File providers

Built-in file providers:

| Format | Family | Status | Output |
|---|---|---|---|
| CSV | file | built-in | one table with header and rows |
| JSON | file | built-in | JSON array of row objects |
| JSONL | file | built-in | one JSON object per line |
| XML | file | built-in | table root with row and column elements |

CSV and JSONL are dependency-free. JSON uses stable key ordering. XML validates
element names before serialization.

### 9.3 Table providers

Open-source table manifests:

| Format | Optional dependency | Example capabilities |
|---|---|---|
| Delta | `deltalake` | ACID, snapshots, schema evolution |
| Iceberg | `pyiceberg` | snapshots, schema evolution, time travel |
| Hudi | `hudi` | upserts, snapshots, schema evolution |

The current baseline providers are declarative and fail with a writer-not-
installed error until a compatible implementation is installed. This prevents
an availability report from being confused with write capability.

### 9.4 Provider extension contract

A third-party provider should expose:

```python
class FormatProvider(Protocol):
    manifest: FormatManifest

    def export(self, table: SyntheticTable) -> str | bytes: ...
```

Table providers must additionally validate requested protocol versions and
should declare their dependency and capability requirements in the manifest.

## 10. Plugin routes and contracts

All routes are under `/v1/synthetic-data-studio`.

### 10.1 Formats

```http
GET /v1/synthetic-data-studio/formats?workspace_id=<id>
```

Response:

```json
[
  {
    "format_id": "jsonl",
    "status": "ready",
    "missing_dependencies": [],
    "reason": ""
  }
]
```

Possible statuses include `ready` and `optional_missing`.

### 10.2 Create plan

```http
POST /v1/synthetic-data-studio/plans?workspace_id=<id>
Idempotency-Key: plan-key-1
Content-Type: application/json
```

Body:

```json
{
  "seed": 42,
  "tables": [],
  "relationships": []
}
```

Response:

```json
{
  "status": "created",
  "run_id": "run-…",
  "planFingerprint": "…",
  "tables": ["customers"]
}
```

### 10.3 Generate

```http
POST /v1/synthetic-data-studio/generate?workspace_id=<id>
Idempotency-Key: generation-key-1
```

Response:

```json
{
  "status": "generated",
  "run_id": "run-…",
  "contract": "synthetic-data-studio/generation/v1",
  "planFingerprint": "…",
  "tables": [
    {"name": "customers", "rows": [{"id": 1}]}
  ],
  "error": null,
  "validation": {
    "passed": true,
    "errors": [],
    "evidenceId": "validation-…"
  }
}
```

### 10.4 Validate

```http
POST /v1/synthetic-data-studio/validate?workspace_id=<id>
```

Body must contain the plan and, for an existing run, `run_id`.

Response:

```json
{
  "status": "validated",
  "contract": "synthetic-data-studio/validation/v1",
  "checks": ["schema", "primary_keys", "foreign_keys"],
  "errors": [],
  "evidenceId": "validation-…"
}
```

### 10.5 Export

```http
POST /v1/synthetic-data-studio/export?workspace_id=<id>
```

Body:

```json
{
  "run_id": "run-…",
  "table": "customers",
  "format_id": "jsonl"
}
```

Response:

```json
{
  "status": "completed",
  "contract": "synthetic-data-studio/export/v1",
  "run_id": "run-…",
  "table": "customers",
  "format_id": "jsonl",
  "content": "{\"id\":1}\n"
}
```

When an artifact store is injected, the response also contains an `artifact`
object with digest and storage reference.

### 10.6 Run inspection

```http
GET /v1/synthetic-data-studio/runs?workspace_id=<id>
GET /v1/synthetic-data-studio/runs/<run_id>?workspace_id=<id>
```

Run inspection is read-only and must not mutate generation or validation state.

### 10.7 Health

```http
GET /v1/synthetic-data-studio/health?workspace_id=<id>
```

The health response distinguishes service readiness from catalog degradation.
The plugin remains locally usable when an optional catalog service is absent.

### 10.8 Async generation

```http
POST /v1/synthetic-data-studio/generate/async?workspace_id=<id>
GET /v1/synthetic-data-studio/jobs/<job_id>?workspace_id=<id>
POST /v1/synthetic-data-studio/jobs/<job_id>/cancel?workspace_id=<id>
```

Jobs are bounded local tasks. Queued and running jobs are recovered from the
jobs SQLite database on process restart. Cancellation is best effort and is
reported explicitly as `cancelled` when accepted.

## 11. HTTP authorization model

The Ronin control plane authenticates the request before plugin dispatch. Plugin
routes without a path workspace use the explicit `workspace_id` query
parameter. The server maps:

| Plugin permission | Workspace permission |
|---|---|
| `synthetic:read` | `project.read` |
| `synthetic:write` | `project.write` |
| `synthetic:execute` | `project.write` |

Missing workspace context or unmapped permission fails with HTTP 403. The
plugin must never bypass the host authorization layer by authorizing inside a
handler.

## 12. UI behavior

The web module is `web/js/synthetic-data-studio.js` and is loaded by
`web/index.html`.

The UI:

1. Loads the active workspace from `sessionStorage` with a local fallback.
2. Adds the workspace query parameter to Govern Studio API requests.
3. Accepts a JSON plan in a bounded textarea.
4. Displays generation output and run id.
5. Loads available formats from the backend.
6. Shows only providers whose status is `ready`.
7. Allows table and format selection for export.
8. Displays catalog availability and recent runs where those routes are
   available.
9. Escapes rendered values before inserting them into HTML.
10. Presents failures as user-visible, non-throwing status text.

The UI must not infer that synthetic data is anonymous or privacy-preserving.

## 13. Security and safety requirements

- Treat all plan JSON as untrusted input.
- Do not evaluate expressions or execute code from plans.
- Validate names before creating table, XML or catalog identifiers.
- Bound rows, payload size and asynchronous worker counts at the host boundary.
- Require workspace context for HTTP plugin routes.
- Require host authorization before handler invocation.
- Use content-addressed storage and verify bytes after writes.
- Do not log generated row values or sample values by default.
- Keep sample profiling bounded and avoid copying the full sample into output.
- Report optional provider absence explicitly.
- Never equate generation success with privacy approval.

## 14. Failure behavior

| Failure | Expected behavior |
|---|---|
| Empty idempotency key | `ValueError` / invalid request |
| Same key, different plan | Conflict error |
| Unknown run id | Not-found error from route boundary |
| Plan mismatch for run | Explicit fingerprint mismatch error |
| Generate before valid plan | Failed run or invalid request |
| Validate before generation | `run has no generated result` |
| Unknown table | Export error |
| Unknown format | `unknown exporter` error |
| Optional writer absent | Provider unavailable / fail closed |
| Publication hook failure | Run becomes `failed` |
| Artifact integrity mismatch | Artifact integrity error |
| Unsupported DB schema version | Database open fails closed |
| Unauthorized HTTP request | HTTP 401/403 |
| Authorization dependency unavailable | HTTP 503 |

## 15. Observability and audit

The PluginHost records a sanitized route invocation event containing:

- plugin id;
- HTTP method and contribution path;
- permission name;
- parameter names, not sensitive values;
- success or failure outcome.

The application-level evidence id is deterministic for a validation report. Logs
must not include full generated datasets, raw samples, authorization tokens or
idempotency secrets.

## 16. Testing specification

### 16.1 Unit tests

Unit tests must cover:

- column and table validation;
- supported kinds;
- null-rate constraints;
- deterministic generation;
- primary-key uniqueness;
- foreign-key integrity;
- sample profiling bounds;
- CSV, JSON, JSONL and XML serialization;
- XML identifier safety;
- optional provider fail-closed behavior;
- canonical fingerprints.

### 16.2 Application tests

Application tests must cover:

- create-run lifecycle;
- same-key idempotency;
- same-key/different-plan conflict;
- plan mismatch during generate and validate;
- generation failure persistence;
- validation-before-generation rejection;
- SQLite restart recovery;
- SQLite schema version handling;
- artifact metadata recovery;
- concurrent run creation;
- concurrent artifact sequence allocation.

### 16.3 Plugin tests

Plugin tests must cover:

- manifest identity;
- route registration;
- service and artifact-store injection;
- JSON plan decoding;
- generate, validate and export handlers;
- unknown format errors;
- content-addressed artifact responses;
- asynchronous job submission and polling;
- run inspection and health responses.

### 16.4 Integration tests

The HTTP integration test must cross the real server boundary and verify:

```text
authenticated request
  -> workspace extraction
  -> permission mapping
  -> PluginHost route resolution
  -> Govern Studio handler
  -> JSON HTTP response
```

The current acceptance path covers real HTTP generation, validation and export
with workspace authorization.

## 17. Operational procedures

### 17.1 Local startup checklist

```text
plugin entry point discoverable
plugin manifest validates
workspace authorization available
SQLite path writable
artifact root writable
required provider status = ready
web module loaded
```

### 17.2 Recovery

On restart:

1. Open the SQLite database.
2. Reject unsupported schema versions.
3. Recover durable runs by idempotency key and run id.
4. Recover queued or running asynchronous jobs according to the job lease
   policy.
5. Verify artifact bytes by digest before treating them as usable.
6. Re-run validation before publication or downstream use if policy requires it.

### 17.3 Optional provider installation

Installing a provider must be explicit. After installation:

1. restart or reload provider discovery;
2. verify `format_availability()` reports `ready`;
3. validate the provider protocol version;
4. perform a small export smoke test;
5. record the provider version in the run evidence.

## 18. Distribution verification

Build a wheel with:

```powershell
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir .tmp-wheel
```

Verify the wheel contains:

- `studio_synthetic_data`;
- `com.ronin.synthetic-data-studio` plugin implementation;
- `govern_studio` under `ronin.plugins.v1`;
- Delta, Iceberg and Hudi entries under `ronin.formats.v1`.

Install into an isolated target and run:

```python
from importlib.metadata import entry_points

plugin_entry = next(
    item for item in entry_points(group="ronin.plugins.v1")
    if item.name == "govern_studio"
)
plugin = plugin_entry.load()()
assert plugin.manifest.id == "com.ronin.synthetic-data-studio"
```

## 19. Compatibility and evolution

The following are versioned contracts:

- plugin API: `1.0`;
- capability ids: suffix `.v1`;
- generation response: `synthetic-data-studio/generation/v1`;
- validation response: `synthetic-data-studio/validation/v1`;
- export response: `synthetic-data-studio/export/v1`;
- SQLite schema: `PRAGMA user_version`;
- format provider protocols and manifests.

Backward-compatible additions may add optional response fields and new
providers. Breaking changes require a new capability or contract version,
explicit migration, and compatibility tests.

## 20. Reference implementation map

```text
python/studio_synthetic_data/engine.py
python/studio_synthetic_data/formats.py
python/studio_synthetic_data/application.py
python/studio_synthetic_data/async_generation.py
python/studio_synthetic_data/persistence.py
python/studio_synthetic_data/plugin.py
python/studio_synthetic_data/local_catalogs.py
python/studio_synthetic_data/publication.py
web/js/synthetic-data-studio.js
tests/test_synthetic_data.py
tests/test_govern_studio_formats.py
tests/test_govern_studio_application.py
tests/test_synthetic_data_persistence.py
tests/test_synthetic_data_publication.py
tests/test_synthetic_data_plugin.py
tests/integration/test_workspace_project_http_api.py
```

## 21. Acceptance criteria

Govern Studio is considered operational when all of the following are true:

- the plugin is discoverable from the packaged wheel;
- the manifest validates against the Ronin plugin API;
- a plan can create an idempotent run;
- the same plan can generate deterministic tables;
- declared relationships validate;
- validation produces evidence;
- supported formats export successfully;
- optional unavailable formats fail closed;
- exported artifacts have verifiable content identity;
- runs and artifact metadata survive restart;
- concurrent idempotency and artifact writes are deterministic;
- HTTP requests pass authentication and workspace authorization;
- the UI can submit, inspect and export a run;
- unit, application, plugin and HTTP integration tests pass;
- documentation accurately describes the deployed contracts.

