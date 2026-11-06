from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_docker_qualification_script_uses_immutable_image_and_real_suites() -> None:
    script = (ROOT / "tools" / "run_docker_qualification.ps1").read_text(encoding="utf-8")

    assert "[Parameter(Mandatory = $true)]" in script
    assert "[string]$EvidenceDirectory" in script
    assert "Evidence directory is not empty" in script
    assert '"docker-qualification.log"' in script
    assert "docker build --file docker/Dockerfile" in script
    assert "-ImageId is allowed only with -TestFilter" in script
    assert "current checkout's Docker image is not qualified" in script
    assert "$needsPostgres = -not $TestFilter" in script
    assert "$needsFloci = -not $TestFilter" in script
    assert "$needsAzurite = -not $TestFilter" in script
    assert "if ($needsPostgres) {" in script
    assert "if ($needsFloci) {" in script
    assert "if ($needsAzurite) {" in script
    assert "Infrastructure is selected by suite" in script
    assert "strict v0.1 acceptance is omitted" in script
    assert "selected zero test cases; an empty selection cannot pass" in script
    assert "$imageWasBuiltFromCheckout = $false" in script
    assert "$imageWasBuiltFromCheckout = $true" in script
    assert (
        '$imageAction = if ($imageWasBuiltFromCheckout) { "built from checkout" } else { "reused" }'
        in script
    )
    assert "selected fixtures: {6}" in script
    assert script.index("if ($needsPostgres) {") < script.index(
        "docker run --detach --name $postgresContainerName"
    )
    assert script.index("if ($needsFloci) {") < script.index("docker compose -p $flociProject")
    assert script.index("if ($needsAzurite) {") < script.index("docker compose -p $azuriteProject")
    assert "-ImageId is allowed only with -TestFilter" in script
    assert "current checkout's Docker image is not qualified" in script
    assert "$needsPostgres" in script
    assert "$needsFloci" in script
    assert "$needsAzurite" in script
    assert "if ($needsPostgres) {" in script
    assert "if ($needsFloci) {" in script
    assert "if ($needsAzurite) {" in script
    assert "docker image inspect $ImageTag --format '{{.Id}}'" in script
    assert "RONIN_DOCKER_QUALIFICATION_IMAGE" in script
    assert "function Get-FreeLoopbackPort" in script
    assert "postgres:16.4-alpine" in script
    assert "$env:RONIN_POSTGRES_TEST_DSN = $postgresDsn" in script
    assert "docker rm --force --volumes $postgresContainerName" in script
    assert '$ErrorActionPreference = "Continue"' in script
    assert "$ErrorActionPreference = $previousErrorActionPreference" in script
    assert "finally {\n            $ErrorActionPreference" in script
    assert "requires zero skips and failures" in script
    assert "tests/integration/test_worker_runtime_real.py" in script
    assert "tests/e2e/test_v01_journey.py" in script
    assert 'Write-Output "Docker acceptance scope:' in script
    assert "$pytestArguments = @(" in script
    assert '"-v", "--durations=15"' in script
    assert "& $python -m pytest @pytestArguments" in script
    assert "TestFilter" in script
    assert "if ($TestFilter) {" in script
    assert "Diagnostic only: strict v0.1 acceptance was not evaluated" in script
    assert "qualification_python.psm1" in script
    assert "Get-RoninTestPythonEnvironment" in script
    assert "Executed: $caseName" in script
    assert '"v01-acceptance.xml"' in script
    assert '"v01-acceptance-strict.json"' in script


def test_docker_and_postgres_qualifications_share_the_hash_locked_test_environment() -> None:
    helper = (ROOT / "tools" / "qualification_python.psm1").read_text(encoding="utf-8")
    docker = (ROOT / "tools" / "run_docker_qualification.ps1").read_text(encoding="utf-8")
    postgres = (ROOT / "tools" / "run_postgres_test_suite.ps1").read_text(encoding="utf-8")

    assert "requirements-test.lock" in helper
    assert "--require-hashes" in helper
    assert "lockSha256" in helper
    assert "projectSha256" in helper
    assert "FileShare]::None" in helper
    assert "Import-Module" in docker
    assert "Get-RoninTestPythonEnvironment" in docker
    assert "Import-Module" in postgres
    assert "Get-RoninTestPythonEnvironment" in postgres
    assert "& $python -m pytest" in postgres


