param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [string]$ImageRef = "sha256:fb9029dad0d8d5aade4bb5809c8a4e027f416a158fedc633c65667d0b21b01b8",
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
    throw "POSIX qualification evidence must be outside the checkout: $evidenceRoot"
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
if ($ImageRef -notmatch '^sha256:[0-9a-f]{64}$') {
    throw "ImageRef must be the digest of the locally built Ronin qualification image."
}

$expectedTests = @(
    "test_untracked_executable_mode_changes_dirty_identity",
    "test_mounted_file_secret_resolver_rejects_symlinks",
    "test_safe_checkout_path_rejects_escape_and_symlink",
    "test_posix_returncode_fallback_does_not_poll_and_reap_native_process",
    "test_source_text_rejects_nul_and_safe_checkout_rejects_symlink_components",
    "test_safe_checkout_path_rejects_escape_and_symlink_traversal",
    "test_mounted_file_secret_rejects_broad_permissions",
    "test_connector_rejects_symlink"
)
$selection = @(
    "tests/test_vcs_git.py::test_untracked_executable_mode_changes_dirty_identity",
    "tests/test_secret_resolvers.py::test_mounted_file_secret_resolver_rejects_symlinks",
    "tests/test_source_control.py::test_safe_checkout_path_rejects_escape_and_symlink",
    "tests/test_container_resource_observation.py::test_posix_returncode_fallback_does_not_poll_and_reap_native_process",
    "tests/test_small_contract_survivors.py::test_source_text_rejects_nul_and_safe_checkout_rejects_symlink_components",
    "tests/test_vcs_source.py::test_safe_checkout_path_rejects_escape_and_symlink_traversal",
    "tests/test_mounted_file_secrets.py::test_mounted_file_secret_rejects_broad_permissions",
    "tests/test_local_file_ingestion.py::test_connector_rejects_symlink"
)

$runId = [guid]::NewGuid().ToString("N").Substring(0, 10)
$containerName = "ronin-posix-qualification-$runId".ToLowerInvariant()
$junitPath = Join-Path $evidenceRoot "posix-junit.xml"
$timingsPath = Join-Path $evidenceRoot "pytest-timings.json"
$gitVersionPath = Join-Path $evidenceRoot "git-version.txt"
$transcriptPath = Join-Path $evidenceRoot "qualification.log"
$summaryPath = Join-Path $evidenceRoot "qualification.json"
$environmentNames = @(
    "RONIN_PYTEST_TIMINGS_PATH", "RONIN_TEST_EXECUTION_MODE", "RONIN_TEST_SELECTION",
    "RONIN_TEST_COVERAGE", "RONIN_TEST_SERVICE_PROFILE", "RONIN_TEST_SOURCE_COMMIT",
    "RONIN_TEST_WORKTREE_CLEAN", "RONIN_TEST_QUALIFICATION_MODE"
)
$oldEnvironment = @{}
foreach ($name in $environmentNames) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$startedAt = [DateTimeOffset]::UtcNow
$clock = [Diagnostics.Stopwatch]::StartNew()
$testResult = 1
$dockerExitCode = 1
$junitSummary = $null
$timingSummary = $null
$failureMessage = $null
$runtimeScript = @'
set -eu
python -m ensurepip --upgrade >/dev/null 2>&1
python -m pip install --disable-pip-version-check --no-cache-dir --root-user-action=ignore \
  --require-hashes --target /tmp/ronin-test-packages \
  -c /workspace/requirements-test.lock \
  -r /workspace/tools/posix-test-requirements.lock >/dev/null
git --version > /evidence/git-version.txt
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/tmp/ronin-test-packages:/workspace/python
python -m pytest -p no:cacheprovider -p tools.pytest_timing_report -q \
  --junitxml=/evidence/posix-junit.xml \
  tests/test_vcs_git.py::test_untracked_executable_mode_changes_dirty_identity \
  tests/test_secret_resolvers.py::test_mounted_file_secret_resolver_rejects_symlinks \
  tests/test_source_control.py::test_safe_checkout_path_rejects_escape_and_symlink \
  tests/test_container_resource_observation.py::test_posix_returncode_fallback_does_not_poll_and_reap_native_process \
  tests/test_small_contract_survivors.py::test_source_text_rejects_nul_and_safe_checkout_rejects_symlink_components \
  tests/test_vcs_source.py::test_safe_checkout_path_rejects_escape_and_symlink_traversal \
  tests/test_mounted_file_secrets.py::test_mounted_file_secret_rejects_broad_permissions \
  tests/test_local_file_ingestion.py::test_connector_rejects_symlink
'@
$runtimeScript = $runtimeScript -replace "`r`n", "`n"
$encodedScript = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($runtimeScript))
$mountRepo = "type=bind,source=$repoRoot,target=/workspace,readonly"
$mountEvidence = "type=bind,source=$evidenceRoot,target=/evidence"

