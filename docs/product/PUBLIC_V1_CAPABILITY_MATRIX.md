# Ronin Public v1 capability matrix

## Current exact-SHA snapshot — 10 November 2026

The current runtime/test candidate is `74fb53338dd62bc246c55b503b33ce2715795364`,
which makes the visible default context the same context used by Runs, keeps
Project deep links aligned with the workspace context, and adds a safe recent-
context switcher. Its exact web receipt is static Chromium `140/140`, web audit
`69` files with zero failures, and budget `2,106,569` asset bytes, `68` requests,
`36` modules, `13` stylesheets and
`5,639` HTML bytes. Candidate-bound Docker, Helm/kind, live, artifact,
SBOM/provenance, VEX and Floci receipts are recorded in the release checklist;
the exact technical lanes pass, while license-policy, legal, security-human,
manual visual, provider-family, rollback/support and governance gates remain
open.
Release status remains separate from the green web lane and is still **NO-GO**
at `0/13` families.
The ledger remains **0/13 families qualified**: mandatory family journeys,
provider matrix, manual visual review, legal/claims decisions, security triage,
full provider/toolchain matrix and security acceptance are still open. The UI target remains a deliberate
next phase: unify authoring, evidence, lineage, operations and progressive
disclosure to approach the usability/depth bar of Databricks, Dataiku, Palantir
and Fabric while keeping Ronin's charcoal/copper/gold identity.

## Historical snapshot — 3 November 2026

Use [`RELEASE_DECISION_CHECKLIST_2026-11-03.md`](RELEASE_DECISION_CHECKLIST_2026-11-03.md)
for the concise GO/NO-GO gate ledger; this matrix retains capability detail
and historical diagnostic evidence.

The latest tracked `main` baseline is `f9a0456ab7df3e2bb77247d54b4336fca64903b0`.
This checkout is on the `20261029` working branch and contains uncommitted
implementation changes, so neither that SHA nor the results below identify a
release candidate. Release qualification remains **blocked at 0/13 families**.

**Latest live regression (3 November):** after extending Ingestion Studio
through governed PostgreSQL snapshot, watermark bootstrap, changed-row
incremental sync and unchanged replay, all **32/32** live Playwright cases
passed with zero skips in 211.74 s. The run used the actual Ronin API,
PostgreSQL, Kafka and Docker worker; it audited 162 HTTP events (153 OK, 9
expected WARN), no 5xx/network errors or unexpected authorization gaps, and
1,493 INFO / 9 WARNING / 0 ERROR application log records. Both dependency
caches hit and the isolated stack was removed. Exact diagnostic evidence and
limits are in §30 of `PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`. P2 remains partial
and no family is release-qualified: this dirty-worktree run does not cover the
full connector/provider matrix, failure/retry recovery, or a clean candidate.

The SQL live route was then strengthened to prove its result, not merely that
the UI issued a request: it creates its own project fixture, verifies HTTP 200,
`value = 1`, one row, and matching rendered output. The optimized focused
diagnostic passed 1/1 with one real API `OK` in 39.06 s end to end (4.55 s
Playwright); PostgreSQL, Kafka and Ronin API were active and both caches hit.
Details and evidence are in §31 of
`PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`. The complete live suite was rerun
after this assertion: 32/32, 0 skipped, 200.88 s total (166.76 s Playwright),
25/25 routes audited, 165 HTTP events (156 OK, 9 expected WARN), no 5xx/network/
auth gaps, 1,497 INFO / 9 WARNING / 0 ERROR; PostgreSQL, Kafka, Ronin API and
Docker worker were active and the stack was cleaned. This remains dirty-worktree
diagnostic evidence, not candidate qualification; §31 records artifact paths
and limits.