def test_docker_vex_scan_is_digest_bound_and_uses_an_explicit_author() -> None:
    vex = json.loads((ROOT / "docker" / "qualification-image-vex.openvex.json").read_text())
    script = (ROOT / "tools" / "verify_docker_vex.ps1").read_text(encoding="utf-8")
    statements = {item["vulnerability"]["name"]: item for item in vex["statements"]}

    assert vex["author"] == "Ronin release qualification"
    assert set(statements) == {"CVE-2026-107891", "CVE-2026-119586", "CVE-2026-4738"}
    for statement in statements.values():
        assert statement["status"] == "not_affected"
        assert statement["justification"] == "vulnerable_code_not_present"
        assert len(statement["products"]) == 2
        assert {product["@id"].split("@", maxsplit=1)[0] for product in statement["products"]} == {
            "pkg:docker/ronin",
            "pkg:docker/ronin-probe",
        }
        assert all(
            re.fullmatch(r"pkg:docker/[^@]+@sha256:[0-9a-f]{64}", product["@id"])
            for product in statement["products"]
        )
    musl = statements["CVE-2026-107891"]
    assert "security.alpinelinux.org/vuln/CVE-2026-107891" in musl["impact_statement"]
    assert all(
        product["subcomponents"]
        == [{"@id": "pkg:apk/alpine/musl@1.2.6-r3?os_name=alpine&os_version=3.24"}]
        for product in musl["products"]
    )
    sqlite = statements["CVE-2026-119586"]
    assert "sqlite3 executable" in sqlite["impact_statement"]
    assert "command-line shell" in sqlite["impact_statement"]
    assert all(
        product["subcomponents"]
        == [{"@id": "pkg:apk/alpine/sqlite@3.53.4-r0?os_name=alpine&os_version=3.24"}]
        for product in sqlite["products"]
    )
    zlib = statements["CVE-2026-4738"]
    assert "GDAL" in zlib["impact_statement"]
    assert "libgdal" in zlib["impact_statement"]
    assert all(
        product["subcomponents"]
        == [{"@id": "pkg:apk/alpine/zlib@1.3.2-r1?os_name=alpine&os_version=3.24"}]
        for product in zlib["products"]
    )
    assert "--vex-author $author" in script
    assert "[IO.Path]::IsPathRooted($VexPath)" in script
    assert '"-VexPath must name an existing VEX file."' in script
    assert "valid immutable registry digest or local image ID" in script
    assert "Docker Scout version" in script
    assert "worktree_clean = ($gitStatus.Count -eq 0)" in script
    assert '"qualification-image-vex.openvex.json"' in script
    assert "Copy-Item -LiteralPath $vexFullPath -Destination $vexEvidence" in script
    assert "vex_sha256 = $vexSha256" in script
    assert "local-image-config-digest" in script
    assert '"CVE-2026-107891", "CVE-2026-119586", "CVE-2026-4738"' in script
    assert "if ($productMatches.Count -ne 1)" in script
    assert "pkg:apk/alpine/sqlite@3.53.4-r0?os_name=alpine&os_version=3.24" in script
    assert "pkg:apk/alpine/zlib@1.3.2-r1?os_name=alpine&os_version=3.24" in script
    assert "if ($rawFindings.Count -ne $expectedFindings.Count)" in script
    assert "if ($vexFindings.Count -ne 0)" in script
    assert "security_review_required = $true" in script
    assert "release_security_gate_closed = $false" in script
    assert "VEX scan" in script


