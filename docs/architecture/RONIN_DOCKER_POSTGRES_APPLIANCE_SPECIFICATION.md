# Ronin Docker/PostgreSQL Appliance Specification

**Status:** Implemented reference specification  
**Product:** Ronin Community Edition  
**Audience:** maintainers, plugin authors, operators, security reviewers and future Ronin Pro implementers  
**Runtime baseline:** Python 3.11, PostgreSQL 16, Docker Compose v2

## 1. Purpose

Ronin is a local-first application for individual work. This specification defines the appliance module that packages Ronin as a self-contained Docker deployment with a local PostgreSQL database and a controlled mechanism for starting additional Docker workloads. It is the operational contract for the current implementation, not a proposal for a hosted SaaS platform.

The appliance must provide:

- one reproducible Ronin application image;
- durable relational state in PostgreSQL on the user's machine;
- an HTTP API and browser UI for local use;
- asynchronous jobs executed by a worker;
- optional studios and data workloads launched as isolated containers;
- local logs, traces, metrics and audit records;
- backup and restore procedures;
- deterministic health checks and qualification tests.

The design deliberately keeps the Docker control-plane boundary narrow: only the runner broker may access the Docker socket. The API and worker request workload operations through a broker protocol and never manipulate Docker directly.

## 2. Scope and product boundary

### 2.1 Included in Ronin

The open-source product contains the common platform, local persistence, plugin contracts, individual-user workflows and local-only observability. Local integrations may include a Docker engine on the same machine, but the product does not send telemetry or operational data to third-party systems.

### 2.2 Reserved for Ronin Pro

Ronin Pro may reuse the contracts and add commercial plugins for identity federation, collaboration, remote execution, enterprise clouds, Databricks, Snowflake, Fabric, governance, project management, incident management, enterprise reporting and managed observability. Those capabilities must be implemented as separate distributions/plugins and must not be smuggled into the community appliance through hidden network dependencies.

### 2.3 Non-goals

- multi-tenant hosted operation;
- implicit cloud connectivity;
- exposing the Docker socket to application code;
- treating a container restart as a durable workflow state transition;
- storing large binary artifacts in PostgreSQL by default;
- allowing arbitrary plugins to execute privileged host operations.

## 3. Functional specification

### 3.1 Application services

The appliance exposes the existing Ronin HTTP API and UI through the `server` container. The server is responsible for request validation, authentication policy appropriate to local mode, plugin API composition, orchestration commands and read models. It must remain stateless apart from transient caches and therefore be restartable without data loss.

The `worker` container consumes durable jobs, executes local plugin work and reports progress. It must be possible to stop and restart the worker without losing queued work or creating duplicate successful effects.

The `runner-broker` container performs Docker workload lifecycle operations. It validates an allowlisted workload specification, creates and removes containers, attaches network and volume policies, and returns lifecycle events. It is the only service that receives `/var/run/docker.sock`.

The `postgres` container owns durable state. Its data is stored in the named `ronin-postgres` volume and survives application container replacement.

### 3.2 Required user journeys

- start the appliance and observe a ready health state;
- create and update local projects, workspaces, workflows and schedules;
- submit jobs and observe queued, running, succeeded, failed and cancelled states;
- launch an approved studio or data-engineering workload;
- inspect workload logs and execution evidence;
- use ML Studio lab, model, run, search and model-card features;
- inspect local logs, traces, metrics and audit events;
- stop and restart services without losing PostgreSQL state;
- back up PostgreSQL and restore it into a new local deployment;
- run the qualification suite against the built image.

### 3.3 Failure semantics

Every externally visible operation has an explicit outcome. Validation failures are client errors and are not retried. Transient database, broker and container-start failures are retryable according to bounded backoff. A worker lease expires if heartbeats stop; a later worker may reclaim the job. Effects that cross a process boundary require an idempotency key or a durable operation identifier.

The system must fail closed when configuration is unsafe, a required database migration is missing, a plugin declares an incompatible API version, or a workload image is not permitted by policy.

## 4. Deployment topology

The Compose deployment consists of four mandatory services and optional workload containers:

```text
Browser/CLI
    |
    v
  server  -------> postgres:5432
    |
    +-----------> durable job records <----------- worker
                                                  |
                                                  v
                                           runner-broker
                                                  |
                                                  v
                                      Docker Engine / studios
```

Service responsibilities:

- `postgres`: PostgreSQL 16.4 Alpine, persistent named volume, healthcheck, loopback-only host binding by default.
- `server`: Ronin API/UI, readiness endpoint, plugin discovery and API composition.
- `worker`: background execution, lease heartbeats, plugin worker hooks and result persistence.
- `runner-broker`: narrowly scoped Docker lifecycle broker, health endpoint and broker audit events.
- optional workload containers: studios, data engineering, ML and AI runtimes created by the broker from approved image specifications.

