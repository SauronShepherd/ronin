# Notebook execution intent

Ronin notebooks are product assets, not runtime-specific scripts. Their canonical document model must stay portable across local execution, containers, Kubernetes, Spark-compatible runtimes, SQL engines, ML/AI kernels and future adapters.

## Canonical cell model

A notebook contains ordered immutable cells with a stable `CellId`, a bounded semantic kind (`code`, `sql`, `markdown`), source text, an optional execution language for executable cells, and explicit dependencies on other executable cells.

The authored document order is presentation intent. It is not, by itself, an execution dependency. Independent executable cells keep authored order only as a deterministic scheduling tie-breaker.

Markdown is document content, not an execution step. Markdown cells cannot declare execution dependencies, and executable cells cannot depend on Markdown. This prevents documentation layout from silently becoming runtime semantics.

## Portable identity and serialization

Canonical notebook files use schema `ronin.notebook/v1`. Serialization is deterministic JSON and records only authored intent: ordered cells, stable IDs, persisted identity provenance, source, language and explicit dependencies. Runtime outputs, execution counters, timestamps, provider metadata, credentials and mutable kernel state are intentionally excluded.

A cell ID is derived from a persisted `CellIdentityAnchor` containing a bounded boundary (`authoring` or `import`), a stable namespace for the owning source document, and a source-stable cell reference. Identity therefore survives source edits and unrelated reordering; it is not derived from mutable cell content, current position, clocks or randomness inside `studio_notebook`.

Deserialization is strict. Unknown or missing v1 keys, unsupported schema versions, malformed identities and any mismatch between a persisted cell ID and its identity anchor fail closed. Schema evolution must therefore be explicit rather than silently dropping unknown semantics.

Import adapters supply source-stable references and an explicit namespace. For nbformat 4.5+ inputs, the persisted Jupyter cell `id` is a natural adapter-side reference when present. Older or foreign formats require the importer to allocate and persist an equivalent stable external reference before subsequent round trips; the pure domain never invents identity from list position.

Canonical JSON is a transport-neutral representation, not a filesystem API. Reading, writing, migration and format-specific conversion remain adapter/application concerns so the pure notebook package stays usable in local, air-gapped and distributed deployments alike.

## Dependency analysis

`studio_notebook` performs pure deterministic dependency analysis. It produces:

- a topological `execution_order` for executable cells;
- execution `levels` that identify cells whose declared dependencies are satisfied together; and
- stable violations for unknown dependencies, dependencies on non-executable cells, or cycles.

Invalid dependency graphs return no partial execution plan. Runtime code must not guess around a broken canonical graph.

The pure analyzer does not parse Python, SQL, Scala or vendor-specific magic syntax to infer hidden dependencies. Future authoring/import adapters may propose inferred dependencies, but changing canonical execution intent requires an explicit document update that can be reviewed and versioned.

## Runtime boundary

Kernel/session behavior belongs outside the pure notebook domain. This includes package installation, environment configuration, filesystem/network access, secret resolution, Spark/session creation, SQL dialect dispatch, container/pod lifecycle, cancellation, resource accounting and provider-specific notebook magics.

`studio_kernel` is the typed preparation/evidence boundary around that side-effecting behavior. `prepare_notebook_execution()` consumes the exact immutable `NotebookDocument`, a successful `ResolvedRuntimeSnapshot`, a `RepositoryRevision`, and a `KernelRequestAdapter`. It first requires a valid canonical dependency graph and emits requests only for executable cells in deterministic dependency order.

The adapter owns language- and magic-specific interpretation. It may return a separate `executable_source`, normalized `KernelDirective` fields and explicit required permissions, while every `CellExecutionRequest` retains the original authored source independently. Preparation fails closed if an adapter changes the cell identity or returns a directive under a different adapter identity. Preparing a run therefore cannot silently rewrite `%pip`, `%%sql`, `%%configure` or future syntax back into the authored notebook.