def test_gitleaks_allowlist_is_limited_to_reviewed_historical_fingerprints() -> None:
    entries = (ROOT / ".gitleaksignore").read_text(encoding="utf-8").splitlines()

    assert len(entries) == 4
    assert all(
        re.fullmatch(r"[0-9a-f]{40}:[^:*]+:generic-api-key:[1-9][0-9]*", entry) for entry in entries
    )
    assert {entry.split(":", maxsplit=3)[1] for entry in entries} == {
        "tools/run_docker_qualification.ps1",
        "tests/test_s3_json_connector.py",
        "tests/e2e/test_v01_journey.py",
    }


def test_local_docker_qualification_runs_real_s3_profiles_with_isolated_cleanup() -> None:
    script = (ROOT / "tools" / "run_docker_qualification.ps1").read_text(encoding="utf-8")
    compose = (ROOT / "examples/cloud-studio/compose.floci.yaml").read_text(encoding="utf-8")

    assert '$flociProject = "ronin-docker-s3-' in script
    assert '$env:RONIN_TEST_S3_ENDPOINT = "http://127.0.0.1:$flociPort"' in script
    assert "tests/integration/test_s3_json_connector_real.py" in script
    assert "tests/integration/test_ml_s3_artifact_store_real.py" in script
    assert "down --volumes --remove-orphans" in script
    assert '"127.0.0.1:${RONIN_FLOCI_PORT:-4566}:4566"' in compose


def test_local_docker_qualification_runs_real_azure_blob_profile_with_azurite() -> None:
    script = (ROOT / "tools" / "run_docker_qualification.ps1").read_text(encoding="utf-8")
    compose = (ROOT / "examples/connectors/compose.azurite.yaml").read_text(encoding="utf-8")

    assert '$azuriteProject = "ronin-docker-azure-' in script
    assert '"RONIN_AZURITE_ACCOUNT_KEY"' in script
    assert "tests/integration/test_azure_blob_connector_real.py" in script
    assert "down --volumes --remove-orphans" in script
    assert "mcr.microsoft.com/azure-storage/azurite:3.35.0@sha256:" in compose
    assert '"127.0.0.1:${RONIN_AZURITE_PORT:-10000}:10000"' in compose


def test_release_artifact_targets_accept_external_evidence_paths() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    check_target = next(line for line in makefile.splitlines() if line.startswith("check:"))
    assert "dependency-surfaces-check" in check_target
    assert "agent-skills-validate" in check_target
    assert "AGENT_SKILLS_OUTPUT ?=" in makefile
    assert "$(AGENT_SKILLS_OUTPUT)" in makefile
    assert "RONIN_QUALIFICATION_OUTPUT ?=" in makefile
    assert makefile.count("$(RONIN_QUALIFICATION_OUTPUT)") >= 4


def test_browser_test_targets_validate_locked_dependencies_without_clean_reinstall() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    helper = (ROOT / "web-tests" / "ensure-dependencies.mjs").read_text(encoding="utf-8")

    assert "web-test-deps:" in makefile
    assert makefile.count("web-test-deps") >= 5
    assert "npm --prefix web-tests ci" not in makefile
    assert ".ronin-test-lock.sha256" in helper
    assert "package-lock.json" in helper
    assert "runNpm(['ls', '--depth=0']" in helper
    assert "runNpm(['ci'])" in helper
    assert "chromium.executablePath()" in helper
    assert "playwright', 'install', 'chromium" in helper


def test_playwright_outputs_are_candidate_scoped_and_ci_is_not_required() -> None:
    config = (ROOT / "web-tests" / "playwright.config.mjs").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_OUTPUT_DIR" in config
    assert "PLAYWRIGHT_HTML_OUTPUT_DIR" in config
    assert "PLAYWRIGHT_JUNIT_OUTPUT_FILE" in config
    assert "process.env.CI" not in config


