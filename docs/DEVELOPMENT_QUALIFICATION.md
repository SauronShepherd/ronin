# Development and qualification commands

Run commands from the repository root. Focused repository-tool checks use
`requirements-dev.lock`; the complete Python suite uses `requirements-test.lock`
to include and lock all optional runtime extras. Browser checks additionally
require Playwright Chromium and the web dependencies from `package-lock.json`.

## Local Spark evidence

When PySpark is installed, run the bounded local SQL qualification:

```text
python tools/local_spark_qualification.py --output artifacts/local-spark-qualification.json
```

This records Spark/Python versions and a correctness digest. It is local
PySpark evidence only; it never substitutes for external Spark Connect
qualification, which requires `SPARK_CONNECT_ENDPOINT`. The local worker is
bounded to 30 seconds by default; use `--timeout-seconds` to adjust it. A
`timeout` result is incomplete evidence and never a pass.

## Provider-neutral query-engine evidence

Run the bounded local contract qualification with an explicit external-provider
status:

```text
python tools/query_engine_qualification.py --output artifacts/query-engine-qualification.json
```

The local DuckDB result is marked qualified only when its lifecycle, bounded
rows, and correctness digest match. QueryFlux remains `not_configured` until
an operator supplies `RONIN_QUERYFLUX_QUALIFICATION_COMMAND`. When configured,
the command is executed with a bounded timeout and must emit JSON evidence with
`provider: queryflux` and `status: qualified`; local evidence still does not
claim QueryFlux production qualification.

## Source and contract checks

```text
make check
make lint-openapi
python -m tools.route_consistency
python -m tools.capability_status docs/product/public-v1-status.json
```

`lint-openapi` compares the canonicalized `api/openapi-v1.json` document with
`api/openapi-v1.sha256`. Any public contract edit must update the snapshot only
after review of the route-compatibility impact.

## Installed Studio checks

Build an artifact and qualify the installed package, not the checkout:

```text
make ui-installed
make ui-a11y
```

The installed browser smoke visits the supported Studio routes and fails on
missing assets, module errors, page errors, console errors, or horizontal
overflow. The accessibility run covers the 320px, 768px, and desktop viewport
matrix with axe-core.

For a developer-visible Chromium run against a locally served Studio:

```text
make ui-e2e-headed
RONIN_UI_SLOW_MO_MS=200 make ui-e2e-headed
```

Set `RONIN_STUDIO_AUDIT_URL` when the local server is not at the default URL.

## Command target map

The Make targets used by the build plan map to the following checks. Run them
from the repository root. Browser targets validate locked JavaScript
dependencies and install them only when their cache is missing or stale.

| Target | Purpose |
| --- | --- |
| `make check` | Format, lint, OpenAPI, typing, architecture, route, Studio, dependency, contract, test and performance gates. |
| `make web-test-deps` | Validate the Playwright lock and installed package tree; install dependencies/Chromium only when missing or stale. |
| `make ui-e2e` | Headless Playwright route and journey qualification from `web-tests`. |
| `make ui-e2e-headed` | Visible Chromium Playwright run for local diagnosis. |
| `make ui-a11y` | Installed-package browser smoke plus the 320px/768px/desktop accessibility matrix. |
| `make ui-installed` | Installed wheel Studio smoke, including packaged assets and browser errors. |
| `tools/run_helm_qualification.ps1` | Helm lint/render plus isolated kind deployment, health, UI/API, persisted job and restart checks; dirty runs are diagnostics only. |
| `make browser-audit` | Browser audit against `RONIN_STUDIO_AUDIT_URL` (default `http://127.0.0.1:8080/studio/`). |
| `python tools/local_spark_qualification.py ...` | Optional local Spark engine evidence; requires PySpark. |
| `python tools/query_engine_qualification.py ...` | Local engine evidence and explicit QueryFlux configuration status. |
| `docs/quality/MUTATION_CAMPAIGN_FINAL.md` | Frozen historical mutation evidence; no recurring mutation command exists. |

