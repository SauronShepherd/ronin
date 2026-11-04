# Ronin test workflow: fast feedback to release evidence

This guide separates quick feedback from evidence that proves real product
behavior. A fast or filtered run is useful for iteration; it is not a release
qualification. Do not report “everything tested” from a unit test, static page,
filtered suite, or a run with unreviewed skips.

## Quick reference: what was actually tested?

The test suite is split into lanes because a unit test cannot prove that the
real database, container worker, browser/API wiring, logs and deployment all
work together. Use the matching lane and keep its result scoped:

| Question | Run | Evidence it gives |
| --- | --- | --- |
| Did this Python change work locally? | `python -m pytest -q tests/test_<area>.py` | Only the named tests; no real service unless that test starts one. Usually the quickest feedback. |
| Does the changed database path work against PostgreSQL? | `pwsh -NoProfile -File tools/run_postgres_test_suite.ps1 -EvidenceDirectory "$env:TEMP/ronin-pg-focused" -TestPath tests/<module>.py -AllowDirtyWorktree` | Selected tests against isolated PostgreSQL 16.4, including service startup and cleanup. Filtered runs do not provide full coverage. |
| Does the complete Python regression and coverage still pass? | `pwsh -NoProfile -File tools/run_postgres_test_suite.ps1 -EvidenceDirectory "$env:TEMP/ronin-python-full"` | All collected Python tests except `tests/perf`, branch coverage, exact skips and JUnit. This took about 9 minutes on the 2026-11-03 host. |
| Do the product UI, API, real services, messages and logs agree? | `pwsh -NoProfile -File tools/run_live_product_qualification.ps1 -WorkerImage <image>` | Live browser journeys against Ronin and its backing services, with API traffic correlated to structured logs. A static Playwright run does not prove this. |
| Does the real container/deployment work? | `tools/run_docker_qualification.ps1` and `tools/run_helm_qualification.ps1` | Docker worker/provider acceptance and Helm/kind behavior. These are separate lanes with separate receipts. |
| Did Semantic Studio retain tenant isolation and Bundle behavior? | `python -m pytest -q tests/test_semantic_store.py tests/test_semantic_runtime.py tests/integration/test_workspace_project_http_api.py tests/test_openapi_snapshot.py` | SQLite persistence/import, actual HTTP route, authorization and OpenAPI contract; the HTTP module starts a real local server. |
| Did the semantic Browser journey still work? | `npm test --prefix web-tests -- --grep "Semantic Studio"` | Chromium UI interactions and request contracts against the test route; it does not replace live API/service qualification. |

For a change, start with its focused test, then run only the real-service lane
for a boundary it crosses. After an integration batch, run each affected full
family once. A release still needs every required family and manual review on
one clean candidate; do not add the lane counts from different source trees and
call them a release pass. The receipts show selected, passed, skipped, failed,
elapsed time, service versions and cleanup status.

### Fast, reviewable test loop

Use this sequence to avoid paying the setup cost of a full qualification after
every edit while preserving the service boundary that needs proof:

1. **Code-only feedback:** run the exact affected unit module, without Docker.
   This checks logic quickly; it is not integration evidence.
2. **Changed service boundary:** run one explicit test module through its
   service runner (`run_postgres_test_suite.ps1`, the Docker family runner, or
   the specific provider runner). Do not start unrelated services.
3. **Changed UI/API journey:** use the filtered live runner for that journey;
   inspect actual API outcomes and correlated logs, not only browser assertions.
4. **After the change batch settles:** run each affected family once, then the
   required full release gates. Do not rerun unchanged families per edit.

For a measured local-only Python run, capture exact node IDs and timings, then
replay a bounded slowest subset without coverage or services:

```powershell
$env:RONIN_TEST_EXECUTION_MODE = 'local-only-diagnostic'
$env:RONIN_TEST_SERVICE_PROFILE = 'none'
$env:RONIN_TEST_COVERAGE = 'disabled'
$env:RONIN_TEST_SELECTION = 'local-only profiling selection'
$env:RONIN_PYTEST_TIMINGS_PATH = "$env:TEMP/ronin-local-timings/pytest-timings.json"
python -m pytest -p tools.pytest_timing_report -q tests/<unit-module>.py
python -m tools.test_run_summary "$env:RONIN_PYTEST_TIMINGS_PATH"
python -m tools.pytest_slowest_selection `
  "$env:RONIN_PYTEST_TIMINGS_PATH" `
  "$env:TEMP/ronin-local-timings/slowest-nodeids.txt" --count 20 --run
```

The slowest-case replay is a profiling aid only; it deliberately cannot run
service-backed timings outside their family runner and cannot substitute for
coverage or regression qualification. Family runners retain their own setup,
service and cleanup measurements. To inspect those receipts consistently:

```powershell
python -m tools.test_run_summary "$env:TEMP/ronin-pg-focused/pytest-timings.json"
python -m tools.test_run_summary `
  "$env:TEMP/ronin-pg-focused/pytest-timings.json" `
  --junit "$env:TEMP/ronin-pg-focused/pytest-postgres.xml"
python -m tools.test_run_summary "$env:TEMP/ronin-pg-focused/runner-timings.json"
python -m tools.test_run_summary "$env:TEMP/ronin-live-focused/qualification-summary.json"
```

The summary reports scope, selection, real service profile, result counts,
five slowest cases, collection-skip reasons, failed node IDs, phase timings and
cleanup state. Live receipts fail closed if browser totals or API/log
correlation counts disagree. Always open the referenced raw JSON/JUnit and logs
when a count, skip, failure, or cleanup state needs review. When `--junit` is
supplied, it compares the executed/pass/skip/fail totals and returns nonzero if
timing JSON and JUnit disagree. A two-module collection-skip probe confirmed
the current v4 hook records module-level skips; the historical full receipt
above predates that hook despite having a v4 schema marker, and must be
replaced by a fresh full run before relying on its counts.
This makes test scope legible; it does not expand coverage or certify the
release on its own.

For legacy SQLite semantic definitions, first make a database backup and
determine the correct workspace for each old project ID from the operator's
own inventory: the old rows contain no workspace identifier. Then run the
explicit migration once per project:

```powershell
python tools/migrate_semantic_project_scope.py `
  --database .ronin/ronin.sqlite3 `
  --workspace-id default `
  --project-id examples/demo
```

The tool atomically moves models and dashboards, allows exact replays, and
aborts without deleting the legacy rows if the target contains conflicting
definitions. Never infer the destination workspace from a project name alone.

### Recent test-cost optimization — 2026-11-03

The repository inventory now parses each Python source file once; determinism
is checked twice on a small fixture. A current run exposed another hotspot in
marker extraction: it lowercased each complete file once per marker. Caching
the lowercase text per file reduced the same repository-scan case from **48.56
s to 10.90 s (77.5% on this host)** while traversing the same 849 Python files.
The complete `tests/test_plugin_inventory.py` module passed **4/4 in 13.81 s**;
the fixture now asserts case-insensitive marker counts as well as route and
package extraction. This is a measured improvement to one test, not a claim
that the complete 9-minute Python/PostgreSQL suite became 77.5% faster. The
earlier full-suite receipt reported a differently named test and is historical;
its 27.92 s timing is not used as the before measurement here.

A second measured hotspot was repeated source-package resolution for every
test file, although test paths are outside `python/` and cannot belong to a
product package. The inspector now skips that resolution only for files known
to be external test files; product paths still receive the same escape/symlink
checks. On this host, the repository-scan case fell from **46.97 s to 10.10 s**
and the updated inventory module passed **5/5 in 13.29 s**. This is a separate
rerun from the lowercase-text measurement above; timings are load-sensitive,
and the full Python/PostgreSQL suite has not been rerun after this change.

The filtered Streaming live journey was also narrowed to its real dependencies.
Previously, `-TestGrep streaming` started PostgreSQL and Redpanda and seeded the
unrelated graph/catalog/workflow fixtures. It now starts only Redpanda, seeds
only the workspace plus the real Kafka topic/connection/stream, and records
PostgreSQL as not started. On this Windows host, the same positive
health → consume one record → persisted checkpoint journey took 79.08 s with
the old setup and 36.96 s after narrowing it (about **53% less wall time**);
the new run adds a deliberate invalid-limit case and checks its rendered error
message. The final run passed **1/1 Playwright case**, made four real API calls
(3 expected `OK`, 1 expected `WARN`/HTTP 400), correlated all four with
structured request logs, recorded zero server/network errors, and cleaned the
Redpanda container/network. Receipt:
`$env:TEMP/ronin-live-streaming-final-verified-20261103`.

The later definition-editor journey exposed a form field named `id` shadowing
the form's legacy `id` property. The submit handler silently skipped the API
write, and the live test waited for the whole 60 s case timeout. It now reads
the explicit `id` attribute, retains the save receipt after refreshing the
definition list, and has a static Playwright regression for load → edit → save.
The live streaming wait now has populated-field assertions and an explicit 10 s
response deadline. The static regression passed **1/1 in 11.4 s**. The later
live Redpanda + Ronin API journey passed **1/1**, including reset → consume →
save unchanged definition with resume → idle replay → invalid-limit warning.
It exercised 10 real API calls (9 OK, 1 expected WARN/400), correlated all 10
with structured logs and recorded no server/network errors in **43.96 s total**
(13.6 s browser case). Compared with the failing 114.65 s run, this removed the
60 s blind wait and cut total diagnostic time by about 62%. The filtered
receipt still excludes PostgreSQL and does not establish all-route coverage.
Receipt: `$env:TEMP/ronin-live-streaming-reset-resume-final-20261103`.

For the fast UI regression loop:

```powershell
npm test --prefix web-tests -- `
  --grep "Streaming Studio loads, edits, and saves" --workers=1
```