def test_live_browser_suite_requires_real_services_and_emits_api_evidence() -> None:
    package = (ROOT / "web-tests" / "package.json").read_text(encoding="utf-8")
    preflight = (ROOT / "web-tests" / "tests" / "live-preflight.mjs").read_text(encoding="utf-8")
    live_suite = (ROOT / "web-tests" / "tests" / "product-live.spec.mjs").read_text(
        encoding="utf-8"
    )
    helper = (ROOT / "web-tests" / "tests" / "live-support.mjs").read_text(encoding="utf-8")

    assert "live-preflight.mjs" in package
    assert '"test": "playwright test --grep-invert \\"[Ll]ive\\""' in package
    assert '"test:live"' in package
    assert "tests/ingestion-live.spec.mjs" in package
    assert "tests/product-live.spec.mjs" in package
    assert "assertLiveConfiguration" in preflight
    assert "RONIN_LIVE_API_TOKEN" in helper
    assert "must be outside the repository" in preflight
    assert "route ${route.id}" in live_suite
    assert "UI-only: no API route declared" in live_suite
    assert "route ${route.id} has no published API contract" in live_suite
    assert "authorization: authorization ? 'present' : 'missing'" in helper
    assert "await fetch(upstreamUrl" in helper
    assert "x-ronin-request-id" in helper


def test_live_postgres_seed_is_repeatable_and_keeps_existing_database_data() -> None:
    seed = (ROOT / "web-tests" / "fixtures" / "live-postgres.sql").read_text(encoding="utf-8")
    script = (ROOT / "tools" / "seed_live_postgres.ps1").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS" in seed
    assert "ON CONFLICT" in seed
    assert "DROP TABLE" not in seed
    assert "live-postgres.sql" in script
    assert "verification failed" in script


def test_live_product_runner_isolated_and_reports_all_active_routes() -> None:
    script = (ROOT / "tools" / "run_live_product_qualification.ps1").read_text(encoding="utf-8")

    assert "Get-FreeLoopbackPort" in script
    assert script.index("docker image inspect $WorkerImage") < script.index(
        "docker compose -p $composeProject --profile qualification-streaming up -d --wait"
    )
    assert script.index("docker image inspect $WorkerImage") < script.index(
        "Get-LivePythonEnvironment $hostPython $testRequirements"
    )
    assert (
        "docker compose -p $composeProject --profile qualification-streaming up -d --wait" in script
    )
    assert "docker compose -p $composeProject down -v --remove-orphans" in script
    assert "RONIN_LIVE_API_TRAFFIC_OUTPUT" in script
    assert '"RONIN_STUDIO_E2E_TOKEN"' in script
    assert "$env:RONIN_STUDIO_E2E_TOKEN = $env:RONIN_TOKEN" in script
    assert "Scripts\\python.exe" in script
    assert "requirements-test.lock" in script
    assert "pip freeze --all" in script
    assert "Get-LivePythonEnvironment" in script
    assert "--no-compile --require-hashes -r $RequirementsLock" in script
    assert "qualification-cache\\python" in script
    assert "pip check" in script
    assert ".ronin-qualification-cache.json" in script
    assert "FileShare]::None" in script
    assert (
        '"PYTHONPATH", "RONIN_LIVE_PYTHON", "FORCE_COLOR", "npm_config_color", '
        '"NO_COLOR", "DEBUG_COLORS"'
    ) in script
    assert "$env:FORCE_COLOR = $null" in script
    assert '$env:npm_config_color = "false"' in script
    assert "$env:NO_COLOR = $null" in script
    assert '$env:DEBUG_COLORS = "0"' in script
    assert '$env:OMP_NUM_THREADS = "1"' in script
    assert '$env:OPENBLAS_NUM_THREADS = "1"' in script
    assert '$env:MKL_NUM_THREADS = "1"' in script
    assert '$env:BLIS_NUM_THREADS = "1"' in script
    assert '$env:NUMEXPR_NUM_THREADS = "1"' in script
    assert "tests/live-runs.spec.mjs" in script
    assert "Get-Command pwsh -ErrorAction SilentlyContinue" in script
    assert "Get-Command powershell -ErrorAction Stop" in script
    assert "& $seedPowerShell.Source -NoLogo -NoProfile" in script
    assert "Invoke-WebRequest $env:RONIN_STUDIO_E2E_URL -UseBasicParsing -TimeoutSec 2" in script
    assert "[System.Collections.Generic.Queue[object]]::new()" in script
    assert "$routeQueue.Enqueue($nestedRouteEntry)" in script
    assert "[System.Collections.Generic.HashSet[string]]::new" in script
    assert "$caseNameSet.Contains($expectedRouteCase)" in script
    assert "$trafficQueue.Enqueue($trafficDocument)" in script
    assert "$traffic.Add($trafficEntry)" in script
    assert "$serverErrors.Add($trafficEvent)" in script
    assert "must be outside the checkout" in script
    assert "missingRoutes" in script
    assert "requires 30 cases" in script
    assert "requires -WorkerImage" in script
    assert "$env:RONIN_IMAGE = $workerImageId" in script
    assert '"live-worker.stdout.log"' in script
    assert "testcase/skipped" in script
    assert "ensure-dependencies.mjs" in script
    assert "web-test-dependency-cache.json" in script
    assert "Playwright dependency cache" in script
    assert "qualification-summary.json" in script
    assert "failurePhase" in script
    assert "realServices" in script
    assert "apiTraffic" in script


