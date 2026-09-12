# Ronin documentation

This is the documentation entry point for the current v0.1 alpha implementation. It separates source-level implementation from automated qualification so readers do not confuse code that exists with release evidence that has not been rerun.

## Works in current code

The current source tree implements the v0.1 local execution foundation: CLI, authenticated HTTP API, OpenAPI contract, `pyronin`, durable SQLite-backed job/run/attempt execution, worker leasing and reclaim, container execution, public evidence retrieval, typed project/action grants, canonical JSON identity boundaries, production Compose topology, readiness, and clean-artifact qualification tooling.

Start with:

- `docs/product/COMPOSE_QUICKSTART_V01.md` for the supported local operator journey;
- `api/openapi-v1.json` for the HTTP wire schema;
- `docs/product/API_COMPATIBILITY_V1.md` for alpha compatibility rules;
- `docs/product/CANONICAL_JSON_V1.md` for identity-bearing JSON;
- `docs/product/EVIDENCE_REFERENCE_V1.md` for portable evidence semantics;
- `CONTRIBUTING.md` for contributor setup, governance, and review expectations.

## Last automated qualification

GitHub Actions and automated tests are currently disabled. The repository therefore does not claim a new exact-head 15/15 release qualification for current `main`. Historical automated evidence predates later product and identity changes and must not be presented as current release proof.

The strict v0.1 journey, tests, coverage, mutation, Docker qualification, Security qualification, release qualification, provenance, and publication gates remain separate evidence layers to restore when maintainer policy permits it.

## Alpha / unstable

Ronin remains `0.1.0a*`. HTTP/OpenAPI/CLI/SDK changes follow the strict alpha compatibility rules documented in `docs/product/API_COMPATIBILITY_V1.md`. Identity-bearing formats are versioned and fail closed. Operational budgets are published, but current-head benchmark qualification is pending while execution-derived validation is disabled.

The project is currently single-maintainer. The Autonomous Builder implements accepted work but does not create human governance authority or replace public contributor discussion.

## Planned or blocked

The following are not current product claims:

- restored CI/GitHub Actions and exact-head release qualification;
- private vulnerability reporting policy until a real channel is selected and verified;
- repository/ref protection at the v0.1 release gate;
- post-v0.1 data-platform breadth such as ingestion, CDC, lakehouse, SQL federation, streaming, catalog, BI, ML, GenAI, RAG, or additional runtimes;
- language-neutral remote/non-Python runner protocol before that post-v0.1 scope is explicitly opened.

## Contributor versus operator paths

Operators who want to run Ronin locally should use `docs/product/COMPOSE_QUICKSTART_V01.md` and the public CLI/API contracts. Contributors changing the repository should use `CONTRIBUTING.md` and the architecture/product contracts under `docs/product/`.

## Release and change communication

`docs/RELEASE_RUNBOOK.md` documents the intended contributor-operable release sequence and the current blockers. `CHANGELOG.md` records user-visible changes and compatibility notes without implying release readiness.

## Troubleshooting

For Compose startup, token/authentication, readiness, Docker access, cleanup, and local operator flow, use `docs/product/COMPOSE_QUICKSTART_V01.md`. For contributor-environment issues, verify that dependencies came from `requirements-dev.lock`, the checkout is clean, the expected Python version is active, Docker is available where required, and no disabled workflow was accidentally reactivated.

If a documented command is source-reviewed but has not been rerun under the current code-only policy, treat it as implementation documentation rather than current qualification evidence.
