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

`ronin-old` contains useful prior behavior for `%%sql`, `%%configure` and `%pip`, but that implementation mutates notebook objects and can invoke subprocesses. Ronin therefore treats it as reuse evidence for future kernel/adapters rather than copying it into `studio_notebook`.

The historical Fakebric notebook shape also demonstrates useful nbformat 4 interoperability and persisted Jupyter cell IDs, but it mixed execution outputs, runtime metadata and notebook validation into the service/runtime layer. Ronin reuses the interoperability lesson while keeping canonical authored intent and runtime evidence separate.

Adapters may translate supported magics into typed execution requests, but they must preserve security boundaries, audit evidence, cost/resource attribution, reproducibility and explicit failure semantics. No adapter-specific syntax becomes part of the canonical notebook dependency graph merely because a provider supports it.

## Evidence and future integration

Cell dependency analysis and the portable document are the document-level execution contract. Later kernel/orchestrator slices should attach run evidence without mutating the authored notebook: resolved runtime profile, cell attempt IDs, repository revision, timestamps, exit state, logs, metrics, traces, lineage, resource/cost attribution and materialized outputs.

Data lineage is related but distinct from cell execution dependencies. Assets read or written by a cell should be represented through lineage/evidence contracts rather than overloaded into the cell DAG. This separation allows Ronin to explain both *why a cell ran after another cell* and *which data/model/knowledge assets influenced its result*.