def test_semantic_live_diagnostic_skips_unrelated_postgres_and_kafka_containers() -> None:
    script = (ROOT / "tools" / "run_live_product_qualification.ps1").read_text(encoding="utf-8")
    seed = (ROOT / "tools" / "seed_live_studio.py").read_text(encoding="utf-8")
    live = (ROOT / "web-tests" / "tests" / "product-live.spec.mjs").read_text(encoding="utf-8")

    assert '$semanticOnlyDiagnostic = $TestGrep -eq "semantic"' in script
    assert (
        'Write-Output "$diagnosticName-only diagnostic: SQLite product routes do not require '
        'PostgreSQL or Kafka containers."' in script
    )
    assert (
        "$sqliteOnlyDiagnostic = $semanticOnlyDiagnostic -or $mlOnlyDiagnostic -or "
        "$syntheticOnlyDiagnostic -or $qualityOnlyDiagnostic" in script
    )
    assert "$postgresStarted = -not ($streamingOnlyDiagnostic -or $sqliteOnlyDiagnostic)" in script
    assert "$kafkaStarted = -not $sqliteOnlyDiagnostic" in script
    assert (
        "if (-not $sqliteOnlyDiagnostic) {\n        & $python -m tools.seed_live_streaming"
        in script
    )
    assert (
        "$env:RONIN_LIVE_REQUIRE_POSTGRES = if ($streamingOnlyDiagnostic -or $sqliteOnlyDiagnostic)"
    ) in script
    assert "& $python -m tools.seed_live_studio --semantic-only" in script
    assert '"RONIN_SQL_PARQUET_ROOT"' in script
    assert '$env:RONIN_SQL_PARQUET_ROOT = Join-Path $liveDataDir "sql-parquet"' in script
    assert '"--semantic-only"' in seed
    assert "write_parquet_rows(" in seed
    assert '"live_orders.parquet"' in seed
    assert "Execute dashboard" in live
    assert "semantic/dashboards/live_overview/execute" in live


def test_ml_live_diagnostic_skips_unrelated_postgres_and_kafka_containers() -> None:
    script = (ROOT / "tools" / "run_live_product_qualification.ps1").read_text(encoding="utf-8")
    live = (ROOT / "web-tests" / "tests" / "product-live.spec.mjs").read_text(encoding="utf-8")

    assert '$mlOnlyDiagnostic = $TestGrep -eq "mlstudio"' in script
    assert "$composeStarted = -not $sqliteOnlyDiagnostic" in script
    assert '"Machine Learning Studio"' in script
    assert (
        "run Machine Learning Studio browser journey against isolated SQLite and real Ronin APIs"
        in script
    )
    assert "loads and reaches the live API" in live
    assert "if (-not $sqliteOnlyDiagnostic) {" in script


