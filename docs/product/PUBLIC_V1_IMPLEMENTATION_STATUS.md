# Ronin Public v1 implementation status

**Status authority:** `docs/product/PUBLIC_V1_SCOPE.md` defines the product/release target.  
**Machine-readable ledger:** `docs/product/public-v1-status.json`.  
**Capability matrix:** [`PUBLIC_V1_CAPABILITY_MATRIX.md`](PUBLIC_V1_CAPABILITY_MATRIX.md).
**Architecture decisions:** [`docs/architecture/PUBLIC_V1_ADRS.md`](../architecture/PUBLIC_V1_ADRS.md).

## Current exact-SHA qualification — 11 November 2026

The current runtime/test candidate is `76966e8b` (`Chromium 164 passed, 33 explicit skips, 0 failed; Python 4511 passed, 77 skipped, 0 failed`).
Environments now uses an Observe/Author/Govern workbench with deterministic diff
preview and pause/restore actions; Deployments uses Observe/Bind/Operate with an
explicit project/environment scope and a validated bindings-array replacement.
Both surfaces inherit the visible workspace context and retain their existing API
contracts.
Runs now uses the same default context shown by the shell (`default /
examples/demo / local`), and direct Project deep links synchronize their
workspace scope without clearing a project explicitly chosen by the operator,
and the Runs surface refuses unauthenticated requests before contacting the API.
The context selector also remembers up to five safe recent contexts without
persisting credentials. The complete static Chromium suite passes `147/147`;
web audit passes with `69` files, `38` modules, `180` route invocations and
`0` failures; budget is `2,123,786` asset bytes, `70` requests, `36` modules,
`15` stylesheets and
`5,778` HTML bytes. Exact candidate security evidence is bound to the
runtime/probe images: Docker Scout reports `0` vulnerabilities and the empty
digest-bound OpenVEX verifier reports `0` raw and `0` post-VEX findings;
Gitleaks reports zero findings. The tracked license inventory and policy are
reconciled against the current lock, but 22 dependency review decisions remain
missing; legal approval remains open.

Candidate-bound qualification receipts are green for Docker (`27/27`, strict
v0.1 `15/15`), Helm/kind, live UI/API (`33/33`, 254 correlated events), SDK
artifacts (`90/90`), exact supply-chain evidence, and Floci with Terraform
`1.13.5`/AWS provider `6.65.0`. The full Python/PostgreSQL run passed after the
package/configuration contract was synchronized: `4563/4590` with `27` explicit
skips and `0` failures at `%TEMP%\\ronin-python-full-817ae3c-rerun-20261110`.

This is technical qualification only. Public v1 remains **0/13 (0%, NO-GO)**:
manual visual/product signoff, legal/NOTICE/claims, security/VEX triage and
acceptance, provider/credential qualification, rollback/support, the complete
provider/toolchain matrix and CI/branch governance remain open. The intended product bar remains a simpler,
more powerful, original control plane with the operational clarity of
Databricks, Dataiku, Palantir and Fabric.

### Historical exact-SHA qualification — `4157181`

The historical runtime/test candidate `4157181843d47893e77d62bed62fdafeb31d6f0b`
is pushed and adds a tenth UI pass: Projects becomes an Author/Connect/Operate/
Govern decision workbench with an operational brief that shows source posture,
next gate and a secret-safe Source column, while the connection dialog gets
deterministic bootstrap before the heavy modules. It sits on top of the governed Catalog,
Semantic, Scheduler, Quality, Data Engineering, Ingestion, ML and Workspaces
workbenches. Its exact receipt is static Chromium `132/132`, web audit `68`
files with zero failures, and budget `2,088,109` bytes. Installed PyRonin
artifact qualification is `90/90`; Docker is `27/27` and strict v0.1 `15/15`
on image
`sha256:af76b755b4bf64ef17f1a670d7b35e1e099f8cd8b26b808194446fb30be6755e`;
Helm/kind install/readiness/health/API/persistence/restart/cleanup pass; live
is `33/33` over 25 active routes with 247 correlated events and no server or
network errors; and Docker Scout/OpenVEX is `3 raw / 0 applied` for that image.
The diff from `8a85586` contains no Python or backend runtime changes, so its
`4562 passed, 27 skipped, 0 failed` PostgreSQL receipt and coverage `53/53`,
`62/62` remain the applicable backend evidence. Trivy is unavailable, so the
container SBOM gate and human VEX/security review remain open. These local
receipts do not silently close the release ledger or human-owned gates.

The exact Python/PostgreSQL receipt is green on the clean documentation tree:
`4562 passed, 27 skipped, 0 failed` of `4589`; coverage passes `53/53` and
`62/62`, with both status-ledger contracts passing. The 27 skips remain
explicitly environment/provider/POSIX gates, not silently converted support
claims.

This does not change the release decision: Public v1 remains **0/13 (0%,
NO-GO)**. Manual visual/product signoff, legal/NOTICE/claims, security reviewer
acceptance, Trivy availability, Terraform `1.13.5`, provider qualification,
CI/branch governance and the complete 13-family evidence matrix remain open.
The UI is a stronger control plane, but the product still needs the deeper,
simpler and more powerful authoring/evidence/operations experience targeted at
Databricks, Dataiku, Palantir and Fabric.

**Historical workspace snapshot (2026-10-25):** At that time main was `4686571b403d1499ffbd8f15fce4b01f650b99e8`, merge of PR #547. PR #430–#546 were merged. PR #520
reconciles Public v1 to exclude in-product GenAI/RAG/agent execution, keeps
coding-agent skills external-only, and places multi-user administration in
Ronin Pro. Its exact-head CI, Docker/PostgreSQL, Web, Security, Release, Status
consistency, external-skills boundary and prerelease-artifact workflows passed.
PR #531 reconciles ML qualification wording. PR #532 adds atomic, exact-replay SQLite ontology Bundle import, including rollback on a late missing asset or conflicting definition; its 55 focused tests, Python 3.11/3.12, Docker/PostgreSQL storage coverage and all six exact-head post-merge workflows passed on `main@29dd455d4ba80d546e830571f2139228d29c6594`. PR #539 adds typed ontology semantics and PR #540 closes unsafe RQL joins for mismatched scalar types and null/missing values. On `main@0b32db1c83e681a08e8118e23c0e4b744b3929a5`, PR checks passed 3,921 local tests (66 platform/provider skips), Python 3.11/3.12, Docker runtime and strict acceptance, PostgreSQL storage coverage, Web, Security, Release, Status and evidence workflows; all six post-merge exact-head workflows passed. `mutation` remained skipped by policy and is not reported as pass. The ontology storage coverage ratchet remains at 76.35%. PR #542 makes Graph `=`/`!=` filters type-aware; its full local suite passed 3,922 tests with 66 environment/platform skips, and its required PR gates passed. Los seis workflows post-merge exact-head de `main@4e63e69334a2ae55ce6bc1c2656742193cb919bb` pasaron. PR #544 corrects OpenLineage export: observed edges emit RunEvents with standard column-lineage facets, declared edges emit DatasetEvents with lineage facets, and validation/transport now enforce bounded payloads and no redirects. The full local suite passed 3,954 tests with 66 skips in 489.21s; all six post-merge exact-head workflows passed. `mutation` remains skipped by policy. PR #546 passed the 3,960-test local suite (66 skips in 453.06s) and all six exact-head post-merge workflows; mutation remained skipped by policy. P6 remains partial and Public v1 remains incomplete.
OpenLineage follow-up source `f91dbfbf6e30d54e18ada1c23c5f2a37983db157` (code tree tested as `b8e6d7834692e35688054f50655f8f73733d34cb`) additionally restricts the known lineage facets to dataset entities and rejects them under run/job. Its 132 focused tests and full local suite (3,962 passed, 66 skipped in 447.66s), Ruff, format, mypy (425 files) and architecture checks passed on the pre-merge code tree. After merge as PR #547, the six exact-head `push` workflows on `main@4686571b403d1499ffbd8f15fce4b01f650b99e8` all passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/40109332120), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/40109332165), [Web](https://github.com/SauronShepherd/ronin/actions/runs/40109332135), [Release](https://github.com/SauronShepherd/ronin/actions/runs/40109332179), [Security](https://github.com/SauronShepherd/ronin/actions/runs/40109332128), and [Status](https://github.com/SauronShepherd/ronin/actions/runs/40109332149). Docker jobs passed PostgreSQL-backed `postgres-storage-coverage` (4,014 passed, 14 skipped; the connector-real test skipped in that job) and the separate `non-docker-qualification` suite (4,015 passed, 11 skipped; it configured `RONIN_CONNECTOR_POSTGRES_DSN` and ran `test_postgres_connector_real.py`), real Docker runtime (8 passed), frozen v0.1 strict acceptance (15/15), and one S3-compatible LocalStack artifact lifecycle test. The PostgreSQL suites are separate and overlap; do not sum their counts. These workflow results do not qualify P6 or any of the 13 Public v1 families; P6 remains partial.
Recent
increments add configurable ML algorithms and preprocessing, selective retry,
non-destructive artifact retention preview, fail-closed reference discovery with
bounded enumeration, bounded-memory local artifact pagination, and paged manual
cleanup that validates a complete bounded inventory before deletion, plus bounded
durable job evidence and cell-result reads across SQLite, PostgreSQL and memory,
Bayesian stopping, ordered directional trial tie-breakers with strict bounded
input validation, a manual-retention guard that requires an explicit opt-in
before an empty live set can delete every artifact, and bounded ML candidate grids.
PR #505 supports up to eight algorithm×preprocessor combinations; its PR Docker
qualification passed in 9m50s and all six exact-head workflows passed on
`main@ad53878fac49330d29824dabf1f27e4c4bd2d9d8`. PR #509 adds durable ML
registration after digest revalidation and passed all six exact-head workflows
on `main@156d60784e8e0c5e23f1383c2cf96dc8860560e3`. PR #510 records the ML
build-plan progress and optimization findings on `main@8c7b7e3a8c9cbbbca7b4cdb8ca1d383125b52afa`.
Global cleanup remains disabled because there is no cross-store write barrier. The
PR #482 prevents an empty live digest set from deleting every artifact unless the
caller opts in with an explicit boolean. Its 26 focused tests, CI Python 3.11/3.12,
Web, Security, Release, Status consistency, Docker PR qualification and all six
post-merge exact-head workflows passed. Local Docker qualification passed 21 tests;
two PostgreSQL-dependent tests were skipped without a local DSN, and strict
acceptance passed 15/15. The global sweep remains disabled until writers and
retention share a cross-store consistency barrier.
Untracked qualification output directories are not release evidence.
PR #527 added atomic, exact-replay SQLite ML Registry Bundle imports. PR #528 extends that transaction guarantee to PostgreSQL, including feature definitions, and merged at `main@72a89d06eaf33f604a613376e630a01c5b163dfd`. Its required exact-head CI, Docker/PostgreSQL coverage, Security, Release and Status gates passed; mutation remained skipped. The first coverage run executed 3929 tests (14 skipped) and prompted the documented ratchet update before the successful rerun. PR #529 then fixed a POSIX child-watcher/Popen polling race that caused synthetic exit code 255 in CI 3.12 and the real Docker worker. Local Windows Docker/PostgreSQL focused coverage passed (11 passed, 1 POSIX-only skip); PR CI and all six post-merge exact-head workflows passed on `main@313b8b87670e3f5cad8d641eeeb4f29cf0c31d63`.
**Observed source head:** `6b929e33e3b8d558ba3221cbec0ed842f5031174` (2026-11-13).
The runtime/test candidate is recorded separately in the exact qualification
receipt; the ledger does not close the release. The live qualification harness
was rerun on this candidate with the same worker image used for Docker/Helm;
earlier receipts remain historical.