For each edit, run the focused test first, then the relevant browser/database
integration tier. Run `make check` once for the full local Python and quality
gate: it already includes the full non-performance suite, coverage gates and
performance tests. Do not run `make test` and `make check` back-to-back for the
same source state; that repeats the full suite. PostgreSQL qualification is a
separate environment gate and runs the full suite with real PostgreSQL enabled.

`ui-visual` is not currently a Make target: visual checks are covered by the
Playwright suite and installed Studio smoke, while a separate visual baseline
must not be claimed until its reference artifacts and review policy exist.

Static Playwright uses `PLAYWRIGHT_WORKERS` (default 2); increasing it can
shorten local visual checks when the host has spare CPU and memory. Live
journeys stay single-worker because their cases share mutable fixture data.

## Live product and Docker test receipts

Use a unique evidence directory for each run. Do not use the static Playwright
server as evidence for API, database, logging, or worker behavior.

```powershell
# Focus one PostgreSQL test file during implementation. This starts a fresh
# real PostgreSQL container and avoids collecting the entire repository.
$evidence = Join-Path $env:TEMP ("ronin-postgres-focused-" + [guid]::NewGuid().ToString("N"))
pwsh -NoProfile -File tools/run_postgres_test_suite.ps1 `
  -EvidenceDirectory $evidence -TestPath "tests/integration/test_postgres_catalog_store.py" `
  -AllowDirtyWorktree

# Full non-performance Python suite with PostgreSQL-backed cases enabled.
$evidence = Join-Path $env:TEMP ("ronin-postgres-full-" + [guid]::NewGuid().ToString("N"))
pwsh -NoProfile -File tools/run_postgres_test_suite.ps1 `
  -EvidenceDirectory $evidence

# Focus a real live journey while iterating (diagnostic only; no route-wide gate).
$evidence = Join-Path $env:TEMP ("ronin-live-focused-" + [guid]::NewGuid().ToString("N"))
pwsh -NoProfile -File tools/run_live_product_qualification.ps1 `
  -EvidenceDirectory $evidence -TestGrep "route sql loads and reaches the live API" `
  -AllowDirtyWorktree

# Full real application journeys: isolated Ronin API, PostgreSQL, Kafka,
# and Docker worker; audits active routes, API traffic, browser/server/worker logs.
$evidence = Join-Path $env:TEMP ("ronin-live-full-" + [guid]::NewGuid().ToString("N"))
pwsh -NoProfile -File tools/run_live_product_qualification.ps1 `
  -EvidenceDirectory $evidence -WorkerImage ronin:qualification

# The gate includes actual PostgreSQL backup/restore with a data comparison.
# Dirty-tree diagnostic: Docker integration + strict v0.1 acceptance using real
# Docker workers, PostgreSQL, S3-compatible Floci and Azure Blob Azurite.
# For release qualification, require a clean checkout and remove the dirty flag
# from both commands below.
$runId = [guid]::NewGuid().ToString("N")
$dockerEvidence = Join-Path $env:TEMP "ronin-docker-$runId"
$helmEvidence = Join-Path $env:TEMP "ronin-helm-$runId"
$imageTag = "ronin:qualification-$($runId.Substring(0, 8))"
pwsh -NoProfile -File tools/run_docker_qualification.ps1 `
  -EvidenceDirectory $dockerEvidence -ImageTag $imageTag -AllowDirtyWorktree
if ($LASTEXITCODE -ne 0) { throw "Docker qualification failed; see $dockerEvidence" }

# This consumes the exact Docker receipt and immutable image ID from above.
pwsh -NoProfile -File tools/run_helm_qualification.ps1 `
  -EvidenceDirectory $helmEvidence -DockerEvidenceDirectory $dockerEvidence `
  -ImageRef $imageTag -AllowDirtyWorktree
if ($LASTEXITCODE -ne 0) { throw "Helm/kind qualification failed; see $helmEvidence" }

# Fast Docker integration diagnostic for a specific pytest name/expression.
# Real services still start, but strict acceptance is intentionally omitted.
$evidence = Join-Path $env:TEMP ("ronin-docker-focused-" + [guid]::NewGuid().ToString("N"))
pwsh -NoProfile -File tools/run_docker_qualification.ps1 `
  -EvidenceDirectory $evidence -TestFilter "azure_blob_discovers" `
  -AllowDirtyWorktree
