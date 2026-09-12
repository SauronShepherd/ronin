<p align="center">
  <img src="docs/assets/ronin-logo.webp" alt="Ronin logo" width="360">
</p>

# Ronin

**The lordless Data + AI OS platform.**

Ronin is being built as a professional, free, open-source and self-hostable **Data + AI platform** designed around portability rather than a mandatory proprietary control plane.

## Public release contract

The existing `0.1.0a*` work is an **engineering alpha and execution foundation**, not the product-completeness gate for Ronin's first public release.

Ronin Public v1 will not be declared complete until the platform has end-to-end supported paths for data integration, lakehouse/SQL, scheduling/orchestration, catalog/lineage/ontology/knowledge graph, data quality, AI/ML/MLOps, GenAI/RAG/agents, semantic models/dashboards, streaming, observability/alerts/FinOps, multi-user security, deployment and vendor migration.

The normative contracts are:

- [`docs/product/PUBLIC_V1_SCOPE.md`](docs/product/PUBLIC_V1_SCOPE.md) — mandatory product capability families and release gate;
- [`docs/product/PLATFORM_PORTABILITY_V1.md`](docs/product/PLATFORM_PORTABILITY_V1.md) — import/export and migration contract for Microsoft Fabric, Databricks, Palantir Foundry/AIP and Dataiku DSS;
- [`docs/product/PUBLIC_V1_ROADMAP.md`](docs/product/PUBLIC_V1_ROADMAP.md) — implementation waves from the current foundation to Public v1;
- [`docs/product/BRAND_V1.md`](docs/product/BRAND_V1.md) — Ronin Brown visual identity.

The original [`docs/product/V01_SCOPE.md`](docs/product/V01_SCOPE.md) remains the contract for the historical/local execution-foundation milestone. It no longer defines the completeness bar for the first complete Ronin product release.

## Product direction

Public v1 is intended to let a team migrate a representative project away from **Microsoft Fabric, Databricks, Palantir Foundry/AIP or Dataiku DSS**, operate the supported portable subset in Ronin without a mandatory dependency on the source vendor, and export it through documented canonical/adaptor formats.

Ronin does not promise fictional byte-for-byte compatibility with every proprietary feature. Migration behavior is classified explicitly as `exact`, `translated`, `partial`, `passthrough`, `unsupported` or `manual_decision`; objects may not be silently dropped or semantically weakened.

The target platform includes:

- workspaces, projects, repositories, environments and secrets;
- data connections, ingestion, lakehouse assets and SQL;
- notebooks, code and a Data Engineering Studio;
- DAG planning/scheduling with retries, backfills, triggers and durable history;
- persistent catalog, lineage, ontology and knowledge graph;
- data quality and data contracts;
- AI/ML Lab, experiment tracking, model registry, evaluation and serving;
- GenAI/RAG/agent development and evaluation;
- graph intelligence and provider-neutral graph execution;
- semantic models, metrics and dashboards;
- streaming and event-triggered workflows;
- Monitoring & Alerts plus Cost Control / FinOps;
- CLI, HTTP API, Python SDK and a web Studio over the same backend contracts.

## Brand

Ronin's dominant brand color is **brown**, with gold/amber accents and charcoal/ivory neutrals derived from the logo. Red, green and blue are reserved for semantic/status use rather than the application identity. See [`docs/product/BRAND_V1.md`](docs/product/BRAND_V1.md).

## Current foundation

The current source tree already provides reusable platform primitives:

- durable `Job -> Run -> Attempt` execution over SQLite;
- crash/reclaim/resume semantics;
- authenticated project-scoped HTTP control plane;
- OpenAPI 3.1 and `pyronin`;
- typed least-privilege grants;
- public portable execution evidence;
- CLI commands including `serve`, `worker`, `submit`, `status`, `logs`, `evidence`, `jobs` and `cancel`;
- local Git revision identity;
- real-Docker worker execution;
- production local image/Compose topology;
- canonical identity-bearing JSON and artifact/license qualification tooling.