The default host exposure is local-only. Publishing the API beyond loopback is an operator decision and must be protected by an external authentication and TLS boundary; the community appliance does not pretend to provide enterprise ingress controls.

## 5. Configuration contract

### 5.1 Core variables

- `RONIN_STORAGE_BACKEND`: `postgres` in the appliance; `sqlite` remains available for lightweight development fallback.
- `RONIN_DATABASE_URL`: PostgreSQL DSN used by the server and worker.
- `RONIN_JOBSTORE_DATABASE_URL`: jobstore DSN; defaults to the main database when omitted.
- `RONIN_AUDIT_DATABASE_URL`: audit DSN; defaults to the main database when omitted.
- `RONIN_POSTGRES_PORT`: host port, default `5432`, bound to loopback.
- `RONIN_POSTGRES_DB`, `RONIN_POSTGRES_USER`, `RONIN_POSTGRES_PASSWORD`: database bootstrap settings.
- `RONIN_API_PORT`: local API port.
- `RONIN_LOG_LEVEL`: structured logging threshold.
- `RONIN_PLUGIN_MODE`: normal, safe or strict startup policy.
- `RONIN_DOCKER_QUALIFICATION_IMAGE`: immutable image ID used by real qualification tests.
- `RONIN_REAL_DOCKER_QUALIFICATION`: explicit opt-in for tests that create real containers.

### 5.2 Configuration rules

Environment values are parsed once into typed settings. Invalid URLs, unsupported backends, weak production secrets and contradictory service settings produce startup errors. Passwords, tokens and DSNs containing credentials must never be logged. `.env.example` documents names and safe development defaults but contains no usable secret.

The Compose file must use service DNS names for container-to-container traffic (`postgres`, `runner-broker`) and must not rely on host `localhost` from inside a container.

## 6. Persistence architecture

### 6.1 Provider-neutral ports

Domain services depend on storage protocols, not SQL statements. The principal ports cover identity/RBAC, audit, jobs, workflows, schedules, ML labs/models/runs, execution records and artifact metadata. SQLite adapters support fast local development; PostgreSQL adapters provide appliance durability.

No plugin may import a concrete database adapter to implement normal business behaviour. A plugin receives a storage capability through its context and can be rejected if it requests a capability unavailable in the current mode.

### 6.2 PostgreSQL domains

The schema includes durable records for:

- users, roles, permissions and assignments;
- audit events and security-relevant actor metadata;
- queued jobs, attempts, leases, heartbeats and terminal results;
- workflows, workflow versions, schedules and run history;
- ML labs, models, versions, runs, metrics and model cards;
- execution specifications, workload containers and lifecycle events;
- artifacts, checksums, media types, locations and retention metadata;
- plugin installation, compatibility and migration state where applicable.

All tables require stable identifiers, creation/update timestamps and explicit ownership or tenancy fields where the domain needs them. Timestamps are stored in UTC. JSON is used for versioned extension payloads, while query-critical fields remain typed columns with indexes.

### 6.3 Transactions and migrations

Schema creation and evolution are explicit, repeatable and versioned. A migration is applied transactionally where PostgreSQL permits it, is safe to run once, and records its version. Application startup must check the expected schema version before serving requests. Destructive migrations require a backup and a separately reviewed migration step.

Job enqueue plus its domain event is one transaction. Job claim changes the lease atomically. Terminal state transitions use compare-and-set semantics so a late worker cannot overwrite a newer result.

### 6.4 Artifacts and evidence

PostgreSQL stores metadata and integrity information. Large outputs should use a local managed artifact directory or a future object-storage adapter. Every artifact record contains a digest, media type, size, producer operation and retention status. The local appliance does not silently upload artifacts.

## 7. Job and workload lifecycle

```text
submit -> queued -> claimed -> running -> succeeded
                         |          |
                         |          +-> failed
                         +-> lease expires -> reclaimable
queued/running -> cancellation requested -> cancelled
```

The worker protocol is:

1. Select a compatible queued job using an atomic claim.
2. Create an attempt identifier and lease expiry.
3. Emit a started event and heartbeat while executing.
4. Submit a broker operation when a Docker workload is required.
5. Persist stdout/stderr references and structured progress.
6. Commit exactly one terminal result using compare-and-set.
7. Release or retain artifacts according to policy.

The broker protocol requires an operation ID, workload type, immutable image reference, command, environment allowlist, resource limits, network policy, volume policy and timeout. The broker refuses host-path mounts, privileged mode, arbitrary capabilities and unapproved images unless an explicit local-development policy says otherwise.

## 8. Docker security boundary