This uses mocked API responses and proves the form-to-request contract only;
follow it with the filtered live command below to prove the real API, broker,
logging and visible success/warning messages.

Focused Streaming Python/API regression loop (isolated run: **41/41 in 14.71 s**;
slowest individual selected case 0.56 s):

```powershell
python -m pytest -q --durations=10 `
  tests/test_streaming_kafka.py `
  tests/test_streaming_runtime.py `
  tests/test_streaming_health.py `
  tests/test_streaming_bundle.py `
  tests/integration/test_workspace_project_http_api.py `
  tests/test_openapi_snapshot.py `
  -k stream
```

That selection passed **41/41, 50 deselected, 0 failures in 14.71 s** when run
alone. A repeat concurrent with the two-case Chromium Streaming Studio suite
passed **41/41 in 16.28 s**; the browser suite passed **2/2 in 18.1 s**. It
covers transport and byte budgets, oversized record/batch rejection, poison
message checkpoint safety, durable sink/checkpoint behavior, idempotent replay,
health projection, Bundle reset/resume, definition read/write permissions,
invalid input, redacted broker failure, and bounded OpenAPI contracts. It does
not require Docker or PostgreSQL. After it passes, exercise the actual
browser/API/broker path:

```powershell
pwsh -NoProfile -File tools/run_live_product_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-live-streaming-<unique>" `
  -TestGrep streaming -AllowDirtyWorktree
```

The Kafka source now applies hard internal bounds of 1 MiB per record and 8 MiB
per micro-batch, caps librdkafka fetch/queue buffering, rejects connection
options that could override those caps, and fails without advancing checkpoints
for oversized or poison records. The first live attempt caught an invalid
librdkafka buffer relationship (HTTP 503); the corrected `receive.message.max.bytes`
is `fetch.max.bytes + 512`. The final live run proved this configuration is
accepted by Redpanda, processed five valid events in batches of **2, 2, 1**
(lag **5 → 3 → 1 → 0**) and returned idle on the next batch. A real poison topic
proved two HTTP 422 rejections, persistent lag of one and no payload leakage.
The journey passed **1/1** with 20 correlated API/log events (17 OK, 3 expected
WARN), zero server/network errors and **88.16 s total** (19.8 s browser case);
PostgreSQL was not started. The byte-boundary cases are unit-tested, not yet
generated against the live broker. This filtered
receipt is diagnostic for a dirty worktree and one route; it is not the
all-route live gate, full Docker qualification, or release qualification.
Expand to the full relevant family after the code batch settles.

### Streaming Bundle API/Studio round-trip — 2026-11-03

The existing Bundle domain service is now wired to authenticated export,
verify/plan and import routes plus the Streaming Studio. The import plan
returns definitions, unresolved binding requests and a SHA-256 digest. The
commit request must contain the same archive/digest, a target for every
binding and an explicit `reset` or `resume` policy for every stream. Ronin
validates the archive again and commits definitions/checkpoint policies
atomically. The archive cap is 700 KiB so Base64 plus request metadata fits
within the shared 1 MiB JSON body budget. The UI verifies the downloaded
archive digest, prevents import until mappings and per-stream policies are
selected, and requires a new preview if the selected file or destination
workspace changes.

The first live attempt found that the Bundle planner incorrectly treated the
last `/` in `events/main` as an ID separator. The validation now retains the
full hierarchical stream ID, with a regression test. Exact feedback commands:

```powershell
python -m pytest -q `
  tests/test_streaming_bundle.py `
  tests/integration/test_workspace_project_http_api.py::test_stream_bundle_api_export_plan_import_reset_and_resume_are_audited `
  tests/integration/test_workspace_project_http_api.py::test_stream_bundle_import_rejects_changed_plan_digest_before_mutation

npm test --prefix web-tests -- --grep "Streaming Studio" --workers=1

pwsh -NoProfile -File tools/run_live_product_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-live-streaming-bundle-<unique>" `
  -TestGrep streaming -AllowDirtyWorktree
```

The latest dirty-tree live receipt passed **1/1 Chromium**, made 27 real API
calls all correlated to structured HTTP logs (24 `OK`, 3 expected `WARN`),
and had no server/network errors. It exported two definitions, planned the
same digest, imported with `reset`, processed a real Redpanda batch, imported
with `resume`, and confirmed lag stayed at 3 before the existing 2/2/1,
idle and poison-message journey. PostgreSQL was not started; Redpanda cleanup
succeeded. Receipt:
`$env:TEMP/ronin-live-streaming-bundle-retry-20261103-201633`.

This closes the Bundle UI journey gap recorded earlier, not P11 as a whole.
Real-broker byte-overload and recovery are covered by a separate diagnostic
below; broader operational evidence and clean-candidate family qualification
remain open.

### Real-broker oversized Kafka record and recovery — 2026-11-03

The filtered Playwright Streaming journey now also creates a Redpanda topic
that accepts a JSON record larger than Ronin's 1 MiB limit. It verifies that
the real API returns a sanitized 422, does not advance the checkpoint (lag
remains one), and does not leak the payload. The operator then explicitly
repoints the stream to a healthy topic, resets the checkpoint, consumes the
recovery event and verifies lag reaches zero. This exercises UI, Ronin API,
Redpanda, durable checkpoint, visible result and correlated logs together.

```powershell
pwsh -NoProfile -File tools/run_live_product_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-live-streaming-overload-<unique>" `
  -TestGrep streaming -AllowDirtyWorktree
```

Latest run passed **1/1 Chromium**, 36/36 API events correlated to structured
logs (32 `OK`, 4 expected `WARN`), zero server/network failures, and cleanup
succeeded in **60.07 s**. PostgreSQL was intentionally not started for this
Kafka-only diagnostic. Receipt:
`$env:TEMP/ronin-live-streaming-overload-final-7b49698233e9452c8954a8c5b1cc1ed8`.
The initial fixture failed before the app started because confluent-kafka
requires topic configuration to be a dictionary; the corrected `{}` config
was then accepted. The first browser assertion also exposed the intentional
generic/redacted API error contract; the test now requires the redacted
message and independently confirms the over-limit record is rejected by
checkpoint/lag behavior. This remains dirty-worktree evidence, not full P11 or
release qualification.

#### Focused regression after Bundle integration

The full directly affected regression set was collected as **99 tests** and
passed **99/99 in 45.71 s** on the dirty worktree. It included the streaming
domain, HTTP project/workspace routes, complete OpenAPI snapshot checks,
static Studio contracts, and architecture positive/negative gates. The slowest
case was the full architecture contract scan at 5.72 s; each of the 99 cases
was below 1.4 s. This is a focused regression, not the full Python suite.

For a faster edit loop while changing the Kafka/stream behavior, keep selection
by feature rather than rerunning every workspace/project HTTP test:

```powershell
python -m pytest -q --durations=10 `
  tests/test_streaming_kafka.py `
  tests/test_streaming_runtime.py `
  tests/test_streaming_health.py `
  tests/test_streaming_bundle.py `
  tests/integration/test_workspace_project_http_api.py `
  tests/test_openapi_snapshot.py `
  -k stream
```

