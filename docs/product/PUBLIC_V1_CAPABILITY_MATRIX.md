# Ronin Public v1 capability matrix

**Status authority:** [`PUBLIC_V1_SCOPE.md`](PUBLIC_V1_SCOPE.md) and the
machine-readable [`public-v1-status.json`](public-v1-status.json).

**Observed candidate:** `d5c5c9acbf1b50a534f01f2b10dc6bdcf0dc2d5a`.

This matrix is a conservative release view of P1–P14. `implemented` means
that the repository contains the described source path. `qualified` means
that the path has current, repeatable evidence in this checkout. A capability
is `release-qualified` only when its complete mandatory Public v1 journey,
provider evidence, security evidence and exact-candidate release evidence are
all present. No P1–P14 family is release-qualified in the current snapshot.

| Capability | Implemented | Qualified | Release-qualified | Known limitations | Required optional dependency | Supported deployment profile |
| --- | --- | --- | --- | --- | --- | --- |
| P1 Workspace, projects and source control | Partial | Partial | No | Membership, complete authoring journeys and remote-provider certification remain incomplete. | Git executable; OIDC/secret provider for production identity flows. | Local SQLite; Compose/PostgreSQL reference profile. |
| P2 Connectors and ingestion | Partial | Partial | No | Production driver qualification and broad incremental-source coverage remain incomplete. | PostgreSQL, S3/Azure/JDBC drivers; provider credentials. | Local bounded files/HTTP; Compose/PostgreSQL; configured object storage. |
| P3 Lakehouse and SQL | Partial | Partial | No | QueryFlux, remote/catalog qualification and full format/service coverage remain incomplete. | DuckDB locally; Iceberg/Delta libraries; Trino/QueryFlux for remote paths. | Local bounded Parquet/DuckDB; Compose; configured remote engine. |
| P4 Data Engineering Studio | Partial | Partial | No | Worker/evidence lineage, complete CRUD and full authoring surfaces remain incomplete. | Notebook/runtime dependencies; PostgreSQL for runtime qualification. | Local/Compose reference profile. |
| P5 Durable DAG scheduler | Partial | Partial | No | Crash/restart deployment evidence, provider qualification, broader operators and PostgreSQL HA remain incomplete. | PostgreSQL for HA; SMTP/HTTPS notification endpoints. | Local single leader; Compose single-node reference. |
| P6 Catalog and lineage | Partial | Partial | No | Event-standard certification and complete asset-family integration remain incomplete. | OpenLineage HTTP endpoint for remote export. | Local SQLite; Compose/PostgreSQL reference profile. |
| P7 Data quality and contracts | Partial | Partial | No | Provider qualification and complete alert/product surfaces remain incomplete. | Optional SQL/Python execution runtimes; SMTP/HTTPS delivery. | Local/Compose reference profile. |
| P8 AI/ML/MLOps | Partial | Partial | No | Feature engineering, broader algorithms, MLflow/network serving and production qualification remain incomplete. | Numerical Python stack; MLflow or serving provider for interoperability paths. | Local deterministic training/inference; Compose reference profile. |
| P9 GenAI/RAG/agents | Partial | Partial | No | Judge-provider evaluation, production qualification and full artifact portability remain incomplete. | OpenAI-compatible provider; vector/runtime provider for production use. | Local deterministic fixtures; Compose with configured provider. |
| P10 Semantic models and dashboards | Partial | Partial | No | Export/import and production qualification remain incomplete; broader planning is bounded. | DuckDB/SQL engine for execution; browser runtime for Studio. | Local SQLite/DuckDB; Compose reference profile. |
| P11 Streaming and real time | Partial | Partial | No | Production Kafka and end-to-end qualification remain incomplete. | Kafka broker/client runtime. | Local bounded polling tests; Compose with Kafka profile. |
| P12 Observability, alerts and FinOps | Partial | Partial | No | Broader service adoption and production qualification remain incomplete. | Prometheus scrape target; SMTP/HTTPS notification endpoint. | Local/Compose reference profile. |
| P13 Multi-user security and audit | Partial | Partial | No | External identity/secret-provider qualification and production certification remain incomplete. | OIDC issuer/JWKS; external secret backend; PostgreSQL for parity qualification. | Local bearer/auth test profile; Compose/PostgreSQL reference. |
| P14 Deployment and operations | Partial | Partial | No | PostgreSQL multi-node/HA and external production qualification remain incomplete. | Docker; Kubernetes/Helm; PostgreSQL; S3-compatible artifact store. | Local, Docker Compose, constrained single-replica Kubernetes/Helm. |

## Evidence and qualification commands

The following commands establish repository-local evidence, but do not turn
partial product families into release-qualified capabilities:

```powershell
python -m pytest -q
ruff check python tests tools packages docker
ruff format --check python tests tools packages docker
python tools/generate_public_v1_status.py --check
pwsh -File tools/run_docker_qualification.ps1 -ImageTag ronin:qualification-local
python tools/migration_fixture_certification.py --output qualification-evidence/migration-local
npm test -- --reporter=line  # from web-tests
```

External or maintainer-controlled evidence still required includes real
provider qualification, exact-candidate aggregate release evidence, legal and
NOTICE review, a verified private vulnerability-reporting channel, branch and
ruleset verification, and the mandatory end-to-end Studio journeys. Historical
or fixture-only evidence must not be promoted to release qualification.

## Reading rule

The machine-readable ledger remains authoritative for status changes. Update
this matrix in the same change as the ledger when a capability boundary,
qualification result, dependency or deployment profile changes. Do not mark a
row `release-qualified` while `public-v1-status.json` reports an incomplete or
blocked release.
