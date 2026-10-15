# Data Enginerring Studio — Full Specification

**Status:** Implemented, tested, operationally qualified, and documented.

**Plugin id:** `com.sauronshepherd.ronin.data-enginerring-studio`

**Product label:** `Data Enginerring Studio` (the spelling is intentional and
must remain stable for compatibility).

## 1. Product purpose

Data Enginerring Studio is Ronin's local-first environment for designing,
validating, debugging, previewing, and executing data-transformation
pipelines. It offers a visual graph designer and a programmatic IDE over one
provider-neutral canonical pipeline representation.

The same authored pipeline can target `local-preview`, `spark-connect`, or
`spark-sdp` (SDP Studio) without rewriting its intent. Portability is
capability-based: unsupported constructs produce diagnostics and fail closed.

## 2. Functional specification

### Authoring

- Provide a navigation item guarded by `data-engineering:read`.
- Provide an operator palette, graph canvas, node selection, and edge creation.
- Provide a pipeline JSON editor and a code/IDE editor.
- Keep graph, JSON, and programmatic surfaces synchronized through the same IR.
- Support stable pipeline identity, name, nodes, edges, operators, parameters,
  ports, origin metadata, ownership, and labels.

### Operators and validation

- Use a versioned builtin operator catalog.
- Reject unknown operators, malformed nodes, invalid ports, invalid edges,
  illegal topology, and non-canonical node identities.
- Return `valid`, `portable`, `contract`, `runtime`, node/edge counts, an IR
  digest, and diagnostics containing code, message, path, and severity.
- Derive identities and hashes from canonical content, not UI ordering.

### Local preview

- Execute without external services.
- Accept named fixture datasets.
- Enforce bounded rows and bounded result payloads.
- Return `status`, `mode`, `runtime`, `rows_by_node`, `metrics`, and diagnostics.
- Preserve the last valid state when preview fails.

### Runtime providers

`local-preview` executes deterministic fixtures. `spark-connect` uses an
explicit `sc://host:port` endpoint, lazily creates a Spark Connect session,
executes bounded SQL, normalizes rows, and records endpoint/row-count
evidence. `spark-sdp` preserves SDP project artifacts and delegates
declarative validation/compilation to SDP Studio.

### SDP Studio

- Import project YAML and named pipeline documents losslessly.
- Preserve source digest, project identity, pipeline identity, and artifact
  references.
- Support the official `sdpstudio validate` CLI as the mandatory external
  qualification path.
- Preserve external diagnostics and generated artifacts.
- Never silently replace source documents with generated output.

### Durable execution

Submitting a run requires project id, revision key, IR digest, and runtime.
The result is a durable plan containing job id, run id, job type,
idempotency key, request digest, parameters, and runtime. The worker bridge
executes the plan under lease fencing and persists immutable evidence.

### Evidence and lineage

Evidence contains a storage reference, SHA-256 digest, byte size, runtime,
provider, execution reference, metrics, and normalized diagnostics. Lineage
retains observed source/transformation/target relationships and execution
references and can be exported as OpenLineage-compatible observations.

### IDE and debugging

IDE sessions contain ordered cells, authored source, prepared source, outputs,
diagnostics, breakpoints, parameters, execution state, and runtime metadata.
Debugging never bypasses authorization or changes canonical pipeline identity.

## 3. Canonical IR

The pipeline model contains `version`, optional UI `id`/`name`, `config`,
`nodes`, and `edges`. A node contains an id, `instance_key`, versioned
operator reference, parameters, typed input/output ports, origin, ownership,
and optional label. Edges reference source/target node ids and ports.

Node ids are derived from operator, parameters, ports, and instance key. A
hand-authored id that does not match the derived semantic id is invalid.
Canonical serialization has deterministic ordering and is hashed with SHA-256.
The digest is used for compilation, idempotency, evidence, and audit.

## 4. Plugin contract

The manifest declares plugin API compatibility, workspace dependency, config
schema, UI entry point, migration `data-engineering.schema.v1`, job type
`data-engineering.pipeline-run.v1`, and these capabilities:

- `data-engineering.projects.v1`
- `data-engineering.pipelines.v1`
- `data-engineering.ir.v1`
- `data-engineering.compiler.v1`
- `data-engineering.preview.v1`
- `data-engineering.quality.v1`
- `data-engineering.lineage.v1`
- `data-engineering.runtime-provider.v1`

Declared permissions are `data-engineering:read`,
`data-engineering:write`, and `data-engineering:execute`.

## 5. HTTP API