**Current worktree update (2026-10-30; dirty diagnostic candidate):** P3 now includes a project-authorized local DuckDB `POST .../sql/explain` route and a SQL Studio action. The route reuses project-read authorization, validates the shared read-only SELECT contract and registered relation scope, forwards a bounded execution deadline, incrementally caps serialized plan rows, and redacts paths, URLs and inline secret assignments. Providers without the optional capability return an explicit 501. Targeted verification is recorded in `PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`; this does not qualify P3 or the release, and the historical notes below remain historical snapshots.

**Suite completa más reciente (30-10-2026):** Windows/Python 3.13/PostgreSQL 16.4: **4.404 passed, 24 skipped, 0 failed**; Linux/Python 3.11.18/PostgreSQL 16.4 en Docker: **4.412 passed, 16 skipped, 0 failed**, 4.428 casos JUnit; `tests/perf`: **3/3**. No hubo warnings de coverage/procesos hijos. El test positivo del sandbox ahora aísla los hooks `pytest-cov` del worker; los 47 tests focalizados de superficie/calidad/sandbox pasan en Linux y Windows. Ruff check/format y mypy del test modificado pasan. Los resultados son del worktree sucio basado en `f9a0456`, no de un candidato limpio; el ledger sigue en **0/13**. Véase §18 del plan fechado para diagnóstico, skips y expediente.

PR #552 merged at 19:41:11 UTC. Required PR checks passed; all six exact-head push workflows on the merge SHA passed (CI 40388942726, Docker 40388942459, Web 40388942544, Release 40388943097, Security 40388942691, Status consistency 40388942624). `mutation` and release publish/verdict jobs were skipped by policy and are not passes. The remote feature branch was deleted; local main is aligned with origin/main.

PR #553 merged at 01:20 UTC on 2026-10-27 as `main@993f519e02e611a951b258bb266979fa747e7bbf`. All required PR checks and all six exact-head post-merge workflows passed; `mutation` was skipped by policy. The branch was deleted after merge.

**SQL execution budgets integrated by PR #553:** the request contract now accepts bounded `timeout_ms` and `max_result_bytes`; DuckDB interrupts overdue queries and enforces result limits during fetch, while the HTTP adapter enforces the exact serialized payload cap. SQL Studio forms and OpenAPI expose/document both bounds and the route maps timeout/result-limit failures to 408/413. Focused SQL/API tests passed 85/85, Playwright passed 96 with 3 external-service skips, local Docker worker qualification passed 8/8 against a fresh PostgreSQL database, frozen v0.1 acceptance passed 16 with 3 Spark-configuration skips, and performance tests passed 3/3. The local whole-suite attempt had 4,111 passes, 22 skips and three documentation-sync failures; after correcting those ledgers, the affected tests passed 6/6. The whole suite was not rerun locally, but exact-head CI passed both Python versions and Docker qualification. These tests do not qualify P3 or the release. Explicit pagination/cancel/explain, governed assets, source-revision evidence, CPU bounds, engine-neutral semantics, and full SQL journeys remain open.

