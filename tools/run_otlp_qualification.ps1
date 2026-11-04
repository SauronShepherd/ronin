param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [string]$ImageRef = "otel/opentelemetry-collector-contrib@sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621",
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
    throw "OTLP qualification evidence must be outside the checkout: $evidenceRoot"
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
if ($ImageRef -notmatch '^otel/opentelemetry-collector-contrib@sha256:[0-9a-f]{64}$') {
    throw "ImageRef must be a digest-pinned OpenTelemetry Collector Contrib image."
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

function Test-LoopbackPort([int]$TargetPort) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $client.Connect([Net.IPAddress]::Loopback, $TargetPort)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

$port = Get-FreeLoopbackPort
$runId = [guid]::NewGuid().ToString("N").Substring(0, 10)
$containerName = "ronin-otlp-qualification-$runId".ToLowerInvariant()
$configPath = Join-Path $evidenceRoot "collector-config.yaml"
$junitPath = Join-Path $evidenceRoot "otlp-junit.xml"
$timingsPath = Join-Path $evidenceRoot "pytest-timings.json"
$transcriptPath = Join-Path $evidenceRoot "qualification.log"
$containerLogPath = Join-Path $evidenceRoot "collector-container.log"
$summaryPath = Join-Path $evidenceRoot "qualification.json"
$expectedTests = @("test_real_otlp_collector_accepts_traces_metrics_and_logs")
$collectorConfig = @'
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      exporters: [debug]
    logs:
      receivers: [otlp]
      exporters: [debug]
'@
Set-Content -LiteralPath $configPath -Value $collectorConfig -Encoding utf8

$startedAt = [DateTimeOffset]::UtcNow
$clock = [Diagnostics.Stopwatch]::StartNew()
$serviceStarted = $false
$cleanupStatus = "not-required"
$cleanupError = $null
$testResult = 1
$failureMessage = $null
$junitSummary = $null
$timingSummary = $null
$startupSeconds = $null
$pytestSeconds = $null
$cleanupSeconds = $null
$pytestPython = $null
$environmentNames = @(
    "RONIN_OTLP_TEST_ENDPOINT", "RONIN_PYTEST_TIMINGS_PATH", "RONIN_TEST_EXECUTION_MODE",
    "RONIN_TEST_SELECTION", "RONIN_TEST_COVERAGE", "RONIN_TEST_SERVICE_PROFILE",
    "RONIN_TEST_SOURCE_COMMIT", "RONIN_TEST_WORKTREE_CLEAN", "RONIN_TEST_QUALIFICATION_MODE"
)
$oldEnvironment = @{}
foreach ($name in $environmentNames) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

Import-Module (Join-Path $PSScriptRoot "qualification_python.psm1") -Force
$pytestPython = Get-RoninTestPythonEnvironment -CheckoutRoot $repoRoot
Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
try {
    Write-Output "Source HEAD: $candidateSha"
    Write-Output "Qualification mode: $qualificationMode"
    Write-Output "Collector image: $ImageRef"
    docker run --detach --name $containerName --publish "127.0.0.1:${port}:4318" `
        --mount "type=bind,source=$configPath,target=/etc/otelcol-contrib/config.yaml,readonly" $ImageRef
    if ($LASTEXITCODE -ne 0) { throw "Could not start the pinned OpenTelemetry Collector container." }
    $serviceStarted = $true

    $startupClock = [Diagnostics.Stopwatch]::StartNew()
    $deadline = (Get-Date).AddMinutes(2)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-LoopbackPort -TargetPort $port) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    $startupClock.Stop()
    $startupSeconds = [Math]::Round($startupClock.Elapsed.TotalSeconds, 3)
    if (-not $ready) {
        docker logs $containerName 2>&1 | Set-Content -LiteralPath $containerLogPath -Encoding utf8
        throw "Pinned OpenTelemetry Collector did not listen on OTLP/HTTP within two minutes."
    }
    Write-Output "OpenTelemetry Collector ready on loopback port $port"

    [Environment]::SetEnvironmentVariable("RONIN_OTLP_TEST_ENDPOINT", "http://127.0.0.1:${port}", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_PYTEST_TIMINGS_PATH", $timingsPath, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_EXECUTION_MODE", "otlp-local-diagnostic", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SELECTION", "tests/integration/test_otlp_collector_real.py", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_COVERAGE", "disabled", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SERVICE_PROFILE", $ImageRef, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SOURCE_COMMIT", $candidateSha, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_WORKTREE_CLEAN", [string]($workingTreeStatus.Count -eq 0), "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_QUALIFICATION_MODE", $qualificationMode, "Process")

    Push-Location $repoRoot
    $pytestClock = [Diagnostics.Stopwatch]::StartNew()
    try {
        & $pytestPython -m pytest -q -p tools.pytest_timing_report "--junitxml=$junitPath" tests/integration/test_otlp_collector_real.py
        $testResult = $LASTEXITCODE
    } finally {
        $pytestClock.Stop()
        $pytestSeconds = [Math]::Round($pytestClock.Elapsed.TotalSeconds, 3)
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath $junitPath) -or -not (Test-Path -LiteralPath $timingsPath)) {
        throw "OTLP pytest did not produce both JUnit and timing evidence."
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
        throw "OTLP qualification is incomplete: inspect JUnit, timings and test output."
    }
    Write-Output ("OTLP real-service tests: {0}/{1} passed, 0 skipped/failed." -f $junitSummary.passed, $junitSummary.expected)
} catch {
    $failureMessage = $_.Exception.Message
    $testResult = 1
    Write-Output "Qualification error: $failureMessage"
} finally {
    $cleanupClock = [Diagnostics.Stopwatch]::StartNew()
    if ($serviceStarted) {
        docker logs $containerName 2>&1 | Set-Content -LiteralPath $containerLogPath -Encoding utf8
        docker rm --force --volumes $containerName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $cleanupStatus = "failed"
            $cleanupError = "Could not remove OpenTelemetry Collector container '$containerName'."
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
        schema = "ronin.otlp-qualification/v1"
        source_commit = $candidateSha
        worktree_clean = ($workingTreeStatus.Count -eq 0)
        qualification_mode = $qualificationMode
        service = [ordered]@{
            image = $ImageRef
            protocol = "OTLP/HTTP"
            started = $serviceStarted
        }
        selection = $expectedTests
        tests = $junitSummary
        timing_summary = $timingSummary
        phases_seconds = [ordered]@{
            service_startup = $startupSeconds
            pytest = $pytestSeconds
            cleanup = $cleanupSeconds
        }
        test_exit_code = $testResult
        cleanup_status = $cleanupStatus
        cleanup_error = $cleanupError
        failure = $failureMessage
        elapsed_seconds = [Math]::Round($clock.Elapsed.TotalSeconds, 3)
        evidence = @("collector-config.yaml", "otlp-junit.xml", "pytest-timings.json", "qualification.log", "collector-container.log")
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryPath -Encoding utf8
    Stop-Transcript | Out-Null
    Write-Output "Qualification receipt: $summaryPath"
    if ($cleanupStatus -eq "failed") { Write-Warning $cleanupError }
}

exit $testResult