The selection reduces unrelated HTTP integration cases while retaining the
route cases whose names include `stream`; do not treat it as a replacement for
the 99-case regression above after changing shared control-plane or architecture
code. The current checkout also lists **103 non-live Chromium tests** across 17
files; run `npm test -- --list` to inspect exact selection before execution.
Mocked browser cases validate UI request/response behavior; the live Redpanda
receipt above is separate evidence for API persistence, broker effects, and
structured log correlation.

## 0.1 Recommended edit loop and progress reporting

Use this decision rule for each change. It avoids rebuilding or restarting
unrelated infrastructure while making the tested surface and remaining gap
visible in the report:

| Changed surface | First run (fast feedback) | Escalate only when | What to report |
| --- | --- | --- | --- |
| Pure Python function or contract | The directly related unit test file, e.g. `python -m pytest -q tests/test_<area>.py` | Shared package/API contract changed, or change spans multiple modules | Exact files/node IDs, pass/fail/skip counts, elapsed time |
| HTTP handler, SQL, storage adapter | Focused test module; if it needs PostgreSQL, use `run_postgres_test_suite.ps1 -TestPath ... -TestFilter ...` | Schema, transaction, persistence or server composition changed | Service/version, selected vs deselected, result, startup/test/cleanup times |
| Browser UI with no API contract change | Playwright spec(s) for the affected route in the static lane | Route invokes live API, mutates shared data, or has auth/logging behavior | Spec/case counts and explicitly state static/mock or live |
| Browser journey or API response/log semantics | Live qualification with `-TestGrep` for the exact journey | Shared route contracts, auth, common fixtures, or cross-feature wiring changed | Browser cases, API event count, correlated log count, status/outcome totals |
| Dockerfile, entrypoint, worker, runtime dependency, Compose service | Build the changed image and run the narrow Docker diagnostic with `-ImageId <digest> -TestFilter <relevant expression>` | Image/runtime behavior or release candidate changed; then run full Docker gate | Immutable image ID, suites selected, services actually started, acceptance gate omitted/present |
| Helm chart/deployment configuration | Helm structure tests first | Runtime deployment behavior changed; then Helm/kind qualification using the same image digest | Chart assertions or kind phase counts and image ID |
| Cross-cutting or final candidate | Run each complete required family once after changes settle | Any subsequent code change reopens the affected family gate | Complete lane ledger; never infer unrun lanes as green |

### Make progress observable

Before a run, state the exact command/scope and why that layer is sufficient.
During long runs, report the active phase from the runner (environment,
service readiness, test execution, evidence audit, cleanup). Afterward report:
`selected / passed / skipped / failed`, filtered-out count, elapsed time by
phase, evidence directory, and one sentence naming what the run does not prove.
For a suite with multiple subsystems, summarize coverage as a matrix of test
families, real services, browser/API routes, and untested families. A single
percentage is misleading unless its denominator is a finite, versioned list of
required gates; use the release ledger for that denominator.

Do not run the full Python, Docker, and live-browser matrix after every local
edit. A focused pass speeds diagnosis; it must never be described as full
qualification. When a focused run fails, stop widening the suite until its
cause is understood. When it passes, widen only across the boundaries the
change actually crossed. At the end of an integration batch, run the full
families affected by the batch and the release-required matrix once.

## 0. Shortest reliable loop

Use the narrowest scope that still exercises the code you changed, then widen
only when the change crosses a boundary. This avoids paying for Docker startup
and full coverage on every edit while keeping the final proof tied to real
services:

1. **Pure local logic:** run the changed test module directly, or use the
   `-LocalOnly` runner below if you need retained timing/JUnit evidence.
2. **Storage, connector, or server behavior:** use that subsystem's focused
   test selection with its real service runner. A unit test with a mock does
   not prove the live service contract.
3. **Container/runtime or user journey:** run the focused Docker or live
   product qualification. Reuse an immutable image only if the Docker image
   inputs themselves did not change.
4. **Release claim:** run every required family on one clean candidate and
   complete the manual UI, security, packaging, and release review gates.

Each step has an explicit evidence boundary. Green at one step means only that
step passed; it does not promote to the next one. If a run is slow, inspect
`runner-timings.json` first: environment creation, service readiness, pytest,
and cleanup are timed separately so the expensive phase is visible before
changing what gets tested. The harness measures time but has no before/after
benchmark yet; do not claim a speedup until equivalent runs on the same host
and source candidate demonstrate it.

### Fastest safe commands (PowerShell)

Start with local-only tests when the change is pure Python and the selected
module has no real-service fixture. This path does **not** start Docker,
PostgreSQL, or coverage instrumentation. It is a feedback loop, not evidence
for PostgreSQL or release coverage:

```powershell
# One test file; quickest useful regression check
python -m pytest -q tests/test_<area>.py

# Same scope with retained JUnit, per-test timing, and an explicit no-service receipt
pwsh -NoProfile -File tools/run_postgres_test_suite.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-unit-<area>-<unique>" `
  -TestPath tests/test_<area>.py -LocalOnly -AllowDirtyWorktree
```

If pytest reports a slow case, inspect the timings before broadening. The
selector writes exact test node IDs and excludes skipped cases. It can rerun
only a prior **local-only** selection; PostgreSQL/service-backed timing files
are deliberately refused by `--run`:

```powershell
python -m tools.pytest_slowest_selection `
  "$env:TEMP/ronin-unit-<area>-<unique>/pytest-timings.json" `
  "$env:TEMP/ronin-slowest-<area>-<unique>.txt" `
  --count 20 --run --checkout .
```

Escalate only across a boundary the change touches:

1. PostgreSQL behavior: the same runner without `-LocalOnly`, with an exact
   `-TestPath`; this starts isolated PostgreSQL 16.4 and turns coverage off for
   the filtered diagnostic.
2. Docker worker/provider behavior: use the focused Docker runner and a prior
   immutable image digest only if image inputs are unchanged. Rebuild if a
   Dockerfile, lock, entrypoint, or worker runtime input changed.
3. Browser/API/logging behavior: use the live browser runner with a title
   filter; it starts Ronin and the named backing services. Static Playwright is
   for rendering/mocked contracts only.
4. At a settled integration checkpoint, run each affected family once. Run the
   full release matrix only against the frozen clean candidate.

Never use `-k` as the only record of what was run when an exact `-TestPath` or
node ID can be recorded. Keep the evidence directory unique and inspect its
JUnit, timing JSON, service startup/cleanup timings, skips and exact selected
IDs. A smaller test selection is faster because it tests less; it is not an
optimization of an equivalent full suite.

### Measured cost from the 2026-11-03 local diagnostic

These measurements describe the exact diagnostic receipts named in this
section, not the current uncommitted worktree by implication. The reporter and
runner settings may change elapsed time; capture a new receipt before claiming
an optimization. A faster focused selection is not a speedup of the equivalent
full suite.

The feedback-flow update itself was checked on the current dirty worktree:
pytest timing/selection tests passed **14/14 in 2.65 s**; Playwright configuration discovery listed **134 cases in 19 files**;
one static Chromium accessibility smoke passed (**1/1 in 6.3 s**). This proves
the harness loads and the line reporter works on a real browser run. It is not
a full static-browser regression or release qualification, and the single
smoke does not establish a suite-wide speedup.

### Current full-family rerun — 3 November 2026

After the previous evidence snapshot, the full Python/PostgreSQL, Docker,
Helm/kind, live browser/API and image vulnerability lanes were rerun against
the then-current dirty worktree. These diagnostic receipts supersede earlier
timings for this worktree; they still cannot qualify a clean release candidate:

| Lane | Current result | Elapsed | Evidence / limits |
| --- | --- | ---: | --- |
| Python + isolated PostgreSQL 16.4 | JUnit/pytest output: 4,467 passed, 26 skipped, 0 failed (4,493 total); branch coverage enabled | 538.81 s pytest terminal; 542.32 s runner pytest phase; 546.36 s total | `$env:TEMP/ronin-python-full-current-20261103`; cleanup succeeded. The old v3 timing JSON omitted two module-level collection skips; JUnit and pytest terminal summary include them. In that run, 9 Docker/worker acceptance cases and 3 provider tests were qualified separately by the Docker lane. Trino 2/2, OTLP Collector 1/1, POSIX 8/8 on Linux, SDP official CLI 1/1 and Spark Connect 1/1 have since passed in isolated lanes. SDP JSON-stdio remains unqualified on the current worktree. |
| Docker + PostgreSQL + Floci + Azurite + strict v0.1 | 27 passed, 0 skipped/failed; strict acceptance 15/15 | 173.31 s pytest | `$env:TEMP/ronin-docker-full-current-20261103`; freshly built worker/runtime image `sha256:fb9029dad0d8d5aade4bb5809c8a4e027f416a158fedc633c65667d0b21b01b8`; all temporary services cleaned. |
| Trino real-service integration | 2/2 passed: prepared scalar bindings and exact result-byte budget boundaries; 0 skipped/failures | 22.73 s total; service startup 13.85 s, pytest 5.69 s, cleanup 1.38 s | `pwsh -NoProfile -File tools/run_trino_qualification.ps1 -EvidenceDirectory "$env:TEMP/ronin-trino-<unique>" -AllowDirtyWorktree`; local Trino 484 pinned to `sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f`; receipt `$env:TEMP/ronin-trino-qualification-20261103-e7a48077`. Dirty-worktree diagnostic only; does not certify a production Trino deployment or the P3 family. |
| Spark Connect real-service integration | 1/1 passed, 0 skips/failures; real Spark 4.2.0 SQL execution and Ronin artifact persistence | 27.91 s total; dependency-cache hit; service startup 0.04 s, pytest 21.70 s, cleanup 1.97 s | `pwsh -NoProfile -File tools/run_spark_connect_qualification.ps1 -EvidenceDirectory "$env:TEMP/ronin-spark-<unique>" -AllowDirtyWorktree`; image `sha256:84a4eedb1abcf36a90808d5a1310e3e910b78c85d85aaa1599e31af5f862ed59`; receipt `$env:TEMP/ronin-spark-connect-qualification-20261103-ccbb305d`. Initial dependency preparation took 229.08 s and exposed a missing `pytz`, now hash-locked; later runs reuse the lock-keyed local cache. Dirty-worktree diagnostic; not a candidate-bound P3 qualification. |
| OTLP real-service integration | 1/1 passed: one real OTLP/HTTP collector accepted and exported traces, metrics and logs; no skips/failures | 5.03 s total; service startup 0.02 s, pytest 1.97 s, cleanup 1.17 s | `pwsh -NoProfile -File tools/run_otlp_qualification.ps1 -EvidenceDirectory "$env:TEMP/ronin-otlp-<unique>" -AllowDirtyWorktree`; Collector Contrib pinned to `sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621`; receipt `$env:TEMP/ronin-otlp-qualification-20261103-f933985d`. Dirty-worktree diagnostic only; it does not close P12 telemetry delivery/alert/FinOps journeys or a clean-candidate gate. |
| POSIX behavior on Linux | 8/8 previously platform-skipped node IDs passed, 0 skips/failures | 22.22 s total including ephemeral pytest setup; pytest session 11.81 s | `pwsh -NoProfile -File tools/run_posix_contract_qualification.ps1 -EvidenceDirectory "$env:TEMP/ronin-posix-<unique>" -AllowDirtyWorktree`; Ronin qualification image pinned to `sha256:fb9029dad0d8d5aade4bb5809c8a4e027f416a158fedc633c65667d0b21b01b8`; Git 2.54.0; receipt `$env:TEMP/ronin-posix-qualification-20261103-0841ce5d`. Checkout mounted read-only; pytest dependencies hash-locked. Diagnostic only; does not replace the approved supported-platform matrix or clean-candidate run. |
| Helm + kind | 11 qualification phases passed | runner receipt | `$env:TEMP/ronin-helm-full-current-20261103`; Helm v4.3.0, same image digest; health, Studio/API, queued-job persistence after pod restart, Secret boundary and cluster cleanup passed. |
| Browser + live Ronin API | 33/33 passed, 25 routes (23 API-backed); 168/168 API events correlated to structured logs (158 OK, 10 WARN); 0 5xx/network errors | 163.43 s total; 122.37 s Playwright | `$env:TEMP/ronin-live-full-current-20261103`; used the same worker image digest, real PostgreSQL and Kafka; service cleanup succeeded. |
| Browser static, accessibility and UI behaviors | 101/101 passed in the full static suite (about 3 min); after adding a guard against broken resources, route traversal/responsive sweep passed 26/26 in 1.1 min | 3 min full lane; 1.1 min focused rerun | API `/v1` 404s from the static file server are classified as expected; unexpected HTTP failures and failed network requests fail route traversal. Full suite evidence was generated before that last guard; focused route receipt validates the updated guard. Neither run replaces manual visual review. |
| Docker Scout + digest-bound VEX | 1 raw Alpine musl finding, 0 after explicit VEX author | about 46 s | `$env:TEMP/ronin-docker-vex-full-current-20261103`; finding remains an exception requiring human acceptance and applies only to the exact image digest. |
| Gitleaks current worktree | 0 leaks in 72.98 MB | 27.9 s (latest full-tree scan) | `$env:TEMP/ronin-gitleaks-tree-final-20261103`; refreshed after the latest implementation, formatting and evidence-ledger edits. History is unchanged and was previously 0 across 1,873 commits. |

These lanes provide broad functional, deployment, API/logging and container
evidence for the current worktree. They do not close the 13-family release
ledger: the tree is dirty, several provider/platform cases are unavailable,
manual visual review and maintainer decisions remain, and the artifact-bound
release bundle has not been rebuilt from one clean candidate.

### Local quality and coverage gates — same 3 November Python receipt

`make` is not installed on this Windows host, so the non-test Makefile targets
were invoked directly with the pinned Python environment and available Ruff/Go
tools. All passed: Ruff formatting/lint across 899 files; mypy 437 files;
OpenAPI snapshot; architecture and negative gates; route consistency (187
operations); Studio surface (125/229 declared operations); web audit (60 files,
no failures); web budgets; canonical JSON and runner protocol; dependency
surfaces; status ledger; agent skills; and performance tests (5/5 in 5.25 s).
The coverage report from the full Python run then passed all configured package
floors and the per-file storage ratchet (53 files). Logs:
`$env:TEMP/ronin-static-quality-current-20261103` and
`$env:TEMP/ronin-coverage-gates-current-20261103`.

That focused rerun caught a stale hard-coded image digest in
`test_docker_vex_scan_is_digest_bound_and_uses_an_explicit_author`. It now
checks the PURL's immutable SHA-256 shape; `verify_docker_vex.ps1` remains the
runtime check that binds the statement to the scanned image. After formatting
the two affected test modules, the Docker runner contract and project HTTP API
modules passed **62/62 in 30.01 s**. Ruff format/lint passed after that change.

These checks reproduce the relevant Makefile targets, but do not constitute a
single `make check` run or clean-candidate evidence. The full Python suite is
reported separately above; no test selection or coverage floor was reduced.

