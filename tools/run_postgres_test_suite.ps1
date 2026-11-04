param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [string]$TestPath,
    [string]$TestFilter,
    [string]$MarkerExpression,
    [switch]$LocalOnly,
    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runnerWallClock = [Diagnostics.Stopwatch]::StartNew()
$phaseTimings = [ordered]@{
    source_commit = $null
    worktree_clean = $null
    qualification_mode = $null
    execution_mode = $null
    selection = $null
    coverage_enabled = $null
    service_profile = $null
    python_environment_seconds = $null
    postgres_startup_seconds = 0.0
    pytest_wall_seconds = $null
    cleanup_seconds = $null
    cleanup_status = "not-required"
    cleanup_error = $null
    total_wall_seconds = $null
}
$hasSelection = [bool]($TestPath -or $TestFilter -or $MarkerExpression)
if ($LocalOnly -and -not $TestPath) {
    throw "-LocalOnly requires an explicit test file path; keyword or marker selection alone could collect service-backed tests."
}
$checkoutPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$evidenceRoot = [IO.Path]::GetFullPath($EvidenceDirectory)
if (
    $evidenceRoot.Equals($repoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $evidenceRoot.StartsWith($checkoutPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw "PostgreSQL test evidence must be outside the checkout: $evidenceRoot"
}
if (Test-Path -LiteralPath $evidenceRoot) {
    if (@(Get-ChildItem -LiteralPath $evidenceRoot -Force).Count -gt 0) {
        throw "Evidence directory is not empty; use a new unique candidate/run path: $evidenceRoot"
    }
} else {
    New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
}
if ($TestPath) {
    $testPathFull = [IO.Path]::GetFullPath((Join-Path $repoRoot $TestPath))
    if (-not $testPathFull.StartsWith($checkoutPrefix, [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $testPathFull -PathType Leaf)) {
        throw "-TestPath must name an existing test file inside the repository: $TestPath"
    }
    $TestPath = [IO.Path]::GetRelativePath($repoRoot, $testPathFull)
}
if ($LocalOnly -and $TestPath -match '(^|[/\\])(integration|e2e|perf)([/\\]|$)') {
    throw "-LocalOnly cannot target integration, e2e, or perf test paths; use the corresponding real-service runner."
}
if ($LocalOnly -and $MarkerExpression -match '(?i)(^|\s|\()integration(\s|\)|$)') {
    throw "-LocalOnly cannot select the integration marker; use the isolated PostgreSQL runner for real-service tests."
}

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return $listener.LocalEndpoint.Port
    } finally {
        $listener.Stop()
    }
}

$candidateSha = (git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $candidateSha -notmatch '^[0-9a-f]{40}$') {
    throw "Could not identify the exact source candidate."
}
$workingTreeStatus = @(git -C $repoRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw "Could not determine whether the worktree is clean." }
if ($workingTreeStatus.Count -gt 0 -and -not $AllowDirtyWorktree) {
    throw "Refusing release qualification with a dirty worktree. Use -AllowDirtyWorktree only for diagnostics; its evidence is not release-candidate evidence."
}
$qualificationMode = if ($workingTreeStatus.Count -gt 0) { "DIRTY-WORKTREE DIAGNOSTIC" } else { "CLEAN-CANDIDATE QUALIFICATION" }
$phaseTimings.source_commit = $candidateSha
$phaseTimings.worktree_clean = ($workingTreeStatus.Count -eq 0)
$phaseTimings.qualification_mode = $qualificationMode
Import-Module (Join-Path $PSScriptRoot "qualification_python.psm1") -Force
$phaseClock = [Diagnostics.Stopwatch]::StartNew()
$python = Get-RoninTestPythonEnvironment -CheckoutRoot $repoRoot
$phaseClock.Stop()
$phaseTimings.python_environment_seconds = [Math]::Round($phaseClock.Elapsed.TotalSeconds, 3)
$runId = [guid]::NewGuid().ToString("N").Substring(0, 10)
$containerName = "ronin-pytest-pg-$($candidateSha.Substring(0, 8))-$runId".ToLowerInvariant()
$port = Get-FreeLoopbackPort
$password = [guid]::NewGuid().ToString("N")
$dsn = "postgresql://ronin:$password@127.0.0.1:$port/ronin_test"
$report = Join-Path $evidenceRoot "pytest-postgres.xml"
$transcript = Join-Path $evidenceRoot "pytest-postgres.log"
$pytestOutput = Join-Path $evidenceRoot "pytest-output.log"
$timingsFile = Join-Path $evidenceRoot "pytest-timings.json"
$coverageFile = Join-Path $evidenceRoot ".coverage"
$savedTimingsPath = [Environment]::GetEnvironmentVariable("RONIN_PYTEST_TIMINGS_PATH", "Process")
$envNames = @(
    "RONIN_TEST_POSTGRES_DSN", "RONIN_POSTGRES_TEST_DSN", "RONIN_CONNECTOR_POSTGRES_DSN",
    "RONIN_POSTGRES_DSN", "COVERAGE_FILE"
)
$postgresDsnEnvNames = @(
    "RONIN_TEST_POSTGRES_DSN", "RONIN_POSTGRES_TEST_DSN", "RONIN_CONNECTOR_POSTGRES_DSN",
    "RONIN_POSTGRES_DSN"
)
$savedEnvironment = @{}
foreach ($name in $envNames) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$executionMetadataNames = @(
    "RONIN_TEST_EXECUTION_MODE", "RONIN_TEST_SELECTION",
    "RONIN_TEST_COVERAGE", "RONIN_TEST_SERVICE_PROFILE", "RONIN_TEST_SOURCE_COMMIT",
    "RONIN_TEST_WORKTREE_CLEAN", "RONIN_TEST_QUALIFICATION_MODE"
)
$savedExecutionMetadata = @{}
foreach ($name in $executionMetadataNames) {
    $savedExecutionMetadata[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$containerStarted = $false
$testResult = 1

Start-Transcript -LiteralPath $transcript -Force | Out-Null
try {
    Write-Output "Source HEAD: $candidateSha"
    Write-Output "Qualification mode: $qualificationMode"
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SOURCE_COMMIT", $candidateSha, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_WORKTREE_CLEAN", [string]($workingTreeStatus.Count -eq 0), "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_QUALIFICATION_MODE", $qualificationMode, "Process")
    if (-not $LocalOnly) {
        [Environment]::SetEnvironmentVariable("RONIN_TEST_EXECUTION_MODE", "postgres-diagnostic-or-full", "Process")
        [Environment]::SetEnvironmentVariable("RONIN_TEST_SERVICE_PROFILE", "isolated-postgres-16.4", "Process")
        $phaseClock.Restart()
        try {
            docker run --detach --name $containerName `
                --publish "127.0.0.1:${port}:5432" `
                --env "POSTGRES_USER=ronin" `
                --env "POSTGRES_PASSWORD=$password" `
                --env "POSTGRES_DB=ronin_test" `
                postgres:16.4-alpine
            if ($LASTEXITCODE -ne 0) { throw "Could not start isolated PostgreSQL 16.4 test container." }
            $containerStarted = $true

            $deadline = (Get-Date).AddSeconds(90)
            do {
                docker exec $containerName pg_isready -U ronin -d ronin_test | Out-Null
                if ($LASTEXITCODE -eq 0) { break }
                Start-Sleep -Milliseconds 500
            } while ((Get-Date) -lt $deadline)
            if ($LASTEXITCODE -ne 0) { throw "The isolated PostgreSQL test container did not become ready." }
        } finally {
            $phaseClock.Stop()
            $phaseTimings.postgres_startup_seconds = [Math]::Round($phaseClock.Elapsed.TotalSeconds, 3)
        }

        foreach ($name in $postgresDsnEnvNames) {
            [Environment]::SetEnvironmentVariable($name, $dsn, "Process")
        }
    }
    if (-not $LocalOnly) { [Environment]::SetEnvironmentVariable("COVERAGE_FILE", $coverageFile, "Process") }

    Write-Output "Candidate: $candidateSha"
    if ($LocalOnly) {
        Write-Output "Local-only diagnostic: no Docker service, PostgreSQL DSN, or coverage instrumentation; this is not PostgreSQL evidence."
        [Environment]::SetEnvironmentVariable("RONIN_TEST_EXECUTION_MODE", "local-only-diagnostic", "Process")
        [Environment]::SetEnvironmentVariable("RONIN_TEST_SERVICE_PROFILE", "none", "Process")
        foreach ($name in $postgresDsnEnvNames) {
            [Environment]::SetEnvironmentVariable($name, $null, "Process")
        }
    } else {
        Write-Output "PostgreSQL: postgres:16.4-alpine at isolated loopback port $port"
    }
    $phaseTimings.execution_mode = [Environment]::GetEnvironmentVariable("RONIN_TEST_EXECUTION_MODE", "Process")
    $phaseTimings.service_profile = [Environment]::GetEnvironmentVariable("RONIN_TEST_SERVICE_PROFILE", "Process")
    $pytestArguments = @(
        "-p", "tools.pytest_timing_report", "--durations=15", "--ignore=tests/perf",
        "--junitxml=$report"
    )
    if ($TestPath) { $pytestArguments += $TestPath }
    if ($TestFilter) {
        $pytestArguments += @("-k", $TestFilter)
    }
    if ($MarkerExpression) { $pytestArguments += @("-m", $MarkerExpression) }
    [Environment]::SetEnvironmentVariable("RONIN_PYTEST_TIMINGS_PATH", $timingsFile, "Process")
    $isFiltered = $hasSelection
    $selectionDescription = @()
    if ($TestPath) { $selectionDescription += "path=$TestPath" }
    if ($TestFilter) { $selectionDescription += "keyword=$TestFilter" }
    if ($MarkerExpression) { $selectionDescription += "marker=$MarkerExpression" }
    if (-not $selectionDescription) { $selectionDescription = @("full-nonperformance-suite") }
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SELECTION", ($selectionDescription -join ";"), "Process")
    if ($isFiltered) {
        $pytestArguments = @("-v") + $pytestArguments
        $selection = if ($TestPath) { "file '$TestPath'" } else { "pytest selection" }
        if ($TestFilter) { $selection += " and -k '$TestFilter'" }
        if ($MarkerExpression) { $selection += " and -m '$MarkerExpression'" }
        if ($LocalOnly) {
            Write-Output "Filtered local-only diagnostic: selected $selection without Docker. Tests that need a service must be run with the corresponding integration runner."
        } else {
            Write-Output "Filtered diagnostic: selected $selection against isolated real PostgreSQL. Coverage collection is disabled for speed; this is not full-suite or full-coverage evidence."
        }
    } else {
        $pytestArguments += @("--cov", "--cov-branch", "--cov-report=")
        [Environment]::SetEnvironmentVariable("RONIN_TEST_COVERAGE", "enabled", "Process")
        Write-Output "Full Python/PostgreSQL scope: all non-performance Python tests, including cases enabled by the isolated PostgreSQL service. The slowest 15 cases and exact outcomes are recorded below."
    }
    if ($isFiltered) { [Environment]::SetEnvironmentVariable("RONIN_TEST_COVERAGE", "disabled", "Process") }
    $phaseTimings.selection = [Environment]::GetEnvironmentVariable("RONIN_TEST_SELECTION", "Process")
    $phaseTimings.coverage_enabled = [Environment]::GetEnvironmentVariable("RONIN_TEST_COVERAGE", "Process")
    $runKind = if ($LocalOnly) { "Filtered local-only diagnostic" } elseif ($isFiltered) { "Filtered PostgreSQL diagnostic" } else { "Full Python/PostgreSQL suite" }
    Push-Location $repoRoot
    $pytestClock = [Diagnostics.Stopwatch]::StartNew()
    try {
        & $python -m pytest @pytestArguments 2>&1 |
            ForEach-Object { "$_" -replace [regex]::Escape($dsn), "postgresql://<redacted>" } |
            Tee-Object -FilePath $pytestOutput
        $testResult = $LASTEXITCODE
    } finally {
        $pytestClock.Stop()
        $phaseTimings.pytest_wall_seconds = [Math]::Round($pytestClock.Elapsed.TotalSeconds, 3)
        Pop-Location
    }
    if ($testResult -ne 0 -and -not (Test-Path -LiteralPath $report)) {
        throw "$runKind failed with exit code $testResult and did not produce a JUnit report. See $pytestOutput"
    }

    [xml]$junit = Get-Content -Raw -LiteralPath $report
    $cases = @($junit.SelectNodes("//testcase"))
    $skipped = $junit.SelectNodes("//testcase/skipped").Count
    $failed = $junit.SelectNodes("//testcase/failure | //testcase/error").Count
    $passed = $cases.Count - $skipped - $failed
    if ($cases.Count -eq 0) {
        throw "PostgreSQL diagnostic selected no tests. Check -TestPath '$TestPath' and -TestFilter '$TestFilter'."
    }
    $junitDuration = 0.0
    foreach ($suite in @($junit.SelectNodes("//testsuite"))) {
        $junitDuration += [double]$suite.GetAttribute("time")
    }
    if ($isFiltered) {
        $collectionSkippedCases = @($cases | Where-Object {
            $skipNode = $_.SelectSingleNode("skipped")
            $skipNode -and $skipNode.GetAttribute("message") -eq "collection skipped"
        })
        $selectedCases = @($cases | Where-Object {
            $skipNode = $_.SelectSingleNode("skipped")
            -not ($skipNode -and $skipNode.GetAttribute("message") -eq "collection skipped")
        })
        $selectedSkipped = @($selectedCases | Where-Object { $_.SelectSingleNode("skipped") }).Count
        $selectedFailed = @($selectedCases | Where-Object { $_.SelectSingleNode("failure | error") }).Count
        $selectedPassed = $selectedCases.Count - $selectedSkipped - $selectedFailed
        if ($selectedCases.Count -eq 0) {
            throw "The filtered PostgreSQL diagnostic selected no executable test cases. Collection-only skips do not count as a pass."
        }
        $selectionMatch = [regex]::Match((Get-Content -Raw -LiteralPath $pytestOutput), 'collected \d+ items? / (?<deselected>\d+) deselected')
        $deselected = if ($selectionMatch.Success) { [int]$selectionMatch.Groups["deselected"].Value } else { 0 }
        Write-Output ("{0}: {1}/{2} selected passed, {3} selected skipped, {4} selected failed, {5} deselected, {6} unrelated collection skips; pytest {7}s." -f `
            $runKind, `
            $selectedPassed, $selectedCases.Count, $selectedSkipped, $selectedFailed, $deselected, $collectionSkippedCases.Count, [Math]::Round($junitDuration, 2))
    } else {
        Write-Output ("{0}: {1}/{2} passed, {3} skipped, {4} failed; pytest {5}s." -f `
            $runKind, $passed, $cases.Count, $skipped, $failed, [Math]::Round($junitDuration, 2))
    }
    foreach ($case in $cases) {
        $skipNode = $case.SelectSingleNode("skipped")
        $failureNode = $case.SelectSingleNode("failure | error")
        if (-not $isFiltered -and -not $skipNode -and -not $failureNode) { continue }
        $outcome = if ($skipNode) { "SKIP" } elseif ($failureNode) { "FAIL" } else { "PASS" }
        Write-Output ("{0}: {1}::{2}" -f $outcome, $case.GetAttribute("classname"), $case.GetAttribute("name"))
        if ($skipNode) {
            $skipReason = $skipNode.GetAttribute("message")
            if (-not $skipReason) { $skipReason = $skipNode.InnerText }
            Write-Output "Skip reason: $skipReason"
        }
        if ($failureNode) { Write-Output "Failure: $($failureNode.InnerText)" }
    }
    if ($testResult -ne 0) { throw "$runKind failed with exit code $testResult. See $pytestOutput and $report" }
    if ($isFiltered) {
        Write-Output "Diagnostic only: rerun without -TestPath, -TestFilter, -MarkerExpression, or -LocalOnly for the complete Python/PostgreSQL suite and coverage."
    }
    Write-Output "Evidence: $evidenceRoot"
    Write-Output "Pytest console output: $pytestOutput"
} finally {
    $cleanupClock = [Diagnostics.Stopwatch]::StartNew()
    if ($containerStarted) {
        docker rm --force --volumes $containerName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $phaseTimings.cleanup_status = "failed"
            $phaseTimings.cleanup_error = "Could not remove isolated PostgreSQL container '$containerName' (docker exit $LASTEXITCODE)."
            $testResult = 1
            Write-Warning "$($phaseTimings.cleanup_error) The run is incomplete and must not be treated as a pass."
        } else {
            $phaseTimings.cleanup_status = "succeeded"
        }
    }
    foreach ($name in $envNames) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
    }
    [Environment]::SetEnvironmentVariable("RONIN_PYTEST_TIMINGS_PATH", $savedTimingsPath, "Process")
    foreach ($name in $executionMetadataNames) {
        [Environment]::SetEnvironmentVariable($name, $savedExecutionMetadata[$name], "Process")
    }
    $cleanupClock.Stop()
    $phaseTimings.cleanup_seconds = [Math]::Round($cleanupClock.Elapsed.TotalSeconds, 3)
    $phaseTimings.total_wall_seconds = [Math]::Round($runnerWallClock.Elapsed.TotalSeconds, 3)
    $phaseTimings | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidenceRoot "runner-timings.json") -Encoding utf8
    if ($phaseTimings.cleanup_status -eq "failed") {
        Write-Output "Run result: INCOMPLETE (cleanup failed); see runner-timings.json."
    }
    Stop-Transcript | Out-Null
}

exit $testResult
