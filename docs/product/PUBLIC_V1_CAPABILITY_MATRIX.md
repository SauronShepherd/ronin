# Ronin Public v1 capability matrix

## Current exact-SHA snapshot — 18 November 2026

D100 is bound to clean candidate e6f635dfe9159351711f44af9199e573e6e8a5bb.
The production implementation boundary is the same SHA because the bridge
replay-idempotency fix is production behavior. The full live route passes
42/43 with 0 failures and 1 deliberate multi-broker skip; the separate RF3
companion passes 1/1. The worker image was built from the candidate at digest
sha256:2a725e756e3d9dd1dfc5ff7b724b3f88c9ea10176fa6eebc9e748cf9004fd0d8.
The route audit covers 25 active routes (24 API-backed and 1 UI-only) and
439/439 correlated API events. The full runner's non-zero status is its strict
policy for the deliberate skip, not a failed case.
D93 extends the bounded single-broker backpressure journey to `65,536`
records with segmented `8,192`-record resume requests: `1/1` passed,
`19/19` correlated `OK` API events, lag-zero drain, idle replay, reset and
two stable `7`-record replays. The timeout is explicitly bounded at `1,800 s`
total and `600 s` per request; this is not indefinite operation.
D89 refreshes exact-candidate wheel/sdist identity, runtime/probe TARs,
application SBOM, two distinct container inventories, local provenance and
strict supply-chain evidence. Trivy `0.76.1` `vuln,secret` scans report `0`
vulnerabilities and `0` secrets for both images; the technical evidence is
not human VEX/license/security acceptance.
D90 refreshes the route-wide live audit on the same candidate with PostgreSQL,
Redpanda, the Ronin API and a real worker: `25` active routes (`24` API-backed
and `1` UI-only), `39/40` browser cases passed, `1` explicit multi-broker skip,
and `379/379` correlated API events. D91 supplies the required focused
three-broker RF3 failover with the same candidate and worker available: `1/1`
passed, `0` skips, and `5/5` correlated `OK` API events. The route-wide default
skip remains explicit and is not converted into a PASS.
D92 extends the exact-candidate bounded single-broker backpressure journey to
`32,768` records: `1/1` passed, `12/12` correlated `OK` API events, zero
unexpected errors and cleanup. It is a filtered streaming-only cell with an
explicit `600 s` request timeout, not indefinite operation.
D88 revalidates the exact-candidate Helm/kind deployment: Helm 4.3.1 passes
lint, four-resource render with the token confined to the Secret,
install/readiness, health/UI/jobs API, queued-job persistence after restart,
revision-2 upgrade, revision-1 rollback and cleanup. D87 binds the same
candidate to Docker `27/27` and strict v0.1 `15/15` on image
`sha256:c8f2d52af735703ace9bcf10a9d928cf086e5b1b907ad7d8f0703c8fcbfbf2d9`.
D86 revalidates three-broker RF3 failover (`1/1`, `5/5` correlated `OK` API
events); D85 revalidates bounded single-broker backpressure at `16,384`
records (`1/1`, `12/12` correlated `OK` events); D84 revalidates Docker/worker
`27/27` with strict acceptance `15/15`; and D83 revalidates the full
Python/PostgreSQL suite at `4,753/4,784`, with `31` explicit skips and `0`
failures. The new candidate boundary contains `1,599` files and
`16,765,557` bytes.

These are finite exact-SHA cells. They improve P11 evidence but do not
qualify indefinite operation, production topology, provider breadth, the
complete family journey or human release decisions. The ledger remains
`1/13` families, `0/10` gates and **NO-GO**.

## Prior exact-candidate snapshot — 17 November 2026

The following D82–D38 entries are retained for traceability and remain bound
to their stated prior candidates; they are not current-SHA evidence unless
the entry says so explicitly.