**Historical implementation candidate (now merged by PR #552):** `codex/postgres-catalog-support@5f2a3bbaba8f32446293b9d280f6fe2d1bc7bd74` added governed catalog pagination/search and a durable quality workflow across SQLite/PostgreSQL, API, Studio and observability. Its full local suite passed 4,097 tests with 24 environment/platform skips in 337.92s; Docker runtime/acceptance passed 23 tests and strict v0.1 acceptance passed 15/15 using a fresh PostgreSQL database. Coverage run also passed 4,097/24; it emitted 679 Python 3.13 `ResourceWarning` reports, which remain under investigation. Per-file storage ratchet baselines were raised to measured catalog and PostgreSQL-core coverage. This evidence is local and does not qualify a Public v1 family.

The follow-up `68519402` aligned HTTP adapter and DuckDB statement validation on the shared read-only `SELECT` subset; it is included in PR #552. Its focused SQL/API tests passed 26/26. This did not implement pagination, cancel, explain or source-revision evidence; RPV1-304 remains partial.

Commit `2109cbc9` wires the local-composed SQL Studio API to a project-scoped DuckDB engine, verifies the project exists before namespace creation, serializes typed query results, and closes the engine on server shutdown. SQL/composition/server/Parquet tests passed 46/46; the full Python suite with Docker PostgreSQL passed 4,104 tests with 24 environment/platform skips in 590.19s; `tests/perf` passed 3/3. PR #552 then fixed the no-DSN storage coverage gate to exclude PostgreSQL-only `postgres_quality.py` only in that lane; the full Docker lane still measures it. The final PR rerun passed Python 3.11/3.12, Docker/PostgreSQL, Web, Security, ledger and Release packaging; all six exact-head post-merge workflows also passed. Mutation and release publication/verdict jobs were skipped by policy. These results do not qualify P3 or the Public v1 release.

PR #547 restricts known OpenLineage facets to dataset entities. All six exact-head `push` workflows passed (links above); Docker workflow details and conditional skip are stated above. Five focused test commands on a clean worktree of this SHA passed: connectors/checkpoints/ingestion 54; Streaming Bundle 6; PostgreSQL Bundle 2 using PostgreSQL 16.4 in an ephemeral Docker container; OTLP exporter 5; and OTLP collector integration 1 using an ephemeral Docker collector. These 68 tests are local focused evidence only and do not replace the pre-merge 3,962-test result or qualify any of the 13 family gates.
**Release status:** **INCOMPLETE**.

**Scope amendment (2026-10-24):** No Ronin tier provides in-product GenAI/model invocation, RAG, or agent execution. Ronin coding-agent skills are external instructions consumed outside the product. Multi-user identity, user/group administration and multi-user deployment belong to Ronin Pro. Dated evidence notes below preserve their original scope context; the current release denominator excludes GenAI and Pro capabilities.

**Verified release progress:** **0% (0/13 active Public v1 capability families are
release-qualified).** A family counts only after its mandatory Public v1
journey and applicable provider, security and exact-head evidence are complete.
No active family is release-qualified; this is a release-completion metric, not a measure of
code already implemented. P9 is out of scope.

**Build-plan implementation progress:** **not calculable**. No reproducible weighted rubric currently maps partial implementation across the 13 active capability families to a global percentage. The earlier 14% estimate is retired; it must not be reported as current progress. GenAI and multi-user Pro capabilities do not count.

PR [#557](https://github.com/SauronShepherd/ronin/pull/557) integrated the QueryFlux SQL result-byte limit and OpenAPI route parity. All required PR checks passed; mutation was skipped by policy. Six post-merge exact-SHA workflows passed on the merge commit: CI 40444233807, Docker 40444233763, Web 40444233747, Release 40444233740, Security 40444233748 and Status consistency 40444233746. Local verification of this merge SHA passed **4,090 tests with 74 environment/platform skips** and performance tests **3/3**. This does not qualify P3 or any release family.

PR [#558](https://github.com/SauronShepherd/ronin/pull/558) binds QueryFlux execution to explicit workspace/project path scopes, authorizes the project resource and rejects cross-workspace project IDs before execution. Its HTTP integration case, focused route/API checks, local full suite (**4,091 passed, 74 skipped**) and performance suite (**3/3**) passed on the PR candidate. All required PR checks and all six exact-head post-merge workflows passed on `main@56e42c77f5dfc4bc60a3a0047f0a09fdfc112688`: CI 40446346828, Docker 40446346782, Web 40446346833, Release 40446347050, Security 40446346780 and Status consistency 40446346794. Docker qualification included real Docker runtime acceptance and PostgreSQL storage coverage. `mutation` remained skipped by policy. This closes an authorization gap but does not qualify P3 or any release family.

**QueryFlux pagination and SQL route follow-up integrated by PRs #560/#561:** PR #560 added immutable content-addressed result pages scoped to project/run/attempt, authorized page retrieval, durable SQLite/PostgreSQL references and Studio retrieval/export of loaded pages. It also reconciled `/v1/sql` timeout/result-byte enforcement and OpenAPI response/error shapes. PR #561 fixed the explicit empty-cursor edge case: `cursor=` now returns 400 instead of restarting at page one. Focused local evidence includes 82 SQL/QueryFlux tests, 7 HTTP SQL tests, a separate overlapping group of 48, 3 QueryFlux Playwright journeys and the corrected legacy SQL journey. The local web suite initially had one stale `dialect` expectation (98 passed, 3 skipped, 1 failed); after updating it, the affected journey and QueryFlux journeys passed. Mypy (429 files), Ruff, formatting (896 files), OpenAPI and diff checks passed. These separate local runs are not represented as one clean full-suite run. PR #560 and #561 required checks passed; all six exact-head push workflows passed on `main@cca60214044402867094335a2c999a50c3c7fda7` (CI 40452266063, Docker 40452265954, Web 40452266016, Release 40452265985, Security 40452265996, Status consistency 40452266002). The first PR #561 Docker evidence upload timed out after runtime/acceptance passed; its rerun passed and uploaded evidence. `mutation` was skipped by policy. P3 remains partial: durable cancellation, safe explain, governed assets/source revisions, CPU budgets, broader journeys and provider qualification remain open. Release remains 0/13; global implementation progress is not calculable; integral clean-review streak is 0/10.

This document records implementation state only. It does not claim test execution, legal review, human decisions, release qualification or operational evidence that does not exist.

### SQL typed scalar-binding candidate (2026-10-27)

The current candidate makes typed SQL scalar bindings explicit and consistent
across `DurableHTTPApplication.sql` and `SqlHTTPAdapter`: `null`, `boolean`,
signed 64-bit `integer`, finite `float`, and bounded `string`. Unknown fields,
unsupported types, type mismatches, non-finite floats, out-of-range integers,
more than 1,000 parameters, and strings over 512 KiB fail before engine execution.
Existing untagged JSON scalars remain accepted and are normalized to preserve
Public v1 client compatibility. OpenAPI and API compatibility documentation
describe both forms. Local focused tests cover the live HTTP route and DuckDB
binding behavior; remote engine parameter parity is still unqualified.

The current-code/API/ledger focused suites pass 61 tests. The whole local
Python run reported 4,072 passed, 72 skipped and one failure caused by the
OpenAPI hash becoming stale after the schema edit. The snapshot was updated and
the focused suite, including `test_openapi_snapshot`, passes; the whole suite
was not rerun after the final schema and string-limit refinement. Local Docker
qualification passed 21 tests and strict v0.1 acceptance 15/15; two PostgreSQL
worker tests skipped because no DSN was configured. That image was built before
the final schema/string-limit refinement and does not cover SQL bindings;
exact-head PR CI remains required.

This slice does not close RPV1-304/P3: pagination, durable cancellation,
explain, catalog-backed asset registration, source revisions in query evidence,
CPU budgets, engine-neutral provider semantics, complete journeys and provider
qualification remain open. Release progress remains **0/13 (0%, NO-GO)**;
global implementation progress is **not calculable**. Integral clean review
streak after this code change: **0/10**.

**Shared query-engine binding follow-up:** `QueryRequest` now enforces the
shared read-only `SELECT` grammar and carries normalized typed scalar values in
its canonical digest. The local transport binds parameters through DuckDB; the
Trino transport emits `EXECUTE IMMEDIATE ... USING`, with string values encoded
as UTF-8/base64 expressions. QueryFlux rejects execution unless its discovered
engine advertises `parameter_binding: true`. The durable query evidence retains
the request digest without persisting bound values. The current worktree passes
74 focused tests across DuckDB, Trino request construction, QueryFlux, capability
authorization and evidence, including a live Trino 484 Docker transport test
for string, int64, boolean, float and null bindings. This does not certify the
full QueryFlux/provider deployment; the dynamic QueryFlux route also lacks
static core OpenAPI coverage.
RPV1-304 and Public v1 remain partial; release is still **0/13 (0%, NO-GO)**,
and global implementation progress remains **not calculable**.

## Reading this snapshot

The source tree is the authority for implementation presence. The status ledger
is intentionally conservative: a capability is `partial` until its mandatory
Public v1 path is complete end to end. Historical CI/evidence files retain the
candidate SHA they were generated for and are not promoted to current-head
evidence. Older narrative entries that say `0/14` predate the 2026-10-24 scope
amendment; the current denominator is `0/13`.

## Exact-head qualification snapshot

On `main@1edb11a5123bf9ef3c29b7eb2d6d189cc459b8ea`, PR #451 fixes scheduler
dispatch to pass the exact digest-pinned PipelineIR into `execute_pipeline` and
rejects runners that cannot execute that definition. All six exact-head workflows
passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39390985070),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39390984778),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39390984964),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39390985032),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39390984768) and
[Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39390984813).
Docker qualification took 9m36s. P5 remains partial; release progress remains
0% (0/14).

On `main@6dc051ec18d8c54cb61bab37aba59a72f8dc843a`, PR #450 adds S3-compatible
artifact qualification to CI with LocalStack. The exact-head workflow set passed:
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39387588485),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39387588518),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39387588423),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39387588440),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39387588444) and
[Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39387588479).
Docker qualification took 9m27s. Product support remains partial; this is not a
production-vendor certification.

On `main@a5d6a246e67d9f7c7e656c2b56101d6c9f3e6866`, PR #443 adds workspace-scoped
registration of successful durable ML executions as candidate model versions after
rechecking artifact size and digest; PR #445 integrates the flow into Studio. PR #446
adds workspace-scoped artifact retrieval in digest-verified chunks capped at 512 KiB
and a chunked UI download. PR #447 fingerprints executable source, Python and ML
dependencies, backend, options and upstream outputs for checkpoint reuse and durable
result provenance; changed outputs invalidate downstream stages. Its CI and Docker
qualification passed. PR #448 adds promotion after successful execution registration;
79/79 local Playwright tests pass. All six post-merge exact-head checks for `a5d6a24`
passed, including [CI](https://github.com/SauronShepherd/ronin/actions/runs/39379910718),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39379910700),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39379910676),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39379910703),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39379910695) and
[Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39379910759).
On `main@c2df9035d9bdbd24b7dee4357d884807645e5048`, PR #449 adds selective retries
for failed durable ML executions from a selected pipeline stage. All six post-merge
exact-head workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39384556262),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39384556283),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39384556228),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39384556222),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39384556217) and
[Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39384556223).
PR [#441](https://github.com/SauronShepherd/ronin/pull/441) passed CI
Python 3.11/3.12, quality, security, verification, ledgers and [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39371246065)
(8m54s, including PostgreSQL-backed coverage, a real Docker worker and strict
frozen v0.1 acceptance). Public v1 remains incomplete; P8 is partial and release
progress remains 0% (0/14).

On `main@92165f5dbf23b6153c62b0150d4e74e300ac1dd8`, post-merge [CI](https://github.com/SauronShepherd/ronin/actions/runs/39367136040),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39367136035),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39367136031),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39367136019)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39367136046)
passed. [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39367136062)
also passed at 04:07:53Z. PR [#439](https://github.com/SauronShepherd/ronin/pull/439)
passed its exact-head Docker qualification in 8m40s, including PostgreSQL-backed
coverage, a real Docker worker and strict frozen v0.1 acceptance. Public v1 remains
incomplete and P8 remains partial.

On `main@18b2cdecc1380886edeba2a0ad16305be065fa43`, all six post-merge
workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39309554646),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39309554163),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39309554116),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39309554392),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39309554126)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39309554432).
PR [#436](https://github.com/SauronShepherd/ronin/pull/436) passed exact-head
CI (Python 3.11/3.12), Docker qualification (**8m20s**), Web, Security, Release,
ledgers and verification. Post-merge Docker took **8m43s**, including PostgreSQL
coverage, a real Docker worker and strict frozen v0.1 acceptance. PipelineIR now
governs the supported six local stages, and durable checkpoints let re-execution
reuse successful stage outputs. Explicit per-node retry, downstream invalidation and
materialization remain incomplete. Public v1 remains incomplete and P8 remains
partial.

On `main@2d3f7d3b43d0b3b9268a57860e19e707a57a02e8`, all six post-merge
workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39300808656),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39300808822),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39300808898),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39300808705),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39300808877)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39300808941).
PR [#434](https://github.com/SauronShepherd/ronin/pull/434) passed exact-head CI,
Docker qualification (8m50s), Web, Security and Release; Docker covered
PostgreSQL-backed storage, a real Docker worker and strict frozen v0.1
acceptance. Public v1 remains incomplete and P8 remains partial.

On `main@95d25d0e5fccebac66d5a52a814a6c4ad7036f82`, all six post-merge
workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39295218270),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39295221825),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39295218170),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39295218134),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39295218175)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39295218271).
Docker included PostgreSQL-backed storage coverage, real Docker workers and strict
frozen v0.1 acceptance. PR [#432](https://github.com/SauronShepherd/ronin/pull/432)
closed the inline row/column/byte-limit bypass and passed exact-head CI and Docker.
These checks qualify the merged changes; P8 and Public v1 remain incomplete.

On `main@43654932b573a8e84339095323ed8a424a21cb23`, all six post-merge
workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39287975345),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39287975304),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39287975253),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39287975331),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39287975149)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39287975583).
Docker included PostgreSQL-backed storage coverage, real Docker worker
qualification and strict frozen v0.1 acceptance. PR [#430](https://github.com/SauronShepherd/ronin/pull/430)
was squash-merged as `43654932b573a8e84339095323ed8a424a21cb23` after its exact-head
CI, Docker, Security, Release and Status consistency checks passed. These checks
qualify the merged change; they do not close P8 or any Public v1 release family.

On the prior `main@58876c2a759fdb2d6dd93ba354ca6b5ce75ffbff` snapshot
(2026-10-17), GitHub reported success for [CI](https://github.com/SauronShepherd/ronin/actions/runs/39029783787)
(Python 3.11/3.12), [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783816),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783792),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783786),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783791)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39029783794).
Docker included PostgreSQL storage coverage, real container qualification, and
strict frozen v0.1 acceptance (15 passed, zero skips/failures/errors). CI's
`mutation` job was skipped; skipped is not pass. This is exact-head automation
evidence only. The Public v1 release remains **INCOMPLETE**, and product
qualification remains **blocked** by incomplete capability journeys and
external/human-owned evidence.