| Lane | Result | Measured pytest time | Interpretation |
| --- | --- | ---: | --- |
| Focused timing/selection/runner-contract tests | 30 passed | 10.37 s | Fast feedback for the test harness changes |
| Performance suite | 5 passed | 11.58 s | Separate performance regressions; small enough to run after relevant changes |
| Full Python + isolated PostgreSQL | 4,465 passed, 24 skipped, 0 failed (4,489 selected) | 549.09 s pytest; 558.86 s total (9m 19s) | Broad regression with branch coverage. The 24 skips comprise 9 Windows/POSIX capability skips, 6 Docker-opt-in cases (separately covered by the Docker lane, not necessarily one-to-one), and 9 provider/configuration cases; external providers remain uncertified |
| Docker + PostgreSQL + Floci + Azurite + strict v0.1 | 27 passed, 0 skipped, 0 failed; acceptance 15/15 | 259.39 s pytest (4m 19s) | Real container, database, object-storage emulators and worker journeys; image `sha256:3cffbb1acd492a0d8ccd290232edfb8526055924ede4d4ee78702f8d192d7158` |
| Live browser/API, PostgreSQL + Kafka + Docker worker | 33 passed, 0 skipped, 0 failed; 25 routes audited | 159.83 s total (127.36 s Playwright) | 168 real API events: 158 OK, 10 WARN; all correlated to structured HTTP logs by request ID, status and outcome |
| Docker Scout raw + digest-bound VEX | 1 raw finding; 0 after VEX | ~15 s | Docker Scout 1.27.0; only the vendor-fixed Alpine musl backport is excepted for the exact image digest |
| Gitleaks current tree + branch history | 0 leaks | 8.5 s + 54.1 s | Gitleaks 8.30.1 scanned 73.28 MB of current files and 1,873 commits reachable from the current branch |
| pip-audit test/runtime/bootstrap locks | 0 advisories | ~20 s | 101 test packages, 3 runtime packages and 1 pip bootstrap package; pinned inputs only, no dependency resolution |

These are diagnostic timings from a **dirty** worktree, so they do not qualify
a release candidate and cannot be compared as a controlled before/after
benchmark. The latest Docker run built the image from this checkout, used the
cached Python environment, and passed strict acceptance. Its 259.39 s pytest
duration is dominated by real worker crash recovery and backup/restore (the
slowest cases took 50.40 s, 44.36 s, 44.15 s and 39.61 s); shortening those
waits without changing the behavior under test would weaken the evidence. The
live run used that same immutable image. The latest full rerun includes the
P1 project Bundle lifecycle test and took 159.83 s: PostgreSQL/Kafka startup
9.74 s, Python/browser dependency preparation 8.90 s, fixture seeding and
server startup 7.27 s, browser journeys 131.66 s, evidence audit 0.57 s and
cleanup 1.68 s. Playwright JUnit time was 127.36 s. It passed all 33 cases;
the added case drove a real credential rejection, project create, manifest
export, deterministic Bundle download and idempotent reimport. The live suite
uses one worker because route cases mutate shared seeded state (projects,
quality runs, ML labs, workflows and other product data), so broad parallel
execution could race and make the result unreliable.

The full Python run took 558.86 s total: PostgreSQL startup 2.17 s, environment
setup 6.17 s, pytest 549.09 s, and cleanup 0.75 s. Test setup/call/teardown
accounts for 472.19 s; collection and session/report overhead account for most
of the remainder. The slowest Python cases were real contention/recovery
(20.99 s), plugin inventory (12.86 s), and PostgreSQL HTTP composition
(11.80 s). The slowest Docker cases exercise worker recovery and backup/restore,
so retain them in the full Docker gate. Evidence directories for the latest
image-bound Docker, Helm and live browser/API runs:
`$env:TEMP/ronin-docker-helm-prep-20261103`,
`$env:TEMP/ronin-helm-kind-qualification-20261103`, and
`$env:TEMP/ronin-live-p1-bundle-full-20261103`. The earlier Python full-suite evidence is
`$env:TEMP/ronin-postgres-full-fixed-20261103`.

A fresh reconciliation run for the timing collector took **508.75 s total**
(PostgreSQL startup 7.25 s, pytest 499.13 s, cleanup 0.77 s). It selected
4,558 cases: 4,531 passed, 26 skipped and one architecture-contract failure;
JUnit and timing JSON matched exactly, including two collection-level Docker
opt-in skips. Receipt: `$env:TEMP/ronin-python-full-summary-v4-20261103`.
The architecture failure was fixed by declaring the server's existing
`studio_semantic` dependency and the affected architecture plus summary tests
passed **25/25** afterward. Because the full suite predates that fix, do not
call this a full-suite pass; rerun it on the eventual frozen candidate.

### Image vulnerability scan and digest-bound VEX

The current local image scan is reproducible with:

```powershell
pwsh -NoProfile -File tools/verify_docker_vex.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-docker-vex-run"
```

The runner verifies that the image digest matches the product PURL in
`docker/qualification-image-vex.openvex.json`, records raw and VEX-applied
SARIF reports, and rejects any raw finding except the specifically reviewed
Alpine musl backport. It passes the document author via `--vex-author` because
Docker Scout defaults that allow-list to Docker authors. For the recorded
image, the raw report contained 1 finding (`CVE-2026-107891` on
`pkg:apk/alpine/musl@1.2.6-r3?os_name=alpine&os_version=3.24`) and the VEX
report contained 0. Evidence:
`$env:TEMP/ronin-docker-vex-current-20261103`.
This applies only to image
`sha256:3cffbb1acd492a0d8ccd290232edfb8526055924ede4d4ee78702f8d192d7158`;
rebuilding the image requires regenerating and reviewing the exception for its
new digest. Alpine's [security tracker](https://security.alpinelinux.org/vuln/CVE-2026-107891)
marks musl `1.2.6-r3` on `3.24-main` fixed. Docker's [VEX documentation](https://docs.docker.com/scout/how-tos/create-exceptions-vex/)
describes the accepted `not_affected` status and VEX author filter.

A zero VEX-applied finding count does not close release security on its own:
the image was built from a dirty tree, Gitleaks and final artifact scans are
still outstanding, and a human reviewer must accept the exception.

The contract file and runner are covered by
`test_docker_qualification_contract.py`: the latest focused diagnostic passed
20/20 in 4.95 s. This contract check does not scan an image; the Scout run
above is the actual image scan.

Gitleaks 8.30.1 ran as the pinned container image
`ghcr.io/gitleaks/gitleaks@sha256:b109bc5f8f76a38196a3e413704fc5b9e3c32360bce4e4b603bd6f45b3721dbb`.
The file scan covered 73.25 MB of the dirty current worktree (0 findings); the
history scan covered 1,873 commits reachable from branch `20261029` (0
findings). These are separate scopes. Reports are in
`$env:TEMP/ronin-gitleaks-current-final-20261103` and
`$env:TEMP/ronin-gitleaks-history-20261103`.

`pip-audit 2.10.1` reported no known advisories in the hash-pinned test lock
(101 packages), Docker runtime lock (3 packages) and pip bootstrap lock (1
package), using `--no-deps --disable-pip`. This audits the listed pinned
packages without dependency resolution; it does not replace auditing final
installed artifacts. JSON reports are in
`$env:TEMP/ronin-pip-audit-runtime-locks-20261103` and
`$env:TEMP/ronin-pip-audit-locked-noresolve-20261103.json`.

The safe optimization is to avoid repeating release gates for every edit. Use
focused tests during implementation, then run each required full lane once
after changes settle. The data does not justify parallelizing the shared
PostgreSQL or live product suites: tests share database/process state, and UI
journeys mutate common fixtures. Do not add workers to these gates until a
separate-database isolation pilot proves identical test IDs, coverage
thresholds and outcomes. Python and browser dependency caches are already
hits; real recovery waits and service startup are the main measured costs.

Use this iteration order to avoid repeating unrelated work:

1. Run changed unit modules (usually seconds).
2. Run the exact service-backed modules for the changed boundary, using the
   matching family runner (seconds to a few minutes).
3. Run static, type and contract checks affected by the change.
4. Run the broad Python + PostgreSQL suite after cross-cutting changes and at
   the final candidate checkpoint; it cost about nine minutes on this host.
5. Run full Docker and live browser/API acceptance after integration changes
   settle and again on the final candidate. A filtered Docker diagnostic can
   reuse a prior immutable image by digest, but cannot qualify changed image
   inputs or strict acceptance.