| Method | Route | Contract |
|---|---|---|
| GET | `/v1/data-engineering/health` | Plugin/store/provider readiness |
| GET | `/v1/data-engineering/runtimes` | Runtime capabilities and state |
| POST | `/v1/data-engineering/pipelines/validate` | Compile canonical IR |
| POST | `/v1/data-engineering/pipelines/preview` | Bounded local execution |
| POST | `/v1/data-engineering/pipelines/runs` | Durable run planning |
| POST | `/v1/data-engineering/sdp/import` | Lossless SDP import |

All API routes are authenticated and authorized by Ronin's control plane.
Permission mapping is `read -> project.read`, `write -> project.write`, and
`execute -> scheduler.write`. Local qualification may supply `workspace_id`;
production authorization comes from authenticated control-plane context.

The UI assets are served under `/studio/`, including
`/studio/data-enginerring-studio.html`, and may share the API origin.

## 6. Persistence and consistency

- Revisions are immutable, content-addressed, and optimistic-concurrency
  protected.
- Compilation reports are keyed by revision/runtime and retain digest,
  diagnostics, portability, provider, and artifact metadata.
- Outbox events are committed transactionally and receive `published_at` only
  after successful delivery; retries are idempotent.
- Evidence is immutable and written only by a current lease holder.
- Recovery creates a new revision or run; it never overwrites prior artifacts.

## 7. Security

- The browser is not an authorization boundary.
- Every plugin route is authenticated and permission checked.
- Provider credentials never appear in pipeline JSON, IR, logs, evidence, or
  lineage.
- Request bodies, fixtures, rows, and diagnostic payloads are bounded.
- Static asset serving rejects traversal, hidden-file, and out-of-root paths.
- Operational output redacts sensitive values.

## 8. UI behavior

The page contains a product header, runtime selector, Validate/Preview/Submit
controls, operator palette, JSON editor, graph canvas, result status region,
runtime inspector, and code editor. API calls include workspace context and
show structured network/non-JSON/HTTP errors. Successful validation stores its
IR digest for durable submission.

The browser acceptance journey is: open the Studio from Ronin HTTP, add or
edit a pipeline, Validate, Preview, and Submit durable run. The expected
responses are valid JSON, `status=completed`, and `status=planned` with job/run
identifiers.

## 9. Testing and qualification

### Unit and integration tests

Test compiler rules, preview, runtimes, Spark Connect normalization, SDP
import, revisions, SQLite persistence, compilations, execution, evidence,
lineage, IDE sessions, worker behavior, plugin registration, control-plane
permissions, static serving, and HTTP dispatch.

### Browser E2E

`tools/run_data_engineering_browser_e2e.py` starts a real Ronin
`WorkspaceProjectHTTPServer`, serves the UI from the same origin, loads the
real plugin host, and supports the Validate → Preview → Submit journey.

### External E2E

`tools/run_data_engineering_external_e2e.ps1` starts the official Spark Connect
server, runs `select 1`, persists evidence, and invokes the official
`sdpstudio validate` command. The mandatory SDP success output is
`Pipeline model is valid.`. The JSON-stdio provider test is an optional
additional contract and may be skipped when not configured.

## 10. Operations

At startup, verify plugin discovery, workspace dependency readiness, artifact
store, compilation store, and `/v1/data-engineering/health`. Do not treat a
configured endpoint as availability; run qualification probes.

For validation failures preserve source and diagnostics. For Spark failures
preserve endpoint evidence. For SDP failures preserve source artifacts and
digest. For evidence failures inspect artifact-store health and lease fencing.
For outbox failures retry by stable event identity. Never report an unavailable
provider as success.

## 11. Acceptance gates

The module is complete only when:

1. the manifest, dependency, capabilities, permissions, and migration validate;
2. UI assets and API routes are served by Ronin;
3. graph and IDE surfaces share canonical IR;
4. validation and hashing are deterministic;
5. local preview is bounded and reproducible;
6. real Spark Connect executes and persists evidence;
7. official SDP Studio validates an imported project;
8. revisions, compilations, outbox, runs, evidence, and lineage are durable;
9. stale leases cannot write evidence;
10. browser E2E completes Validate, Preview, and Submit;
11. tests, lint, bytecode compilation, operations, and release documentation
    pass.

## 12. Implementation map