```

The filtered live command is intentionally labelled a diagnostic: it starts
the real services and captures API/log evidence for matching cases, but does
not claim complete route coverage. The unfiltered command is the route-wide
live qualification. Static Playwright remains useful for layout and client
behavior, but it is not interchangeable with either live command. At the
latest measured diagnostic, the full live run took 200.88s (171.28s for
browser journeys); the expanded Docker run took 157.19s (155.96s in pytest).
Both runners retain per-phase timings and now print a concise final receipt
with executed/pass/skip/fail counts and real-service/API/log status. These
measurements are a baseline, not a performance promise.

For the shortest reliable feedback loop, start with one changed test file or a
pytest `-k` expression, then run the Docker integration gate when the change
touches runtime, persistence, workers, or connectors. Run the strict v0.1 gate
and Helm/kind gate before release; Helm refuses to run without the matching
full Docker receipt and image ID. Keep stateful live-service gates sequential
to avoid port, database, and container contention. Focused runs are diagnostics
and never count as full-family release evidence.

The focused PostgreSQL command starts a fresh real PostgreSQL container and
accepts `-TestPath` (a test file), `-TestFilter` (a pytest `-k` expression), or
both. `-TestPath` avoids collecting all 4,000+ repository tests; coverage
collection is disabled for this focused diagnostic. Its receipt lists selected
cases, unrelated collection skips, and the slowest 15 cases. Use it after a
targeted change. The unfiltered PostgreSQL run executes the full
non-performance Python suite (the latest measured run took 884.06s on this
Windows host; a prior run took 589.02s, so host load and slow integration
fixtures materially affect wall time). It uses quiet pytest output; the receipt prints the summary and
individual skips/failures, while JUnit retains every case and the top 15
durations. Run it after a coherent batch instead of after every small edit. A
filtered run is diagnostic and does not claim full suite or coverage
qualification. `make check` already runs the Python suite,
coverage gates, and performance checks, so don't run `make test` and then
`make check` for the same source state.

Use this feedback loop to keep iteration time and evidence clear:

1. Run the narrowest matching unit/contract file (typically seconds), then
   Ruff on the files changed.
2. For a changed PostgreSQL path, use `-TestPath` and add `-TestFilter` only
   when one case is enough. This still starts real PostgreSQL; inspect the
   receipt's selected/pass/skip/fail counts and JUnit before treating it as
   evidence.
3. Run the affected real-service tier (Docker, live API/browser, or provider)
   once the local contract is stable. A static browser server does not prove
   API behavior.
4. Run the full Python/PostgreSQL suite with coverage, then the complete live
   and Docker qualifications once per coherent batch and again on the final
   clean candidate. Do not repeat these release gates after each edit.

The full Python/PostgreSQL run is about ten minutes on this Windows host. Its
console stays concise; the JUnit and pytest log preserve exact cases and
failure details, and the receipt calls out skips rather than counting them as
passes. Compare the receipt's collection, test, and total times before
optimizing any further. Keep timeouts, retry/recovery windows, and waits when
they exercise production behavior; improve fixture startup, test selection,
or redundant setup instead.

Latest measured dirty-worktree run on 2026-11-03: the full Python/PostgreSQL
suite completed **4,440 passed, 25 skipped, 0 failed of 4,465 in 884.06s**.
The skips were reported individually; they include opt-in Docker tests in this
lane, unavailable external services (OTLP, Trino, Spark and SDP), and Windows
platform limits such as symlink privileges. Those behaviors are not counted as
tested by this run. The separate Docker qualification then built the Ronin
image and exercised PostgreSQL, real Docker workers, Floci/S3 and
Azurite/Azure: **26/26 passed, 0 skipped, 0 failed in 175.99s of pytest**;
the strict v0.1 gate independently passed **15/15 steps**. Evidence is under
`%TEMP%\ronin-postgres-after-perf-isolation-69dd7cb13747472f82e2511f9124b47b`
and `%TEMP%\ronin-docker-after-jdbc-checkpoint-7674c094952a4c2687ee2b7b2c3d4647`.
Both are dirty-worktree diagnostics, not candidate release evidence.

The slowest cases identify where time goes: the full suite's top case was the
third-party wheel build/discovery test (**46.44s**). Its isolated discovery
subprocess used to scan all global site-packages despite testing a clean-room
wheel. Adding Python's `-S` mode made the focused test pass in **13.91s**
(15.09s total including pytest startup); this compares a focused run with a
full-suite run, not a controlled same-load benchmark. The Docker lane's two
process-crash recovery cases took **42.50s** and **37.34s** because they wait
for the production 30-second lease to expire. Those waits are part of the
recovery contract and should not be shortened just to improve the benchmark.
Do not parallelize the shared-state live journey or latency benchmark. For
normal iteration, use `-TestPath` (not repository-wide `-k`) for a
PostgreSQL-focused test, then the matching real-service diagnostic; this avoids
full test collection and coverage setup. Run the full Python/PostgreSQL,
Docker/strict acceptance and live browser/API gates once per coherent batch
and on the final clean candidate. `make check` already includes the complete
non-performance Python suite, coverage gates and performance lane, so running
`make test` immediately before it duplicates the same expensive tests.

The Helm gate requires `server.bindPolicy: insecure-plaintext-network` as an
explicit operator value because its ClusterIP chart serves plaintext HTTP on a
non-loopback interface. The policy is disabled in default values. Use this
single-node chart only on a trusted local cluster, keep its Service private,
and use `kubectl port-forward`; remote access needs a TLS terminator.
`container-internal` is reserved for Ronin's supported Compose bridge. The
runner checks the image identity and rendered Secret boundary, performs live
health/UI/API calls, submits a job, verifies it remains after a pod restart,
and removes only its own temporary cluster. JSON receipt and logs stay in the
evidence directory.

With the dependency cache warm, a focused live SQL/API run passed 1/1 in
44.41s, reporting one real API `OK` and zero log errors. The focused Azure
Docker diagnostic passed 1/1 against Azurite; its first warm-up pytest took
33.48s, and a repeat took 2.11s total (0.74s in the Azure call). The repeat
receipt names the exact node ID and labels the run diagnostic-only. An initial
attempt exposed that the old Docker runner used global Python without the
Azure SDK; the runner now uses a lock-fingerprinted test venv. First-time cache
creation remains setup cost and is separated from repeat execution.

The Docker pytest suite has 26 selected cases at this revision. Interpret a
filtered run by its case-to-service contract: the harness makes isolated
fixtures available, while an individual test exercises only its declared
path.

| Test file / selection | Real dependency exercised |
| --- | --- |
| `test_http_json_connector_real.py` | Bounded HTTP JSON connector ↔ governed loopback HTTP fixture; pagination, retry, replay and rejection paths |
| `test_azure_blob_connector_real.py` | Azure SDK ↔ Azurite Blob |
| `test_s3_json_connector_real.py`, `test_ml_s3_artifact_store_real.py` | S3 SDK ↔ Floci |
| `test_docker_container_executor_real.py` | Docker container resource limits/isolation |
| `test_worker_runtime_real.py` | Docker worker; PostgreSQL-backed case additionally exercises PostgreSQL persistence and recovery |
| `test_v01_journey.py` | Product CLI, worker, durable job/evidence/recovery journey |

The Docker runner now installs/uses a separate cached virtual environment
fingerprinted from `requirements-test.lock` and `pyproject.toml`; this keeps
optional connector SDKs (such as Azure) present without relying on global
Python packages. Its final receipt lists the exact pytest cases and explicitly
says when strict acceptance was not run.

For every change, run its focused unit/contract tests first, then only the
affected real-service tier. Run the Python/PostgreSQL and complete live/Docker
tiers after a coherent set of changes, before release evidence. Avoid running
`make test` and `make check` back-to-back: `make check` already includes the
same full suite. Keep recovery tests' 30-second lease waits and live Playwright
single-worker execution; they validate production recovery timing and shared
mutable state. Do not trade them for speed without a separately qualified
equivalent test design.

The bounded-contention HTTP latency benchmark lives in `tests/perf` and runs
without coverage instrumentation. It still exercises the real local API,
SQLite store and SDK; moving it there prevents global coverage overhead from
being mistaken for request latency. The current performance tier has five
tests and passed 5/5 in 9.37s. The benchmark's exact POST/GET p95 and maxima
print with `-s` and remain in the pytest/JUnit evidence when configured.

## Release evidence

Run release qualification locally to create the exact wheel/sdist identity,
SPDX SBOM, installed-artifact evidence bundle, and fail-closed verdict. Validate
the resulting local evidence with:

```text
python -m tools.release_evidence validate <bundle.json>
python -m tools.release_evidence verdict <bundle.json> --required-gate <gate>
python -m tools.artifact_identity <wheel> <sdist> --output artifact-identity.json
```

Skipped, missing, stale, or wrong-commit evidence is never a passing release
verdict. Mutation evidence is historical and frozen in
`docs/quality/MUTATION_CAMPAIGN_FINAL.md`. Mutation testing is not a recurring
qualification gate or release prerequisite; future quality evidence comes from
the ordinary unit, integration, contract, and end-to-end suites.

## Fast feedback versus release qualification

Use the smallest tier that can answer the question; a fast tier does not
replace the broader tiers:

| Tier | What it exercises | Use it for |
| --- | --- | --- |
| Focused Python/JS tests | Selected unit and contract cases; no live services unless a test explicitly opts in | Each code change and failure diagnosis |
| Static Playwright | Real browser rendering/navigation against the static asset server; live API tests are excluded, so no backend claim | Layout, responsive, accessibility and client-only regressions |
| PostgreSQL integration | Storage/API behavior against a disposable real PostgreSQL service | Changes to persistence, SQL, migrations or API adapters |
| Live product qualification | Browser journeys against a running Ronin API, fresh PostgreSQL and Redpanda fixtures; optional immutable worker image | Candidate-level functional/API/logging evidence |
| Docker qualification | Built runtime image, real worker/container and strict acceptance journeys | Candidate-level packaging and execution evidence |

The live runner writes `qualification-summary.json` in its evidence directory.
It reports the candidate/dirty-worktree status, elapsed time, executed/passed/
skipped/failed browser cases, real API-traffic counts/outcomes, service setup,
and paths to JUnit, browser traffic and server/worker logs. Check this summary
alongside those raw files; a static Playwright run is never API evidence, and a
failed setup phase is not a passed product test.

In the live route matrix, routes declaring `required_api` are explicitly
reported as “loads and reaches the live API”. Routes without that contract
(currently Home and Settings) are named “UI-only” and must not make API
coverage claims. A filtered run reports whether it was a live API diagnostic
or a UI-only diagnostic; a zero-call run cannot pass as API evidence.

Live-run infrastructure and data remain unique per invocation: Compose project,
credentials, database, Kafka topic fixtures, Ronin state, browser artifacts and
logs are never reused. Only dependency installations are cached. The Python
cache key includes the Python executable/version, `requirements-test.lock`,
`pyproject.toml` and repository path; it uses a cross-process lock, validates
the installed dependency graph with `pip check`, and is rebuilt when its
fingerprint or consistency check changes. Python's global `compileall` during
pip install is disabled because the live journey imports only the modules it
uses. Playwright's `node_modules` cache is accepted only when `package.json`,
`package-lock.json` and `npm ls --depth=0` all agree; Chromium is installed only
when the locked Playwright executable is absent. `make ui-e2e`, `make ui-a11y`,
headed/debug runs and live qualification share `web-tests/ensure-dependencies.mjs`;
running one target no longer clears dependencies used by the others. A cache
miss still installs from the lock.

`npm test` excludes test titles marked Live; `npm run test:live` is the separate
suite that requires the live preflight and actual Ronin services. This avoids a
green static report that also silently lists backend tests as skipped.

The live product runner saves `pip freeze` beside browser, API-traffic and
server-log evidence. Its PostgreSQL/Redpanda Compose services are removed on
exit. A run using `-AllowDirtyWorktree` is diagnostic evidence only: it does
not bind results to a clean release commit or artifact.