D82 revalidates current exact-candidate bounded three-broker failover:
replication factor `3`, journey `1/1`, and `5/5` correlated `OK` API events
with cleanup. PostgreSQL, worker execution and route-wide audit are outside
this filtered cell, so it does not qualify indefinite operation or the full
P11 family.
D81 adds current exact-candidate bounded single-broker backpressure evidence:
`16,384` records pass in `1/1`, with `12/12` correlated `OK` API events,
request timeout `300 s`, no unexpected errors and cleanup. PostgreSQL, worker,
multi-broker and route-wide audit are outside this filtered cell, so it does
not qualify indefinite operation or the complete P11 family.
D80 refreshes the exact-candidate Docker-to-Helm/kind chain: Docker passes
`27/27` with strict v0.1 `15/15`; Helm 4.3.1 passes lint, the four-resource
Secret boundary, install/readiness, health/UI/jobs API, queued-job persistence
after restart, revision-2 upgrade, revision-1 rollback and cleanup. The image
is removed by immutable ID after the hand-off. This is finite deployment and
worker evidence, not complete P11/P14 qualification or indefinite operation.
D79 revalidates the exact-candidate Docker/worker and strict v0.1 cell:
`27/27` tests pass with `0` skips and `0` failures, strict acceptance is
`15/15`, the digest-bound image is cleaned up, and PostgreSQL, Floci/S3,
Azurite/Azure Blob, recovery and appliance backup/restore all pass in the
stated finite scope. This supports P11 worker/journey evidence but does not
qualify the complete family or indefinite operation.
D78 revalidates the full non-performance Python/PostgreSQL suite on this
candidate: `4,753/4,784` pass, `31` explicit cases skip and `0` fail, with
successful isolated PostgreSQL cleanup and `13` ResourceWarning entries
retained for follow-up. The cell does not cover the opt-in Docker worker,
multi-broker, external provider/collector/CLI, symlink or indefinite-operation
lanes.
D77 refreshes current-SHA wheel/sdist identity, runtime/probe TARs, a `110`-
component CycloneDX application SBOM, two bound Trivy container inventories
and local in-toto/SLSA provenance. Strict supply-chain validation passes, and
current runtime/probe Trivy scans report `0` vulnerabilities and `0` secrets
each. D76 fixes the live qualification route audit and records a bounded
exact-candidate route-wide cell: `25` active routes (`24` API-backed,
`1` UI-only), `376/376` correlated events and `0` unexpected server errors;
its default fixture remains closed by one explicit multi-broker skip. The
separate three-broker diagnostic passes `1/1` with `5/5` correlated `OK`
events. D74 adds the candidate boundary, wheel/sdist identity and local
provenance; D73 adds exact-candidate source security evidence: Gitleaks and pip-audit are clean,
Trivy filesystem and worker-image scans report `0` vulnerabilities and `0`
secrets, and `193` supply-chain/release/security contracts pass. D72 adds an
exact-candidate Docker worker/Notebook cell: Docker `27/27`, strict
v0.1 `15/15`, and live Notebook `1/1` with `18/18` correlated `OK` API events.
The worker uses a digest-pinned image with real PostgreSQL and Redpanda. D71
adds an exact-candidate live three-broker failover slice: `1/1` with
replication factor `3`, `5/5` correlated `OK` API events and cleanup. The
bounded case excludes PostgreSQL and worker execution and does not qualify the
full P11 family. D70 adds an exact-candidate live single-broker sustained-backpressure slice:
`1/1` at `16,384` records with `12/12` correlated `OK` API events and cleanup.
The bounded case uses `RequestTimeoutSeconds=300` and does not qualify the full
P11 family. D69 adds a full exact-candidate Python/PostgreSQL revalidation:
`4,753/4,784`
with `31` explicit skips and `0` failures, isolated PostgreSQL cleanup and
`13` ResourceWarnings retained for follow-up. D68 remains linked for the
corrected exact-candidate Docker→Helm chain: `27/27` Docker tests,
strict v0.1 acceptance `15/15`, and all Helm/kind install, API, queued-job
restart-persistence, upgrade, rollback and cleanup phases pass. The harness
contract selection is `25/25`.
D67 adds a `87/87` local streaming/worker regression and a live single-broker
backpressure journey over `16,384` records. The case passes `1/1`, preserves
the durable cap/resume/reset/replay assertions and correlates `12/12` API
events, all `OK`, with cleanup succeeded. The same candidate's full
Python/PostgreSQL regression passes `4,753/4,784` with `31` explicit skips and
`0` failures. The run is bounded and uses an explicit
`RequestTimeoutSeconds=300`; it does not qualify P11 or close any release gate.
D66 remains the source of the separate real worker Notebook,
three-broker failover and clean security scans.
D38 adds candidate-bound P11 broker-restart recovery and a probe Alpine lock
refresh after the preceding image showed 11 MEDIUM findings with available
fixed versions. The exact candidate sandbox passes 95 streaming/API tests and
24 Docker contract tests with zero failures/skips. Real Redpanda/Kafka and
Ronin APIs execute 2/2 streaming cases, 52/52 API events are correlated, the
injected outage returns expected 503 responses, and four records resume from
the durable checkpoint to zero lag with cleanup. Artifact qualification passes
92/92, Gitleaks/pip-audit are clean, Trivy reports 0 vulnerabilities and 0
secrets in runtime/probe, and fail-closed SBOM/provenance validation passes.
Candidate browser archive execution is **SKIP** because `@playwright/test` is
not packaged. The license gate remains closed on 21 human decisions. D37's
previous exact candidate still supplies the separate P14 Compose/Helm evidence;
P14 remains partial/in progress
because external object-store recovery, supported-platform coverage and
production qualification remain open.
D39 then binds an unfiltered real-service journey to the clean documentation
candidate: PostgreSQL, Redpanda/Kafka, Ronin API and the D38 worker execute
`34/34` live cases, audit `25` active routes (`24` API-backed and `1` UI-only),
and correlate `296/296` API events (`279` OK, `17` expected WARN) with cleanup.
This is finite route/API/worker evidence; D39 does not claim a sustained
supervisor/backpressure soak or rerun D38's full Python, scan or license lanes.
The complete candidate suite is recorded as **FAIL** (`4685` passed, `81`
skipped, `8` failed) because the archive has no `.git` metadata for six worker
source-binding cases and two Git-backed status/surface checks; these failures
are not counted as PASS or SKIP.

