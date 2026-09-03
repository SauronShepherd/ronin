# Ronin

Ronin is being built as a professional, free, open-source and self-hostable **Data + AI platform**. The target spans data integration, engineering, SQL, lakehouse, streaming, governance/lineage/ontology, BI/semantic models, data science, ML/MLOps, GenAI/RAG/agents, security, observability and FinOps in one coherent product.

Ronin is local-first and vendor-neutral: it should be useful on a laptop, reproducible in Docker/Compose and scalable on Kubernetes, while supporting commercial and open runtimes through replaceable adapters rather than a mandatory proprietary control plane.

## Projects and runtimes

Ronin is multi-project. Each project selects a primary Git repository (with optional supporting repositories) and an execution profile. Execution can point to adapter-discovered profiles such as Microsoft Fabric Runtimes or Databricks Runtime/LTS profiles, local Spark, Spark Connect, Kubernetes or future engines, while the canonical core models compatibility as provider-neutral capabilities rather than vendor-specific branches.

See [`docs/product/PROJECTS_AND_EXECUTION.md`](docs/product/PROJECTS_AND_EXECUTION.md) for the project/repository/runtime contract.

## Current status

The repository is in **E1 — Core IR/domain foundations**. Pure immutable graph primitives, executable architecture boundaries and strict quality gates exist; the broader product capabilities above are targets and are not yet claimed as implemented.

## Development

```bash
python -m pip install -e '.[dev]'
make check
make mutation
```

`make check` runs formatting/linting, strict type checking, the architecture gate and tests. `studio_core` has a mandatory 100% line/branch coverage gate with zero exclusions. `make mutation` is the separate, more expensive mutation-quality gate; it requires at least 90% killed mutants and rejects incomplete or invalid mutation evidence.

## Layout

- `python/` — product Python packages.
- `tests/` — executable quality and architecture contracts.
- `tools/` — repository quality gates.
- `docs/product/` — product and domain contracts.
- `docs/automation/` — durable progress, backlog and decision log for incremental autonomous work.

Ronin reuses mature implementation ideas and code from the author's `sdp-studio` and `ronin-old` repositories where that accelerates the target architecture without reviving historical defects or vendor coupling.
