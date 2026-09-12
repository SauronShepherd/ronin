# Ronin documentation

This is the documentation entry point for Ronin.

The repository currently contains a substantial local execution/control-plane foundation under the `0.1.0a*` engineering line. That foundation is no longer the completeness bar for the first complete public product release. The target is **Ronin Public v1**, a coherent self-hostable Data + AI OS with migration/portability profiles for Microsoft Fabric, Databricks, Palantir Foundry/AIP and Dataiku DSS.

## Public v1 product contracts

Read these first for the target product:

- `docs/product/PUBLIC_V1_SCOPE.md` — mandatory capability families and the release gate;
- `docs/product/PLATFORM_PORTABILITY_V1.md` — canonical Ronin Bundle and vendor import/export semantics;
- `docs/product/PUBLIC_V1_ROADMAP.md` — implementation waves from the current foundation to Public v1;
- `docs/product/BRAND_V1.md` — Ronin Brown visual identity.

`docs/product/V01_SCOPE.md` remains useful as the historical contract for the local durable-execution foundation. It does **not** define Public v1 completeness.

## Works in current source

The current source tree implements the local execution foundation:

- CLI;
- authenticated HTTP API;
- OpenAPI contract;
- `pyronin`;
- durable SQLite-backed job/run/attempt execution;
- worker leasing and reclaim;
- container execution;
- public evidence retrieval;
- typed project/action grants;
- canonical JSON identity boundaries;
- production local Compose topology;
- readiness and artifact qualification tooling.

Start with:

- `docs/product/COMPOSE_QUICKSTART_V01.md` for the current local operator journey;
- `api/openapi-v1.json` for the current HTTP wire schema;
- `docs/product/API_COMPATIBILITY_V1.md` for alpha compatibility rules;
- `docs/product/CANONICAL_JSON_V1.md` for identity-bearing JSON;
- `docs/product/EVIDENCE_REFERENCE_V1.md` for portable evidence semantics;
- `CONTRIBUTING.md` for contributor setup, governance and review expectations.

## Required Public v1 surfaces

The complete product target includes:

- workspace/project/source-control management;
- connections and ingestion;
- lakehouse and SQL;
- Data Engineering Studio;
- restart-safe DAG planner/scheduler;
- persistent catalog and lineage;
- ontology and knowledge graph;
- data quality and contracts;
- AI/ML Lab and MLOps;
- GenAI/RAG/agents;
- graph intelligence/RQL;
- semantic models and dashboards;
- streaming and real-time processing;
- Monitoring & Alerts;
- Cost Control / FinOps;
- multi-user security and audit;
- local/Compose/Kubernetes deployment profiles;
- certified migration profiles for Fabric, Databricks, Palantir and Dataiku.

The web Studio must expose these capabilities through the same backend contracts used by API/CLI/SDK; it is not a second semantic implementation.

## Portability principle

Ronin's migration contract does not hide incompatibilities. Every source-platform object must be reported as one of:

- `exact`;
- `translated`;
- `partial`;
- `passthrough`;
- `unsupported`;
- `manual_decision`.

No importer may silently omit an object or claim semantic preservation when it cannot prove it.

## Brand

Ronin's dominant identity is brown, with gold/amber accents and charcoal/ivory neutrals derived from the logo. Red, green and blue remain semantic/status colors rather than the first-party application identity. See `docs/product/BRAND_V1.md`.

## Qualification status

GitHub Actions and automated tests are currently disabled. The repository therefore does not claim exact-head full release qualification for current `main`.

The Public v1 product gate is broader than the older 15-step local execution journey. Missing any mandatory capability family means Public v1 remains incomplete.

## Alpha / unstable

Ronin remains `0.1.0a*`. HTTP/OpenAPI/CLI/SDK changes follow the strict alpha compatibility rules documented in `docs/product/API_COMPATIBILITY_V1.md`. Identity-bearing formats are versioned and fail closed.

The project is currently single-maintainer. The Autonomous Builder implements accepted work but does not create human governance authority or replace public contributor discussion.

## Human-blocked release requirements

Some release requirements cannot be fabricated by code:

- private vulnerability reporting policy until a real private channel is selected and verified;
- legal/license policy decisions that require human review;
- governance decisions explicitly assigned to a maintainer;
- credentials and external vendor access required for certification fixtures.

These remain visible blockers rather than reasons to weaken the release contract.

## Contributor versus operator paths

Operators using the current foundation should use `docs/product/COMPOSE_QUICKSTART_V01.md` and the current CLI/API contracts.

Contributors building toward Public v1 should start with `PUBLIC_V1_SCOPE.md`, `PLATFORM_PORTABILITY_V1.md` and `PUBLIC_V1_ROADMAP.md`, then follow `CONTRIBUTING.md` and the architecture/product contracts under `docs/product/`.

## Release and change communication

`docs/RELEASE_RUNBOOK.md` documents the existing release mechanics and blockers. It must be expanded before Public v1 to include the new migration, web, data, ML, scheduler, security and deployment qualification gates.

`CHANGELOG.md` records user-visible changes without implying release readiness.

## Troubleshooting

For current Compose startup, token/authentication, readiness, Docker access, cleanup and local operator flow, use `docs/product/COMPOSE_QUICKSTART_V01.md`.

For contributor-environment issues, verify that dependencies came from `requirements-dev.lock`, the checkout is clean, the expected Python version is active, Docker is available where required and no disabled workflow was accidentally reactivated.

If a documented command has been source-reviewed but not rerun under the current code-only policy, treat it as implementation documentation rather than current qualification evidence.