The exact-candidate streaming selection passes `95` tests. The unfiltered
live Chromium/API/worker result passes `34/34`; checkout
Ruff, mypy, architecture/negative gates, route consistency, dependency
surfaces, OpenAPI, Studio, daily-progress, public-status and diff checks pass.
Gitleaks reports zero findings and pip-audit reports no known vulnerabilities.
Candidate browser archive evidence is **SKIP** because `@playwright/test` is
not packaged; the live Chromium result is from the clean exact-SHA checkout.
P10
remains partial and the release ledger is **1/13 families qualified, 0/10
gates, NO-GO**.

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

**Observed source baseline:** `633980dd3b08affcc604dc918c1a6cbf026cc408` (current exact candidate; the implementation code baseline remains `0a0cd36d47e403808db519f62eefd726f95637a4`, this is not a release qualification claim, and the required human/provider gates remain open).

The D67 scaled backpressure slice passes `1/1` with a real local
single-broker Redpanda fixture and `12/12` correlated `OK` events. The D66
worker-backed Notebook Studio slice passes `1/1` with a real local
Docker worker and `16/16` correlated events. Its exact three-broker failover
slice passes `1/1` with `5/5` events. The full unfiltered run is intentionally
`NOT_COUNTED` because the default single-broker fixture skips the multi-broker
case; no skip is converted into PASS. The candidate receipt also records
clean Gitleaks, pip-audit and Trivy filesystem/image scans. P11 remains
partial: indefinite supervisor operation, production topology, external
provider breadth, complete operator evidence and the full family journey remain
open.

The D21 scheduler slice adds exact-candidate evidence for the bounded local
API/SQLite/daemon journey and fail-closed identity input boundaries at
`f667460650525a5d8a155cad1be5dcff2fc3fd14`. The D22 catalog slice at
`91a2d5efec61bd1776a302027eda2d6e00aeecd3` adds exact local workspace-scoped
catalog/revision, search, lineage, persistence and authorization evidence and
fixes the advertised GET revision route mismatch. It does not demonstrate an
independent project-level filter or authorization claim, PostgreSQL, a Docker
worker or an external provider; P5 and P6 remain partial and the release
ledger remains 1/13 families, 0/10 gates and **NO-GO**.