On the prior `main@41a2024fde3de508d29c2fc3f9960b611f075edd` snapshot,
GitHub reported success for CI, Docker, Web, Security, Release and Status
consistency. The prior `main@fa8cc731f4af11120328b25aa207cb39897503d5`
snapshot also passed [CI](https://github.com/SauronShepherd/ronin/actions/runs/39034134947),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134890),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134789),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034135001),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134870)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39034134902).
Docker passed PostgreSQL storage coverage, real container qualification, and
strict frozen v0.1 acceptance. PR #396's isolated dispatcher termination test
passed the scheduler/API suite (151 tests), Ruff, and local image qualification
(21 passed; strict acceptance 15/15). This candidate additionally implements
the first PostgreSQL run/task snapshot store; its real PostgreSQL Docker
integration passed 3/3 with 95% adapter coverage, plus Ruff, architecture and
mypy. Standard CI excludes this PostgreSQL-only module from its no-service
coverage gate; Docker runs the full per-file coverage gate against PostgreSQL.
The snapshot store
does not implement dispatch, fencing, events, backfills or task evidence, and
does not exercise daemon shutdown/restart or close the broader Public v1 paths.

The prior `main@46f98056b9c501a374fe0f33a1548110f3cbf17f` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39035748927),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39035748910),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39035748905),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39035748879),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39035748917),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39035748936).
The merged PR #397 exact commit `b1b4574d336b1d16cd4b2975e0f996563a8042a1`
and PR #398 exact commit `53f4cc8d6c827e0caa6a8624dff3543d1d6dd4ed`
passed CI (Python 3.11/3.12), Docker, Web, Security, Release, Status
consistency, quality, dependencies and negative gates. Docker passed
PostgreSQL storage coverage, real container qualification, and strict frozen
v0.1 acceptance; `mutation` was skipped.

The prior `main@2a7d0c9ef697d3de131f04d0973b49bfb2e1c780` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39036976451),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39036976461),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39036976408),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39036976428),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39036976444),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39036976413).
The prior `main@e3ca935055968460ba4a0cc3063617c42383b45f` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39039830705),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39039830679),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39039830690),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39039830694),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39039830715),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39039830750).
The prior `main@586801468a6b1cdc0f28d72d0da585ceb3ca2fd1` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39041024109),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39041024090),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39041024085),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39041024151),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39041024086),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39041024136).
The prior `main@209991ab4b67a1d1cdb85057432e80bda1c2bfdd`, including the
squash merge of PR #401, passed [CI](https://github.com/SauronShepherd/ronin/actions/runs/39047807894),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39047807872),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39047807911),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39047807769),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39047807778),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39047807882).
PR #402 added PostgreSQL task-attempt claims, lease heartbeat/fencing,
expiry reclaim/retry, terminal completion and resource-pool capacity. Its exact
head passed Python 3.11/3.12, PostgreSQL-backed storage coverage and Docker
qualification; `mutation` was skipped. The squash commit is
`main@0ccb5fdd68b8849f860c7ffe9ef2526e4ec9b3e4`; on `main@ef0d107`, exact-head
Status consistency and Security passed, with CI, Docker, Web and Release
running. PR #404 added the PostgreSQL schema-4 execution
outbox with lease-fenced writes, idempotent intent replay, expired-attempt
protection and terminal reconciliation; its required CI, Docker (7m45s),
`ledgers`, Security, dependencies and remaining checks passed. `mutation` was
skipped. PostgreSQL event delivery, backfills and task-evidence stores remain
incomplete, and the scheduler HTTP routes stay unavailable for that profile.
PostgreSQL snapshots, replay-safe branch decisions and generation-fenced
leadership persist in main. The real PostgreSQL integration passed 4 tests
with 87% leadership-adapter coverage, including repeat execution against the
same database. The local scheduler/workflow suite passed 115 tests. Ruff,
formatting, architecture, focused mypy for the adapter, and status generator
checks passed. The repository-wide mypy command reports three existing
unused-ignore errors in unrelated files. Standard CI
excludes PostgreSQL-only adapters from its no-service coverage gate; Docker
runs the full per-file coverage gate against PostgreSQL. PostgreSQL scheduler
HTTP routes remain unavailable until task execution state and the remaining
scheduler stores are qualified.

The audit for PR #401 found that a branch decision arriving after task completion
could overwrite the terminal task state. The fix rejects late decisions in both
SQLite and PostgreSQL under their transaction locks, increments SQLite
`row_version` for a persisted decision, and tests that a rejected update leaves
state and version unchanged. CI and Docker passed on code candidate
`a5ae71629589b5d722c4ba29c50492661fe94728`; Docker passed PostgreSQL storage
coverage, real container qualification, and strict v0.1 acceptance. The 0% release
progress remains unchanged because P5 and all other mandatory capability families
remain partial.

The PostgreSQL task-attempt implementation passed real PostgreSQL integration
in Docker: 14 focused tests passed and focused line coverage reached 81%.
PR #404 added the PostgreSQL execution intent outbox and terminal reconciliation.
PRs #406–#414 now provide PostgreSQL event delivery, backfills, task evidence,
schedule cursors/fires and the workflow/schedule HTTP adapter. Later PRs qualified
the combined daemon-crash→Docker-worker→terminal-reconciliation journey. P5 remains
partial because complete controller recovery, broad operator conformance and
notification-provider qualification remain incomplete.

The current workspace includes the implementation families listed in the
package inventory (`studio_ai_studio`, `studio_cloud`, `studio_data_engineering`,
`studio_migration`, `studio_ml`, `studio_streaming`, `studio_synthetic_data`,
and the shared runtime/storage/server packages). It also includes the current
ML, migration, Cloud Studio, PostgreSQL and synthetic-data contracts under
`docs/`; those documents describe implemented slices and remaining boundaries,
not Public v1 completion.

## Historical local verification (prior snapshot)

These local results were recorded against the prior source snapshot
`dfdb1045de2e997caa191ba81a8ec640c1dd04bd`, not the observed candidate above.
The full `python -m pytest -q` verification produced **2266 passed, 15 skipped**
with zero failures or errors. The skips are
environment-gated Docker/PostgreSQL/Spark/provider qualification checks, not
test failures.
The latest focused contract verification produced **144 passed**.
Additional evidence recorded for that snapshot includes Docker qualification
(21 historical CI checks plus 5 current real-Docker tests), real PostgreSQL integration (11 passed), the installed-wheel
browser smoke (no console/request/CSP failures), installed-wheel accessibility
(no violations at 320/768/1440 px), and four credential-free migration fixture
certifications. These checks do not constitute current-head or Public v1 release qualification.

That snapshot's local checks additionally passed Ruff format/lint across all 881
Python files, the public import smoke for 32 packages, 11 Data Engineering
async tests, and installed-wheel plus installed-sdist Studio Chromium and
accessibility qualification (zero console/request/CSP, axe, or layout failures).

Mutation evidence is retained as a historical, frozen record in
`docs/quality/MUTATION_CAMPAIGN_FINAL.md`. Recurring mutation qualification is
retired by product decision and is not a release or implementation blocker.
Current product readiness is determined by ordinary unit, integration, contract,
and end-to-end verification plus the capability matrix; temporary mutation
workspaces and generated reports are not release evidence.

## Status vocabulary

