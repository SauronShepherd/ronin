# Ronin Public v1 release claims — draft, not approved

This ledger prevents README, website, package metadata and release notes from
claiming support that has not been qualified. It is a planning artifact, not a
public product promise. Every family remains release-blocked until its complete
journey and applicable gates pass against the same clean candidate. Current
qualification progress is **0/13 families (0%)**.

## Product contract

- One local operator; no multi-user identity or administration in Public v1.
- Ronin does not provide GenAI, RAG, model-provider invocation or an in-product
  agent runtime. Coding-agent skills are external instructions distributed by
  Ronin and run by the user's separate coding agent.
- Public deployment claims are limited to single-host local/Compose profiles
  until each additional profile has exact-candidate evidence. Kubernetes/Helm
  is single-replica only in the Public chart.
- `requires-python = ">=3.11"` is package metadata, not proof that every Python
  version or operating system is supported.

## Claims requiring qualification

| Family | Candidate profile to qualify | Optional services/packages | Known limits before approval | Claim status |
| --- | --- | --- | --- | --- |
| P1 Workspaces, projects, source control | Local SQLite and single-host Compose/PostgreSQL | Git; external identity and secret providers are Pro | Remote-provider and complete installed UI journeys remain open | Blocked |
| P2 Connectors and ingestion | Local files and real PostgreSQL; each object-store/JDBC connector separately | PostgreSQL, S3/Azure/Ozone and JDBC drivers | Production driver and incremental-source coverage incomplete | Blocked |
| P3 Lakehouse and SQL | Bounded Parquet/DuckDB locally; each remote query engine separately | DuckDB, open-table libraries, Trino | Full provider, format, SQL Studio and QueryFlux qualification incomplete | Blocked |
| P4 Data Engineering Studio | Local/Compose notebook and pipeline worker | Python/Arrow runtimes and PostgreSQL where applicable | Worker/evidence lineage and complete public CRUD remain incomplete | Blocked |
| P5 Durable DAG scheduler | SQLite single-leader and PostgreSQL Compose profiles | PostgreSQL; Docker worker; SMTP/HTTPS notifications | Broad recovery, provider and operator conformance incomplete | Blocked |
| P6 Catalog and lineage | SQLite and PostgreSQL separately | OpenLineage endpoint for remote export | Consumer/provider certification and full asset-family integration open | Blocked |
| P7 Data quality and contracts | Local bounded runtime and Compose profile | Optional SQL/Python runtimes; SMTP/HTTPS | Provider qualification and complete alert/product journeys open | Blocked |
| P8 Classical ML/MLOps | Local deterministic execution; PostgreSQL and S3-compatible paths separately | `ml` extra; artifact backend | Broader algorithm, serving, provider and production qualification open; GenAI excluded | Blocked |
| P10 Semantic models and dashboards | Local SQL/DuckDB and installed-browser profile | DuckDB or configured SQL engine | Export/import and end-to-end provider qualification incomplete | Blocked |
| P11 Streaming and real time | Local broker-backed Compose profile | Kafka broker/client | Broker-backed health route passed live against Redpanda; full processing journey, stream lifecycle API/UI and provider qualification remain incomplete | Blocked |
| P12 Observability, alerts and FinOps | Local/Compose with real route and state transitions | Prometheus; SMTP/HTTPS | Service adoption, privacy and provider qualification incomplete | Blocked |
| P13 Security and governance, single operator | Local bearer-token/scopes and Compose | Scanner versions and security fixtures | Security release gate incomplete; Gitleaks was unavailable on the host. Trivy 0.76.1 ran in Docker against the exact runtime/probe TARs and found zero vulnerabilities/secrets, but this is dirty-worktree evidence and must be repeated for a clean candidate | Blocked |
| P14 Deployment and operations | Clean local install, Compose, and one-replica Helm separately | Docker; PostgreSQL; Helm/kind; Terraform/Floci for cloud emulation | Version identity, installed artifacts, backup/restore and provider qualification incomplete | Blocked |

## Platform evidence boundary

The current test host is Windows with CPython 3.13.15. Real service tests used
Linux containers and PostgreSQL 16.4. Node 26.13.0, npm 11.20.0, Docker Compose
5.6.1, Go 1.27.0, kind 0.33.0, Terraform 1.16.2 and pip-audit 2.10.1 were
observed. The plan's Floci/Terraform qualification expects Terraform 1.13.5;
the installed version does not match. Helm, GNU Make and Gitleaks were not
installed on the host. Trivy was also absent from the host, but version 0.76.1
was run in Docker against the exact runtime/probe image TARs; reports are in
`%TEMP%\ronin-apk-locked-scan-20261030`. No claim is approved for macOS, a
direct Linux host install, CPython 3.11/3.12, or alternate CPU architectures
based on this run.

## Approval rule

Before publication, replace each `Blocked` with a scoped claim only after the
family's end-to-end journey, required provider/security evidence and release
gates pass against the exact clean SHA and artifacts. Record OS, Python,
optional dependencies and any unsupported operation in the final README and
release notes. A missing provider, skip, static mock or dirty-worktree result
does not approve a claim.