| Area | Location |
|---|---|
| Plugin boundary | `python/studio_data_engineering/plugin.py` |
| Compiler/IR | `compiler.py`, `previews.py` |
| Spark provider | `spark_connect.py` |
| SDP provider | `sdp_adapter.py` |
| Revisions/storage | `revisions.py`, `sqlite_revisions.py`, `compilations.py` |
| Execution/evidence | `execution.py`, `execution_bridge.py`, `worker.py`, `evidence.py` |
| Lineage/IDE | `lineage.py`, `ide.py` |
| UI | `web/data-enginerring-studio.html/.js/.css` |
| HTTP qualification | `tests/integration/test_data_engineering_http.py` |
| External qualification | `tools/run_data_engineering_external_e2e.ps1` |
| Browser qualification | `tools/run_data_engineering_browser_e2e.py` |
| Operations | `docs/product/DATA_ENGINERRING_STUDIO_OPERATIONS_EN.md` |
| Release checklist | `docs/product/DATA_ENGINERRING_STUDIO_RELEASE_CHECKLIST_EN.md` |

## 13. Detailed architecture

### 13.1 Layering

The module is organized into provider-neutral layers with dependency direction
from authored intent toward execution:

1. **UI layer:** graph, JSON editor, IDE, diagnostics, and runtime controls.
2. **HTTP/plugin adapter:** authentication context, permission enforcement,
   request validation, response normalization, and contribution registration.
3. **Application layer:** validation, preview, revision application, run
   planning, compilation persistence, and import orchestration.
4. **Domain layer:** canonical IR, operator catalog, identity derivation,
   diagnostics, state transitions, and provider-neutral evidence contracts.
5. **Provider ports:** Spark Connect, SDP Studio, local fixture execution, and
   future providers.
6. **Infrastructure adapters:** SQLite, artifact storage, outbox delivery,
   worker execution, and external process invocation.

Provider implementations must not introduce provider-specific concepts into the
canonical domain model. Provider-specific metadata belongs in an adapter
result or evidence extension.

### 13.2 Data flow

The normal path is:

`UI authoring → canonical IR → validation → IR digest → revision/compilation
record → runtime selection → durable plan or bounded preview → provider
execution → evidence → lineage/outbox`.

The UI may request preview before a revision is persisted, but durable
submission must reference a revision key and digest. A provider result is not
considered durable until evidence has been stored successfully.

### 13.3 Dependency boundaries

- UI depends only on documented HTTP contracts.
- HTTP adapters depend on plugin contributions and authorization ports.
- Domain/compiler code does not import HTTP frameworks, browser code, or
  provider SDKs.
- Spark Connect imports are lazy and isolated to the provider module.
- SDP Studio invocation is isolated behind `SdpStudioProvider`.
- Storage adapters implement ports and do not redefine domain invariants.
- Workers consume durable plans and do not mutate authored source.

## 14. State machines

### 14.1 Pipeline revision

The logical revision lifecycle is:

`working → validated → persisted → superseded`.

Invalid revisions remain inspectable with diagnostics but cannot transition to a
durable execution request. A superseded revision remains readable for audit.

### 14.2 Compilation

`requested → compiling → succeeded | failed`.

Compilation success requires a deterministic report and digest. Compilation
failure retains diagnostics and does not publish a success event.

### 14.3 Durable run

`planned → queued → running → succeeded | failed | cancelled`.

The transition authority is the durable execution layer. The UI may request a
transition but cannot directly assign terminal state. Every terminal state
must retain a reason and correlation identifiers.

### 14.4 Evidence

`produced → serialized → stored → referenced`.

If storage fails, the run must not claim complete evidence. Existing evidence
must remain immutable and a retry must use the same logical execution identity
where the idempotency contract requires it.

## 15. Detailed persistence model

### 15.1 Revision record

Required fields:

- `project_id`;
- `pipeline_id`;
- `revision_key` and monotonic revision number;
- canonical source/IR digest;
- source artifact references;
- parent revision or expected revision;
- author/actor metadata;
- created timestamp;
- validation status and diagnostics reference.

### 15.2 Compilation record

Required fields:

- revision key;
- runtime id and provider version;
- IR digest;
- portable/valid status;
- diagnostics;
- generated artifact references;
- compiler request and event identity;
- created timestamp.

### 15.3 Execution record

Required fields:

- job id and run id;
- project and revision identity;
- request and IR digests;
- runtime/provider;
- parameters digest or bounded parameters;
- idempotency key;
- attempt and lease information;
- state transition timestamps;
- evidence and lineage references;
- normalized failure information.

### 15.4 Outbox record

Required fields:

- event id;
- event type and schema version;
- aggregate key;
- canonical payload;
- attempt count;
- last error code;
- `published_at` only after confirmed delivery.

## 16. Error contract

Errors are normalized into stable codes and safe messages. At minimum, the
module distinguishes:

- invalid request or malformed JSON;
- invalid pipeline IR;
- unsupported operator;
- unsupported runtime capability;
- revision conflict;
- provider unavailable;
- provider execution failure;
- artifact storage failure;
- lease-fencing failure;
- outbox delivery failure;
- unauthorized or forbidden operation.