Repository evidence records a lowercase Git object ID and, when the checkout is dirty, an optional SHA-256 identity for the dirty patch. Runtime selection evidence remains the immutable provider-neutral snapshot from `studio_core`; kernel preparation does not add provider configuration, credentials, wall-clock time or random IDs to either authored intent or runtime selection.

`ronin-old` contains useful prior behavior for `%%sql`, `%%configure` and `%pip`, but that implementation mutates notebook objects and can invoke subprocesses. Ronin treats those semantics as adapter reuse evidence rather than copying their mutation/subprocess boundary into canonical notebook or kernel contracts.

The historical Fakebric notebook shape also demonstrates useful nbformat 4 interoperability and persisted Jupyter cell IDs, but it mixed execution outputs, runtime metadata and notebook validation into the service/runtime layer. Ronin reuses the interoperability lesson while keeping canonical authored intent and runtime evidence separate.

No adapter-specific syntax becomes part of the canonical notebook dependency graph merely because a provider supports it. Actual kernel/session I/O, isolation, secret resolution, cancellation, permission enforcement, redaction, package installation and provider-specific lifecycle behavior remain adapter/orchestrator responsibilities.

## Execution-session controls

`KernelExecutionSession` is the fail-closed control boundary around a concrete `KernelCellExecutor`. It does not launch processes, containers or pods itself. Instead, the executor advertises normalized isolation facts and performs the actual side effect only after the session policy has accepted those facts and the cell's declared permission requirements.

The default `SessionPolicy` accepts container or Kubernetes isolation and requires a dedicated identity plus network and filesystem isolation. Process execution is therefore an explicit opt-in policy choice rather than an accidental local default. A concrete adapter must truthfully implement the isolation it advertises; `ExecutorIsolation` is a contract assertion, not cryptographic proof. Adapter qualification and integration tests must verify real enforcement before an executor is treated as production-safe.

Permissions are checked before the executor receives the cell. Missing permissions produce the normalized `kernel.permission.denied` result and ordered `permission.denied`, `cell.failed` and `session.failed` events without invoking the executor. Cancellation uses a small signal protocol so local processes, containers, Kubernetes jobs and future remote runtimes can implement their own interruption mechanism without entering the canonical notebook model.

Operational events reuse the durable `ExecutionAttemptId` plus contiguous `ExecutionEventId.sequence`. The initial `JsonlExecutionEventSink` writes canonical JSON Lines, flushes and fsyncs every event, rejects mixed attempts and out-of-order sequence numbers, and redacts common bearer/token/password/API-key and URI-credential forms before persistence. This gives local/offline deployments durable evidence without requiring a distributed event service; restart/resume and shared durable stores remain later replaceable sink implementations.

Executor exceptions are normalized to `kernel.executor.error`; raw adapter exception text is not written to the event ledger. An executor result that changes the requested `CellId` is rejected. These controls surround the existing immutable notebook/runtime/repository/reproducibility nucleus rather than modifying authored intent.

## Evidence and future integration

Per-cell execution results use normalized immutable states (`succeeded`, `failed`, `cancelled`). Failed results require a stable failure code instead of copying an arbitrary raw provider exception into canonical evidence. Results may attach typed references for logs, metrics, traces, lineage, materialized outputs, resource usage and cost; the referenced storage/observability systems remain replaceable.

`NotebookExecutionEvidence` binds those results back to the exact prepared request and rejects duplicate or unknown result cell identities. It may represent partial evidence while a run is active, and exposes whether every requested executable cell has a result without mutating the underlying document or request.

The next concrete execution slice should implement and qualify local/container executors behind `KernelCellExecutor`, including enforceable isolation, cancellation propagation and resource/cost evidence, then add runtime-evidence collectors for effective settings and package/environment/image/artifact digests. Concrete launchers must not reintroduce notebook mutation or provider branches into the canonical contracts.

Data lineage is related but distinct from cell execution dependencies. Assets read or written by a cell should be represented through lineage/evidence contracts rather than overloaded into the cell DAG. This separation allows Ronin to explain both *why a cell ran after another cell* and *which data/model/knowledge assets influenced its result*.