The D23 ontology/graph slice at `94911d26dcf90051fdfa7049d7ef4dd67a654272`
adds exact local workspace-scoped ontology, RQL, graph-neighbor, restart and
scheduler-scope evidence. It does not mount graph actions, demonstrate an
independent project-level catalog filter/authorization claim, PostgreSQL, a
Docker worker or an external provider; P5 and P6 remain partial and the
release ledger remains 1/13 families, 0/10 gates and **NO-GO**.

The D24 integration slice at `870484a5b749b14a443d2bbf062c3ec10183ab31`
adds real local HTTP coverage through the SDK and CLI, Graph Studio workspace
context and ontology-schema reads, bounded negative paths and restart recovery.
It does not mount graph actions or add an independent project-level catalog
filter/authorization claim, and it does not certify PostgreSQL, Docker or an
external provider; P6 remains partial and the release ledger remains 1/13
families, 0/10 gates and **NO-GO**.

The D25 quality slice at `2da767235dd633159e8e13dda73723bdef052cba` adds a
real local SQLite/HTTP contract/check/result/report journey through PyRonin and
the public CLI, including digest pinning, threshold failure without a false
pass, malformed-row rejection, workspace denial and restart recovery. Quality
Studio now inherits the active workspace context. PostgreSQL/custom-rule
providers, external alerts, complete catalog/lineage quality integration and
candidate browser evidence remain open; P7 is `in_progress`, not qualified,
and the release ledger remains 1/13 families, 0/10 gates and **NO-GO**.

The D26 quality slice at `9ca22d7b24e622203484d58707ec550b4c6cf9a4` adds
real local alert rules/instances/evaluation/acknowledgement through the
SQLite/HTTP composition and bounded quality summaries to catalog assets and
lineage edges. Catalog Studio renders the resulting quality state; failed-run
alert state and acknowledgement survive restart, and replay is deterministic.
The candidate browser is `SKIP` because the exact archive does not contain
`@playwright/test`; the checkout Catalog + Quality Studio contract passed 9/9.
PostgreSQL/custom-rule providers, external alert delivery, broader provider and
consumer qualification and complete P7 qualification remain open; the ledger
remains 1/13 families, 0/10 gates and **NO-GO**.

The D27 ML slice at `f685a54b7b5f39cef3a9998480e2bc4dedd235b3` adds a real
local HTTP/SQLite journey through Lab creation, quality, durable `local.sklearn`
training, artifact registration after digest verification, model-card/artifact
retrieval, prediction, workspace denial and restart recovery. The candidate
journey is 1/1, the composed local suite is 26/26, ML unit tests are 298/298
and ML HTTP integration is 3/3. Candidate browser evidence is `SKIP` because
the exact archive lacks `@playwright/test`; checkout Catalog + Quality Studio
passes 9/9. PostgreSQL/S3/MLflow/serving providers, broader algorithm/search
performance and complete P8 qualification remain open; the ledger remains
1/13 families, 0/10 gates and **NO-GO**. See
`docs/qualification/candidates/candidate-f685a54b-d27.json`.

The D28 ML lifecycle slice at
`360ce3092afcf485c113ccfb781069914abc3ee0` adds the real local
HTTP/SQLite path from evaluation-gated promotion through digest-pinned serving,
health/telemetry, numeric drift reporting, rollback, post-rollback rejection,
workspace denial and restart recovery. The journey is 1/1, the composed local
suite is 27/27, ML unit tests are 298/298 and ML HTTP integration is 3/3.
Candidate browser evidence remains `SKIP` because the exact archive lacks
`@playwright/test`; checkout ML Studio passes 9/9. PostgreSQL/S3/MLflow/
external serving providers, broader algorithm/search performance and complete
P8 qualification remain open; the ledger remains 1/13 families, 0/10 gates
and **NO-GO**. See
`docs/qualification/candidates/candidate-360ce309-d28.json`.