This is an iteration schedule, not a reduction of release scope. A full gate
after source changes is still required for release. To claim a speedup, compare
the same selected node IDs, service versions, coverage setting, image inputs,
cache state and machine; report wall time beside executed counts so a smaller
selection cannot be mistaken for a faster equivalent run.

The live lane intentionally expects zero `ERROR`/5xx events for a successful
qualification. Its 9 expected warning responses (400/401/403/409) were
correlated to `WARNING` log records. The separate HTTP integration test
`test_control_plane_access_logs_ok_warn_and_error_with_redacted_correlation`
injects a failing catalog dependency into the real HTTP server and verifies an
expected 500/`ERROR`, request-ID correlation, and secret redaction. This keeps
failure-path proof without treating a deliberate 500 as a pass in every live
product journey. The browser proxy records Ronin's `X-Ronin-Request-Id`; the
live qualification now fails if any captured API event lacks a matching
structured application HTTP log with the same ID, status, and outcome.

For normal implementation iterations, do not rerun the full release matrix
after each small change. Run the changed test module first, then the narrowest
real-service family touched by that change. Run the complete Python,
PostgreSQL, Docker, browser/API and static-browser lanes once the feature work
has settled, and again only after changes that affect those qualified surfaces.
This reduces repeated setup and unrelated test execution while preserving the
full release gate. It does not reduce the scope required for a release claim.

## 1. Choose the smallest useful layer

### Fastest way to get an honest answer

For an implementation change, start with the changed test file or exact node
IDs. Add the relevant runner contract tests when changing a harness. If the
behavior depends on a service, run that service's focused lane next. Expand to
the family lane only when the shared boundary changed; run the full matrix once
for the frozen candidate. This keeps feedback proportional to the change
without calling a filtered pass a release qualification.

Each runner receipt must state the source SHA and dirty/clean mode, exact
selection, selected/executed/passed/skipped/failed counts, per-test timing,
service startup, test time, cleanup and total duration. Check both the receipt
and JUnit; a green console line alone does not show that the intended test ran.
The complete Python/PostgreSQL lane is still about 9 minutes, and should not be
repeated for a change confined to a single UI file, runner contract or provider
adapter. The retained timing data makes the expensive test IDs visible for
targeted follow-up.

| Layer | What it answers | Typical command | What it does not prove |
| --- | --- | --- | --- |
| Unit | Does the changed function handle its local inputs and failure cases? | `python -m pytest -q tests/test_ronin_appliance_backup.py tests/test_postgres_backup.py` | Docker, PostgreSQL server behavior, API/UI wiring |
| Harness contract | Does the runner select the right suites, fixtures, evidence and release gates? | `python -m pytest -q tests/test_docker_qualification_contract.py tests/test_runner_broker_compose_topology.py` | That Docker services actually start or that product behavior works |
| Focused live integration | Does this exact journey work against its real local service? | Docker qualification with `-TestFilter` (examples below) | Unselected services, journeys, strict acceptance or the full candidate |
| Family regression | Does the broader Python/PostgreSQL, live UI/API, or Docker family still work? | Corresponding full runner without filters | Other families and clean-candidate release status |
| Release gate | Does the complete candidate pass the required family, security, artifact, UI/API and manual checks? | All gates, from one clean immutable candidate, followed by manual review | Anything outside the declared release matrix |

## Test lanes and what counts as real coverage

| Lane | Command / entry point | What it actually exercises | Evidence to inspect |
| --- | --- | --- | --- |
| Changed Python logic | `python -m pytest -q tests/<changed_test_file>.py` | Only the named tests; no service unless that test creates one | Exit code and exact test IDs |
| Python + real PostgreSQL (focused) | `tools/run_postgres_test_suite.ps1 -TestPath tests/<module>.py` | Selected Python tests with an isolated PostgreSQL 16.4 container; coverage is off | `pytest-postgres.xml`, output log, timings, selected/skipped/failed counts, cleanup status |
| Python + real PostgreSQL (complete) | `tools/run_postgres_test_suite.ps1` with no selectors | All collected Python tests except `tests/perf`, with branch coverage; PostgreSQL-backed cases use the isolated DB | JUnit, timing JSON, `.coverage` data, skips and their reasons; the release coverage gate consumes the data |
| HTTP/REST connector integration | `python -m pytest -q tests/integration/test_http_json_connector_real.py` | Connector requests against a real loopback HTTP server; covers status handling, pagination, retries and byte limits | Exact test results and HTTP request assertions; this is not an external-provider certification |
| Docker runtime and providers | `tools/run_docker_qualification.ps1` | Current checkout image, worker/runtime journeys, PostgreSQL, Floci/S3, Azurite/Azure and strict v0.1 acceptance | Image digest, JUnit, service logs, strict acceptance receipt and cleanup result |
| Browser static/mock | `npm test --prefix web-tests` | Rendering and browser behavior against the static server; API calls are mocked or unavailable in this lane | Playwright JUnit/HTML, screenshots/traces; never treat API errors here as live API evidence |
| Browser + live API | `tools/run_live_product_qualification.ps1 -WorkerImage <tag-or-digest>` | Ronin server and APIs with real backing services, Playwright journeys and a real worker image | Browser JUnit, `live-api-traffic.json`, server/worker logs, service cleanup |
| Human visual review | Open the candidate UI and follow the visual checklist in the release plan | Layout, responsive behavior, interaction, keyboard/focus and legibility on the actual candidate | Dated screenshots/notes tied to the candidate SHA; automation does not replace this |
| SDP Studio official CLI | `tools/run_sdp_cli_qualification.ps1 -EvidenceDirectory "$env:TEMP/ronin-sdp-cli" -AllowDirtyWorktree` | Creates an example project under a separate temporary data root and runs the official CLI validation test | CLI version, separated stdout/stderr, exact 1-test JUnit, timing v4, isolated root and evidence receipt |
| Spark Connect | `tools/run_spark_connect_qualification.ps1 -EvidenceDirectory "$env:TEMP/ronin-spark-connect" -AllowDirtyWorktree` | Starts digest-pinned Spark 4.2.0 Connect, then checks SQL execution through Ronin's provider and persisted pipeline evidence | Image digest, hash-locked client install report/cache identity, exact 1-test JUnit, timing v4, server log and cleanup receipt |
| Trino / OTLP / POSIX skips | `tools/run_trino_qualification.ps1`, `tools/run_otlp_qualification.ps1`, `tools/run_posix_contract_qualification.ps1` | Focused real Trino, real Collector, and Linux-only cases omitted by Windows | Exact manifests, service/image identity, timings, logs and cleanup receipt per lane |

The **full automated regression pass** is not one pytest command: run the
complete Python/PostgreSQL lane, the complete Docker lane and the full live
browser/API lane. Run static browser tests as a separate rendering lane. Then
run the remaining release-specific security, packaging, artifact and manual
gates from the release plan. A selected test or a static browser pass cannot
stand in for any of those complete lanes. The live runner requires a worker
image even when the rest of the API suite could start without one, because the
full run is meant to prove notebook execution through a real worker.

The local commands assume the repository's locked test environment is active.
The PowerShell runners create or reuse their fingerprinted, hash-locked Python
environment. Use the runner when service isolation and retained evidence matter.

For a focused browser loop, pass a Playwright title filter through the live
runner. This starts the real server and backing services, but is diagnostic
only and does not audit every route:

```powershell
pwsh -NoProfile -File tools/run_live_product_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-live-focused" `
  -WorkerImage ronin:qualification `
  -TestGrep 'project Bundle'
```

For a UI-only spec that does not depend on live APIs, run a file and title
filter against the static Playwright server:

```powershell
npm test --prefix web-tests -- --grep '<case title>' --workers=1
```

The package script runs with `web-tests` as its working directory, so the
checked-in Playwright config and its `webServer`/`baseURL` settings are loaded.
Do not invoke Playwright via `npm exec` from the repository root for relative
URL specs.

Keep `--workers=1` for the live lane because journeys mutate shared seeded
application state. Static tests may use more workers only when fixtures are
independent. Playwright's line reporter streams completed cases to the terminal;
HTML/JUnit artifacts remain the detailed evidence.

## 2. Fast backup/restore iteration