Raw provider stack traces may be logged in restricted diagnostics, but must not
be returned to the browser or persisted as unbounded evidence.

## 17. API examples

### Validation response

```json
{
  "valid": true,
  "portable": true,
  "contract": "data-engineering.ir.v1",
  "runtime": "local-preview",
  "node_count": 2,
  "edge_count": 1,
  "ir_digest": "sha256-hex-digest",
  "diagnostics": []
}
```

### Preview response

```json
{
  "status": "completed",
  "mode": "preview",
  "runtime": "local-preview",
  "rows_by_node": {"source": [{"id": 1}]},
  "metrics": {"source": {"output_rows": 1}},
  "diagnostics": []
}
```

### Durable plan response

```json
{
  "status": "planned",
  "job_type": "data-engineering.pipeline-run.v1",
  "delegation": "jobs.execution.v1",
  "job_id": "job-data-engineering-...",
  "run_id": "run-data-engineering-...",
  "idempotency_key": "stable-key",
  "request_digest": "sha256-hex-digest"
}
```

## 18. Non-functional requirements

### Determinism

Equal canonical input, provider version, and configuration must produce equal
IR digest, validation result, and compilation identity. Time and randomness
must be injected at I/O boundaries rather than created by pure domain code.

### Performance

- UI preview must be bounded by row, payload, and execution limits.
- Compilation must not require starting Spark for local validation.
- Spark Connect sessions must be lazy and reusable only within explicit
  provider/session lifetime rules.
- SQLite writes must remain transactional and bounded.
- API handlers must enforce request timeouts.

### Reliability

- Retries must be idempotent.
- Evidence must survive provider retries and worker restarts.
- Stale workers must be fenced.
- Outbox delivery must be recoverable.
- A provider outage must not corrupt source or revision state.

### Security

- Authorization is deny-by-default.
- Plugin permissions must be declared before routes are registered.
- Static serving must be confined to the configured web root.
- Secrets must be referenced, not copied into pipeline payloads.
- Logs and evidence must apply redaction and size limits.

### Compatibility

- Plugin API compatibility is declared in the manifest.
- IR versions are explicit and must reject unsupported versions.
- Route and response changes require coordinated contract updates.
- Provider versions and qualification results are retained with compilation
  and evidence metadata.

## 19. Observability schema

Every log, metric, event, and evidence record should be correlatable by:

`plugin_id`, `project_id`, `pipeline_id`, `revision_key`, `ir_digest`,
`job_id`, `run_id`, `attempt_id`, `execution_ref`, and `runtime`.

Recommended metrics include validation count, validation failure count,
preview duration, preview row count, provider request duration, provider
failure count, evidence write duration, outbox retry count, and stale-lease
rejection count.

## 20. Qualification commands

The mandatory local gate is:

```powershell
$files = Get-ChildItem tests -Filter 'test_data_engineering_*.py' |
  ForEach-Object { $_.FullName }
pytest -q @files
ruff check python/studio_data_engineering tools/data_engineering_qualification.py
python -m compileall -q python/studio_data_engineering
```

The mandatory external gate configures `SDP_PROJECT_ID`,
`SDPSTUDIO_DATA_ROOT`, and `SPARK_HOME`, then runs
`tools/run_data_engineering_external_e2e.ps1`. It must show a passing Spark
smoke and the official SDP output `Pipeline model is valid.`.

The HTTP gate runs the integration test and the browser qualification runner.

## 21. Traceability matrix

| Requirement family | Primary implementation | Primary evidence |
|---|---|---|
| Manifest/discovery | `plugin.py` | plugin and registry tests |
| IR/compiler | `compiler.py` | compiler/plugin tests |
| Preview | `previews.py` | preview/plugin tests |
| Spark Connect | `spark_connect.py` | external Spark smoke |
| SDP Studio | `sdp_adapter.py` | official CLI validation |
| Revisions | `revisions.py` | revision tests |
| Persistence | `sqlite_revisions.py`, `compilations.py` | SQLite tests |
| Execution | `execution.py`, `worker.py` | execution/worker tests |
| Evidence | `evidence.py` | evidence/fencing tests |
| Lineage | `lineage.py` | lineage tests |
| IDE | `ide.py` | IDE tests and browser UI |
| HTTP authorization | `control_plane.py` | HTTP integration tests |
| UI/static assets | `web/` | static/UI/browser tests |
| Operations | English runbook | release checklist |

## 22. Change management

Any change to IR, routes, permissions, provider contracts, persistence schema,
evidence shape, or runtime semantics must update this specification, the
corresponding tests, and the English release checklist. A change is not
complete until the affected mandatory gates are rerun and their evidence is
retained with the release.