foreach ($name in $environmentNames) {
    [Environment]::SetEnvironmentVariable($name, $null, "Process")
}
[Environment]::SetEnvironmentVariable("RONIN_PYTEST_TIMINGS_PATH", "/evidence/pytest-timings.json", "Process")
[Environment]::SetEnvironmentVariable("RONIN_TEST_EXECUTION_MODE", "posix-docker-diagnostic", "Process")
[Environment]::SetEnvironmentVariable("RONIN_TEST_SELECTION", "8 skipped POSIX-specific pytest node IDs", "Process")
[Environment]::SetEnvironmentVariable("RONIN_TEST_COVERAGE", "disabled", "Process")
[Environment]::SetEnvironmentVariable("RONIN_TEST_SERVICE_PROFILE", $ImageRef, "Process")
[Environment]::SetEnvironmentVariable("RONIN_TEST_SOURCE_COMMIT", $candidateSha, "Process")
[Environment]::SetEnvironmentVariable("RONIN_TEST_WORKTREE_CLEAN", [string]($workingTreeStatus.Count -eq 0), "Process")
[Environment]::SetEnvironmentVariable("RONIN_TEST_QUALIFICATION_MODE", $qualificationMode, "Process")

Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
try {
    Write-Output "Source HEAD: $candidateSha"
    Write-Output "Qualification mode: $qualificationMode"
    Write-Output "Python image: $ImageRef"
    $dockerArgs = @(
        "run", "--rm", "--name", $containerName, "--network", "bridge", "--user", "0:0",
        "--mount", $mountRepo, "--mount", $mountEvidence,
        "--workdir", "/workspace", "--entrypoint", "/bin/sh"
    )
    foreach ($name in $environmentNames) {
        $dockerArgs += @("--env", $name)
    }
    $dockerArgs += @($ImageRef, "-c", "printf '%s' '$encodedScript' | base64 -d | sh")
    & docker @dockerArgs
    $dockerExitCode = $LASTEXITCODE
    $testResult = $dockerExitCode
    if ($dockerExitCode -ne 0) { throw "POSIX contract tests failed inside the isolated Linux container." }

    if (-not (Test-Path -LiteralPath $junitPath) -or -not (Test-Path -LiteralPath $timingsPath)) {
        throw "POSIX pytest did not produce both JUnit and timing evidence."
    }
    [xml]$junit = Get-Content -Raw -LiteralPath $junitPath
    $cases = @($junit.SelectNodes("//testcase"))
    $names = @($cases | ForEach-Object { $_.GetAttribute("name") })
    $skipped = @($cases | Where-Object { $_.SelectSingleNode("skipped") }).Count
    $failed = @($cases | Where-Object { $_.SelectSingleNode("failure | error") }).Count
    $missing = @($expectedTests | Where-Object { $_ -notin $names })
    $unexpected = @($names | Where-Object { $_ -notin $expectedTests })
    $junitSummary = [ordered]@{
        expected = $expectedTests.Count
        collected = $cases.Count
        passed = $cases.Count - $skipped - $failed
        skipped = $skipped
        failed = $failed
        missing = $missing.Count
        unexpected = $unexpected.Count
    }
    $timingReport = Get-Content -Raw -LiteralPath $timingsPath | ConvertFrom-Json
    $timingSummary = $timingReport.summary
    if (
        $cases.Count -ne $expectedTests.Count -or $skipped -ne 0 -or $failed -ne 0 -or
        $missing.Count -gt 0 -or $unexpected.Count -gt 0 -or
        $timingSummary.selected -ne $expectedTests.Count -or
        $timingSummary.executed -ne $expectedTests.Count
    ) {
        $testResult = 1
        throw "POSIX qualification manifest is incomplete or differs from the expected eight tests."
    }
    $testResult = 0
    Write-Output ("POSIX Linux tests: {0}/{1} passed, 0 skipped/failed." -f $junitSummary.passed, $junitSummary.expected)
} catch {
    if ($testResult -eq 0) { $testResult = 1 }
    $failureMessage = $_.Exception.Message
    Write-Output "Qualification error: $failureMessage"
} finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], "Process")
    }
    $clock.Stop()
    $containerStillExists = @(& docker ps -a --filter "name=^/${containerName}$" --format "{{.Names}}")
    $cleanupStatus = if ($containerStillExists.Count -eq 0) { "succeeded" } else { "failed" }
    if ($cleanupStatus -eq "failed") {
        $failureMessage = "Temporary Linux qualification container remains: $($containerStillExists -join ', ')"
        $testResult = 1
    }
    $summary = [ordered]@{
        schema = "ronin.posix-qualification/v1"
        source_commit = $candidateSha
        worktree_clean = ($workingTreeStatus.Count -eq 0)
        qualification_mode = $qualificationMode
        image = $ImageRef
        selection = $selection
        tests = $junitSummary
        timing_summary = $timingSummary
        pytest_session_seconds = if ($timingReport) { $timingReport.timing.pytest_session_body_seconds } else { $null }
        git_version = if (Test-Path -LiteralPath $gitVersionPath) { (Get-Content -Raw $gitVersionPath).Trim() } else { $null }
        docker_exit_code = $dockerExitCode
        cleanup_status = $cleanupStatus
        failure = $failureMessage
        elapsed_seconds = [Math]::Round($clock.Elapsed.TotalSeconds, 3)
        started_at_utc = $startedAt.ToString("O")
        evidence = @("posix-junit.xml", "pytest-timings.json", "git-version.txt", "qualification.log")
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8
    Stop-Transcript | Out-Null
    Write-Output "Qualification receipt: $summaryPath"
}

exit $testResult