The Docker socket is a high-privilege capability. Compose mounts it only into `runner-broker`. The server and worker have no socket mount. Broker requests are validated against a schema and an allowlist before reaching the Docker SDK/CLI boundary.

The default posture is:

- non-root application users where supported;
- read-only image references by digest for qualification and production-like runs;
- no host network mode;
- no privileged containers;
- bounded CPU, memory, process and log resources;
- explicit named volumes rather than arbitrary host paths;
- dedicated Compose network;
- loopback host publishing;
- healthchecks that test readiness, not merely process existence.

The socket boundary is an operational trust boundary, not a complete sandbox. Operators must understand that a local user who can control the broker can control the local Docker engine.

## 9. Plugin architecture

### 9.1 Plugin identity and discovery

Plugins are Python distributions with a stable identifier, semantic version, supported Ronin API range, declared capabilities, dependencies and optional migrations. Discovery uses Python packaging entry points and a deterministic lock/configuration layer. Import errors, duplicate identifiers and incompatible versions are startup failures in strict mode and quarantined plugins in safe mode.

### 9.2 Lifecycle

The lifecycle is discover, validate manifest, resolve dependencies, load isolated module, register contributions, run startup hook, serve, stop and unload. Startup hooks must be bounded and idempotent. A plugin cannot mutate global application state during import. Failure during registration rolls back its contributions and records a diagnostic.

### 9.3 Contribution model

Each plugin may contribute zero or more of:

- UI routes, static assets, navigation entries and capability-gated views;
- REST routes, schemas, error mappings and OpenAPI fragments;
- commands, job handlers, workflow steps and scheduler handlers;
- storage ports, migrations and read-model projections;
- broker workload definitions and lifecycle callbacks;
- structured log enrichers, trace spans, metrics and audit event types;
- extension points consumed by other plugins.

The UI and REST portions are separate adapters over the same domain service. A plugin with no UI remains valid. A plugin with UI must not require the browser to understand private server internals.

### 9.4 Extensible plugins

A plugin may publish named extension points with a versioned protocol. Extensions declare the target plugin ID, extension-point ID, compatibility range, priority and configuration schema. Resolution is deterministic, cycles are rejected, and extension failures are isolated from the host where possible. Commercial Ronin Pro plugins may extend Ronin extension points without modifying community source files.

### 9.5 Capability security

Plugin contexts expose explicit capabilities: database repository, audit writer, logger, tracer, metrics registry, job scheduler, broker client and artifact store. A plugin receives only the capabilities declared in its manifest. Direct process spawning, socket creation, Docker access and arbitrary filesystem writes are not part of the default context.

## 10. Logging, tracing, metrics and audit

The local observability plugins are functional plugins, not hard-coded cross-cutting imports. They provide:

- structured JSON-capable application logs written locally;
- correlation ID, request ID, plugin ID, job ID and operation ID enrichment;
- in-process trace spans and timing information;
- counters, gauges and histograms exposed to local diagnostics;
- immutable audit records for actor, action, target, outcome and reason.

Ronin local mode has no external exporter. Exporter extension points exist for Ronin Pro, but the community implementation must reject or ignore unconfigured external sinks rather than contacting them implicitly. Sensitive values are redacted before persistence and output.

## 11. ML Studio integration

ML Studio uses the same plugin and job contracts. Lab metadata, model versions, runs, metrics and model cards are stored through the PostgreSQL ML adapter. Runtime backends are selected through a backend registry and may use local container workloads. Prediction and training payloads are validated against versioned schemas; optional metadata such as hyperparameters must not break compatible clients.

The ML API includes lab operations, model/version operations, run execution, search and model-card retrieval. OpenAPI must contain every registered route, including search and model-card routes. Route consistency tests are mandatory.

## 12. API and UI contracts

All REST routes use versioned prefixes and typed request/response models. Error responses include a stable error code, human-readable message, correlation ID and optional field violations. Internal exception details are logged, not returned to clients.

The OpenAPI document is generated or updated as part of the build and checked against route registration. UI assets are packaged as project data files and served by the server. UI calls use the public API contract and must display degraded states for unavailable optional plugins.

Backward compatibility follows semantic versioning. Removing a route or changing a persisted event requires a deprecation period and migration notes.

## 13. Operations

### 13.1 Start

From the repository root:

```powershell
docker compose up -d postgres
docker compose up -d server worker runner-broker
docker compose ps
```

The normal operator path may use `docker compose up -d`, which starts PostgreSQL first through health dependencies. Readiness is confirmed through the API health endpoint and service healthchecks.

### 13.2 Inspect and stop

```powershell
docker compose logs --tail=200 server worker runner-broker postgres
docker compose ps
docker compose stop
```

