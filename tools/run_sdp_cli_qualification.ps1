param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [string]$SdpCliPath,
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
    throw "SDP qualification evidence must be outside the checkout: $evidenceRoot"
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

if (-not $SdpCliPath) {
    $command = Get-Command sdpstudio -ErrorAction SilentlyContinue
    if (-not $command) { throw "The SDP Studio CLI 'sdpstudio' is not installed or not on PATH." }
    $SdpCliPath = $command.Source
}
if (-not (Test-Path -LiteralPath $SdpCliPath -PathType Leaf)) {
    throw "SDP Studio CLI executable does not exist: $SdpCliPath"
}

$dataRoot = Join-Path $evidenceRoot "isolated-sdp-data"
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
$versionPath = Join-Path $evidenceRoot "sdpstudio-version.txt"
$createStdoutPath = Join-Path $evidenceRoot "project-create.stdout.txt"
$createStderrPath = Join-Path $evidenceRoot "project-create.stderr.txt"
$junitPath = Join-Path $evidenceRoot "sdp-junit.xml"
$timingsPath = Join-Path $evidenceRoot "pytest-timings.json"
$transcriptPath = Join-Path $evidenceRoot "qualification.log"
$summaryPath = Join-Path $evidenceRoot "qualification.json"
$environmentNames = @(
    "SDPSTUDIO_DATA_ROOT", "SDP_PROJECT_ID", "RONIN_PYTEST_TIMINGS_PATH",
    "RONIN_TEST_EXECUTION_MODE", "RONIN_TEST_SELECTION", "RONIN_TEST_COVERAGE",
    "RONIN_TEST_SERVICE_PROFILE", "RONIN_TEST_SOURCE_COMMIT", "RONIN_TEST_WORKTREE_CLEAN",
    "RONIN_TEST_QUALIFICATION_MODE", "PATH"
)
$oldEnvironment = @{}
foreach ($name in $environmentNames) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$startedAt = [DateTimeOffset]::UtcNow
$clock = [Diagnostics.Stopwatch]::StartNew()
$testExitCode = 1
$projectId = $null
$cliVersion = $null
$projectCreated = $false
$junitSummary = $null
$timingSummary = $null
$pytestSeconds = $null
$failure = $null
Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
try {
    [Environment]::SetEnvironmentVariable("SDPSTUDIO_DATA_ROOT", $dataRoot, "Process")
    [Environment]::SetEnvironmentVariable("PATH", "$(Split-Path -Parent $SdpCliPath);$($oldEnvironment['PATH'])", "Process")
    Write-Output "Source HEAD: $candidateSha"
    Write-Output "Qualification mode: $qualificationMode"
    Write-Output "SDP Studio CLI: $SdpCliPath"

    $versionOutput = @(& $SdpCliPath version)
    if ($LASTEXITCODE -ne 0) { throw "Could not read SDP Studio CLI version." }
    $cliVersion = ($versionOutput -join " ").Trim()
    $cliVersion | Set-Content -LiteralPath $versionPath -Encoding utf8

    $createOutput = @(& $SdpCliPath project create ronin-release-qualification --from-example retail-etl 2> $createStderrPath)
    $createExitCode = $LASTEXITCODE
    $createOutput | Set-Content -LiteralPath $createStdoutPath -Encoding utf8
    if ($createExitCode -ne 0) {
        $stderr = if (Test-Path -LiteralPath $createStderrPath) { Get-Content -Raw $createStderrPath } else { "" }
        throw "Could not create an isolated built-in SDP qualification project: $stderr"
    }
    $projectId = @($createOutput | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^[0-9A-Z]{26}$' } | Select-Object -First 1)
    if ($projectId.Count -ne 1) {
        throw "SDP Studio did not return one unambiguous 26-character project ID on stdout."
    }
    $projectId = $projectId[0]
    $projectCreated = $true
    [Environment]::SetEnvironmentVariable("SDP_PROJECT_ID", $projectId, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_PYTEST_TIMINGS_PATH", $timingsPath, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_EXECUTION_MODE", "sdp-official-cli-diagnostic", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SELECTION", "tests/e2e/test_data_engineering_external.py -k real_cli", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_COVERAGE", "disabled", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SERVICE_PROFILE", "SDP Studio official CLI $cliVersion with isolated example project", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SOURCE_COMMIT", $candidateSha, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_WORKTREE_CLEAN", [string]($workingTreeStatus.Count -eq 0), "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_QUALIFICATION_MODE", $qualificationMode, "Process")

    Import-Module (Join-Path $PSScriptRoot "qualification_python.psm1") -Force
    $pytestPython = Get-RoninTestPythonEnvironment -CheckoutRoot $repoRoot
    Push-Location $repoRoot
    $pytestClock = [Diagnostics.Stopwatch]::StartNew()
    try {
        & $pytestPython -m pytest -q -p tools.pytest_timing_report "--junitxml=$junitPath" `
            tests/e2e/test_data_engineering_external.py -k real_cli
        $testExitCode = $LASTEXITCODE
    } finally {
        $pytestClock.Stop()
        $pytestSeconds = [Math]::Round($pytestClock.Elapsed.TotalSeconds, 3)
        Pop-Location
    }
    if ($testExitCode -ne 0) { throw "SDP official CLI integration test failed with exit $testExitCode." }

    [xml]$junit = Get-Content -Raw -LiteralPath $junitPath
    $cases = @($junit.SelectNodes("//testcase"))
    $skipped = @($cases | Where-Object { $_.SelectSingleNode("skipped") }).Count
    $failed = @($cases | Where-Object { $_.SelectSingleNode("failure | error") }).Count
    $correctCase = @($cases | Where-Object { $_.GetAttribute("name") -eq "test_sdp_studio_real_cli_validation" }).Count
    $junitSummary = [ordered]@{
        expected = 1
        collected = $cases.Count
        passed = $cases.Count - $skipped - $failed
        skipped = $skipped
        failed = $failed
        correct_case = $correctCase
    }
    $timingReport = Get-Content -Raw -LiteralPath $timingsPath | ConvertFrom-Json
    $timingSummary = $timingReport.summary
    if (
        $cases.Count -ne 1 -or $skipped -ne 0 -or $failed -ne 0 -or
        $correctCase -ne 1 -or $timingSummary.selected -ne 1 -or $timingSummary.executed -ne 1
    ) {
        throw "SDP CLI pytest evidence did not contain exactly one passing, non-skipped test."
    }
    Write-Output "SDP Studio official CLI: validation test passed 1/1, no skips/failures."
} catch {
    $failure = $_.Exception.Message
    if ($testExitCode -ne 0) { $testExitCode = 1 }
    Write-Output "Qualification error: $failure"
} finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], "Process")
    }
    $clock.Stop()
    $summary = [ordered]@{
        schema = "ronin.sdp-cli-qualification/v1"
        source_commit = $candidateSha
        worktree_clean = ($workingTreeStatus.Count -eq 0)
        qualification_mode = $qualificationMode
        cli_path = $SdpCliPath
        cli_version = $cliVersion
        project_id = $projectId
        project_created = $projectCreated
        test = "tests/e2e/test_data_engineering_external.py::test_sdp_studio_real_cli_validation"
        tests = $junitSummary
        timing_summary = $timingSummary
        pytest_seconds = $pytestSeconds
        test_exit_code = $testExitCode
        failure = $failure
        data_root = $dataRoot
        elapsed_seconds = [Math]::Round($clock.Elapsed.TotalSeconds, 3)
        started_at_utc = $startedAt.ToString("O")
        evidence = @("sdpstudio-version.txt", "project-create.stdout.txt", "project-create.stderr.txt", "sdp-junit.xml", "pytest-timings.json", "qualification.log")
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8
    Stop-Transcript | Out-Null
    Write-Output "Qualification receipt: $summaryPath"
}

exit $testExitCode