### Fast local-only Python feedback

When a change is covered by unit tests that do not require external services,
use the PostgreSQL runner in local-only mode. It does not start Docker, set a
PostgreSQL DSN, or collect coverage. Selection must be explicit, and integration
test files are rejected:

```powershell
# One changed test file (fastest useful feedback)
pwsh -NoProfile -File tools/run_postgres_test_suite.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-unit-focused-file" `
  -TestPath tests/test_backup_manifest.py -LocalOnly -AllowDirtyWorktree

# Narrow within a known unit module; the filter cannot widen beyond that file
pwsh -NoProfile -File tools/run_postgres_test_suite.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-unit-focused-filter" `
  -TestPath tests/test_backup_manifest.py `
  -TestFilter 'round_trip' -LocalOnly -AllowDirtyWorktree
```

The runner records selected, deselected, skipped and failed cases. A local-only
pass proves only those selected local tests; it says nothing about PostgreSQL,
Docker, coverage, or the full suite. If selection collects zero cases, the
runner fails instead of reporting a misleading pass. Prefer direct pytest for
very small loops when evidence retention is unnecessary; use this runner when
you want its JUnit and transcript. Every runner invocation also writes
`pytest-timings.json` with collection/session time, exact node IDs, per-test
phase duration and outcomes, plus whether the run was local-only or PostgreSQL,
its exact selection, and whether coverage was enabled. The current runner is a
manual local tool with no workflow metadata. `runner-timings.json` separately
records Python environment resolution, PostgreSQL startup/readiness, pytest
wall time, cleanup and total wall time so setup costs do not get misattributed
to test execution. Both receipts also record source commit, worktree cleanliness,
qualification mode, selection, coverage and service profile. Compare durations
only for clean worktrees with matching commits and execution contexts. Dirty
worktree runs are useful for diagnosis, but the commit alone cannot identify
their uncommitted contents. To generate a repeatable selection
of the 20 slowest non-skipped cases from that measured run:

The timing evidence schema is v4. Its summary separates selected test items,
module-level collection skips, filtered-out items, executed outcomes and
not-executed items. Collection skips include module node ID and reason because
they never become ordinary test items. Per-test skips retain pytest's skip
reason. The slow-test selector continues to accept v3 receipts.
“Filtered out” means pytest removed a collected item through a marker or
keyword filter; tests outside an explicitly selected file are not counted as
filtered items. `selected_nodeids` and `filtered_out_nodeids` show the exact
test-item lists; `collection_skips` lists module-level skips separately. Use
them with the selection string to understand the scope. A skip remains a gap
whenever the required service or configuration was expected to be present.

```powershell
python -m tools.pytest_slowest_selection `
  "$env:TEMP/ronin-unit-focused-file/pytest-timings.json" `
  "$env:TEMP/ronin-slowest-tests.txt" --count 20 --run `
  --checkout .
```

This is useful to diagnose known bottlenecks after one measured run; it should
not be the default edit loop because slow tests may cover unrelated code. The
selection file contains exact pytest node IDs, not a keyword expression, and
the optional `--run` executes those IDs individually as separate arguments
from the specified checkout. `--run` accepts only a timing report recorded in
local-only/no-service/no-coverage mode; PostgreSQL or other service-backed
selections can still be written to a file, but must be re-run with their family
runner. Start with changed tests, then related subsystem tests, then the real
integration family. Timing totals are diagnostic: they vary by host and must
be compared on the same machine with equivalent fixtures and coverage settings.

`-LocalOnly` requires one explicit test file and rejects files under
`integration`, `e2e`, or `perf`, plus the `integration` marker. It cannot prove
that an arbitrary test module has no hidden service dependency; keep unit
modules service-free by code review and use the normal family runner for tests
that own server or container fixtures.

Do not run the slowest-test selection as a substitute for the changed-code
loop: it helps identify suite hotspots, but often spends time exercising
unrelated areas. Use it to prioritize later optimization work. Coverage is
intentionally off for focused diagnostics and on for the full Python suite;
disabling it in a final full-suite run would make the run faster by weakening
the evidence.

First run the two unit files and the Docker runner contract tests. The unit
cases cover checksum parsing, corrupt or missing sidecars, refusal of an
unverified appliance bundle before Compose is queried, writer restart order,
failure behavior, and S3-backend refusal. They do not contact Docker.

Then run the actual Compose/PostgreSQL restore journey, selecting only its
required fixture:

```powershell
$imageId = docker image inspect ronin:qualification --format '{{.Id}}'
pwsh -NoProfile -File tools/run_docker_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-docker-appliance-focused" `
  -ImageId $imageId `
  -TestFilter appliance_backup_restores_postgres_and_local_data_volume `
  -AllowDirtyWorktree
```

`-ImageId` must be an immutable `sha256:` digest. In filtered mode it skips the
image build and reuses that exact image, which saves build time. The helper and
test code run from the current checkout, but the Ronin container is the
previously built image; this command therefore does not validate changed
Dockerfile or container-runtime code. Omit `-ImageId` if those files changed.
The focused test starts real PostgreSQL and Ronin containers, backs up the
database plus `/var/lib/ronin`, mutates both, restores and checks the original
data. It omits Floci, Azurite and strict v0.1 acceptance.

## 3. Focused provider integrations

The Docker runner starts only the fixture families implied by the filter:

```powershell
# Azure Blob against local Azurite; no PostgreSQL or Floci fixture
pwsh -NoProfile -File tools/run_docker_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-docker-azure-focused" `
  -ImageId $imageId -TestFilter azure_blob -AllowDirtyWorktree

# S3 connector and ML artifact store against local Floci
pwsh -NoProfile -File tools/run_docker_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-docker-s3-focused" `
  -ImageId $imageId -TestFilter 's3_json or ml_s3_artifact' -AllowDirtyWorktree
```

Worker, Docker executor, PostgreSQL and appliance-backup filters start
PostgreSQL. S3 filters start Floci. Azure Blob filters start Azurite. An
unfiltered run starts every fixture required by the complete Docker selection.
Use a new, empty evidence directory for each run. Review the transcript, JUnit,
selected/deselected counts, service logs and cleanup receipt; a zero-test
selection is not a pass.

## 4. Family and full Docker acceptance

After the focused real-service test passes, run the complete family runner
without `-TestFilter`. For Docker this builds the image from the current
checkout, runs worker/runtime, PostgreSQL-backed journeys, S3/Floci, Azure/
Azurite, appliance backup/restore, and strict v0.1 acceptance. It rejects
skips and failures. The digest in the receipt binds the built image; the
evidence directory retains pytest/JUnit and provider logs. A filtered run
intentionally does not execute strict acceptance and must not be substituted
for this gate.

For Python/PostgreSQL, run `tools/run_postgres_test_suite.ps1` without
`-TestPath`, `-TestFilter`, `-MarkerExpression`, or `-LocalOnly` when validating
the full suite and coverage. Selection options are for fast iteration; a
single selected test does not establish repository-wide coverage thresholds.
That full mode still includes the complete pytest collection and coverage
instrumentation, but does not start the separate live API/UI acceptance stack;
run the live qualification below for user-visible end-to-end behavior.
For integration-focused work, `-TestPath` can select an integration module and
the runner will still start isolated real PostgreSQL. The live product/UI/API qualification
must use `tools/run_live_product_qualification.ps1`, which starts the actual
API and backing services. A static web server can only qualify rendering; it
cannot establish API success, warning/error behavior, authorization, or
application logging.

For a PostgreSQL-backed diagnostic limited to a known test module, use an
explicit file selection. Coverage is disabled for filtered runs, and the
runner reports selected, skipped, failed, deselected and unrelated collection
skip counts:

```powershell
pwsh -NoProfile -File tools/run_postgres_test_suite.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-postgres-ingestion-focused" `
  -TestPath tests/test_jsonl_ingestion.py -AllowDirtyWorktree