def test_synthetic_live_diagnostic_uses_sqlite_and_exercises_real_generation_export() -> None:
    script = (ROOT / "tools" / "run_live_product_qualification.ps1").read_text(encoding="utf-8")
    live = (ROOT / "web-tests" / "tests" / "product-live.spec.mjs").read_text(encoding="utf-8")

    assert '$syntheticOnlyDiagnostic = $TestGrep -eq "synthetic"' in script
    assert "$composeStarted = -not $sqliteOnlyDiagnostic" in script
    assert "$postgresStarted = -not ($streamingOnlyDiagnostic -or $sqliteOnlyDiagnostic)" in script
    assert "$kafkaStarted = -not $sqliteOnlyDiagnostic" in script
    assert "& $python -m tools.seed_live_studio --workspace-only" in script
    assert (
        "Synthetic Data Studio generation/export against isolated SQLite and real Ronin APIs"
        in script
    )
    assert "} else if (route.id === 'synthetic') {" in live
    assert "const generatePath = '/v1/synthetic-data-studio/generate';" in live
    assert "const exportPath = '/v1/synthetic-data-studio/export';" in live
    assert "expect(exportPayload.content.trim().split('\\n')).toHaveLength(10);" in live


def test_quality_live_diagnostic_uses_sqlite_and_checks_warn_outcomes() -> None:
    script = (ROOT / "tools" / "run_live_product_qualification.ps1").read_text(encoding="utf-8")
    live = (ROOT / "web-tests" / "tests" / "product-live.spec.mjs").read_text(encoding="utf-8")

    assert '$qualityOnlyDiagnostic = $TestGrep -eq "quality"' in script
    assert "$postgresStarted = -not ($streamingOnlyDiagnostic -or $sqliteOnlyDiagnostic)" in script
    assert (
        "} elseif ($qualityOnlyDiagnostic) {\n        & $python -m tools.seed_live_studio" in script
    )
    assert (
        "run Quality Studio passing and blocking checks against isolated SQLite and real Ronin APIs"
        in script
    )
    assert "} else if (route.id === 'quality') {" in live
    assert "Quality operation failed." in live
    assert "call.status === 409 && call.outcome === 'WARN'" in live


def test_live_runner_precompiles_only_ronin_source_modules() -> None:
    script = (ROOT / "tools" / "run_live_product_qualification.ps1").read_text(encoding="utf-8")

    assert 'Set-QualificationPhase "precompile Ronin Python sources"' in script
    assert "& $python -m compileall -q" in script
    assert 'Join-Path $repoRoot "python"' in script
    assert 'Join-Path $repoRoot "tools/seed_live_studio.py"' in script
    assert "third-party dependencies excluded" in script


def test_live_runner_reuses_only_locked_dependencies_and_keeps_services_per_run() -> None:
    script = (ROOT / "tools" / "run_live_product_qualification.ps1").read_text(encoding="utf-8")

    # The expensive Python/Node packages may be reused only when their lock
    # inputs match; databases, API server state and browser evidence stay run-scoped.
    assert '"requirements=$lockHash"' in script
    assert '"project=$projectHash"' in script
    assert '"version=$pythonVersion"' in script
    assert '"repository=$repoRoot"' in script
    assert '$composeProject = "ronin-live-$($candidateSha.Substring(0, 8))-$runId"' in script
    assert "$liveDataDir = Join-Path $tempRoot $composeProject" in script
    assert "$evidenceFiles.Traffic" in script
    assert "Live API traffic evidence is empty" in script
    assert "structured application HTTP log" in script


def test_release_runners_distinguish_dirty_diagnostics_from_candidate_evidence() -> None:
    for name in (
        "run_live_product_qualification.ps1",
        "run_docker_qualification.ps1",
        "run_postgres_test_suite.ps1",
    ):
        script = (ROOT / "tools" / name).read_text(encoding="utf-8")
        assert "status --porcelain --untracked-files=all" in script
        assert "AllowDirtyWorktree" in script
        assert "DIRTY-WORKTREE DIAGNOSTIC" in script
        assert "CLEAN-CANDIDATE QUALIFICATION" in script
        assert "not release-candidate evidence" in script


