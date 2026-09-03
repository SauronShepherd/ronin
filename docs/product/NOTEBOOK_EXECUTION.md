# Notebook execution intent

Ronin notebooks are product assets, not runtime-specific scripts. Their canonical document model must stay portable across local execution, containers, Kubernetes, Spark-compatible runtimes, SQL engines, ML/AI kernels and future adapters.

## Canonical cell model

A notebook contains ordered immutable cells with a stable `CellId`, a bounded semantic kind (`code`, `sql`, `markdown`), source text, an optional execution language for executable cells, and explicit dependencies on other executable cells.

The authored document order is presentation intent. It is not, by itself, an execution dependency. Independent executable cells keep authored order only as a deterministic scheduling tie-breaker.

Markdown is document content, not an execution step. Markdown cells cannot declare execution dependencies, and executable cells cannot depend on Markdown. This prevents documentation layout from silently becoming runtime semantics.

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

Adapters may translate supported magics into typed execution requests, but they must preserve security boundaries, audit evidence, cost/resource attribution, reproducibility and explicit failure semantics. No adapter-specific syntax becomes part of the canonical notebook dependency graph merely because a provider supports it.

## Evidence and future integration

Cell dependency analysis is the document-level execution contract. Later kernel/orchestrator slices should attach run evidence without mutating the authored notebook: resolved runtime profile, cell attempt IDs, timestamps, exit state, logs, metrics, traces, lineage, resource/cost attribution and materialized outputs.

Data lineage is related but distinct from cell execution dependencies. Assets read or written by a cell should be represented through lineage/evidence contracts rather than overloaded into the cell DAG. This separation allows Ronin to explain both *why a cell ran after another cell* and *which data/model/knowledge assets influenced its result*.