```

Prefer explicit test files over broad `-k` expressions: they make the scope
reviewable and reduce the chance that a filter accidentally omits adjacent
cases. This is still diagnostic evidence, not repository-wide coverage.

The PostgreSQL runner records cleanup status in `runner-timings.json`. If
container cleanup fails, it returns a failing exit code and labels the run
`INCOMPLETE`; inspect and remove the named container before relying on the
evidence or starting another run. A passing pytest result with failed cleanup
is not a complete successful run.

## 5. Evidence checklist: was it really tested?

For each result record:

1. Exact source SHA and clean/dirty state. Dirty-tree evidence is diagnostic.
2. Exact command, selected test IDs, deselected count, skips with reasons,
   failures, duration, and retained JUnit/evidence path.
3. Image digest and real service/provider versions used.
4. The actual user-visible action and response: HTTP status/body, rendered
   success/warning/error message, and the corresponding structured log event.
5. Cleanup outcome for temporary containers, volumes, networks and clusters.
6. What the run did not cover and the next broader gate required.

For a clear answer to “what was tested?”, report four items together: **scope**
(unit / focused real-service / family / release), **selection** (exact node IDs
or family and selected/deselected counts), **result** (passes, skips with
reasons, failures), and **limits/next gate**. A bare “tests passed” omits the
information needed to judge coverage.

Use this short report for each lane:

```text
Lane / scope:
Candidate SHA and clean/dirty:
Command and exact selection:
Selected / passed / skipped / failed:
Real services and immutable image digests:
Evidence directory:
Cleanup status:
What this did not test / next required lane:
```

For the browser/API lane, add HTTP counts by status and expected outcome
(`OK`/`WARN`/`ERROR`), unexpected 5xx/network failures, and matching log counts.
This makes a green UI assertion auditable against the actual API response and
application log instead of relying on the screenshot alone.

For UI/API journeys, explicitly verify that an “OK” message follows a real
successful API response and persisted state; a “WARN” corresponds to the
expected HTTP/API condition; an “ERROR” includes the failed API result and a
correlated error log. Browser screenshots alone cannot verify those contracts.
Manual visual review remains required for layout, responsive behavior,
keyboard/focus, contrast, and the Brown/Ronin visual system.

## 6. Release rule

Run the complete required gates on one clean candidate only after focused
changes have settled. Do not combine results from different SHAs into one
release claim. Manual UI review, human legal/version/claims decisions, and the
full capability-family matrix remain separate release gates. A passing test
suite is evidence for its declared scope, not a claim that every feature or
platform is qualified.

### Semantic Studio and workspace isolation regression — 2026-11-03

Two workspace paths now namespace semantic persistence by the full
`(workspace_id, project_id)` pair. The HTTP integration fixture uses the same
project ID in two workspaces and asserts that models, dashboards and Bundle
imports stay in their own scopes. The semantic HTTP/store/OpenAPI selection
passed **84/84** in 39.81 s; it includes the full workspace HTTP module. The
focused browser selection passed **3/3** Chromium journeys for Bundle
integrity/preview/import, stale-review blocking and saving the valid initial
dashboard through the browser request path. These are dirty-tree diagnostic
results, not a Public v1 family qualification.

### Semantic Studio live lane: exact scope and cost — 2026-11-03

Use this narrow live lane while changing Semantic Studio. It runs Ronin with an
isolated SQLite database and omits PostgreSQL, Kafka, and streaming seed data,
because this journey uses none of them:

```powershell
pwsh -NoProfile -File tools/run_live_product_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-live-semantic-<unique>" `
  -TestGrep semantic -AllowDirtyWorktree
```

The journey is API-backed: Chromium lists a seeded model, downloads a real
Bundle, previews it through the running API, imports it, then reloads models
and dashboards through the API. The 2026-11-03 receipt passed **1/1** in
**33.99 s** total (browser phase 16.71 s; Playwright test body 8.88 s), with
**6 real API events** all correlated to structured HTTP logs, all six `OK`,
and zero application WARN/ERROR/CRITICAL messages. Python and Playwright
dependency caches were hits. The receipt explicitly records PostgreSQL/Kafka
as not started and route-wide audit as not run. This proves the semantic
journey only; it does not prove PostgreSQL, Kafka, all-route browser behavior,
or release readiness.

The preceding 34-second failed attempt exposed a runner bug: it still seeded
Kafka after excluding Kafka. The runner now skips that fixture only for the
semantic filter, and the passing receipt confirms that path. Read
`qualification-summary.json` first: it reports test counts, phase durations,
services started, API outcomes, log levels, cache status, route-audit status,
and evidence paths. Then inspect `live-api-traffic.json` and correlated
server logs for any message under review. Never describe a filtered journey as
“all routes tested.”

Semantic dashboard execution is independently bounded in both runtime paths:
12 tiles, 100,000 aggregate requested rows, 15 seconds total SQL time, and an
8 MiB serialized API response cap (1 MiB reserved for metadata). All model
references and queries are validated before the first SQL call. Queries run
sequentially with remaining time/bytes passed into each call; an over-budget
result, timeout or SQL error stops the sequence and returns no partial result.
Verify these limits and real project-scoped SQL with:

```powershell
python -m pytest -q tests/test_semantic_runtime.py tests/test_openapi_snapshot.py
python -m pytest -q tests/integration/test_workspace_project_http_api.py::test_semantic_dashboard_execution_http_runs_bounded_project_scoped_sql
```

The first command covers both runtimes and a real DuckDB/Parquet fixture plus
preflight, timeout and result-budget failures. The second runs the actual
authenticated control-plane route through the project-scoped DuckDB engine.

### Shorter worker heartbeat contention diagnostics — 2026-11-03

The two SQLite/artifact contention tests previously waited for production
heartbeat intervals (10 seconds) before releasing their deliberately blocked
storage operation. The test now keeps the 30-second production defaults
asserted in the shared fixture, then uses an isolated two-second lease and
100-ms heartbeat only in the two stress scenarios. Both still hold real worker
storage operations, read the durable heartbeat and lease expiry from SQLite,
and assert successful reclaim/completion. Focused reruns passed **2/2**; their
combined call time was **2.96 s**, compared with **32.42 s** in the prior full
suite timing receipt. This is a host/load-sensitive diagnostic comparison,
not a claim that the whole suite is 90% faster. The focused contention module
contains only these two cases and passed **2/2**. No production lease or
heartbeat default changed.

```powershell
python -m pytest -q --durations=10 tests/integration/test_worker_runtime_contention.py
```

### Focused live ML test without unrelated services — 2026-11-03

The ML UI/API journey needs the real Ronin server and local SQLite fixture, but
not PostgreSQL or Kafka. Run just that real route with:

```powershell
pwsh -NoProfile -File tools/run_live_product_qualification.ps1 `
  -EvidenceDirectory "$env:TEMP/ronin-live-ml-<unique>" `
  -TestGrep mlstudio -AllowDirtyWorktree
```

The filtered receipt proves the Chromium journey, actual API calls and
correlated server logs. It does not prove all routes, PostgreSQL/Kafka paths,
or the full release. The initial profile passed **1/1**, with 36/36 API events
correlated and no server/network errors; PostgreSQL/Kafka were not started. It
measured the first ML runtime import at **31.80 s**. A repeat in a new Ronin
process with dependency bytecode cached passed **1/1** in 41.21 s total; the
same cold process import took **5.98 s**. These are two separate diagnostic
runs, not candidate-bound release evidence. The runner now times and performs
a narrow compile pass over Ronin's `python/` tree and live seed helpers before
the route; it does not compile the entire scientific dependency environment.
Inspect the `precompile Ronin Python sources` phase in fresh receipts to see
the setup cost separately from server start and browser work.

After adding that narrow compile phase, a fresh diagnostic receipt passed
**1/1 in 19.54 s**: dependency preparation 1.78 s, Ronin-source precompile
0.43 s, seeding/server startup 3.89 s, browser/API journey 13.05 s. The first
scikit-learn estimator import was still **3.72 s**; the measured search had
28.71 ms preparation and took 3.90 s overall. It produced 36 correlated API
events (35 `OK`, one expected `WARN`), with no `ERROR` or `CRITICAL` logs.
This identifies the cold ML import as the remaining latency hotspot while
keeping it distinct from server/setup time. It is a dirty-worktree diagnostic
receipt, not release evidence.