- **implemented** — the stated foundation/path exists in source and is not known here to require another feature to perform its narrow claimed role;
- **partial** — meaningful source implementation exists, but the mandatory Public v1 family lacks an end-to-end supported path;
- **missing** — no supported implementation path exists for the mandatory capability;
- **blocked** — work/evidence cannot be truthfully completed under a current external or maintainer-controlled prerequisite;
- **human decision** — a maintainer/product/security/legal decision must be made rather than invented by implementation;
- **qualification pending** — implementation exists but current exact-head execution/release evidence does not.

## Repository-grounded capability snapshot

| Capability | Status | Current source truth |
| --- | --- | --- |
| Durable execution foundation | implemented | Job/Run/Attempt, SQLite durability, leases/heartbeat/fencing/reclaim/resume, cancellation, evidence, local/container worker, HTTP/CLI/SDK foundation |
| Workspace/project/source control | partial | workspace/project persistence, authenticated create/read/update/archive workspace and project lifecycles with idempotency, audit and active-project filtering, project manifest, reproducible secret-free deployment manifest with canonical identity, Git identity, environment/deployment bindings, Studio and SDK journeys covering project creation, environment binding, Bundle export/archive, audited/idempotent governed pipeline execution and project-scoped permission inspection; full Public v1 APIs/UI remain. Multi-user membership belongs to Ronin Pro. |
| Connectors/ingestion | partial | connection/discovery/checkpoint contracts, governed local CSV/JSONL, bounded HTTP/PostgreSQL, S3-compatible including Apache Ozone, Azure Blob and JDBC profiles, public capability/plan/preview/checkpoint-health API, Studio actions and SDK parity; production driver qualification and broader incremental coverage remain |
| Lakehouse/SQL | partial | bounded Arrow/Parquet open-data and streaming publication paths, provider-neutral SQL/table contracts, optional local DuckDB engine with bounded relation lifecycle, shared query lifecycle adapter, provider-neutral query-engine contracts/discovery/local transport/Trino HTTP transport, QueryFlux discovery and QueryFlux-to-Trino lifecycle adapters, bounded project-scoped fail-closed read-only SQL HTTP adapter/route, and optional Iceberg/Delta adapters exist; external QueryFlux and remote/catalog qualification, full format features, and broader SQL service remain |
| Data Engineering Studio | partial | notebook/pipeline execution foundations, durable SQL editor revisions/history/bounded export, parameter schemas, pipeline revision comparison/archive, and an authenticated pipeline-revision-to-workflow-run creation route with deterministic idempotency exist; worker/evidence lineage, complete CRUD and complete Web Studio remain |
| Durable DAG scheduler | partial | durable snapshots/task runs, fenced attempts/retries/dependencies, deterministic task→Job planning, execution outbox/reconciliation, deployment-aware controller, timezone-aware durable cron, durable event inbox/delivery, cancellation, timeout enforcement, snapshot-safe bounded backfill, shared resource pools, generation-fenced leader authority, leader-guarded cron/event/backfill/controller services, bounded and continuous daemon orchestration, graceful SIGINT/SIGTERM daemon entrypoint with fenced lease release, group backfill cancellation, fail-closed conditional branches with idempotent persisted decisions/skipped task state, authenticated schedule/event-trigger APIs and Studio authoring, durable adapters for supported operators, optional notification dispatch and durable retry/error recording exist. PostgreSQL dispatch replay, real Docker notebook execution, worker crash/reclaim, and the combined daemon-crash→worker-Docker→terminal-reconciliation journey have focused qualification. Webhook requests reject non-public DNS answers and pin validated addresses through TLS. Broad scheduler/operator conformance, complete controller recovery and notification-provider qualification remain |
| Catalog/lineage | partial | governed asset CRUD/revisions, versioned sensitivity/ownership, glossary authoring, bounded search, lineage HTTP navigation, OpenLineage export/HTTP transport and selected-subgraph Bundle portability exist; event certification and complete asset integration remain |
| Ontology/KG | partial | object/property/link/action schema and persistence, instance materialization, link resolution, bounded graph queries and authorized actions exist; durable replay and public interfaces remain |
| Graph intelligence/RQL | partial | bounded read-only RQL SELECT filtering, one-hop typed traversal, and typed property joins over materialized KnowledgeGraph views exist; planning, provider execution and public API exposure remain |
| Data quality/contracts | partial | versioned definitions/results, all built-in checks, injected SQL/Python/referential checks, quality gates, scheduler release enforcement, quality-to-common-alert transition evaluation, authenticated contract read/replace and run/history/state APIs, pyronin SDK parity including contract authoring, and Quality Studio contract authoring, validation, dry-run, evidence/history and blocking-policy controls exist; provider qualification remains |
| AI/ML/MLOps | partial | experiment/run/model/evaluation provenance, deterministic tabular training, canonical Lab/pipeline digest pinning for scheduled ML runs, digest-verified inference, champion serving resolution, deterministic trial comparison, bounded numeric drift summaries, explicit feature-level threshold assessments, versioned feature definitions with dataset snapshots, workspace-scoped HTTP routes and pyronin SDK parity exist; broader feature engineering, algorithms, MLflow and network serving remain |
| GenAI/RAG/agent runtime | out of scope | No Ronin tier ships model/provider invocation, RAG, tools, or in-product agent runtime/API/Studio. Coding-agent skills are installed for external agent use only. |
| Semantic models/dashboards | partial | safe semantic contracts, canonical persistence, parameterized metric compiler, calculated metrics, SQL metric runtime, bounded declared-column two-model JOIN execution, dashboard CRUD/execution, workspace+project-scoped storage keys, Studio semantic Bundle export/plan/import API with digest-bound preview, project read/write permissions, audit, 700 KiB limit, SQLite atomic model+dashboard import, exact replay and conflict handling exist; an explicit SQLite migration tool rehomes legacy unscoped definitions into an operator-selected workspace with conflict-safe atomicity; dashboard fan-out/cancellation budget, PostgreSQL import and exact-head public API/Studio qualification remain |
| Streaming/real-time | partial | Kafka polling, durable CAS checkpoints, micro-batch processing, Parquet sinks, event-time windows, stream tables, scheduler integration, bounded health/lag and canonical stream-definition Bundles exist. Local execution caps records at 1 MiB and batches at 8 MiB. Focused real Redpanda browser/API proof consumes five records in 2/2/1 batches with lag 5→3→1→0, covers reset/resume and idle replay, and rejects a poison record twice with HTTP 422 without advancing lag or revealing content; all 20 HTTP events correlate with logs. Byte-boundary, poison checkpoint and Bundle reset/resume contract tests pass; real-broker record-overload/recovery now has focused evidence; broader operational, provider and complete Bundle qualification remain |
| Observability/alerts/FinOps | partial | durable metrics/events, threshold alerts, SMTP/webhook notification adapters, durable delivery intents with retry/backoff, Prometheus export, instrumentation, usage pricing, actual-versus-estimated costs, non-ledger forecasts, anomaly hooks and budget gates exist; authenticated alert-rule/evaluation APIs, SDK parity, fail-closed alert operation validation and the Monitoring & Alerts Studio route are covered by static and Playwright smoke evidence; broader service adoption and production qualification remain |
| Security/authentication (single-operator) | partial | bearer auth, transport policy, fail-closed classification-aware policy actions, secret resolver ports, broad mutation audit and append-only audit foundation exist; external provider qualification and release evidence remain. OIDC, user/group administration and multi-user role management are Ronin Pro scope. |
| Local/Compose operations | partial | local/Compose foundation, PostgreSQL metadata healthcheck, PostgreSQL JobStore adapter wired to the server, single-node real-PostgreSQL lifecycle qualification, SQLite backup/restore with path-bound artifact-tree manifests, PostgreSQL dump verification, S3 artifact retry/corruption checks, Kubernetes Job adapter and recovery runbooks exist; Kubernetes/server deployment and multi-user Helm are not Public v1 profiles. Scheduler conformance and backup/restore qualification remain incomplete. |
| Ronin Bundle | partial | deterministic verified archive IO, project/connection/catalog/workflow/schedule/quality/ontology/semantic/stream-definition inventories, shared verified archive reading across importers, atomic SQLite/PostgreSQL workflow commits, atomic SQLite semantic model+dashboard imports, and explicit streaming checkpoint reset/resume bindings exist; durable import receipts/recovery, ML artifacts/data assets, broader PostgreSQL domain adapters, certification and public surfaces remain |
| Fabric migration | qualification pending | deterministic fixture discovery and fail-closed notebook-item translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Databricks migration | qualification pending | deterministic fixture discovery and fail-closed notebook-job translation with dependency/schedule mapping and CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Palantir Foundry data/Ontology migration | qualification pending | deterministic fixture discovery and fail-closed Python-function translation with CLI/report tests; AIP generative models, prompts, agents, tools and model/provider invocation are excluded; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Dataiku DSS migration | qualification pending | deterministic fixture discovery and fail-closed Python/SQL recipe translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Web Studio | partial | authenticated static Studio shell supports job/evidence/event workflows, project-scoped read-only SQL, project/environment/Bundle/governed-pipeline journeys, resource-scoped project permission inspection and a Monitoring & Alerts route; 77 Playwright route/accessibility/history/domain-journey checks pass; authoring editors, domain workflows and complete Public v1 journeys remain |
| Public v1 release qualification | blocked | CI is intentionally absent; latest dirty-worktree digest-pinned Alpine runtime/probe images use exact-version APK package locks and passed Trivy 0.76.1 across all severities with 0 vulnerabilities and 0 secrets; Docker qualification passed 23/23 and strict acceptance 15/15; live UI/API passed 30/30 with 102 real calls and 0 5xx; server logs recorded 1,348 INFO/OK, 4 expected WARN for invalid cron/credentials, and 0 ERROR. This supersedes Debian/VEX evidence. A clean candidate-bound evidence set, complete capability journeys, legal/product decisions and provider certification remain pending. |