The Docker runner now also launches pinned, isolated Floci and executes both
real S3-compatible integration tests (JSON connector retry/readback and ML
artifact/retention). The expanded Docker suite passed 25/25 in 182.13 s and
strict acceptance 15/15 with zero skips/failures; PostgreSQL and Docker worker
also ran. Its focused S3 run passed 2/2 in 7.37 s. Evidence and scope limits
are in §32. This qualifies those local S3 paths diagnostically; P2 remains
partial because Azure, generic JDBC/provider and HTTP/REST full journeys and
the complete provider/failure matrix remain open.

**Latest Helm/kind diagnostic (3 November):** Helm v3.22.1 lint/render and an
isolated single-node kind install passed against the current Ronin image. The
live deployment returned health, Studio and authorized jobs responses; a
submitted queued job remained after a pod restart. The rendered token appeared
only in Secret resources, and the temporary cluster was removed. This chart
requires the explicit local-development `insecure-plaintext-network` bind
policy; it is not a production/TLS deployment. The diagnostic was run on a
dirty worktree and does not complete P14, qualify a release candidate, or
change the 0/13 family count. Exact receipt and remaining P14 gates are in §42
of `PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`.

The 30 October diagnostics over this dirty worktree include the full Python
3.13/PostgreSQL suite (**4,404 passed, 24 skipped, 0 failed; 4,428 JUnit cases**),
Docker runtime (**23/23**) and strict v0.1 acceptance (**15/15**), and real
UI/API qualification (**30/30 Playwright cases; 102 real HTTP calls: 92×200,
5×201, 1×202, 1×400 and 3×401; no unexpected 5xx or browser errors**). The live
server emitted 1,348 INFO/OK logs, 4 expected WARN for invalid cron/credentials,
and 0 ERROR. Static Playwright passed 100 cases and skipped 30 live-only cases;
those live flows were exercised separately. Earlier installed-wheel smoke
covered all 25 routes and axe found no critical/serious issue across three
viewports. Hash-locked dependency audits passed with 0 known Python advisories
(53 development and 92 test dependencies). Gitleaks was not installed on the
host, so no Gitleaks result is claimed; Trivy 0.76.1 secret scanning of the
exact runtime/probe TARs found 0 secrets.

The full Python/PostgreSQL suite was also run in Docker on Linux/Python 3.11.18:
**4,412 passed, 16 skipped, 0 failed** (4,428 JUnit cases); `tests/perf` passed
**3/3**. The previous Windows/Python 3.13 run passed **4,404**, skipped 24 and
had 0 failures. Both runs used the dirty worktree on the `f9a0456` baseline;
neither is a clean-candidate qualification. Full evidence and the coverage-hook
test fix are recorded in §18 of the build plan.

The latest Docker image update replaces Debian Trixie with digest-pinned
Python 3.11 Alpine 3.24.3 and Docker CLI Alpine bases for runtime and probe.
Exact-version APK locks pin the added packages and `apk upgrade` is removed. Trivy 0.76.1 ran with
`vuln,secret` across all severities: both final images reported **0
vulnerabilities and 0 secrets**. The runtime then passed
Docker qualification **23/23** and strict acceptance **15/15**, with no skips.
Compose applies `no-new-privileges` to every Ronin service. This supersedes the
earlier Debian/VEX diagnostic; the VEX exception file was removed. Evidence
paths and image digests are in the dated build-plan record. Package versions
are pinned, while repository availability and base-image digests still
constrain rebuilds; the result remains dirty-worktree evidence, not
candidate-bound release qualification.

These are dirty-worktree diagnostics, not exact-candidate qualification. The
P11 definition, health, run-once, Streaming Bundle API/Studio, and oversized
record rejection/recovery journeys have focused real-broker evidence; broader
operational evidence, exact-candidate qualification, and all 13 release-family
decisions remain open. See the dated execution record in the build plan for
evidence locations and limits.

No CI is required or claimed. Ronin Public v1 remains single-operator, ships no
GenAI or in-product agent runtime, and excludes multi-user administration.
Package/tag version approval and the choice between full Public v1 and the
fully qualified Ronin Local MVP remain human release decisions. If neither
profile meets its complete gates, delay publication.

