# Ronin Public v1 capability matrix

**Status authority:** [`PUBLIC_V1_SCOPE.md`](PUBLIC_V1_SCOPE.md) and the
machine-readable [`public-v1-status.json`](public-v1-status.json).

**Observed candidate:** `cc0ad8f79beef3fcce70ff14f22218605fa9d924` (`main`, 2026-10-21 verification). PR #436 executes the supported six-stage PipelineIR in stable topological order; PR #438/#439 add durable checkpoints and PostgreSQL resume pagination; PR #441 stores verified tabular and K-Means model outputs in `ArtifactStore`; PR #443 registers successful durable runs as candidate models after digest verification; PR #445 integrates registration into Studio; PR #446 adds authorized chunked artifact retrieval and a bounded UI download flow; PR #447 binds checkpoints/results to executable source, Python/dependency versions, backend identity, execution options and upstream outputs; PR #448 adds promotion after execution registration; PR #449 adds selective retry from an explicitly selected ML pipeline stage; PR #450 qualifies artifact lifecycle behavior against S3-compatible LocalStack; PR #451 passes the exact pinned PipelineIR to scheduled runners; PR #452 exposes algorithm selection; PR #453 adds standard scaling; PR #454 adds categorical one-hot encoding; PR #455 adds median imputation; PR #456 composes one-hot encoding and median imputation for mixed features; PR #457 adds a non-destructive retention preview, while global deletion remains disabled; PR #458 adds catalog and ML artifact reference discovery; PR #459 adds bounded durable job evidence and checkpoint discovery; PR #460 discovers all nine reference families and combines them into a fail-closed snapshot; PR #461 bounds workspace/catalog/ML enumeration and fails closed when any inventory exceeds its limit; PR #462 bounds local artifact pagination memory with stable digest cursors; PR #464 bounds manual stale-artifact collection and completes the inventory before deleting, while global cleanup remains disabled; PR #466 bounds durable job evidence and cell-result reads across SQLite, PostgreSQL and memory; PR #470 adds candidate DAGs for classification/regression; PR #471 adds K-Means candidate selection; PR #472 exposes candidate selection in Studio; PR #473 bounds search-space memory; PR #475 gives trials stable identities and derived seeds; PR #476 validates complete search domains before training; and PR #477 applies Bayesian stopping by recent improvement. These PRs passed their checks and six exact-head post-merge workflows, including Docker qualification. Release qualification remains incomplete.

This matrix is a conservative release view of P1–P14. `implemented` means
that the repository contains the described source path. `qualified` means
that the path has current, repeatable evidence in this checkout. A capability
is `release-qualified` only when its complete mandatory Public v1 journey,
provider evidence, security evidence and exact-candidate release evidence are
all present. No P1–P14 family is release-qualified in the current snapshot.

**Verified release progress: 0% (0/14 families release-qualified).** The
percentage counts only complete mandatory Public v1 journeys with applicable
provider, security and exact-candidate evidence. Partial implementation and
isolated green tests do not close a family.

| Capability | Implemented | Qualified | Release-qualified | Known limitations | Required optional dependency | Supported deployment profile |
| --- | --- | --- | --- | --- | --- | --- |
| P1 Workspace, projects and source control | Partial | Partial | No | Membership, complete authoring journeys and remote-provider certification remain incomplete. | Git executable; OIDC/secret provider for production identity flows. | Local SQLite; Compose/PostgreSQL reference profile. |
| P2 Connectors and ingestion | Partial | Partial | No | Production driver qualification and broad incremental-source coverage remain incomplete. | PostgreSQL, S3/Azure/JDBC drivers; provider credentials. | Local bounded files/HTTP; Compose/PostgreSQL; configured object storage. |
| P3 Lakehouse and SQL | Partial | Partial | No | QueryFlux, remote/catalog qualification and full format/service coverage remain incomplete. | DuckDB locally; Iceberg/Delta libraries; Trino/QueryFlux for remote paths. | Local bounded Parquet/DuckDB; Compose; configured remote engine. |
| P4 Data Engineering Studio | Partial | Partial | No | Worker/evidence lineage, complete CRUD and full authoring surfaces remain incomplete. | Notebook/runtime dependencies; PostgreSQL for runtime qualification. | Local/Compose reference profile. |
| P5 Durable DAG scheduler | Partial | Partial | No | Main includes the combined daemon crash/replay→real Docker notebook worker on PostgreSQL→terminal workflow reconciliation journey, along with worker success and crash/reclaim evidence. PostgreSQL stores workflow/task snapshots, replay-safe branch decisions, generation-fenced scheduler leadership, task-attempt leases, resource pools, fenced/idempotent execution intents with terminal reconciliation, durable event delivery, snapshot-safe backfills, task-evidence lookup, workflow cancellation, schedule cursors/fires and the shared workflow/schedule HTTP adapter. Webhook transport rejects non-public DNS and pins verified TLS destinations. Scheduled `ml.run` execution and result evidence are bound to the canonical pipeline and full Lab definition. Broad scheduler/operator conformance and notification-provider qualification remain open. General production HA is outside the Public v1 contract. | SMTP/HTTPS notification endpoints; PostgreSQL for the complete shared scheduler store. | Local SQLite single leader; Compose exposes workflow and schedule routes backed by PostgreSQL scheduler stores. |
| P6 Catalog and lineage | Partial | Partial | No | Event-standard certification and complete asset-family integration remain incomplete. | OpenLineage HTTP endpoint for remote export. | Local SQLite; Compose/PostgreSQL reference profile. |
| P7 Data quality and contracts | Partial | Partial | No | Provider qualification and complete alert/product surfaces remain incomplete. | Optional SQL/Python execution runtimes; SMTP/HTTPS delivery. | Local/Compose reference profile. |
| P8 AI/ML/MLOps | Partial | Partial | No | Scheduled runs and async JobStore requests pin canonical pipeline and Lab digests, and scheduled execution now passes that exact PipelineIR to its runner. Main resolves Lab AssetRefs to workspace-scoped, digest-verified CSV/JSONL snapshots; durable inputs above 1 MiB use ArtifactStore. The local runner executes the supported six-stage graph and reuses outputs only when runtime and upstream dependency identities match; durable results carry that runtime fingerprint. Final tabular and K-Means models are materialized as verified content-addressed ArtifactStore objects. Main registers successful durable executions as candidate models through Studio, provides workspace-scoped artifact retrieval and bounded UI download, and allows direct promotion with the existing reason gate. PR #450 qualifies S3-compatible artifact writes, reads, digest checks and safe stale-object deletion against LocalStack in CI; vendor production qualification is still open. Configurable stages, broader feature/algorithm coverage, MLflow/network serving and production qualification remain incomplete. PR #452 adds an algorithm choice to ML execution requests and binds checkpoints to the canonical pipeline identity. All six post-merge exact-head workflows for `1edb11a` passed. | Numerical Python stack; MLflow or serving provider for interoperability paths. | Local deterministic training/inference; Compose reference profile. |
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
provider qualification, complete Public v1 journeys, exact-candidate aggregate
release evidence, and legal/NOTICE/attribution review plus human release
approval. The private vulnerability-reporting policy is resolved, and GitHub
branch/tag protections have been verified; these administrative checks are not
the remaining product blockers. Historical or fixture-only evidence must not
be promoted to release qualification.

## Reading rule

The machine-readable ledger remains authoritative for status changes. Update
this matrix in the same change as the ledger when a capability boundary,
qualification result, dependency or deployment profile changes. Do not mark a
row `release-qualified` while `public-v1-status.json` reports an incomplete or
blocked release.