## Public v1 source work merged in the current construction sequence

PRs **#242–#288** moved Public v1 from planning into source implementation. Scheduler foundations include deterministic task→Job identity/linking (#259), execution outbox/reconciliation (#260), deployment-aware controller (#262), cron/events (#263/#264), cancellation/timeouts (#265/#267), snapshot-safe backfill (#268), pools (#270), leader fencing (#271/#273), daemon orchestration (#274/#275), and group backfill cancellation (#276). Native Bundle portability added project semantic inventory/export (#278), project import planning (#279), runtime remapping plus atomic project/environment-binding commit (#280), connection round-trip with explicit secret-reference remapping (#282), deterministic dependency-ordered multi-object staging (#283), atomic project+connection commit (#285), explicit selected catalog subgraph export/planning (#287), and atomic catalog asset/revision/lineage commit (#288). PR #266 made Public v1 the active construction authority while preserving the historical v0.1 planning files verbatim.

These merges do **not** imply that their parent capability families are complete. Scheduler branching/skipped semantics, durable notification dispatch, public APIs/Studio authoring, and process/signal wiring now exist; the combined crash/replay/worker/reconciliation journey has focused evidence, while complete controller recovery and broader operator/provider qualification remain. PostgreSQL now persists workflow/task snapshots, branch decisions, leader fencing, task-attempt leases and execution intents with terminal reconciliation, durable event delivery, snapshot-safe backfills, and workspace-scoped task-evidence lookup. Scheduler HTTP routes remain unavailable on the PostgreSQL backend until full scheduler conformance is qualified. Bundle support now covers project, connection, workflow/schedule, quality contracts, ontology definitions, semantic models/dashboards, and an explicitly selected catalog subgraph. Ronin has no in-product GenAI capability; coding-agent skills are consumed externally. PostgreSQL has atomic commit adapters for project/connection, workflow/schedule, and selected catalog imports, but lacks adapters for several other domains and a cross-domain transaction/recovery coordinator. Semantic SQLite Bundle import now atomically commits models and dashboards with exact replay. Catalog export intentionally does not invent whole-catalog revision discovery because the current catalog port does not expose it.

## Invariants that remain mandatory

1. **Canonical identity:** semantic IDs use versioned canonical contracts; physical locators, credentials and ephemeral worker state do not silently enter logical identity.
2. **Durability:** logical retries do not duplicate Job/Run meaning; state transitions are persisted before dependent completion claims.
3. **Fencing:** stale workers/controllers cannot commit authoritative state after lease loss.
4. **Checkpoint safety:** ingestion/stream checkpoints advance only after governed output commit.
5. **Secrets:** portable state stores references only; resolution happens at an authorized execution/deployment edge.
6. **Storage portability:** SQLite remains a supported local adapter while production backends must preserve the same service semantics.
7. **Security:** authorization is typed and resource-scoped; unsupported constraints fail closed; UI never replaces server-side enforcement.
8. **Migration honesty:** every source object is classified as exact, translated, partial, passthrough, unsupported or manual-decision; nothing is silently dropped or upgraded semantically.
9. **Evidence honesty:** implementation presence is not CI/release qualification, and historical evidence is not current-head evidence.

## Human-decision / blocked work

- **License/NOTICE/attribution and release approval:** tooling may inventory facts; maintainers/legal review own conclusions.
- **Provider certifications:** real vendor qualification still needs authorized environments and credentials; fixture-only migration evidence is not certification.
- **#102:** the `coverage-release-gates` target enforces its explicit 90% floor on release and evidence modules. The previously summarized 11 gate modules passed their recorded thresholds; this branch adds `tools/bind_container_sbom.py` to that enforced list with **100% line and branch coverage**. Future evidence-decision modules must join the same floor.
- **#63:** current GitHub API evidence shows protected `main` with eight required checks, admin enforcement, no force pushes or deletion, and an active `v*` tag ruleset. Reconcile the open issue's checklist with this evidence before claiming the issue is fully satisfied.
- **#199, #57, #96, #202:** automated qualification is active and exact-head runs pass on the recorded candidate. The strict 15-step Docker/release gate for #96 landed in #389; keep the broader journey and product/provider/legal criteria open.
- **Mutation:** the campaign is permanently frozen and the score gate retired by product decision. Do not rerun; reopen only through a new explicit product decision and campaign plan.

## Updated critical path

1. Keep this ledger and the active construction plan synchronized with repository truth.
2. Broaden scheduler/operator conformance and qualify notification delivery in supported local/Compose profiles. The combined daemon→real PostgreSQL/Docker worker→terminal reconciliation journey now has exact-candidate Docker evidence. PostgreSQL event, backfill, task-evidence, dispatch replay, worker success and worker crash recovery also have focused evidence. Do not claim production HA.
3. Extend native Bundle support to the next executable canonical metadata family, preferring workflow/pipeline persistence if its canonical snapshot/store contracts preserve identity without deployment locators; then quality/ontology/ML as their contracts permit.
4. Complete store ports for remaining domains; then implement PostgreSQL adapters and an S3-compatible artifact store without changing logical references.
5. Implement the first open data path: Arrow/Parquet + reference open table profile + reference SQL engine, with catalog/lineage/quality hooks.
6. Complete remote connectors and safe incremental checkpoint execution.
7. Expand the Public v1 API and begin Web Studio against documented/generated clients.
8. Complete quality runtime, ontology/KG actions/query, RQL, ML, semantic/dashboard, streaming and observability/alerts/FinOps.
9. Keep multi-user identity, administration and Kubernetes multi-user deployment on the Ronin Pro roadmap.
10. Build the four vendor migration profiles only against executable canonical target capabilities and certify them with exhaustive migration reports.
11. Continue #102 coverage work: `coverage-release-gates` applies a 90% floor to the strict gate, exact-candidate aggregator, artifact identity, release evidence/emission, installed-artifact evidence, artifact/license qualification, SBOM generation, supply-chain evidence, container SBOM binding, and mutation-policy parser. The container binder currently has 100% line and branch coverage.
12. Maintain exact-candidate qualification; the strict Docker/release acceptance gate must pass on its exact candidate. Public v1 remains incomplete until every mandatory family has its supported end-to-end path and the human-owned evidence is approved.

### Reconciled after PRs #420–#421 (2026-10-18)

