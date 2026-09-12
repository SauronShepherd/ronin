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

Ronin now has a durable local execution spine over SQLite, real-Docker worker execution with crash/reclaim/resume semantics, an authenticated project-scoped HTTP control plane, OpenAPI 3.1, the `pyronin` SDK, typed least-privilege grants, public portable evidence retrieval, and supported operator CLI commands including `serve`, `worker`, `submit`, `status`, `logs`, `evidence`, `jobs`, and `cancel`.

A production image and supported Docker Compose topology are implemented in code. See [`docs/product/COMPOSE_QUICKSTART_V01.md`](docs/product/COMPOSE_QUICKSTART_V01.md) for the local startup and demo path.

Authenticated HTTP fails closed against accidental remote plaintext transport. The default `RONIN_BIND_POLICY=loopback` permits plaintext only on explicit loopback targets; the bundled local Compose topology declares `container-internal` for its private bridge, and other plaintext development networks require the explicit `insecure-plaintext-network` policy. Compose also requires an operator-supplied `RONIN_TOKEN` instead of shipping a known default credential. The built-in server does not provide TLS; supported remote use terminates HTTPS externally. See [`docs/product/HTTP_TRANSPORT_V01.md`](docs/product/HTTP_TRANSPORT_V01.md).

The last automated frozen v0.1 qualification remains **13/15**. Historical gaps were production image/Compose startup (`01`) and public portable evidence retrieval (`12`); both capabilities are now present in code, but GitHub Actions are intentionally disabled by maintainer policy, so Ronin must not yet be described as newly qualified 15/15 or release-ready.

The broader Data + AI capabilities described above remain targets unless their concrete implementation is present in the repository. In particular, v0.1 does not claim broad ingestion, SQL/lakehouse, streaming, MLOps, GenAI/agents, enterprise RBAC, Postgres/multi-node HA or Kubernetes product deployment.

## Documentation

Start at [`docs/README.md`](docs/README.md) for the documentation map separating what works in current source, the last automated qualification, alpha/unstable contracts, and planned or blocked work.

Key public contracts include:

- [`docs/product/COMPOSE_QUICKSTART_V01.md`](docs/product/COMPOSE_QUICKSTART_V01.md) — supported local operator journey;
- [`api/openapi-v1.json`](api/openapi-v1.json) and [`docs/product/API_COMPATIBILITY_V1.md`](docs/product/API_COMPATIBILITY_V1.md) — HTTP/OpenAPI compatibility;
- [`docs/product/CANONICAL_JSON_V1.md`](docs/product/CANONICAL_JSON_V1.md) — identity-bearing JSON;
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contributor setup, public proposal process, architecture expectations, and governance boundary;
- [`docs/RELEASE_RUNBOOK.md`](docs/RELEASE_RUNBOOK.md) and [`CHANGELOG.md`](CHANGELOG.md) — release operation and user-visible change communication.

`SECURITY.md` is intentionally not published yet because the project has not selected and verified a private vulnerability-reporting channel. Issue #45 owns that human decision; Ronin must not invent an address or claim a private reporting feature is active.

## Governance and contribution

Ronin is currently a **single-maintainer project with an autonomous build pipeline**. The Autonomous Builder implements accepted work; it does not create human governance authority, replace external contributor authorship, or substitute for public consensus-seeking.

Substantial architecture/product changes require prior public GitHub issue discussion. Bounded fixes and already-accepted implementation work may proceed through ordinary pull requests. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the contribution-based path to greater review/triage responsibility and the rules for recording material private or synchronous decisions back into the public repository record.

## Development

Create an isolated environment and install the exact locked dependency set:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install -e . --no-deps
```

Repository validation commands and the current code-only policy are documented in [`CONTRIBUTING.md`](CONTRIBUTING.md). GitHub Actions and automated tests are currently disabled by maintainer policy. Any local/static evidence must be reported exactly and does not replace full acceptance/CI qualification.

## Layout

- `python/` — product Python packages.
- `tests/` — executable quality and architecture contracts.
- `tools/` — repository quality gates.
- `docker/` and `compose.yaml` — production local container topology.
- `docs/product/` — product and domain contracts.
- `docs/automation/` — durable progress, backlog and decision log for incremental autonomous work.

Ronin reuses mature implementation ideas and code from the author's `sdp-studio` and `ronin-old` repositories where that accelerates the target architecture without reviving historical defects or vendor coupling.
