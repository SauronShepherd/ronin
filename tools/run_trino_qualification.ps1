param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [string]$ImageRef = "trinodb/trino@sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f",
    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$repoPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$evidenceRoot = [IO.Path]::GetFullPath($EvidenceDirectory)
if (
    $evidenceRoot.Equals($repoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $evidenceRoot.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw "Trino qualification evidence must be outside the checkout: $evidenceRoot"
}
if (Test-Path -LiteralPath $evidenceRoot) {
    if (@(Get-ChildItem -LiteralPath $evidenceRoot -Force).Count -gt 0) {
        throw "Evidence directory is not empty; use a new unique run path: $evidenceRoot"
    }
} else {
    New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
}

$candidateSha = (git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $candidateSha -notmatch '^[0-9a-f]{40}$') {
    throw "Could not identify the source revision."
}
$workingTreeStatus = @(git -C $repoRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw "Could not inspect worktree cleanliness." }
if ($workingTreeStatus.Count -gt 0 -and -not $AllowDirtyWorktree) {
    throw "Refusing qualification with a dirty worktree; use -AllowDirtyWorktree for diagnostics only."
}
$qualificationMode = if ($workingTreeStatus.Count -eq 0) { "CLEAN-CANDIDATE QUALIFICATION" } else { "DIRTY-WORKTREE DIAGNOSTIC" }
if ($ImageRef -notmatch '^trinodb/trino@sha256:[0-9a-f]{64}$') {
    throw "ImageRef must be a digest-pinned trinodb/trino image."
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

function Save-ContainerLogs {
    param(
        [Parameter(Mandatory = $true)] [string]$Name,
        [Parameter(Mandatory = $true)] [string]$Path
    )
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Trino emits JVM warnings on stderr even when the service is healthy.
        # Capture both streams without turning those warnings into a runner error.
        $ErrorActionPreference = "Continue"
        docker logs $Name 2>&1 | Set-Content -LiteralPath $Path -Encoding utf8
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

$port = Get-FreeLoopbackPort
$runId = [guid]::NewGuid().ToString("N").Substring(0, 10)
$containerName = "ronin-trino-qualification-$runId".ToLowerInvariant()
$junitPath = Join-Path $evidenceRoot "trino-junit.xml"
$timingsPath = Join-Path $evidenceRoot "pytest-timings.json"
$transcriptPath = Join-Path $evidenceRoot "qualification.log"
$containerLogPath = Join-Path $evidenceRoot "trino-container.log"
$summaryPath = Join-Path $evidenceRoot "qualification.json"
$expectedTests = @(
    "test_trino_real_prepared_scalar_bindings",
    "test_trino_real_result_byte_budget_accepts_exact_limit_and_rejects_one_byte_less",
    "test_queryflux_worker_runner_real_trino_persists_terminal_evidence"
)
$startedAt = [DateTimeOffset]::UtcNow
$clock = [Diagnostics.Stopwatch]::StartNew()
$serviceStarted = $false
$cleanupStatus = "not-required"
$cleanupError = $null
$testResult = 1
$failureMessage = $null
$junitSummary = $null
$timingSummary = $null
$httpClient = $null
$serviceStartupSeconds = $null
$pytestSeconds = $null
$cleanupSeconds = $null
$oldEnvironment = @{}
$environmentNames = @(
    "RONIN_TRINO_TEST_URL", "RONIN_PYTEST_TIMINGS_PATH", "RONIN_TEST_EXECUTION_MODE",
    "RONIN_TEST_SELECTION", "RONIN_TEST_COVERAGE", "RONIN_TEST_SERVICE_PROFILE",
    "RONIN_TEST_SOURCE_COMMIT", "RONIN_TEST_WORKTREE_CLEAN", "RONIN_TEST_QUALIFICATION_MODE"
)
foreach ($name in $environmentNames) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

Import-Module (Join-Path $PSScriptRoot "qualification_python.psm1") -Force
$python = Get-RoninTestPythonEnvironment -CheckoutRoot $repoRoot
Add-Type -AssemblyName System.Net.Http
Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
try {
    Write-Output "Source HEAD: $candidateSha"
    Write-Output "Qualification mode: $qualificationMode"
    Write-Output "Trino image: $ImageRef"
    docker run --detach --name $containerName --publish "127.0.0.1:${port}:8080" $ImageRef
    if ($LASTEXITCODE -ne 0) { throw "Could not start the pinned Trino container." }
    $serviceStarted = $true

    $serviceStartupClock = [Diagnostics.Stopwatch]::StartNew()
    $deadline = (Get-Date).AddMinutes(4)
    $serverInfo = $null
    $httpClient = [System.Net.Http.HttpClient]::new()
    $httpClient.Timeout = [TimeSpan]::FromSeconds(3)
    do {
        $response = $null
        try {
            $response = $httpClient.GetAsync("http://127.0.0.1:${port}/v1/info").GetAwaiter().GetResult()
            if ($response.IsSuccessStatusCode) {
                $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
                $serverInfo = $responseBody | ConvertFrom-Json
                if (
                    $serverInfo.starting -eq $false -and
                    $serverInfo.state -eq "ACTIVE" -and
                    $serverInfo.nodeVersion.version -eq "484"
                ) { break }
            }
            $serverInfo = $null
        } catch {
            $serverInfo = $null
        } finally {
            if ($response) { $response.Dispose() }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    $serviceStartupClock.Stop()
    $serviceStartupSeconds = [Math]::Round($serviceStartupClock.Elapsed.TotalSeconds, 3)
    $httpClient.Dispose()
    $httpClient = $null
    if ($null -eq $serverInfo) {
        Save-ContainerLogs -Name $containerName -Path $containerLogPath
        throw "Pinned Trino did not become ACTIVE at version 484 within four minutes."
    }
    Write-Output "Trino ready: version $($serverInfo.nodeVersion.version), state $($serverInfo.state)"

    [Environment]::SetEnvironmentVariable("RONIN_TRINO_TEST_URL", "http://127.0.0.1:${port}/", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_PYTEST_TIMINGS_PATH", $timingsPath, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_EXECUTION_MODE", "trino-local-diagnostic", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SELECTION", "tests/integration/test_query_engine_trino_real.py", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_COVERAGE", "disabled", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SERVICE_PROFILE", $ImageRef, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SOURCE_COMMIT", $candidateSha, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_WORKTREE_CLEAN", [string]($workingTreeStatus.Count -eq 0), "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_QUALIFICATION_MODE", $qualificationMode, "Process")

    Push-Location $repoRoot
    $pytestClock = [Diagnostics.Stopwatch]::StartNew()
    try {
        & $python -m pytest -q -p tools.pytest_timing_report "--junitxml=$junitPath" tests/integration/test_query_engine_trino_real.py
        $testResult = $LASTEXITCODE
    } finally {
        $pytestClock.Stop()
        $pytestSeconds = [Math]::Round($pytestClock.Elapsed.TotalSeconds, 3)
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath $junitPath) -or -not (Test-Path -LiteralPath $timingsPath)) {
        throw "Trino pytest did not produce both JUnit and timing evidence."
    }

    [xml]$junit = Get-Content -Raw -LiteralPath $junitPath
    $cases = @($junit.SelectNodes("//testcase"))
    $names = @($cases | ForEach-Object { $_.GetAttribute("name") })
    $skipped = @($cases | Where-Object { $_.SelectSingleNode("skipped") }).Count
    $failed = @($cases | Where-Object { $_.SelectSingleNode("failure | error") }).Count
    $missingTests = @($expectedTests | Where-Object { $_ -notin $names })
    $unexpectedTests = @($names | Where-Object { $_ -notin $expectedTests })
    $junitSummary = [ordered]@{
        expected = $expectedTests.Count
        collected = $cases.Count
        passed = $cases.Count - $skipped - $failed
        skipped = $skipped
        failed = $failed
        missing = $missingTests.Count
        unexpected = $unexpectedTests.Count
    }
    $timingReport = Get-Content -Raw -LiteralPath $timingsPath | ConvertFrom-Json
    $timingSummary = $timingReport.summary
    if (
        $testResult -ne 0 -or $cases.Count -ne $expectedTests.Count -or
        $skipped -ne 0 -or $failed -ne 0 -or $missingTests.Count -gt 0 -or
        $unexpectedTests.Count -gt 0 -or $timingSummary.selected -ne $expectedTests.Count -or
        $timingSummary.executed -ne $expectedTests.Count
    ) {
        throw "Trino qualification is incomplete: inspect JUnit, timings and test output."
    }
    Write-Output ("Trino real-service tests: {0}/{1} passed, 0 skipped/failed." -f $junitSummary.passed, $junitSummary.expected)
} catch {
    $failureMessage = $_.Exception.Message
    $testResult = 1
    Write-Output "Qualification error: $failureMessage"
} finally {
    $cleanupClock = [Diagnostics.Stopwatch]::StartNew()
    if ($httpClient) {
        $httpClient.Dispose()
        $httpClient = $null
    }
    if ($serviceStarted) {
        Save-ContainerLogs -Name $containerName -Path $containerLogPath
        docker rm --force --volumes $containerName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $cleanupStatus = "failed"
            $cleanupError = "Could not remove Trino container '$containerName'."
            $testResult = 1
        } else {
            $cleanupStatus = "succeeded"
        }
    }
    $cleanupClock.Stop()
    $cleanupSeconds = [Math]::Round($cleanupClock.Elapsed.TotalSeconds, 3)
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], "Process")
    }
    $clock.Stop()
    $summary = [ordered]@{
        schema = "ronin.trino-qualification/v1"
        source_commit = $candidateSha
        worktree_clean = ($workingTreeStatus.Count -eq 0)
        qualification_mode = $qualificationMode
        service = [ordered]@{
            image = $ImageRef
            version = if ($serverInfo) { $serverInfo.nodeVersion.version } else { $null }
            started = $serviceStarted
        }
        selection = $expectedTests
        tests = $junitSummary
        timing_summary = $timingSummary
        phases_seconds = [ordered]@{
            service_startup = $serviceStartupSeconds
            pytest = $pytestSeconds
            cleanup = $cleanupSeconds
        }
        test_exit_code = $testResult
        cleanup_status = $cleanupStatus
        cleanup_error = $cleanupError
        failure = $failureMessage
        elapsed_seconds = [Math]::Round($clock.Elapsed.TotalSeconds, 3)
        evidence = @("trino-junit.xml", "pytest-timings.json", "qualification.log", "trino-container.log")
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryPath -Encoding utf8
    $clock.Stop()
    Stop-Transcript | Out-Null
    Write-Output "Qualification receipt: $summaryPath"
    if ($cleanupStatus -eq "failed") { Write-Warning $cleanupError }
}

exit $testResult