PR [#420](https://github.com/SauronShepherd/ronin/pull/420) added PostgreSQL-backed worker crash recovery after three durable checkpoints and the complete 30-second lease expiry. A replacement worker reused the three completed cells and executed the remaining two. The merge is `main@37d00eb3d02ad6f6d9e8dba923261c5536d08838`; all six workflows passed exact-head after merge. PR [#421](https://github.com/SauronShepherd/ronin/pull/421) then qualified the combined daemon crash/replay, actual Docker notebook execution against the same PostgreSQL schema, and terminal workflow reconciliation. CI 3.11/3.12 and all required PR checks passed on `0e8becfe517a18e697ab72afe889c20a68d8f204`, including Docker qualification with PostgreSQL-backed coverage, real worker execution and strict acceptance in 8m46s. The squash is `main@a0faef17d4897377765deac8445a60def604fd49`; its exact-head post-merge workflows are being reconciled. P5 remains partial and verified release progress remains 0% (0/14).
PR [#420](https://github.com/SauronShepherd/ronin/pull/420) added PostgreSQL-backed worker crash recovery after three durable checkpoints and the complete 30-second lease expiry. A replacement worker reused the three completed cells and executed the remaining two. The merge is `main@37d00eb3d02ad6f6d9e8dba923261c5536d08838`; all six workflows passed exact-head after merge. PR [#421](https://github.com/SauronShepherd/ronin/pull/421) then qualified the combined daemon crash/replay, actual Docker notebook execution against the same PostgreSQL schema, and terminal workflow reconciliation. CI 3.11/3.12 and all required PR checks passed on `0e8becfe517a18e697ab72afe889c20a68d8f204`, including Docker qualification with PostgreSQL-backed coverage, real worker execution and strict acceptance in 8m46s. The squash is `main@a0faef17d4897377765deac8445a60def604fd49`; all six exact-head post-merge workflows passed. P5 remains partial and verified release progress remains 0% (0/14).

PR #423 fixed the `quality.gate` contract-pinning gap: `contract_digest` is now bound to the canonical persisted `DataContract` and checked before evaluation or evidence recording. It merged as `35072ef4d1940842076814d34a240869ebf48065` after Docker and all remaining exact-head workflows passed. PR #424 closed the webhook DNS-to-private-network SSRF gap by pinning validated public addresses through TLS; Docker and all six exact-head post-merge workflows passed on `e4ddf182fca00a8861140fd1664590d027092b51`.

PR [#425](https://github.com/SauronShepherd/ronin/pull/425) merged the canonical pipeline/Lab digest pin for scheduled `ml.run` jobs as `main@0180e27ffd8171e27f5731b3397a3439ff90e916`; all six exact-head post-merge workflows passed. PR [#426](https://github.com/SauronShepherd/ronin/pull/426) then preserved terminal cancellation when the runner raises late, with deterministic queued/running tests, CI 3.11/3.12 and full Docker qualification; all six exact-head post-merge workflows passed on `main@0afa7db291eddcf0db0a3acc67372c9f55378ef4`. The current candidate reconciles Lab/v1 serialization, metadata, clustering and split semantics; it passes the broad ML suite locally and in Docker, plus a PostgreSQL 16 Lab round-trip. Durable coordinator/workspace fencing, broader Public v1 ML journeys and external qualification remain open.

PRs #522–#525 then added rollback on late PostgreSQL conflicts, a shared verified Bundle reader, and atomic/replayable SQLite semantic model/dashboard imports. PR [#526](https://github.com/SauronShepherd/ronin/pull/526) added portable streaming-definition Bundles with explicit connection/storage/runtime remaps and reset/resume checkpoint binding. Exact-head CI, Docker/PostgreSQL, Security, Release and status consistency passed; it merged as `main@70632ed148b4e433ae0fbf87220f6cb3370ab968`. The current reconciliation keeps release-qualified progress at 0% (0/13): no Public v1 capability family is closed.

## Reconciliación de PostgreSQL scheduler (2026-10-17)

Los PR #406 y #407 añadieron entrega durable de eventos y backfills PostgreSQL, respectivamente. #407 corrigió además la carrera de cancelación al crear workflows. El candidato `8edb47807fc4ce9db23067fd5a933c95d821a8c9` pasó CI 3.11/3.12 y Docker qualification; la integración local con PostgreSQL 16 pasó 10 pruebas del adaptador de backfills (88% de cobertura de ramas), más 27 pruebas SQLite/scheduler relacionadas. El merge actual es `main@418ab8be9604c12d84e2825ec2b925cf865d39b7`. En la observación de reconciliación, CI, Web, Security, Release y Status consistency exact-head de `main` pasaron; Docker qualification seguía en ejecución. Después, `read_task_evidence(workspace_id, attempt_id)` quedó implementado para resolver evidencia del Job asociado al intent durable con aislamiento por workspace, y la prueba de integración de outbox/evidencia/reconciliación pasó en PostgreSQL 16. Esta evidencia no cierra P5 ni cambia el progreso release-qualified de 0% (0/14): faltan recuperación end-to-end del dispatcher y conformance integral de operador/notificaciones.

### Estado reconciliado tras PR #411 (2026-10-17)

`main@39c83b4490328fc0be44a7f4e7f30c4870615491` integra el vínculo PostgreSQL workspace-scoped de workflow con proyecto y entorno (`WorkflowDeploymentBinding`) por medio de migración 6→7. El PR #410 pasó CI 3.11/3.12, Security, Release, Status consistency, Web y Docker (**7m15s**); su primer job Docker expuso una mejora del adaptador `postgres_core.py` hasta 37,61%, así que el ratchet se elevó de 32,00% a ese valor medido.

El PR #411 integra migraciones PostgreSQL 7→9 para solicitudes persistentes de timeout y estado cancelado de intentos. Las funciones compartidas consultan la autoridad de dispatch y las solicitudes PostgreSQL; la detección es repetible, el timeout se reconcilia a retry/fallo, y si el workflow está cancelándose, la finalización conserva el estado cancelado. CI 3.11/3.12 y Docker qualification pasaron; Docker completó la cobertura PostgreSQL, pruebas Docker reales y aceptación estricta en **7m25s**. La cobertura medida de `scheduler_timeout.py` llegó a 68,78%, por lo que su baseline subió a 66,70% manteniendo el ratchet de 2,1 puntos. El merge squash es `main@dacd3ffbecef029a77fdfa6ef09cc45bea232f2c`; CI, Docker (**6m57s**), Web, Security, Release y Status consistency exact-head también pasaron.

El PR [#412](https://github.com/SauronShepherd/ronin/pull/412) delega a PostgreSQL el cambio durable de workflow a `cancelling`, la cancelación de tareas sin intent, el retiro de intents aún no enviados y la reconciliación de Jobs cancelados. La autoridad de cancelación se persiste antes de esperar bloqueos de tareas. Sus 17 pruebas PostgreSQL pasaron en Docker/PostgreSQL 16 con 82% de cobertura del adaptador; CI 3.11/3.12 y Docker qualification completa (**8m14s**) también pasaron. El squash quedó en `main@897e04a3b6c4219d82ed70d13a126c27a97cff4c`; CI, Docker, Web, Security, Release y Status consistency exact-head de main pasaron.

El PR [#414](https://github.com/SauronShepherd/ronin/pull/414) añadió migración PostgreSQL 9→10 con cursores monotónicos y ledger idempotente de schedule fires, implementación del contrato HTTP completo y montaje condicionado de rutas workflow/schedule en Compose. PostgreSQL 16 en Docker pasó **19 pruebas**, incluida una ruta HTTP real, y el módulo nuevo obtuvo 100% de cobertura de líneas y ramas. El PR pasó CI 3.11/3.12 y Docker qualification (**7m54s**); quedó integrado en `main@98e79db96ef45cfca6c3678c59475d5f74d024b6`. CI, Docker, Web, Security, Release y Status consistency exact-head de esa base pasaron. Las rutas generales workflow/schedule están disponibles cuando el backend expone todas las operaciones del contrato.

El PR [#415](https://github.com/SauronShepherd/ronin/pull/415) añadió takeover del `SchedulerDaemon` sobre stores PostgreSQL aislados: tras expirar el lease anterior, la instancia nueva adquiere generación 2 y vuelve a leer el cursor/fire persistente sin duplicarlo. PostgreSQL 16 en Docker pasó **20 tests** del módulo completo y CI 3.11/3.12 más Docker qualification (**6m37s**) pasaron antes del merge `main@2abc6ac3495ae3aa61a406f6f8c5be3e3478b796`. También pasaron todos los workflows exact-head post-merge: CI, Docker, Web, Security, Release y Status consistency. El test cubre takeover/replay de schedule, no recovery del controller.

El PR [#416](https://github.com/SauronShepherd/ronin/pull/416) mueve la entrega síncrona de notificaciones fuera del event loop y renueva el lease durante proveedores lentos. La regresión confirma que un contender no obtiene liderazgo mientras el dispatcher excede el lease inicial. Daemon + PostgreSQL 16 en Docker pasaron **29 tests**, con Ruff, formato y mypy. El squash `main@3b7e9aca15c94d247af2ac459b606e83c2699581` pasó CI 3.11/3.12, Docker qualification (**7m56s**) y todos los workflows exact-head post-merge. No se han cualificado endpoints SMTP/HTTPS reales.

El PR [#417](https://github.com/SauronShepherd/ronin/pull/417) termina un proceso real del `SchedulerDaemon` después de que su Job quede confirmado en PostgreSQL y antes de responder a la llamada dispatch. La instancia reiniciada recupera generación 2, reproduce la intención idempotente y verifica un Job/intent únicos. El módulo PostgreSQL más los tests del daemon pasó localmente en Docker/PostgreSQL 16 (**30 tests**); el candidato pasó CI 3.11/3.12 y Docker qualification (**8m03s**). El merge es `main@c2329b0e46c9a67636f20a5c70c8ba87f65af0ca`; todos los checks post-merge exact-head (CI, Docker, Web, Security, Release y Status consistency) están verdes.

El PR [#418](https://github.com/SauronShepherd/ronin/pull/418) continúa el caso de crash hasta completar el Job persistido desde un worker y reconciliar task/workflow a `succeeded` en el siguiente ciclo del daemon. El módulo PostgreSQL más los tests del daemon pasó localmente con Docker/PostgreSQL 16 (**30 tests**); CI 3.11/3.12 y Docker qualification (**8m13s**) pasaron en el PR. El merge es `main@90bbeb3ed1dd95ff3091a324408895a8836340c1`; CI, Docker, Web, Security, Release y Status consistency exact-head post-merge están verdes.

El PR [#419](https://github.com/SauronShepherd/ronin/pull/419) añadió ejecución de notebook en contenedores Docker reales con Jobs/checkpoints/eventos persistidos en PostgreSQL. La qualification usa una base PostgreSQL dedicada y verifica cinco celdas, estado terminal, checkpoints, evento único y resultados. El módulo worker real pasó localmente (**3 tests**, 67.83s); CI 3.11/3.12 y Docker qualification (**8m11s**) pasaron. El squash es `main@f067affb09d5db74013e66544d16fc2f1423c90a`; todos los checks exact-head post-merge están verdes.

El PR [#420](https://github.com/SauronShepherd/ronin/pull/420) añadió la terminación forzada de un worker PostgreSQL real tras tres checkpoints, espera del lease de 30 segundos y recuperación en proceso sustituto. Reutilizó las tres celdas y ejecutó las dos restantes; Job y evento terminal quedaron persistidos sin duplicados. Los cuatro tests de `tests/integration/test_worker_runtime_real.py` pasaron localmente en Docker/PostgreSQL 16 (**4/4**, 102.57s); CI 3.11/3.12, Docker qualification y los seis workflows exact-head post-merge también pasaron. PR [#421](https://github.com/SauronShepherd/ronin/pull/421) luego integró el journey completo daemon→worker Docker→reconciliación, cuyos checks PR también pasaron. No se cualifican proveedores externos ni operator general/HA; P5 continúa parcial y release-qualified en **0% (0/14)**.


## Current diagnostic validation — 2026-10-30

On dirty branch 20261029 at base f9a0456ab7df3e2bb77247d54b4336fca64903b0, the Windows/Python 3.13/PostgreSQL 16.4 full suite passed **4,404 passed, 24 skipped, 0 failed** (4,428 JUnit cases). The later Linux/Python 3.11.18/PostgreSQL 16.4 full suite passed **4,412 passed, 16 skipped, 0 failed** (4,428 JUnit cases); details and evidence are in §18 of the build plan. Docker qualification passed (**23/23**) and strict v0.1 acceptance passed (**15/15**).

These are diagnostic worktree results, not clean-candidate evidence. The release ledger remains **0/13 families qualified (0%) — NO-GO**. Version 0.0.0, human license/NOTICE and claim approvals, complete family journeys on one clean SHA, and manual visual review remain open. No CI, integrated GenAI, or Public multi-user support was added.

The license qualification gate exposed 21 packages without a current human review and one stale `pyyaml==6.0.3` entry. Its CLI now prints the exact missing/stale keys without a traceback; 103 focused tests plus Ruff, format, and mypy passed. The gate remains failed pending human license/NOTICE decisions.

The first full Python/PostgreSQL rerun after that harness change passed **4,353 tests, 24 skipped, 1 failed**: a Hypothesis slow-generation health check. A second rerun exposed the same non-deterministic health check in another bounded property. Both properties now keep 100 examples; the first bounds generated text to 32 characters while retaining Unicode, and the second suppresses only `HealthCheck.too_slow`. The timed-out quality sandbox test removes pytest-cov hooks from its intentionally terminated multiprocessing child.

The earlier pre-binder rerun recorded in section 16 passed **4,354 tests, 24 skipped, 0 failed** in 807.37 seconds against PostgreSQL 16.4. Its 4,378 JUnit cases match the pytest summary; no coverage warning or secondary .coverage.* file remained, and the temporary PostgreSQL container was removed. The later rerun after the container SBOM boundary tests is recorded in section 17. Evidence remains diagnostic for a dirty worktree, not a clean release candidate. Public v1 remains **NO-GO, 0/13 families qualified** while version, human license/NOTICE and claims decisions, complete candidate-bound journeys, and manual visual review remain open.

Version review: `PUBLIC_V1_SCOPE.md` explicitly calls the existing `0.1.0a*` line an engineering alpha/foundation milestone and does not select the final package version. Do not treat `0.1.0` or `1.0.0` as approved by inference; `ronin-studio 0.0.0` and `pyronin 0.0.1a0` remain diagnostic metadata until the product version is decided.

Supply-chain follow-up: `tools/bind_container_sbom.py` now binds Trivy CycloneDX 1.7 package inventories to exact runtime/probe image TARs and artifact identity; `tools/supply_chain_evidence.py --require-container-inventory` rechecks each full inventory and requires both images. The 123 focused supply-chain tests pass, and the binder has **100% line and branch coverage**. A diagnostic integration using actual Trivy 0.76.1 runtime/probe TARs passed. The final Windows/Python 3.13/PostgreSQL 16.4 rerun passed **4,404 tests, skipped 24, failed 0** (4,428 JUnit cases) in 659.30 seconds; `tests/perf` passed **3/3**. The later Linux/Python 3.11.18/PostgreSQL 16.4 rerun passed **4,412 tests, skipped 16, failed 0** (4,428 JUnit cases) in 730.15 seconds; its separate `tests/perf` run passed **3/3**. The Linux result is recorded in §18 of PLAN_FINAL_RONIN_RELEASE_2026-11-03.md. The 15-module `coverage-release-gates` report passed its 90% floor (95% total). No `CoverageWarning` or secondary `.coverage.*` file remained, and the ephemeral PostgreSQL container was removed. Both runs are dirty-worktree diagnostics, not a release candidate. Release remains **NO-GO, 0/13**; ten clean iterations, clean-candidate qualification, visual review, and human decisions remain open.

## Latest full Python and web rerun — 2026-10-30

After the Quality gate and ML registration fixes, the full Windows/Python 3.13.15 suite with isolated PostgreSQL 16.4 completed with **4,406 passed, 24 skipped, and 0 failed** (4,430 JUnit cases). The complete static Playwright suite reported **100 passed and 31 skipped**; those cases require API-backed live services. The separate Docker-backed Ronin live matrix passed **31/31**, exercised **130 real API calls** with no 5xx responses, and recorded 1,415 INFO, 8 expected WARNING, and 0 ERROR server events. The ML live journey completed training and durable model registration successfully; the full focused ML suite passed 67/67.

Evidence is diagnostic on dirty branch `20261029` at `f9a0456ab7df3e2bb77247d54b4336fca64903b0`, not a clean release candidate. Cold synchronous ML search took 73 seconds and remains an open P8 performance issue. Skips are not counted as passes. Release remains **NO-GO, 0/13**; clean-candidate gates, the full family journeys, manual visual review, and human version/license/NOTICE/claims decisions remain outstanding. No CI, integrated GenAI, or Public multi-user capability was added.

## Latest diagnostic rerun after ML operator evaluation — 2026-10-30

The live ML lifecycle now records an explicit operator evaluation (`passed`,
`failed`, or `unknown`) against the immutable source-run dataset and metrics.
Promotion is blocked until an evaluation is `passed`; cards expose the bounded
review history, and SQLite/PostgreSQL enforce idempotent writes and a 100-review
limit. OpenAPI and its digest were updated.

Windows/Python 3.13.15 with PostgreSQL 16.4: **4,408 passed, 24 skipped, 0
failed**; `tests/perf`: **3/3**. Static Playwright: **101 passed, 31 skipped**.
Docker worker/acceptance: **23/23**, strict acceptance **15/15**. The final real
API/Chromium matrix: **31/31**, all **25 active routes**, **143 API calls**, 0
5xx/network errors, 0 unexpected authorization gaps; expected WARN responses
were 1×400, 5×401, 1×403 and 2×409. Detailed transcripts and artifact paths are
in §24 of `PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`.

The latest ML search still takes about **78 seconds** cold; P8 remains open. All
results are dirty-worktree diagnostics at `f9a0456ab7df3e2bb77247d54b4336fca64903b0`.
Release remains **NO-GO, 0/13 families release-qualified** pending a clean
candidate and complete journeys, human version/license/NOTICE/claims decisions,
manual visual approval, and supported-platform runs. No CI, integrated GenAI,
or Public multi-user support was added.

## Full diagnostic rerun — 2026-10-30

The dirty-worktree Python/PostgreSQL suite passed **4,408**, skipped **24**,
failed **0** (4,432 JUnit cases); `tests/perf` passed **3/3**. Docker worker
qualification passed **23/23**, with strict v0.1 acceptance **15/15**. Static
Playwright passed **101** and skipped **31** live-only cases. A separate live
Chromium/API run passed **31/31**, covered **25/25** routes and made **146 real
API calls** with no 5xx, network errors, or unexpected authorization gaps.
Server logs contained **1,430 INFO/OK**, **9 expected WARN**, **0 ERROR**. All
temporary Docker services were removed. Evidence is under the three
`%TEMP%\ronin-*-full-continuation-20261030` directories referenced in section
26 of the build plan.

ML search remains a P8 performance blocker: the live run completed, but its
38.33-second cold search spent 38.23 seconds in the first trial. Release remains
**NO-GO, 0/13 qualified**; human version/license/NOTICE/claims and visual
approvals, clean-candidate journeys, platform qualification, and ten clean
iterations remain open.

## Follow-up — 2026-10-30

The isolated live ML search completed **1/1** with 36 real API calls. Safe phase
timing shows a **37.38 s** cold search, almost entirely in its first trial; P8
remains open. The live runner now compiles third-party bytecode during setup,
but this did not establish an acceptable search time. The Studio budget was
reviewed for the added SQL explain and ML evaluation-review interactions and
ratcheted to the measured **1,943,645 bytes**; asset/module counts are unchanged.
The size gate and 60-file Studio web audit pass. Focused ML and qualification
contract modules pass **45/45** sequentially; an earlier concurrent run had one
30-second test timeout, which passed in isolation and on the sequential rerun.

These results remain dirty-worktree diagnostics. Public v1 remains **NO-GO,
0/13 release-qualified** pending P8, clean-candidate family journeys, human
release decisions, and manual visual review. Ten clean iterations are not
complete.

## Empaquetado reproducible — 2026-10-31

Dos compilaciones del mismo árbol diagnóstico, con `SOURCE_DATE_EPOCH` fijado,
produjeron wheel y sdist byte a byte idénticos. SHA-256: wheel
`0230ed664aa32e89902d2a581993be840b96e9eeb775f94664b7cda6bb10ef4e` y sdist
`8dec5b0785c53429f95f4acb8b942e32d329a44d932fa883bb88f4d5653b2b04`. Evidencia
en `%TEMP%\ronin-artifacts-repro-20261031`; los artefactos son `0.0.0` y no
califican como release. El plan §27 registra el alcance de este resultado.

El estado sigue **NO-GO, 0/13 (0%)**: P8, decisiones humanas de versión,
licencias/NOTICE y claims, revisión visual manual, candidate SHA limpio,
qualification completa por familia y matriz de plataformas están pendientes.

