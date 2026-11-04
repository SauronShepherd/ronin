param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [string]$ImageRef = "sha256:84a4eedb1abcf36a90808d5a1310e3e910b78c85d85aaa1599e31af5f862ed59",
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
    throw "Spark Connect qualification evidence must be outside the checkout: $evidenceRoot"
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
    throw "ImageRef must be a digest-pinned Apache Spark qualification image."
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
$containerName = "ronin-spark-connect-qualification-$runId".ToLowerInvariant()
$junitPath = Join-Path $evidenceRoot "spark-junit.xml"
$timingsPath = Join-Path $evidenceRoot "pytest-timings.json"
$pipReportPath = Join-Path $evidenceRoot "pyspark-client-install.json"
$sparkLogPath = Join-Path $evidenceRoot "spark-container.log"
$transcriptPath = Join-Path $evidenceRoot "qualification.log"
$summaryPath = Join-Path $evidenceRoot "qualification.json"
$clientLockPath = Join-Path $PSScriptRoot "spark-connect-client.lock"
$clientLockHash = (Get-FileHash -LiteralPath $clientLockPath -Algorithm SHA256).Hash.ToLowerInvariant()
$clientCacheRoot = Join-Path $env:LOCALAPPDATA "Ronin\qualification-cache\spark-connect-client"
$clientCache = Join-Path $clientCacheRoot $clientLockHash
$clientCacheMarker = Join-Path $clientCache ".ronin-lock-sha256"
$clientCacheReport = Join-Path $clientCache "pyspark-client-install.json"
$clientDependencies = $clientCache
$expectedTest = "test_spark_connect_external_smoke"
$environmentNames = @(
    "SPARK_CONNECT_ENDPOINT", "PYTHONPATH", "RONIN_PYTEST_TIMINGS_PATH",
    "RONIN_TEST_EXECUTION_MODE", "RONIN_TEST_SELECTION", "RONIN_TEST_COVERAGE",
    "RONIN_TEST_SERVICE_PROFILE", "RONIN_TEST_SOURCE_COMMIT", "RONIN_TEST_WORKTREE_CLEAN",
    "RONIN_TEST_QUALIFICATION_MODE"
)
$oldEnvironment = @{}
foreach ($name in $environmentNames) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$startedAt = [DateTimeOffset]::UtcNow
$clock = [Diagnostics.Stopwatch]::StartNew()
$serviceStarted = $false
$cleanupStatus = "not-required"
$cleanupError = $null
$testExitCode = 1
$pytestSeconds = $null
$startupSeconds = $null
$failure = $null
$junitSummary = $null
$timingSummary = $null
$pysparkClientVersion = $null
Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
try {
    Write-Output "Source HEAD: $candidateSha"
    Write-Output "Qualification mode: $qualificationMode"
    Write-Output "Spark image: $ImageRef"

    Import-Module (Join-Path $PSScriptRoot "qualification_python.psm1") -Force
    $pytestPython = Get-RoninTestPythonEnvironment -CheckoutRoot $repoRoot
    New-Item -ItemType Directory -Force -Path $clientCacheRoot | Out-Null
    $cacheLockPath = Join-Path $clientCacheRoot "$clientLockHash.lock"
    $cacheLock = $null
    $cacheLockDeadline = (Get-Date).AddMinutes(2)
    while (-not $cacheLock -and (Get-Date) -lt $cacheLockDeadline) {
        try {
            $cacheLock = [IO.File]::Open(
                $cacheLockPath,
                [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite,
                [IO.FileShare]::None
            )
        } catch [IO.IOException] {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $cacheLock) { throw "Timed out waiting for the shared Spark client dependency cache lock." }
    try {
        $cacheIsValid = (
            (Test-Path -LiteralPath $clientCacheMarker -PathType Leaf) -and
            (Get-Content -Raw -LiteralPath $clientCacheMarker).Trim() -eq $clientLockHash -and
            (Test-Path -LiteralPath (Join-Path $clientCache "pyspark\sql\connect") -PathType Container) -and
            (Test-Path -LiteralPath $clientCacheReport -PathType Leaf)
        )
        if (-not $cacheIsValid) {
            if (Test-Path -LiteralPath $clientCache) {
                $resolvedCache = [IO.Path]::GetFullPath($clientCache)
                if (-not $resolvedCache.StartsWith($clientCacheRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Refusing to replace a Spark dependency cache outside its dedicated cache root."
                }
                Remove-Item -LiteralPath $resolvedCache -Recurse -Force
            }
            $stagingCache = "$clientCache.staging-$runId"
            New-Item -ItemType Directory -Force -Path $stagingCache | Out-Null
            & $pytestPython -m pip install --disable-pip-version-check --require-hashes --no-deps `
                --target $stagingCache --report (Join-Path $stagingCache "pyspark-client-install.json") `
                --requirement $clientLockPath
            if ($LASTEXITCODE -ne 0) { throw "Could not install the hash-locked Spark Connect client dependencies." }
            Set-Content -LiteralPath (Join-Path $stagingCache ".ronin-lock-sha256") -Value $clientLockHash -NoNewline -Encoding ascii
            Move-Item -LiteralPath $stagingCache -Destination $clientCache
        } else {
            Write-Output "Spark client dependency cache: hit ($clientLockHash)"
        }
    } finally {
        $cacheLock.Dispose()
    }
    Copy-Item -LiteralPath $clientCacheReport -Destination $pipReportPath -Force
    $pipReport = Get-Content -Raw -LiteralPath $pipReportPath | ConvertFrom-Json
    $pysparkClientVersion = @($pipReport.install | Where-Object { $_.metadata.name -eq "pyspark-client" } | Select-Object -ExpandProperty metadata | Select-Object -ExpandProperty version | Select-Object -First 1)
    if ($pysparkClientVersion.Count -ne 1 -or $pysparkClientVersion[0] -ne "4.2.0") {
        throw "Installed pyspark-client version does not match 4.2.0."
    }
    $pysparkClientVersion = $pysparkClientVersion[0]
    [Environment]::SetEnvironmentVariable("PYTHONPATH", "$clientDependencies;$($oldEnvironment['PYTHONPATH'])", "Process")

    docker run --detach --name $containerName --publish "127.0.0.1:${port}:15002" `
        --entrypoint /opt/spark/sbin/start-connect-server.sh $ImageRef `
        --wait --master "local[1]" --conf spark.connect.grpc.binding.port=15002 `
        --conf spark.sql.warehouse.dir=file:///tmp/ronin-spark-qualification
    if ($LASTEXITCODE -ne 0) { throw "Could not start the pinned Spark 4.2.0 Connect server." }
    $serviceStarted = $true

    $startupClock = [Diagnostics.Stopwatch]::StartNew()
    $deadline = (Get-Date).AddMinutes(4)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-LoopbackPort -TargetPort $port) {
            $ready = $true
            break
        }
        $state = (docker inspect --format '{{.State.Status}}' $containerName 2>$null).Trim()
        if ($state -eq "exited" -or $state -eq "dead") { break }
        Start-Sleep -Milliseconds 500
    }
    $startupClock.Stop()
    $startupSeconds = [Math]::Round($startupClock.Elapsed.TotalSeconds, 3)
    if (-not $ready) {
        docker logs $containerName 2>&1 | Set-Content -LiteralPath $sparkLogPath -Encoding utf8
        throw "Spark 4.2.0 Connect server did not listen on loopback within four minutes."
    }
    Write-Output "Spark Connect server ready on loopback port $port"

    [Environment]::SetEnvironmentVariable("SPARK_CONNECT_ENDPOINT", "sc://127.0.0.1:${port}", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_PYTEST_TIMINGS_PATH", $timingsPath, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_EXECUTION_MODE", "spark-connect-4.2.0-diagnostic", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SELECTION", "tests/e2e/test_data_engineering_external.py -k spark", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_COVERAGE", "disabled", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SERVICE_PROFILE", "Apache Spark 4.2.0 local Connect; pyspark-client 4.2.0", "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_SOURCE_COMMIT", $candidateSha, "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_WORKTREE_CLEAN", [string]($workingTreeStatus.Count -eq 0), "Process")
    [Environment]::SetEnvironmentVariable("RONIN_TEST_QUALIFICATION_MODE", $qualificationMode, "Process")

    Push-Location $repoRoot
    $pytestClock = [Diagnostics.Stopwatch]::StartNew()
    try {
        & $pytestPython -m pytest -q -p tools.pytest_timing_report "--junitxml=$junitPath" `
            tests/e2e/test_data_engineering_external.py -k spark
        $testExitCode = $LASTEXITCODE
    } finally {
        $pytestClock.Stop()
        $pytestSeconds = [Math]::Round($pytestClock.Elapsed.TotalSeconds, 3)
        Pop-Location
    }
    if ($testExitCode -ne 0) { throw "Spark Connect integration test failed with exit $testExitCode." }

    [xml]$junit = Get-Content -Raw -LiteralPath $junitPath
    $cases = @($junit.SelectNodes("//testcase"))
    $names = @($cases | ForEach-Object { $_.GetAttribute("name") })
    $skipped = @($cases | Where-Object { $_.SelectSingleNode("skipped") }).Count
    $failed = @($cases | Where-Object { $_.SelectSingleNode("failure | error") }).Count
    $junitSummary = [ordered]@{
        expected = 1
        collected = $cases.Count
        passed = $cases.Count - $skipped - $failed
        skipped = $skipped
        failed = $failed
        missing = @($expectedTest | Where-Object { $_ -notin $names }).Count
        unexpected = @($names | Where-Object { $_ -ne $expectedTest }).Count
    }
    $timingReport = Get-Content -Raw -LiteralPath $timingsPath | ConvertFrom-Json
    $timingSummary = $timingReport.summary
    if (
        $testExitCode -ne 0 -or $cases.Count -ne 1 -or $skipped -ne 0 -or
        $failed -ne 0 -or $junitSummary.missing -ne 0 -or $junitSummary.unexpected -ne 0 -or
        $timingSummary.selected -ne 1 -or $timingSummary.executed -ne 1
    ) {
        throw "Spark Connect qualification did not execute exactly one passing test without skips."
    }
    Write-Output "Spark Connect integration: 1/1 passed, 0 skips/failures."
} catch {
    $failure = $_.Exception.Message
    if ($testExitCode -ne 0) { $testExitCode = 1 }
    Write-Output "Qualification error: $failure"
} finally {
    $cleanupClock = [Diagnostics.Stopwatch]::StartNew()
    if ($serviceStarted) {
        docker logs $containerName 2>&1 | Set-Content -LiteralPath $sparkLogPath -Encoding utf8
        docker rm --force --volumes $containerName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $cleanupStatus = "failed"
            $cleanupError = "Could not remove Spark Connect container '$containerName'."
            $testExitCode = 1
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
        schema = "ronin.spark-connect-qualification/v1"
        source_commit = $candidateSha
        worktree_clean = ($workingTreeStatus.Count -eq 0)
        qualification_mode = $qualificationMode
        service = [ordered]@{
            image = $ImageRef
            spark_version = "4.2.0"
            started = $serviceStarted
        }
        client = [ordered]@{
            pyspark_client_version = $pysparkClientVersion
            install_report = "pyspark-client-install.json"
        }
        endpoint = if ($port) { "sc://127.0.0.1:${port}" } else { $null }
        selection = "tests/e2e/test_data_engineering_external.py::test_spark_connect_external_smoke"
        tests = $junitSummary
        timing_summary = $timingSummary
        phases_seconds = [ordered]@{
            server_startup = $startupSeconds
            pytest = $pytestSeconds
            cleanup = $cleanupSeconds
        }
        test_exit_code = $testExitCode
        cleanup_status = $cleanupStatus
        cleanup_error = $cleanupError
        failure = $failure
        elapsed_seconds = [Math]::Round($clock.Elapsed.TotalSeconds, 3)
        started_at_utc = $startedAt.ToString("O")
        evidence = @("pyspark-client-install.json", "spark-junit.xml", "pytest-timings.json", "spark-container.log", "qualification.log")
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8
    Stop-Transcript | Out-Null
    Write-Output "Qualification receipt: $summaryPath"
}

exit $testExitCode