def test_postgres_runner_isolates_container_and_externalizes_evidence() -> None:
    script = (ROOT / "tools" / "run_postgres_test_suite.ps1").read_text(encoding="utf-8")
    timing_plugin = (ROOT / "tools" / "pytest_timing_report.py").read_text(encoding="utf-8")
    assert "postgres:16.4-alpine" in script
    assert "127.0.0.1:${port}:5432" in script
    assert "PostgreSQL test evidence must be outside the checkout" in script
    assert '"pytest-output.log"' in script
    assert "Tee-Object -FilePath $pytestOutput" in script
    assert '"postgresql://<redacted>"' in script
    assert "docker rm --force --volumes $containerName" in script
    assert '"--durations=15", "--ignore=tests/perf"' in script
    assert '$pytestArguments = @("-v") + $pytestArguments' in script
    assert "[string]$TestPath" in script
    assert "TestFilter" in script
    assert "GetRelativePath($repoRoot, $testPathFull)" in script
    assert "if ($TestFilter) {" in script
    assert "Filtered PostgreSQL diagnostic" in script
    assert "-LocalOnly" in script
    assert "requires an explicit test file path" in script
    assert "integration|e2e|perf" in script
    assert 'SetEnvironmentVariable($name, $null, "Process")' in script
    assert "MarkerExpression" in script
    assert '"-p", "tools.pytest_timing_report"' in script
    assert '"pytest-timings.json"' in script
    assert '"runner-timings.json"' in script
    assert "python_environment_seconds" in script
    assert "postgres_startup_seconds" in script
    assert "pytest_wall_seconds" in script
    assert "cleanup_seconds" in script
    assert 'cleanup_status = "not-required"' in script
    assert 'cleanup_status = "failed"' in script
    assert 'status = "incomplete"' in script
    assert "test_exit_code = $testResult" in script
    assert "$phaseTimings.failure = $_.Exception.Message" in script
    assert '$phaseTimings.status = if ($testResult -eq 0) { "passed" } else { "failed" }' in script
    assert "The run is incomplete and must not be treated as a pass." in script
    assert 'if ($phaseTimings.cleanup_status -eq "failed")' in script
    assert "Run result: INCOMPLETE (cleanup failed)" in script
    assert "RONIN_TEST_EXECUTION_MODE" in script
    assert "RONIN_TEST_SELECTION" in script
    assert "RONIN_TEST_COVERAGE" in script
    assert "RONIN_TEST_SOURCE_COMMIT" in script
    assert "RONIN_TEST_WORKTREE_CLEAN" in script
    assert "RONIN_TEST_QUALIFICATION_MODE" in script
    assert "source_commit = $null" in script
    assert "worktree_clean = $null" in script
    assert '"source_commit": os.environ.get("RONIN_TEST_SOURCE_COMMIT", "unknown")' in timing_plugin
    assert (
        '"worktree_clean": os.environ.get("RONIN_TEST_WORKTREE_CLEAN", "unknown")' in timing_plugin
    )
    assert "selected passed" in script
    assert "unrelated collection skips" in script
    assert "selected no executable test cases" in script
    assert "Coverage collection is disabled for speed" in script
    assert '$pytestArguments += @("--cov", "--cov-branch", "--cov-report=")' in script
    assert (
        'throw "$runKind failed with exit code $testResult. See $pytestOutput and $report"'
        in script
    )
    assert (
        "Diagnostic only: rerun without -TestPath, -TestFilter, -MarkerExpression, or -LocalOnly"
        in script
    )
    assert 'Write-Output "Skip reason: $skipReason"' in script
    assert "if (-not $isFiltered -and -not $skipNode -and -not $failureNode) { continue }" in script
    assert "See $pytestOutput and $report" in script


def test_docker_image_normalizes_windows_line_endings_for_linux_entrypoint() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    probe = (ROOT / "docker" / "Dockerfile.probe").read_text(encoding="utf-8")

    assert "sed -i 's/\\r$//' /usr/local/bin/ronin-container-entrypoint" in dockerfile
    assert "sed -i 's/\\r$//' /tmp/apk-runtime.lock" in dockerfile
    assert "sed -i 's/\\r$//' /tmp/apk-probe.lock" in probe