The D29 semantic lifecycle slice at
`567ee82eafd30661c5e6c10ea5fe26f3eaad6dce` adds the real local
HTTP/SQLite/DuckDB/Parquet path from persisted semantic model/query through
dashboard execution, tile-budget rejection, semantic Bundle digest/plan/import,
workspace denial and restart recovery. The journey is 1/1, the composed local
suite is 28/28, selected semantic unit/HTTP tests are 36/36, ML unit tests are
298/298 and ML HTTP integration is 3/3. Candidate browser evidence remains
`SKIP` because the exact archive lacks `@playwright/test`; checkout Semantic
Studio passes 6/6. PostgreSQL semantic persistence/import, external
warehouse/provider compatibility, dashboard cancellation/fan-out evidence and
complete P10 qualification remain open; the ledger remains 1/13 families,
0/10 gates and **NO-GO**. See
`docs/qualification/candidates/candidate-567ee82e-d29.json`.

The D30 semantic dashboard slice at
`0c31232eaec42d2f26f8fbc466bd52d2898d09a5` fixes the public dashboard PUT
replacement path by separating it from create/idempotent conflict semantics.
The real local HTTP/SQLite/DuckDB/Parquet journey replaces a dashboard, returns
the independent filtered `ES=5` result, rejects an empty filter with HTTP 400
and recovers after restart. The journey is 1/1 and the composed local suite is
29/29; selected semantic unit/HTTP tests are 36/36, ML unit tests 298/298 and
ML HTTP integration 3/3. Candidate browser evidence remains `SKIP` because the
exact archive lacks `@playwright/test`; checkout Semantic Studio passes 6/6.
PostgreSQL semantic persistence/import, external warehouse/provider
compatibility, dashboard cancellation/fan-out evidence and complete P10
qualification remain open; the ledger remains 1/13 families, 0/10 gates and
**NO-GO**. See
`docs/qualification/candidates/candidate-0c31232e-d30.json`.

