<p align="center">
  <img src="docs/assets/ronin-logo.webp" alt="Ronin logo" width="360">
</p>

# Ronin

## What v0.1 is and is not

The frozen v0.1 scope, explicit non-goals, fifteen-step acceptance journey, and non-functional budgets are defined in [`docs/product/V01_SCOPE.md`](docs/product/V01_SCOPE.md).

Ronin is being built as a professional, free, open-source and self-hostable **Data + AI platform**. The target spans data integration, engineering, SQL, lakehouse, streaming, governance/lineage/ontology, BI/semantic models, data science, ML/MLOps, GenAI/RAG/agents, security, observability and FinOps in one coherent product.

Ronin is local-first and vendor-neutral: it should be useful on a laptop, reproducible in Docker/Compose and scalable on Kubernetes, while supporting commercial and open runtimes through replaceable adapters rather than a mandatory proprietary control plane.

## Projects and runtimes

Ronin is multi-project. Each project selects a primary Git repository (with optional supporting repositories) and an execution profile. Execution can point to adapter-discovered profiles such as Microsoft Fabric Runtimes or Databricks Runtime/LTS profiles, local Spark, Spark Connect, Kubernetes or future engines, while the canonical core models compatibility as provider-neutral capabilities rather than vendor-specific branches.

See [`docs/product/PROJECTS_AND_EXECUTION.md`](docs/product/PROJECTS_AND_EXECUTION.md) for the project/repository/runtime contract.

## Current status

Ronin now has a durable local execution spine over SQLite, real-Docker worker execution with crash/reclaim/resume qualification, an authenticated HTTP control plane, OpenAPI 3.1, the `pyronin` SDK, and supported operator CLI commands including `serve`, `worker`, `submit`, `status`, `logs`, `jobs`, and `cancel`.

The frozen v0.1 journey is currently **13/15 live** in the authoritative Docker qualification context. The two intentionally incomplete steps are production image/Compose startup (`01`) and public portable evidence retrieval (`12`). Typed least-privilege bearer scopes and the public evidence contract are still unfinished, so Ronin is not yet release-ready and should not be described as 15/15 complete.

The broader Data + AI capabilities described above remain targets unless their concrete implementation is present in the repository. In particular, v0.1 does not claim broad ingestion, SQL/lakehouse, streaming, MLOps, GenAI/agents, enterprise RBAC, Postgres/multi-node HA or Kubernetes product deployment.

## Development

```bash
python -m pip install -e '.[dev]'
make check
make mutation
```

`make check` runs formatting/linting, strict type checking, the architecture gate and tests. Coverage is tiered across product packages, with the strictest core tiers at 100% line/branch and additional storage per-file gates. `make mutation` is a separate, more expensive mutation-quality gate; current mutation qualification is intentionally narrower than the full product surface.

## Layout

- `python/` — product Python packages.
- `tests/` — executable quality and architecture contracts.
- `tools/` — repository quality gates.
- `docs/product/` — product and domain contracts.
- `docs/automation/` — durable progress, backlog and decision log for incremental autonomous work.

Ronin reuses mature implementation ideas and code from the author's `sdp-studio` and `ronin-old` repositories where that accelerates the target architecture without reviving historical defects or vendor coupling.