These are retained as the execution/control-plane substrate. They are **not** sufficient by themselves to claim the complete Data + AI OS.

## Projects and runtimes

Ronin is multi-project. Each project selects a primary Git repository, optional supporting repositories and an execution profile. The platform architecture is vendor-neutral: execution profiles and adapters may target local runtimes, Spark-compatible runtimes, container/Kubernetes execution or vendor services while canonical project semantics remain provider-neutral.

See [`docs/product/PROJECTS_AND_EXECUTION.md`](docs/product/PROJECTS_AND_EXECUTION.md) for the existing project/repository/runtime contract. Public v1 expands this into workspace, migration, data, scheduler and platform-level contracts.

## Current qualification status

GitHub Actions and automated tests are currently disabled by maintainer policy. Historical automated evidence predates later source changes, so Ronin must not be described as newly qualified or release-ready from current `main`.

The Public v1 gate is intentionally much broader than the earlier 15-step local execution journey. A missing mandatory capability family means Public v1 is incomplete regardless of how mature the foundation is.

## Documentation

Start at [`docs/README.md`](docs/README.md).

Key current and future contracts include:

- [`docs/product/PUBLIC_V1_SCOPE.md`](docs/product/PUBLIC_V1_SCOPE.md) — complete public product gate;
- [`docs/product/PLATFORM_PORTABILITY_V1.md`](docs/product/PLATFORM_PORTABILITY_V1.md) — vendor migration and canonical bundle rules;
- [`docs/product/PUBLIC_V1_ROADMAP.md`](docs/product/PUBLIC_V1_ROADMAP.md) — implementation order;
- [`docs/product/BRAND_V1.md`](docs/product/BRAND_V1.md) — visual identity;
- [`docs/product/COMPOSE_QUICKSTART_V01.md`](docs/product/COMPOSE_QUICKSTART_V01.md) — current local foundation journey;
- [`api/openapi-v1.json`](api/openapi-v1.json) and [`docs/product/API_COMPATIBILITY_V1.md`](docs/product/API_COMPATIBILITY_V1.md) — current HTTP/OpenAPI compatibility;
- [`docs/product/CANONICAL_JSON_V1.md`](docs/product/CANONICAL_JSON_V1.md) — identity-bearing JSON;
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contributor setup and architecture expectations;
- [`docs/RELEASE_RUNBOOK.md`](docs/RELEASE_RUNBOOK.md) and [`CHANGELOG.md`](CHANGELOG.md) — release operations and user-visible change communication.

`SECURITY.md` is intentionally not published yet because the project has not selected and verified a private vulnerability-reporting channel. A verified private channel is a mandatory Public v1 release requirement; Ronin must not invent one.

## Governance and contribution

Ronin is currently a single-maintainer project with an autonomous build pipeline. The Autonomous Builder implements accepted work; it does not create human governance authority, replace external contributor authorship or fabricate security/legal decisions.

Substantial architecture/product changes require an explicit public record. The Public v1 contracts above are now the target for future implementation work.

## Development

Create an isolated environment and install the exact locked dependency set:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install -e . --no-deps
```

Repository validation commands and the current code-only policy are documented in [`CONTRIBUTING.md`](CONTRIBUTING.md). GitHub Actions and automated tests are currently disabled by maintainer policy. Any local/static evidence must be reported exactly and does not replace full release qualification.

## Layout

- `python/` — current platform/runtime Python packages;
- `tests/` — executable quality and architecture contracts;
- `tools/` — repository quality gates;
- `docker/` and `compose.yaml` — local reference container topology;
- `docs/product/` — product and domain contracts;
- `docs/automation/` — durable progress, backlog and decision log for incremental autonomous work.

Ronin reuses mature implementation ideas and code from the author's earlier projects where that accelerates the target architecture without reviving historical defects or vendor coupling.