`stop` preserves PostgreSQL data. Removing the named volume is a destructive administrative action and must be preceded by a verified backup.

### 13.3 Backup and restore

The backup utility creates a PostgreSQL dump with metadata identifying source database, schema version, timestamp and checksum. Restore is performed into a stopped or isolated target, followed by migration validation and an application smoke test. A restore is not considered complete until projects, jobs, audit records and representative ML records can be read.

### 13.4 Qualification

`tools/run_docker_qualification.ps1` builds the image, resolves its immutable image ID, sets explicit real-Docker qualification variables and runs container executor, worker runtime and end-to-end journey tests. CI runs PostgreSQL-backed tests and uploads evidence. Real Docker qualification is opt-in because it creates containers on the host.

## 14. Test and verification specification

The implementation is accepted only when all applicable layers pass:

- unit tests for domain services, adapters, plugin lifecycle and validation;
- contract tests for Compose topology, qualification script, routes and configuration;
- integration tests against real PostgreSQL for audit, identity/RBAC and jobstore behaviour;
- worker runtime tests using a real Docker engine and immutable image ID;
- end-to-end v0.1 journey tests;
- global Ruff checks for `python`, `packages` and `tools`;
- architecture gate checks for dependency direction and forbidden imports;
- documentation and OpenAPI consistency checks.

The current qualification baseline is recorded in `docs/architecture/plugin-build-status.md`. At the time this specification was written, the full suite reported `1406 passed, 16 skipped`; real PostgreSQL integration reported `8 passed, 1 skipped` plus `1 passed` for the jobstore; real worker qualification reported `2 passed`; and the end-to-end journey reported `16 passed`. Skips must remain explicit and documented; they must not hide failures.

## 15. Image and repository layout

The application image is built by `docker/Dockerfile`. Runtime dependencies include PostgreSQL support through `psycopg[binary]`. The image contains the Python application, packaged UI/data files, entrypoint and healthcheck support. The entrypoint must use Unix line endings and a valid Linux shebang.

Relevant implementation areas:

- `compose.yaml`: appliance topology and health dependencies;
- `docker/Dockerfile`: reproducible application image;
- `docker/container-entrypoint.sh`: runtime bootstrap;
- `python/studio_storage`: provider-neutral and PostgreSQL persistence;
- `python/studio_ml`: ML domain and PostgreSQL adapters;
- `python/studio_core/plugins.py`: plugin context and lifecycle contracts;
- `tools/run_docker_qualification.ps1`: real-image qualification;
- `.github/workflows/docker-qualification.yml`: CI qualification;
- `tests/integration`: real PostgreSQL and Docker integration;
- `tests/e2e`: user-journey verification;
- `docs/architecture/docker-postgres-appliance.md`: operator runbook.

## 16. Performance and scalability

The community appliance targets one local user and bounded local workloads. PostgreSQL indexes cover job state/lease scans, audit time/actor queries, workflow schedules and ML search fields. Long-running work is always asynchronous. API requests must not wait for training or container startup beyond a bounded submission transaction.

The architecture scales structurally because server replicas are stateless and worker concurrency is controlled independently, but the default Compose deployment is intentionally single-node. Ronin Pro may replace local adapters and broker implementations with remote services while preserving domain ports and plugin contracts.

## 17. Recovery objectives

The local appliance has no automatic high availability requirement. Recovery depends on the operator's backup schedule and Docker host availability. The recommended minimum is a periodic PostgreSQL dump plus artifact-directory backup. RPO equals the interval between backups; RTO includes PostgreSQL restore, migration validation, image startup and smoke-test time.

## 18. Acceptance criteria

The module is complete when:

1. `docker compose up -d` starts PostgreSQL and application services with healthy dependencies.
2. The API reports ready only after the configured database is reachable and schema-compatible.
3. Server and worker have no Docker socket access.
4. Broker operations are validated, audited and bounded.
5. Jobs survive worker restart and cannot be terminally overwritten by a stale lease.
6. PostgreSQL data survives application container replacement.
7. Backup and restore are documented and executable.
8. Plugin discovery, UI/API contributions and extension points are covered by tests.
9. Local observability works without external services or network exporters.
10. OpenAPI, Compose, architecture and qualification contract tests pass.
11. Real PostgreSQL, real Docker worker and end-to-end qualification evidence is reproducible.
12. Ronin Pro can add commercial plugins without changing the Ronin core deployment contract.

## 19. Compatibility and change policy

Changes to environment variables, database schema, plugin manifests, extension-point protocols, broker workload specifications or public API routes are compatibility changes. Each change requires an update to this document, the operator runbook, tests and (where applicable) migration/version metadata. A feature is not complete when code merely works locally; it is complete when its failure behaviour, persistence, security boundary, qualification path and documentation are all explicit.