**Límites de alcance:** multiusuario pertenece a Ronin Pro y no forma parte de Public v1. Ronin no integra capacidades GenAI; los coding agents se usan fuera del producto mediante skills. No contar estas capacidades como huecos de release.

**Historical snapshot (2026-10-27):** `main@4542002c` (consolidación local-only posterior a PR #563). La decisión de entonces retiró CI y dejó únicamente el publicador manual de alias Docker Hub. La suite reportada en ese snapshot pasó 4.102 pruebas y omitió 74. Esa evidencia y los workflows de commits anteriores no califican el estado de hoy.

**Status authority:** [`PUBLIC_V1_SCOPE.md`](PUBLIC_V1_SCOPE.md) and the
machine-readable [`public-v1-status.json`](public-v1-status.json).

**Observed source baseline:** `46e4bc566edc3b3ca1620c66a66552eb58d061f8` (current exact candidate; implementation evidence remains bound to the stated product candidate, this is not a release qualification claim, and the required human/provider gates remain open).

**Historical qualification evidence (pre-current no-CI release policy; not a current gate):** `94d8ae2eb9d73f1e367cb7437873650381e90ad2` (`main`, after PR #546 on 2026-10-24; all six exact-head post-merge workflows passed; mutation skipped by policy). The historical workflow references below record repository history only; they do not mean CI is enabled, required, or part of this release. PR #436 executes the supported six-stage PipelineIR in stable topological order; PR #438/#439 add durable checkpoints and PostgreSQL resume pagination; PR #441 stores verified tabular and K-Means model outputs in `ArtifactStore`; PR #443 registers successful durable runs as candidate models after digest verification; PR #445 integrates registration into Studio; PR #446 adds authorized chunked artifact retrieval and a bounded UI download flow; PR #447 binds checkpoints/results to executable source, Python/dependency versions, backend identity, execution options and upstream outputs; PR #448 adds promotion after execution registration; PR #449 adds selective retry from an explicitly selected ML pipeline stage; PR #450 qualifies artifact lifecycle behavior against S3-compatible LocalStack; PR #451 passes the exact pinned PipelineIR to scheduled runners; PR #452 exposes algorithm selection; PR #453 adds standard scaling; PR #454 adds categorical one-hot encoding; PR #455 adds median imputation; PR #456 composes one-hot encoding and median imputation for mixed features; PR #457 adds a non-destructive retention preview, while global deletion remains disabled; PR #458 adds catalog and ML artifact reference discovery; PR #459 adds bounded durable job evidence and checkpoint discovery; PR #460 discovers all nine reference families and combines them into a fail-closed snapshot; PR #461 bounds workspace/catalog/ML enumeration and fails closed when any inventory exceeds its limit; PR #462 bounds local artifact pagination memory with stable digest cursors; PR #464 bounds manual stale-artifact collection and completes the inventory before deleting, while global cleanup remains disabled; PR #466 bounds durable job evidence and cell-result reads across SQLite, PostgreSQL and memory; PR #470 adds candidate DAGs for classification/regression; PR #471 adds K-Means candidate selection; PR #472 exposes candidate selection in Studio; PR #473 bounds search-space memory; PR #475 gives trials stable identities and derived seeds; PR #476 validates complete search domains before training; PR #477 applies Bayesian stopping by recent improvement; PR #478 adds ordered, directional ML trial tie-breakers; PR #480 caps tie-breaker count at eight and rejects unknown keys to match OpenAPI; PR #482 requires explicit opt-in before an empty live set may delete every artifact; PR #501 records the exact-head artifact-writer inventory audit and its six passing post-merge workflows; PR #502 exposes bounded custom PipelineIR v2 candidate submissions; PR #503 adds independently configured prepare branches and checkpoint recovery; PR #505 adds bounded algorithm×preprocessor candidate grids (maximum eight combinations); PR #509 adds durable selected-model registration after artifact identity revalidation; PR #515 closes the runbook, shell regression and candidate-hardening audit; PR #522 adds exact rollback evidence for a late PostgreSQL multi-object Bundle conflict; PRs #523/#524 reuse a single verified archive across project/connection and remaining multi-object importers; PR #525 adds atomic, exact-replay semantic model/dashboard Bundle import; PR #526 adds portable streaming-definition Bundles with explicit remaps and checkpoint reset/resume identity. PR #527 adds atomic, exact-replay SQLite ML Registry Bundle imports. PR #528 extends atomic, exact-replay ML Registry Bundle import to PostgreSQL, including same-transaction feature definitions. PR #529 fixes POSIX subprocess return-code collection; CI 3.11/3.12, Docker/PostgreSQL and all six exact-head post-merge workflows passed. PR #531 reconciles ML release wording. PR #532 makes ontology Bundle imports atomic and exact-replay in SQLite; late missing assets and definition conflicts roll back the full batch. CI, Docker/PostgreSQL storage coverage and all six exact-head workflows passed. No Public v1 family is release-qualified.

Latest P6 slice on `main@94d8ae2eb9d73f1e367cb7437873650381e90ad2`: PR #539 enforces declared ontology property types and typed graph-link equality; PR #540 makes RQL joins distinguish boolean, integer, and number values and exclude null or missing join properties; PR #542 applies type-aware equality to Graph `=`/`!=` filters while preserving explicit null filtering. PR #542 passed 3,922 local tests (66 Windows/environment skips), 107 focused ontology/KG/RQL tests, mypy, Ruff, formatting, Python 3.11/3.12, Docker runtime/qualification, PostgreSQL storage coverage, Security, Release, Web, Status and CI evidence. All six post-merge exact-head workflows passed. `mutation` was skipped by policy and is not counted as passing. PR #544 emits observed lineage as OpenLineage RunEvents with output column-lineage facets and declared lineage as DatasetEvents with lineage facets. It enforces timestamp/schema/facet validation, a 1 MiB event bound, bounded duplicate suppression and redirect-free HTTP delivery. The full local suite passed 3,954 tests with 66 skips; CI 3.11/3.12, Docker runtime/strict acceptance, PostgreSQL storage coverage, Security, Release, Web and Status exact-head workflows passed. `mutation` remains skipped by policy. PR #546 binds event/facet schema URLs to their payloads and rejects mixed event shapes; its full local suite passed 3,960 tests with 66 skips in 453.06s, and all six exact-head post-merge workflows passed; mutation was skipped by policy. P6 remains partial because consumer/provider certification and complete asset-family integration are open.
OpenLineage follow-up source `f91dbfbf6e30d54e18ada1c23c5f2a37983db157` (code tree tested as `b8e6d7834692e35688054f50655f8f73733d34cb`) restricts known lineage facets to dataset entities and rejects them under run/job. Its local evidence is 132 focused tests; full suite 3,962 passed and 66 skipped in 447.66s; Ruff, formatting, mypy and architecture checks passed on that pre-merge code tree. The merged `main@4686571` has six successful exact-head `push` workflows, but the pre-merge full-suite result is not attributed to that SHA; P6 remains partial.

This matrix is a conservative release view of stable family IDs P1–P14. P9 is
explicitly out of scope; Ronin Public v1 qualifies the 13 active families
P1–P8 and P10–P14. Multi-user identity and administration are Ronin Pro
capabilities. `implemented` means
that the repository contains the described source path. `qualified` means
that the path has current, repeatable evidence in this checkout. A capability
is `release-qualified` only when its complete mandatory Public v1 journey,
provider evidence, security evidence and exact-candidate release evidence are
all present. No active Public v1 family is release-qualified in the current snapshot.

**Verified release progress: 0% (0/13 active families release-qualified).** The
percentage counts only complete mandatory Public v1 journeys with applicable
provider, security and exact-candidate evidence. Partial implementation and
isolated green tests do not close a family.

| Capability | Implemented | Qualified | Release-qualified | Known limitations | Required optional dependency | Supported deployment profile |
| --- | --- | --- | --- | --- | --- | --- |
| P1 Workspace, projects and source control | Partial | Partial | No | Complete authoring journeys and remote-provider certification remain incomplete. Multi-user membership belongs to Ronin Pro. | Git executable; external identity/secret provider for Ronin Pro. | Local SQLite; single-host Compose/PostgreSQL reference profile. |
| P2 Connectors and ingestion | Partial | Partial | No | Ingestion Studio now presents a Discover/Preview/Sync/Observe decision flow over the bounded connector contracts; production driver qualification and broad incremental-source coverage remain incomplete. | PostgreSQL, S3/Azure/JDBC drivers; provider credentials. | Local bounded files/HTTP; Compose/PostgreSQL; configured object storage. |
| P3 Lakehouse and SQL | Partial | Partial | No | Main carries typed scalar bindings through local SQL and provider-neutral query requests; Trino supports `EXECUTE IMMEDIATE ... USING` and QueryFlux requires explicit `parameter_binding`. QueryFlux now has stable content-addressed result pages with project authorization, SQLite/PostgreSQL reference stores, and Studio retrieval/export of loaded pages. `/v1/sql` validates and enforces timeout and serialized-result byte limits; empty paging cursors return 400. A project-authorized DuckDB EXPLAIN route and local Studio action now enforce registered relations, timeout, serialized-plan byte limits, and path/URL/inline-secret sanitization; providers without EXPLAIN fail with 501. Live EXPLAIN UI qualification and remote-provider parity remain open. Durable cancel, governed asset registration, source-revision evidence, CPU budgets, complete SQL Studio journeys and broader format coverage remain incomplete. | DuckDB locally; Iceberg/Delta libraries; Trino/QueryFlux for remote paths. | Local bounded Parquet/DuckDB; Compose; configured remote engine. |
| P4 Data Engineering Studio | Partial | Partial | No | Worker/evidence lineage, complete CRUD and full authoring surfaces remain incomplete. | Notebook/runtime dependencies; PostgreSQL for runtime qualification. | Local/Compose reference profile. |
| P5 Durable DAG scheduler | Partial | Partial | No | Main includes the combined daemon crash/replay→real Docker notebook worker on PostgreSQL→terminal workflow reconciliation journey, along with worker success and crash/reclaim evidence. PostgreSQL stores workflow/task snapshots, replay-safe branch decisions, generation-fenced scheduler leadership, task-attempt leases, resource pools, fenced/idempotent execution intents with terminal reconciliation, durable event delivery, snapshot-safe backfills, task-evidence lookup, workflow cancellation, schedule cursors/fires and the shared workflow/schedule HTTP adapter. Webhook transport rejects non-public DNS and pins verified TLS destinations. Scheduled `ml.run` execution and result evidence are bound to the canonical pipeline and full Lab definition. Broad scheduler/operator conformance and notification-provider qualification remain open. General production HA is outside the Public v1 contract. | SMTP/HTTPS notification endpoints; PostgreSQL for the complete shared scheduler store. | Local SQLite single leader; Compose exposes workflow and schedule routes backed by PostgreSQL scheduler stores. |
| P6 Catalog and lineage | Partial | Partial | No | Ontology property types are enforced and graph links use typed, null-safe equality. RQL joins distinguish booleans, integers and numbers and exclude null/missing values. Atomic, exact-replay SQLite ontology Bundle imports are implemented; event-standard certification, complete asset-family integration and provider qualification remain incomplete. | OpenLineage HTTP endpoint for remote export. | Local SQLite; Compose/PostgreSQL reference profile. |
| P7 Data quality and contracts | Partial | Partial | No | Provider qualification and complete alert/product surfaces remain incomplete. | Optional SQL/Python execution runtimes; SMTP/HTTPS delivery. | Local/Compose reference profile. |
| P8 Machine learning and MLOps | Partial | Partial | No | Scheduled runs and async JobStore requests pin canonical pipeline and Lab digests, and scheduled execution now passes that exact PipelineIR to its runner. Main resolves Lab AssetRefs to workspace-scoped, digest-verified CSV/JSONL snapshots; durable inputs above 1 MiB use ArtifactStore. The v2 local runner supports bounded prepare branches and algorithm×preprocessor candidate grids, with deterministic topological execution and checkpoint recovery. Final tabular and K-Means models are materialized as verified content-addressed ArtifactStore objects. Main registers successful durable executions as candidate models through Studio after artifact identity revalidation, provides workspace-scoped artifact retrieval and bounded UI download, and allows direct promotion with the existing reason gate. PR #450 qualifies S3-compatible artifact writes, reads, digest checks and safe stale-object deletion against LocalStack in CI; vendor production qualification is still open. Atomic, exact-replay ML Registry Bundle imports are available in SQLite and PostgreSQL on main; PR #528 required exact-head qualification passed. P8 remains partial because broader ML and provider qualification gaps remain. Arbitrary built-in DAG shapes and plugin-defined stages, broader feature/algorithm coverage, MLflow/network serving and production qualification remain incomplete. PR #509 added the terminal registration stage and passed all six exact-head workflows on `156d607`. | Numerical Python stack; MLflow or serving provider for interoperability paths. | Local deterministic training/inference; Compose reference profile. |
| P9 GenAI, RAG and in-product agents | Out of scope | N/A | N/A | No Ronin tier ships model/provider invocation, RAG, or agent execution. Coding-agent skills are consumed by external agents and remain separate from Ronin's runtime, API, and Studio. | None. | Not applicable. |
| P10 Semantic models and dashboards | Partial | Partial | No | Export/import and production qualification remain incomplete; broader planning is bounded. | DuckDB/SQL engine for execution; browser runtime for Studio. | Local SQLite/DuckDB; Compose reference profile. |
| P11 Streaming and real time | Partial | Partial | No | Definition, health, bounded run-once, Bundle export/plan/import, and oversized-record rejection/recovery have current local contract evidence (**30/30**) plus a current real-Redpanda lane (**1/1**); reset/resume and correlated logs are recorded. Broader operational evidence, provider breadth and exact-candidate full-family qualification remain open. | Kafka broker/client runtime. | Local bounded polling tests; digest-pinned Redpanda profile and Compose. |
| P12 Observability, alerts and FinOps | Partial | Partial | No | Broader service adoption and production qualification remain incomplete. | Prometheus scrape target; SMTP/HTTPS notification endpoint. | Local/Compose reference profile. |
| P13 Security and audit (single-operator) | Partial | Partial | No | External secret-provider qualification and release evidence remain incomplete. OIDC, user/group administration and multi-user authorization belong to Ronin Pro. | Local bearer/auth profile; external secret backend for Ronin Pro. | Local single-operator; single-host Compose/PostgreSQL reference. |
| P14 Deployment and operations | Partial | Partial | No | A combined local PostgreSQL + `/var/lib/ronin` appliance bundle has a current isolated Compose round-trip diagnostic (database rows, artifacts and execution evidence restored) and pre-destructive checksum/inventory validation. Current Docker/Helm qualification receipts also cover readiness, upgrade/rollback and recovery paths. Clean-candidate evidence, supported-platform coverage, external object-store recovery and full release aggregation remain incomplete. Multi-user HA and Kubernetes server profiles belong to Ronin Pro. | Docker; PostgreSQL; local artifacts; external S3 backup is separate. | Local and single-host Docker Compose. |

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