def test_runtime_images_pin_current_bases_and_hash_lock_python_dependencies() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    probe = (ROOT / "docker" / "Dockerfile.probe").read_text(encoding="utf-8")
    runtime_lock = (ROOT / "docker" / "requirements-runtime.lock").read_text(encoding="utf-8")
    pip_lock = (ROOT / "docker" / "pip-bootstrap.lock").read_text(encoding="utf-8")
    apk_runtime_lock = (ROOT / "docker" / "apk-runtime.lock").read_text(encoding="utf-8")
    apk_probe_lock = (ROOT / "docker" / "apk-probe.lock").read_text(encoding="utf-8")

    python_image = (
        "python:3.11-alpine3.24@sha256:"
        "09d17d5e4c16d0a7a1eea690bcb7c6ab8616b211f8421e429e97c1bef5bd0ed2"
    )
    docker_cli = (
        "docker:29.9.2-cli-alpine3.24@sha256:"
        "5e6baf67325a79f64ed3bed6863954d5e05d0f3d4e57cbdb14809346814bbfdb"
    )

    assert f"ARG PYTHON_IMAGE={python_image}" in dockerfile
    assert f"FROM {docker_cli} AS docker-cli" in dockerfile
    assert "apk upgrade" not in dockerfile + probe
    assert "COPY docker/apk-runtime.lock /tmp/apk-runtime.lock" in dockerfile
    assert "apk add --no-cache $(cat /tmp/apk-runtime.lock)" in dockerfile
    assert "--require-hashes -r /tmp/pip-bootstrap.lock" in dockerfile
    assert "pip==26.2.2" in pip_lock
    assert "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" in pip_lock
    assert "apt-get" not in dockerfile + probe
    entrypoint = (ROOT / "docker" / "container-entrypoint.sh").read_text(encoding="utf-8")
    assert 'exec su-exec "$RONIN_UID" "$@"' in entrypoint
    assert "--require-hashes -r /tmp/requirements-runtime.lock" in dockerfile
    assert "--no-deps /tmp/wheels/*.whl" in dockerfile
    assert "pip uninstall --yes pip setuptools wheel jaraco.context" in dockerfile
    assert f"ARG PYTHON_IMAGE={python_image}" in probe
    assert f"FROM {docker_cli} AS docker-cli" in probe
    assert "COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker" in probe
    assert "python -m pip uninstall --yes pip setuptools wheel jaraco.context" in probe
    assert "COPY docker/apk-probe.lock /tmp/apk-probe.lock" in probe
    assert "apk add --no-cache $(cat /tmp/apk-probe.lock)" in probe
    assert "--require-hashes -r /tmp/pip-bootstrap.lock" in probe
    assert "apt-get" not in probe
    assert "RUN git config --system --add safe.directory '*'" in probe
    assert "GIT_CONFIG_KEY_0" not in probe
    assert "psycopg==3.3.6" in runtime_lock
    assert "psycopg-binary==3.3.6" in runtime_lock
    assert "tzdata==2026.4" in runtime_lock
    assert "--hash=sha256:" in runtime_lock
    for lock, expected_count in ((apk_runtime_lock, 19), (apk_probe_lock, 18)):
        packages = [line for line in lock.splitlines() if line]
        assert len(packages) == expected_count
        assert len(packages) == len(set(packages))
        assert all("=" in package for package in packages)
        assert all(
            package.rsplit("=", maxsplit=1)[1].endswith(("-r0", "-r1", "-r2", "-r3"))
            for package in packages
        )


def test_ci_docker_qualification_workflow_is_removed() -> None:
    assert not (ROOT / ".github" / "workflows" / "docker-qualification.yml").exists()


def test_dockerhub_publisher_restricts_mutable_aliases() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-dockerhub.yml").read_text(
        encoding="utf-8"
    )

    assert "type: choice" in workflow
    assert "options:" in workflow
    assert "          - dev" in workflow
    assert "          - edge" in workflow
    assert 'case "$ALIAS" in' in workflow
    assert "dev|edge" in workflow
    assert "Refusing non-development Docker alias" in workflow
    assert "${{ inputs.alias }}" in workflow