The D31 streaming slice at
`902ddc9acea2d8806ba7fab3538ec900a8effc37` adds current real-provider
evidence without changing product code. Redpanda/Kafka, the Ronin API and
Chromium ran in an isolated streaming-only profile and passed `1/1`, with
`38/38` API events correlated to structured logs, `34` `OK`, `4` expected
`WARN`, zero server/network errors and cleanup. The checkout Streaming Studio
contract separately passes `3/3`; the exact candidate streaming selection
passes `44` tests; its archive browser remains `SKIP` because
`@playwright/test` is absent. PostgreSQL, worker, continuous operation,
broader partition/backpressure/failure recovery and full P11 qualification
remain open; P11 is `in_progress` and the ledger remains 1/13 families, 0/10
gates and **NO-GO**. See
`docs/qualification/candidates/candidate-902ddc9a-d31.json`.

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
| P7 Data quality and contracts | Partial | Partial | No | A real bounded local contract/check/result/report journey now covers digest pinning, threshold failure, malformed data, CLI state/history, alert evaluation/acknowledgement, bounded catalog/lineage quality state and SQLite restart recovery; PostgreSQL/custom-rule providers, external alert delivery and full provider/consumer qualification remain incomplete. | Optional SQL/Python execution runtimes; SMTP/HTTPS delivery. | Local/Compose reference profile. |
| P8 Machine learning and MLOps | Partial | Partial | No | Scheduled runs and async JobStore requests pin canonical pipeline and Lab digests, and scheduled execution now passes that exact PipelineIR to its runner. Main resolves Lab AssetRefs to workspace-scoped, digest-verified CSV/JSONL snapshots; durable inputs above 1 MiB use ArtifactStore. The v2 local runner supports bounded prepare branches and algorithm×preprocessor candidate grids, with deterministic topological execution and checkpoint recovery. Final tabular and K-Means models are materialized as verified content-addressed ArtifactStore objects. Main registers successful durable executions as candidate models through Studio after artifact identity revalidation, provides workspace-scoped artifact retrieval and bounded UI download, and allows direct promotion with the existing reason gate. PR #450 qualifies S3-compatible artifact writes, reads, digest checks and safe stale-object deletion against LocalStack in CI; vendor production qualification is still open. Atomic, exact-replay ML Registry Bundle imports are available in SQLite and PostgreSQL on main; PR #528 required exact-head qualification passed. P8 remains partial because broader ML and provider qualification gaps remain. Arbitrary built-in DAG shapes and plugin-defined stages, broader feature/algorithm coverage, MLflow/network serving and production qualification remain incomplete. PR #509 added the terminal registration stage and passed all six exact-head workflows on `156d607`. | Numerical Python stack; MLflow or serving provider for interoperability paths. | Local deterministic training/inference; Compose reference profile. |
| P9 GenAI, RAG and in-product agents | Out of scope | N/A | N/A | No Ronin tier ships model/provider invocation, RAG, or agent execution. Coding-agent skills are consumed by external agents and remain separate from Ronin's runtime, API, and Studio. | None. | Not applicable. |
| P10 Semantic models and dashboards | Partial | Partial | No | Export/import and production qualification remain incomplete; broader planning is bounded. | DuckDB/SQL engine for execution; browser runtime for Studio. | Local SQLite/DuckDB; Compose reference profile. |
| P11 Streaming and real time | Partial | Partial | No | D100 binds production replay idempotency and exact current-candidate live evidence to **e6f635df**: the deterministic stream.record bridge reuses the first persisted received_at when stable content matches and preserves conflict rejection; local runtime passes **14/14** and the combined contract/runtime/bridge selection passes **40/40**. The full live route with PostgreSQL fixture, Redpanda, Ronin API and exact Docker worker passes **42/43** with 0 failures and 1 deliberate multi-broker skip; the separate RF3 companion passes **1/1**, and **439/439** API events correlate. The full live server uses SQLite storage, so this is not PostgreSQL scheduler/runtime qualification. D99, D98, D97, D96, D95, D94 and D93 remain bound to their own candidates. Continuous indefinite operation, production topology, provider breadth, external object-store recovery, scheduler restart recovery, complete operator evidence, complete family qualification and human release decisions remain open. | Kafka broker/client runtime; Docker worker for the bounded notebook journey; PostgreSQL fixture for live ingestion. | Local bounded polling tests; digest-pinned Redpanda profile and Compose. |
| P12 Observability, alerts and FinOps | Partial | Partial | No | D35 adds authenticated CLI parity for usage, costs and budgets; the exact candidate records 222 compatibility/P12 tests, 3/3 local-composed/HTTP journeys, 3/3 isolated PyRonin alert/FinOps SDK tests and a real digest-pinned OTLP Collector lane (1/1, no skips/failures, cleanup). D34's slotted-record and legacy payload compatibility remains covered. External Prometheus deployment, SMTP/HTTPS notification providers, PostgreSQL telemetry/FinOps, public allocation/forecast/policy routes, broader service adoption, candidate browser packaging and production qualification remain incomplete. | Prometheus scrape target; SMTP/HTTPS notification endpoint; PostgreSQL for provider-backed durability. | Local SQLite; Compose reference profile. |
| P13 Security and audit (single-operator) | Partial | Partial | No | Exact candidate C2 adds digest/denormalized-column verification for SQLite and PostgreSQL, a bounded authorized audit route, real PostgreSQL/Docker recovery evidence, and clean-candidate Gitleaks, pip-audit and Trivy scans. External secret-provider qualification and release evidence remain incomplete. OIDC, user/group administration and multi-user authorization belong to Ronin Pro. | Local bearer/auth profile; external secret backend for Ronin Pro. | Local single-operator; single-host Compose/PostgreSQL reference. |
| P14 Deployment and operations | Partial | Partial | No | D37 binds the exact candidate to 69 P14 contracts, 27/27 real Docker tests, strict v0.1 acceptance 15/15, a real PostgreSQL + `/var/lib/ronin` appliance restore, and Helm/kind install/readiness, revision-2 upgrade, rollback to revision 1, health/API, queued-job persistence after restart and cleanup. The authorized Floci/Terraform 1.13.5 provider lane reaches plan/validate but apply times out at 120s and 300s; destroy/state cleanup leave zero resources, so external object-store recovery remains blocked. Supported-platform coverage and full release aggregation remain incomplete. Multi-user HA and Kubernetes server profiles belong to Ronin Pro. | Docker; PostgreSQL; local artifacts; external S3 backup is separate. | Local and single-host Docker Compose. |

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

