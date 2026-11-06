param(
    [string]$EvidenceDirectory = (Join-Path $env:TEMP ("ronin-live-qualification-" + [guid]::NewGuid().ToString("N"))),
    [string]$TestGrep,
    [string]$WorkerImage,
    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$checkoutPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$evidenceRoot = [IO.Path]::GetFullPath($EvidenceDirectory)
if (
    $evidenceRoot.Equals($repoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $evidenceRoot.StartsWith($checkoutPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw "Live qualification evidence must be outside the checkout: $evidenceRoot"
}
if (Test-Path -LiteralPath $evidenceRoot) {
    if (@(Get-ChildItem -LiteralPath $evidenceRoot -Force).Count -gt 0) {
        throw "Evidence directory is not empty; use a new unique candidate/run path: $evidenceRoot"
    }
} else {
    New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
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

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-LivePythonEnvironment([string]$HostPython, [string]$RequirementsLock) {
    $pythonVersion = (& $HostPython --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3\.') {
        throw "Could not identify a supported Python interpreter: $HostPython"
    }
    $lockHash = Get-FileSha256 $RequirementsLock
    $projectMetadata = Join-Path $repoRoot "pyproject.toml"
    $projectHash = Get-FileSha256 $projectMetadata
    $fingerprintInput = [string]::Join("`n", @(
        "schema=2", "repository=$repoRoot", "python=$HostPython", "version=$pythonVersion",
        "requirements=$lockHash", "project=$projectHash"
    ))
    $fingerprintBytes = [Text.Encoding]::UTF8.GetBytes($fingerprintInput)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $fingerprint = ([BitConverter]::ToString($sha.ComputeHash($fingerprintBytes))).Replace("-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
    $cacheRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Ronin\qualification-cache\python"
    New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
    $environmentPath = Join-Path $cacheRoot $fingerprint
    $cacheMarker = Join-Path $environmentPath ".ronin-qualification-cache.json"
    $lockPath = Join-Path $cacheRoot "$fingerprint.lock"
    $lockStream = $null
    $lockDeadline = (Get-Date).AddMinutes(2)
    while ($null -eq $lockStream) {
        try {
            $lockStream = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch [IO.IOException] {
            if ((Get-Date) -ge $lockDeadline) { throw "Timed out waiting for the shared test-environment cache lock: $lockPath" }
            Start-Sleep -Milliseconds 250
        }
    }
    try {
        $python = Join-Path $environmentPath "Scripts\python.exe"
        $cacheHit = $false
        if ((Test-Path -LiteralPath $cacheMarker -PathType Leaf) -and (Test-Path -LiteralPath $python -PathType Leaf)) {
            try {
                $marker = Get-Content -Raw -LiteralPath $cacheMarker | ConvertFrom-Json
                if ($marker.fingerprint -eq $fingerprint) {
                    & $python -m pip check *> $null
                    $cacheHit = $LASTEXITCODE -eq 0
                }
            } catch {
                $cacheHit = $false
            }
        }
        if (-not $cacheHit) {
            if (Test-Path -LiteralPath $environmentPath) {
                $resolvedCacheRoot = [IO.Path]::GetFullPath($cacheRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
                $resolvedEnvironment = [IO.Path]::GetFullPath($environmentPath)
                if (-not $resolvedEnvironment.StartsWith($resolvedCacheRoot, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Refusing to replace an environment outside the qualification cache: $resolvedEnvironment"
                }
                Remove-Item -LiteralPath $resolvedEnvironment -Recurse -Force
            }
            & $HostPython -m venv $environmentPath
            if ($LASTEXITCODE -ne 0) { throw "Could not create the cached Python environment for live qualification." }
            if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
                throw "The cached Python environment did not create its Windows interpreter: $python"
            }
            # pip's default compileall walks every installed module. The live
            # suite imports only the modules it exercises, so compiling the
            # entire scientific/test dependency tree wastes setup time.
            & $python -m pip install --disable-pip-version-check --no-compile --require-hashes -r $RequirementsLock
            if ($LASTEXITCODE -ne 0) { throw "Could not install the hash-locked test/runtime dependencies for live qualification." }
            & $python -m pip install --disable-pip-version-check --no-build-isolation --no-deps --editable $repoRoot
            if ($LASTEXITCODE -ne 0) { throw "Could not install Ronin into the cached live-qualification environment." }
            & $python -m pip check
            if ($LASTEXITCODE -ne 0) { throw "The cached live-qualification Python environment has inconsistent dependencies." }
            [ordered]@{ fingerprint = $fingerprint; python = $pythonVersion; lockSha256 = $lockHash; projectSha256 = $projectHash } |
                ConvertTo-Json | Set-Content -LiteralPath $cacheMarker -Encoding utf8
        }
        return [pscustomobject]@{ Python = $python; CacheHit = $cacheHit; Fingerprint = $fingerprint }
    } finally {
        $lockStream.Dispose()
    }
}

function Set-QualificationPhase([string]$Name) {
    if ($script:phaseStopwatch -and $script:phaseStopwatch.IsRunning) {
        $previous = $script:phase
        if (-not $script:phaseTimings.Contains($previous)) { $script:phaseTimings[$previous] = 0.0 }
        $script:phaseTimings[$previous] += [Math]::Round($script:phaseStopwatch.Elapsed.TotalSeconds, 2)
    }
    $script:phase = $Name
    if ($script:phaseStopwatch) { $script:phaseStopwatch.Restart() }
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
$streamingOnlyDiagnostic = $TestGrep -eq "streaming"
$semanticOnlyDiagnostic = $TestGrep -eq "semantic"
$mlOnlyDiagnostic = $TestGrep -eq "mlstudio"
$syntheticOnlyDiagnostic = $TestGrep -eq "synthetic"
$qualityOnlyDiagnostic = $TestGrep -eq "quality"
$workerImageId = $null
if (-not $WorkerImage -and -not $TestGrep) {
    throw "Full live product qualification requires -WorkerImage so notebook execution is exercised by a real worker."
}
if ($WorkerImage) {
    $workerImageId = (docker image inspect $WorkerImage --format "{{.Id}}" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $workerImageId -notmatch '^sha256:[0-9a-f]{64}$') {
        throw "Worker qualification image is unavailable or invalid: $WorkerImage"
    }
    $existingWorkerContainers = @(docker ps --format "{{.Names}}" | Where-Object { $_ -match '^ronin-[0-9a-f]{32}$' })
    if ($existingWorkerContainers.Count -gt 0) {
        throw "Refusing to run the live worker while other Ronin execution containers are active."
    }
}
$runId = [guid]::NewGuid().ToString("N").Substring(0, 10)
$composeProject = "ronin-live-$($candidateSha.Substring(0, 8))-$runId".ToLowerInvariant()
$tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd([IO.Path]::DirectorySeparatorChar)
$liveDataDir = Join-Path $tempRoot $composeProject
if (-not $liveDataDir.StartsWith($tempRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create live-test data outside the temporary directory: $liveDataDir"
}
if (Test-Path -LiteralPath $liveDataDir) {
    throw "Unique live data directory already exists; refusing to reuse it: $liveDataDir"
}
$postgresPort = Get-FreeLoopbackPort
$kafkaPort = Get-FreeLoopbackPort
$serverPort = Get-FreeLoopbackPort
$controlPlanePort = Get-FreeLoopbackPort
$evidenceFiles = @{
    ServerOut = Join-Path $evidenceRoot "live-server.stdout.log"
    ServerErr = Join-Path $evidenceRoot "live-server.stderr.log"
    BrowserLog = Join-Path $evidenceRoot "browser-live.log"
    Junit = Join-Path $evidenceRoot "browser-live.xml"
    Traffic = Join-Path $evidenceRoot "live-api-traffic.json"
    Html = Join-Path $evidenceRoot "browser-live-html"
    Artifacts = Join-Path $evidenceRoot "browser-live-artifacts"
    WorkerOut = Join-Path $evidenceRoot "live-worker.stdout.log"
    WorkerErr = Join-Path $evidenceRoot "live-worker.stderr.log"
}
$envNames = @(
    "POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD", "RONIN_POSTGRES_PORT", "RONIN_KAFKA_PORT",
    "RONIN_TOKEN", "RONIN_TOKEN_SCOPES", "RONIN_RUNNER_BROKER_TOKEN",
    "RONIN_SERVER_PROFILE", "RONIN_STORAGE_BACKEND", "RONIN_HOST", "RONIN_DB",
    "RONIN_DATA_DIR", "RONIN_SQL_PARQUET_ROOT", "RONIN_WORKSPACE_ID", "RONIN_CONTROL_PLANE_TOKEN",
    "RONIN_CONTROL_PLANE_PERMISSIONS", "RONIN_CONTROL_PLANE_PORT", "RONIN_PORT",
    "RONIN_PG_TEST_USER", "RONIN_PG_TEST_PASSWORD", "RONIN_LIVE_API_URL", "RONIN_LIVE_JOBS_API_URL",
    "RONIN_LIVE_API_TOKEN", "RONIN_LIVE_WORKSPACE", "RONIN_LIVE_PG_PORT",
    "RONIN_LIVE_PG_DATABASE", "RONIN_LIVE_REQUIRE_POSTGRES", "RONIN_LIVE_STREAMING_BOOTSTRAP", "RONIN_LIVE_API_TRAFFIC_OUTPUT", "RONIN_STUDIO_E2E_URL", "RONIN_STUDIO_E2E_TOKEN",
    "PLAYWRIGHT_OUTPUT_DIR", "PLAYWRIGHT_HTML_OUTPUT_DIR", "PLAYWRIGHT_JUNIT_OUTPUT_FILE",
    "RONIN_IMAGE", "RONIN_WORKSPACE", "RONIN_WORKER_OWNER", "RONIN_LIVE_WORKER_ENABLED",
    "PYTHONPATH", "RONIN_LIVE_PYTHON", "FORCE_COLOR", "npm_config_color", "NO_COLOR", "DEBUG_COLORS",
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"
)
$savedEnvironment = @{}
foreach ($name in $envNames) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$server = $null
$worker = $null
$qualificationStopwatch = [Diagnostics.Stopwatch]::StartNew()
$phaseStopwatch = [Diagnostics.Stopwatch]::StartNew()
$phaseTimings = [ordered]@{}
$phase = "preflight"
$pythonCacheHit = $false
$npmCacheHit = $false
$cases = @()
$traffic = @()
$uncorrelatedTraffic = [System.Collections.Generic.List[object]]::new()
$activeRoutes = @()
$apiRequiredRoutes = @()
$summaryJunit = $null
$failureMessage = $null
$failurePhase = $null
$composeStarted = $false
$servicesReady = $false
$postgresStarted = $false
$kafkaStarted = $false
$apiReady = $false
$liveDataCreated = $false
$resultCode = 1

try {
    Write-Output "Source HEAD: $candidateSha"
    Write-Output "Qualification mode: $qualificationMode"
    # Playwright forces FORCE_COLOR in worker processes. Remove NO_COLOR for
    # those children and disable Playwright colors with DEBUG_COLORS instead;
    # restore both caller settings in finally.
    $env:FORCE_COLOR = $null
    $env:npm_config_color = "false"
    $env:NO_COLOR = $null
    $env:DEBUG_COLORS = "0"
    # Keep small local ML qualification runs deterministic on hosts whose BLAS
    # default otherwise expands to every logical CPU and starves the HTTP lane.
    $env:OMP_NUM_THREADS = "1"
    $env:OPENBLAS_NUM_THREADS = "1"
    $env:MKL_NUM_THREADS = "1"
    $env:BLIS_NUM_THREADS = "1"
    $env:NUMEXPR_NUM_THREADS = "1"
    New-Item -ItemType Directory -Path $liveDataDir | Out-Null
    $liveDataCreated = $true

    Set-QualificationPhase "start isolated live-test services"
    $env:POSTGRES_USER = "ronin"
    $env:POSTGRES_DB = "ronin"
    $env:POSTGRES_PASSWORD = [guid]::NewGuid().ToString("N")
    $env:RONIN_POSTGRES_PORT = [string]$postgresPort
    $env:RONIN_KAFKA_PORT = [string]$kafkaPort
    $env:RONIN_TOKEN = [guid]::NewGuid().ToString("N")
    $env:RONIN_LIVE_WORKER_ENABLED = if ($WorkerImage) { "1" } else { "0" }
    $env:RONIN_RUNNER_BROKER_TOKEN = [guid]::NewGuid().ToString("N")
    $env:RONIN_TOKEN_SCOPES = '{"version":1,"grants":[{"version":1,"actions":["read","list","events","submit","execute","cancel","evidence:read"],"resource":{"kind":"project","identifier":"examples/demo"},"constraints":{}}]}'
    $sqliteOnlyDiagnostic = $semanticOnlyDiagnostic -or $mlOnlyDiagnostic -or $syntheticOnlyDiagnostic -or $qualityOnlyDiagnostic
    $composeStarted = -not $sqliteOnlyDiagnostic
    if ($sqliteOnlyDiagnostic) {
        $diagnosticName = if ($mlOnlyDiagnostic) { "Machine Learning Studio" } elseif ($semanticOnlyDiagnostic) { "Semantic Studio" } elseif ($qualityOnlyDiagnostic) { "Quality Studio" } else { "Synthetic Data Studio" }
        Write-Output "$diagnosticName-only diagnostic: SQLite product routes do not require PostgreSQL or Kafka containers."
    } elseif ($streamingOnlyDiagnostic) {
        Write-Output "Streaming-only diagnostic: starting Redpanda without unrelated PostgreSQL fixtures."
        docker compose -p $composeProject --profile qualification-streaming up -d --wait --wait-timeout 120 streaming-broker
    } else {
        docker compose -p $composeProject --profile qualification-streaming up -d --wait --wait-timeout 120 postgres streaming-broker
    }
    if (-not $sqliteOnlyDiagnostic -and $LASTEXITCODE -ne 0) { throw "Could not start the required isolated live-test services for '$composeProject'." }
    $servicesReady = $true
    $postgresStarted = -not ($streamingOnlyDiagnostic -or $sqliteOnlyDiagnostic)
    $kafkaStarted = -not $sqliteOnlyDiagnostic

    if ($postgresStarted) {
        $databaseExists = (docker compose -p $composeProject exec -T postgres psql -U $env:POSTGRES_USER -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'ronin_test'" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect the isolated PostgreSQL database list." }
        if ($databaseExists -ne "1") {
            docker compose -p $composeProject exec -T postgres psql -v ON_ERROR_STOP=1 -U $env:POSTGRES_USER -d postgres -c "CREATE DATABASE ronin_test;"
            if ($LASTEXITCODE -ne 0) { throw "Could not create isolated database ronin_test." }
        }
        $seedPowerShell = Get-Command pwsh -ErrorAction SilentlyContinue
        if ($null -eq $seedPowerShell) {
            $seedPowerShell = Get-Command powershell -ErrorAction Stop
        }
        & $seedPowerShell.Source -NoLogo -NoProfile -File (Join-Path $repoRoot "tools/seed_live_postgres.ps1") -ComposeProject $composeProject -Database ronin_test -User $env:POSTGRES_USER
        if ($LASTEXITCODE -ne 0) { throw "Could not seed the live PostgreSQL browser fixture." }
    }

    $env:RONIN_SERVER_PROFILE = "local-composed"
    $env:RONIN_STORAGE_BACKEND = "sqlite"
    $env:RONIN_HOST = "127.0.0.1"
    $env:RONIN_DB = Join-Path $liveDataDir "ronin.sqlite3"
    $env:RONIN_DATA_DIR = $liveDataDir
    $env:RONIN_SQL_PARQUET_ROOT = Join-Path $liveDataDir "sql-parquet"
    $env:RONIN_WORKSPACE_ID = "default"
    $env:RONIN_CONTROL_PLANE_TOKEN = $env:RONIN_TOKEN
    $env:RONIN_CONTROL_PLANE_PERMISSIONS = "scheduler.read,scheduler.write,workspace.read,workspace.write,project.read,project.write"
    $env:RONIN_PORT = [string]$serverPort
    $env:RONIN_CONTROL_PLANE_PORT = [string]$controlPlanePort
    $env:RONIN_PG_TEST_USER = $env:POSTGRES_USER
    $env:RONIN_PG_TEST_PASSWORD = $env:POSTGRES_PASSWORD
    $env:RONIN_LIVE_API_URL = "http://127.0.0.1:$controlPlanePort"
    $env:RONIN_LIVE_JOBS_API_URL = "http://127.0.0.1:$serverPort"
    $env:RONIN_LIVE_API_TOKEN = $env:RONIN_CONTROL_PLANE_TOKEN
    $env:RONIN_LIVE_WORKSPACE = $env:RONIN_WORKSPACE_ID
    $env:RONIN_LIVE_PG_PORT = [string]$postgresPort
    $env:RONIN_LIVE_PG_DATABASE = "ronin_test"
    $env:RONIN_LIVE_REQUIRE_POSTGRES = if ($streamingOnlyDiagnostic -or $sqliteOnlyDiagnostic) { "0" } else { "1" }
    $env:RONIN_LIVE_STREAMING_BOOTSTRAP = "127.0.0.1:$kafkaPort"
    $env:RONIN_LIVE_API_TRAFFIC_OUTPUT = $evidenceFiles.Traffic
    # The jobs server serves the installed Studio assets. The control-plane
    # listener owns the live workspace APIs and is the proxy target.
    $env:RONIN_STUDIO_E2E_URL = "http://127.0.0.1:$serverPort/studio/"
    $env:RONIN_STUDIO_E2E_TOKEN = $env:RONIN_TOKEN
    $env:PLAYWRIGHT_OUTPUT_DIR = $evidenceFiles.Artifacts
    $env:PLAYWRIGHT_HTML_OUTPUT_DIR = $evidenceFiles.Html
    $env:PLAYWRIGHT_JUNIT_OUTPUT_FILE = $evidenceFiles.Junit
    Set-QualificationPhase "prepare hash-locked Python and browser dependencies"
    $hostPython = (Get-Command python -ErrorAction Stop).Source
    $testRequirements = Join-Path $repoRoot "requirements-test.lock"
    $environment = Get-LivePythonEnvironment $hostPython $testRequirements
    $python = $environment.Python
    $env:RONIN_LIVE_PYTHON = $python
    $pythonCacheHit = $environment.CacheHit
    Write-Output "Python dependency cache: $(if ($pythonCacheHit) { 'HIT' } else { 'MISS (created)' }) [$($environment.Fingerprint.Substring(0, 12))]"
    $pluginTarget = Join-Path $liveDataDir "python-plugins"
    if (-not $TestGrep) {
        & $python -m pip install --disable-pip-version-check --no-build-isolation --no-deps `
            --target $pluginTarget (Join-Path $repoRoot "packages/ronin-plugin-performance")
        if ($LASTEXITCODE -ne 0) { throw "Could not stage the repository's Performance plugin in the isolated live-test environment." }
    } else {
        New-Item -ItemType Directory -Force -Path $pluginTarget | Out-Null
        Write-Output "Filtered live diagnostic: skipping Performance plugin build (not used by a filtered route; full qualification still builds it)."
    }
    $pythonManifest = Join-Path $evidenceRoot "live-python-freeze.txt"
    (& $python --version 2>&1 | Out-String).Trim() | Set-Content -LiteralPath $pythonManifest -Encoding utf8
    & $python -m pip freeze --all | Add-Content -LiteralPath $pythonManifest -Encoding utf8
    $pythonPaths = @(
        (Join-Path $repoRoot "python")
        $pluginTarget
    )
    $env:PYTHONPATH = [string]::Join([IO.Path]::PathSeparator, $pythonPaths)

    Set-QualificationPhase "precompile Ronin Python sources"
    $compileClock = [Diagnostics.Stopwatch]::StartNew()
    & $python -m compileall -q `
        (Join-Path $repoRoot "python") `
        (Join-Path $repoRoot "tools/seed_live_studio.py") `
        (Join-Path $repoRoot "tools/seed_live_streaming.py")
    $compileResult = $LASTEXITCODE
    $compileClock.Stop()
    if ($compileResult -ne 0) { throw "Could not precompile Ronin source modules for the live qualification environment." }
    Write-Output "Ronin source bytecode prepared in $([Math]::Round($compileClock.Elapsed.TotalSeconds, 2))s (third-party dependencies excluded)."

    Set-QualificationPhase "seed live data and start Ronin server"
    if ($semanticOnlyDiagnostic) {
        & $python -m tools.seed_live_studio --semantic-only
    } elseif ($qualityOnlyDiagnostic) {
        & $python -m tools.seed_live_studio
    } elseif ($syntheticOnlyDiagnostic) {
        & $python -m tools.seed_live_studio --workspace-only
    } elseif ($streamingOnlyDiagnostic) {
        & $python -m tools.seed_live_studio --workspace-only
    } else {
        & $python -m tools.seed_live_studio
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not seed the isolated live Studio graph fixture." }

    $server = Start-Process -FilePath $python -ArgumentList @("-m", "studio_cli.entrypoint", "serve") `
        -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $evidenceFiles.ServerOut -RedirectStandardError $evidenceFiles.ServerErr
    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    do {
        $server.Refresh()
        if ($server.HasExited) { throw "Ronin live server exited with code $($server.ExitCode); inspect saved logs." }
        try {
            $null = Invoke-WebRequest $env:RONIN_STUDIO_E2E_URL -UseBasicParsing -TimeoutSec 2
            $ready = $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while (-not $ready -and (Get-Date) -lt $deadline)
    if (-not $ready) { throw "Ronin Studio did not become ready; inspect saved server logs." }
    $apiReady = $true

    if (-not $sqliteOnlyDiagnostic) {
        & $python -m tools.seed_live_streaming
        if ($LASTEXITCODE -ne 0) { throw "Could not seed the isolated live Kafka stream fixture." }
    }

    if ($WorkerImage) {
        # Runtime submissions require the immutable image identifier verified above.
        $env:RONIN_IMAGE = $workerImageId
        $env:RONIN_WORKSPACE = $repoRoot
        $env:RONIN_WORKER_OWNER = "live-qualification-$runId"
        $worker = Start-Process -FilePath $python -ArgumentList @("-m", "studio_cli.entrypoint", "worker") `
            -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $evidenceFiles.WorkerOut -RedirectStandardError $evidenceFiles.WorkerErr
        Start-Sleep -Milliseconds 500
        $worker.Refresh()
        if ($worker.HasExited) { throw "Live worker exited with code $($worker.ExitCode); inspect saved worker logs." }
    }

    $webTestsDirectory = Join-Path $repoRoot "web-tests"
    $dependencyStatusFile = Join-Path $evidenceRoot "web-test-dependency-cache.json"
    Push-Location $webTestsDirectory
    try { node ensure-dependencies.mjs --status-file $dependencyStatusFile; $dependencySetupExit = $LASTEXITCODE }
    finally { Pop-Location }
    if ($dependencySetupExit -ne 0) { throw "Could not validate or install locked Playwright dependencies and Chromium." }
    $dependencyStatus = Get-Content -Raw -LiteralPath $dependencyStatusFile | ConvertFrom-Json
    $npmCacheHit = $dependencyStatus.dependencyCache -eq "hit"
    Write-Output "Playwright dependency cache: $($dependencyStatus.dependencyCache.ToUpperInvariant()) [$($dependencyStatus.fingerprint.Substring(0, 12))]; Chromium: $($dependencyStatus.chromium)."
    $browserPhase = if ($mlOnlyDiagnostic) {
        "run Machine Learning Studio browser journey against isolated SQLite and real Ronin APIs"
    } elseif ($semanticOnlyDiagnostic) {
        "run semantic browser journey against isolated SQLite and real Ronin APIs"
    } elseif ($syntheticOnlyDiagnostic) {
        "run Synthetic Data Studio generation/export against isolated SQLite and real Ronin APIs"
    } elseif ($qualityOnlyDiagnostic) {
        "run Quality Studio passing and blocking checks against isolated SQLite and real Ronin APIs"
    } elseif ($streamingOnlyDiagnostic) {
        "run streaming browser journey against Redpanda and real Ronin APIs"
    } else {
        "run live browser journeys against PostgreSQL, Kafka and real Ronin APIs"
    }
    Set-QualificationPhase $browserPhase
    if ($TestGrep) {
        # `npm run` forwards script arguments through cmd.exe on Windows; an
        # alternation such as `Projects|environments` is then parsed as a pipe.
        # Run preflight and Playwright directly from web-tests so its config is
        # loaded (and its baseURL/output directories are applied) for diagnostics.
        Push-Location $webTestsDirectory
        try {
            node tests/live-preflight.mjs 2>&1 | Tee-Object -FilePath $evidenceFiles.BrowserLog
            if ($LASTEXITCODE -ne 0) { throw "Live UI preflight failed with exit code $LASTEXITCODE." }
            npm exec -- playwright test `
                tests/live-runs.spec.mjs tests/ingestion-live.spec.mjs tests/product-live.spec.mjs `
                --workers=1 "--grep=$TestGrep" 2>&1 |
                Tee-Object -FilePath $evidenceFiles.BrowserLog -Append
        } finally {
            Pop-Location
        }
    } else {
        npm --prefix $webTestsDirectory run test:live 2>&1 |
            Tee-Object -FilePath $evidenceFiles.BrowserLog
    }
    if ($LASTEXITCODE -ne 0) { throw "Live UI/API tests failed with exit code $LASTEXITCODE." }

    Set-QualificationPhase "audit route coverage and real API traffic evidence"
    [xml]$junit = Get-Content -Raw -LiteralPath $evidenceFiles.Junit
    $cases = @($junit.SelectNodes("//testcase"))
    if ($TestGrep) {
        if ($cases.Count -eq 0) { throw "The requested live diagnostic did not execute any tests." }
    } elseif ($cases.Count -lt 30) {
        throw "Live qualification requires 30 cases; only $($cases.Count) were reported."
    }
    if ($junit.SelectNodes("//testcase/skipped").Count -gt 0) { throw "Live qualification contains skipped tests." }
    if ($junit.SelectNodes("//testcase/failure").Count -gt 0 -or $junit.SelectNodes("//testcase/error").Count -gt 0) {
        throw "Live qualification contains failed or errored tests."
    }
    $caseNames = @($cases | ForEach-Object { $_.GetAttribute("name") })
    $routeJson = Get-Content -Raw -LiteralPath (Join-Path $repoRoot "web/routes.json")
    $routeDocument = ConvertFrom-Json -InputObject $routeJson
    $publishedRoutes = [System.Collections.Generic.List[object]]::new()
    $routeQueue = [System.Collections.Generic.Queue[object]]::new()
    $routeQueue.Enqueue($routeDocument)
    while ($routeQueue.Count -gt 0) {
        $routeEntry = $routeQueue.Dequeue()
        if ($null -eq $routeEntry) { continue }
        if ($routeEntry -is [System.Array]) {
            foreach ($nestedRouteEntry in $routeEntry) { $routeQueue.Enqueue($nestedRouteEntry) }
        } else {
            $publishedRoutes.Add($routeEntry)
        }
    }
    $activeRoutes = @($publishedRoutes | Where-Object { $_.state -eq "active" })
    $apiRequiredRoutes = @($activeRoutes | Where-Object { @($_.required_api | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count -gt 0 })
    if (-not $TestGrep) {
        $caseNameSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
        foreach ($caseName in $caseNames) { $null = $caseNameSet.Add([string]$caseName) }
        $missingRoutes = [System.Collections.Generic.List[string]]::new()
        foreach ($route in $activeRoutes) {
            $hasApiContract = @($route.required_api | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count -gt 0
            $expectedRouteCase = if ($hasApiContract) {
                "route $($route.id) loads and reaches the live API"
            } else {
                "route $($route.id) renders (UI-only: no API route declared)"
            }
            if (-not $caseNameSet.Contains($expectedRouteCase)) { $missingRoutes.Add([string]$route.id) }
        }
        Write-Output "Live route coverage audit: $($caseNameSet.Count) unique cases, $($activeRoutes.Count) active routes; $($apiRequiredRoutes.Count) exercise API contracts, $($activeRoutes.Count - $apiRequiredRoutes.Count) are UI-only."
        if ($missingRoutes.Count -gt 0) {
            throw "Live JUnit report is missing routes: $($missingRoutes -join ', ')"
        }
    }
    $trafficJson = Get-Content -Raw -LiteralPath $evidenceFiles.Traffic
    $trafficDocument = ConvertFrom-Json -InputObject $trafficJson
    $traffic = [System.Collections.Generic.List[object]]::new()
    $trafficQueue = [System.Collections.Generic.Queue[object]]::new()
    $trafficQueue.Enqueue($trafficDocument)
    while ($trafficQueue.Count -gt 0) {
        $trafficEntry = $trafficQueue.Dequeue()
        if ($null -eq $trafficEntry) { continue }
        if ($trafficEntry -is [System.Array]) {
            foreach ($nestedTrafficEntry in $trafficEntry) { $trafficQueue.Enqueue($nestedTrafficEntry) }
        } else {
            $traffic.Add($trafficEntry)
        }
    }
    $uiOnlyDiagnostic = $false
    if ($TestGrep -and $cases.Count -gt 0) {
        $uiOnlyDiagnostic = @($cases | Where-Object { $_.GetAttribute("name") -notmatch 'renders \(UI-only: no API route declared\)' }).Count -eq 0
    }
    if ($traffic.Count -eq 0 -and -not $uiOnlyDiagnostic) { throw "Live API traffic evidence is empty for a test expected to exercise the API." }
    $httpLogsByRequestId = @{}
    foreach ($logPath in @($evidenceFiles.ServerOut, $evidenceFiles.ServerErr, $evidenceFiles.WorkerOut, $evidenceFiles.WorkerErr)) {
        if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) { continue }
        foreach ($line in (Get-Content -LiteralPath $logPath)) {
            if (-not $line.TrimStart().StartsWith('{')) { continue }
            try { $logEvent = ConvertFrom-Json -InputObject $line -ErrorAction Stop } catch { continue }
            if ($logEvent.event -ne 'http.request' -or -not $logEvent.request_id) { continue }
            $httpLogsByRequestId[[string]$logEvent.request_id] = $logEvent
        }
    }
    foreach ($trafficEvent in $traffic) {
        $requestId = [string]$trafficEvent.requestId
        if ($requestId -notmatch '^req-[0-9a-f]{32}$' -or -not $httpLogsByRequestId.ContainsKey($requestId)) {
            $uncorrelatedTraffic.Add($trafficEvent)
            continue
        }
        $matchingLog = $httpLogsByRequestId[$requestId]
        if ([int]$matchingLog.status_code -ne [int]$trafficEvent.status -or [string]$matchingLog.outcome -ne [string]$trafficEvent.outcome) {
            $uncorrelatedTraffic.Add($trafficEvent)
        }
    }
    if ($uncorrelatedTraffic.Count -gt 0) {
        throw "Live API traffic has $($uncorrelatedTraffic.Count) events without a matching structured application HTTP log (request ID, status and outcome)."
    }
    $unexpectedMissingAuth = [System.Collections.Generic.List[object]]::new()
    $serverErrors = [System.Collections.Generic.List[object]]::new()
    foreach ($trafficEvent in $traffic) {
        if ($trafficEvent.authorization -ne "present" -and -not (
            $trafficEvent.authorizationKind -eq "missing" -and
            $trafficEvent.method -eq "GET" -and
            $trafficEvent.path -eq "/v1/workspaces" -and
            $trafficEvent.status -eq 401 -and
            $trafficEvent.outcome -eq "WARN"
        )) {
            $unexpectedMissingAuth.Add($trafficEvent)
        }
        if ($trafficEvent.status -ge 500 -or $trafficEvent.status -eq 0) {
            $serverErrors.Add($trafficEvent)
        }
    }
    if ($unexpectedMissingAuth.Count -gt 0 -or $serverErrors.Count -gt 0) {
        throw "Live API traffic contains unexpected unauthenticated requests or server/network errors."
    }
    if ($traffic.Count -gt 0) {
        Write-Output "Live API traffic audit: $($traffic.Count) events, all correlated with structured HTTP logs, 0 unexpected authorization gaps, 0 server/network errors."
    } else {
        Write-Output "UI-only diagnostic passed: 0 API calls (this does not qualify API behavior)."
    }
    $resultCode = 0
    if ($TestGrep) {
        Write-Output "Live diagnostic passed: $($cases.Count) filtered Playwright cases, $($traffic.Count) real API calls."
    } else {
        Write-Output "Live product qualification passed: $($cases.Count) Playwright cases, $($traffic.Count) real API calls."
    }
    Write-Output "Evidence: $evidenceRoot"
} catch {
    $failureMessage = $_.Exception.Message
    $failurePhase = $phase
    Write-Error -Message "Live qualification failed during '$phase': $failureMessage" -ErrorAction Continue
    $resultCode = 1
} finally {
    Set-QualificationPhase "cleanup isolated services and restore environment"
    if ($worker) {
        $worker.Refresh()
        if (-not $worker.HasExited) {
            Stop-Process -Id $worker.Id -Force
            try { $worker.WaitForExit(10000) } catch { }
        }
    }
    if ($server) {
        $server.Refresh()
        if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    }
    if ($composeStarted) {
        docker compose -p $composeProject down -v --remove-orphans
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Cleanup failed for isolated Compose project '$composeProject'."
            $resultCode = 1
        }
    }
    if ($liveDataCreated -and (Test-Path -LiteralPath $liveDataDir)) {
        Remove-Item -LiteralPath $liveDataDir -Recurse -Force
    }
    foreach ($name in $envNames) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
    }
    $qualificationStopwatch.Stop()
    $phaseStopwatch.Stop()
    if (-not $phaseTimings.Contains($phase)) { $phaseTimings[$phase] = 0.0 }
    $phaseTimings[$phase] += [Math]::Round($phaseStopwatch.Elapsed.TotalSeconds, 2)
    $junitCaseCount = 0
    $junitPassedCount = 0
    $junitSkippedCount = 0
    $junitFailedCount = 0
    $junitDurationSeconds = $null
    if (Test-Path -LiteralPath $evidenceFiles.Junit -PathType Leaf) {
        try {
            [xml]$summaryJunit = Get-Content -Raw -LiteralPath $evidenceFiles.Junit
            $summaryCases = @($summaryJunit.SelectNodes("//testcase"))
            $junitCaseCount = $summaryCases.Count
            $junitSkippedCount = $summaryJunit.SelectNodes("//testcase/skipped").Count
            $junitFailedCount = $summaryJunit.SelectNodes("//testcase/failure").Count + $summaryJunit.SelectNodes("//testcase/error").Count
            $junitPassedCount = $junitCaseCount - $junitSkippedCount - $junitFailedCount
            $junitDurationSeconds = [Math]::Round([double]$summaryJunit.testsuites.time, 2)
        } catch { }
    }
    $trafficCount = 0
    $apiOutcomes = [ordered]@{}
    if (Test-Path -LiteralPath $evidenceFiles.Traffic -PathType Leaf) {
        try {
            $summaryTrafficDocument = ConvertFrom-Json -InputObject ([IO.File]::ReadAllText($evidenceFiles.Traffic))
            $summaryTrafficQueue = [System.Collections.Generic.Queue[object]]::new()
            $summaryTrafficQueue.Enqueue($summaryTrafficDocument)
            while ($summaryTrafficQueue.Count -gt 0) {
                $trafficEntry = $summaryTrafficQueue.Dequeue()
                if ($null -eq $trafficEntry) { continue }
                if ($trafficEntry -is [System.Array]) {
                    foreach ($nestedTrafficEntry in $trafficEntry) { $summaryTrafficQueue.Enqueue($nestedTrafficEntry) }
                } else {
                    $trafficCount++
                    $outcome = [string]$trafficEntry.outcome
                    if (-not $apiOutcomes.Contains($outcome)) { $apiOutcomes[$outcome] = 0 }
                    $apiOutcomes[$outcome]++
                }
            }
        } catch { }
    }
    $logLevels = [ordered]@{ INFO = 0; WARN = 0; WARNING = 0; ERROR = 0; CRITICAL = 0 }
    foreach ($logPath in @($evidenceFiles.BrowserLog, $evidenceFiles.ServerOut, $evidenceFiles.ServerErr, $evidenceFiles.WorkerOut, $evidenceFiles.WorkerErr)) {
        if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) { continue }
        foreach ($line in (Get-Content -LiteralPath $logPath)) {
            $severity = $null
            if ($line.TrimStart().StartsWith('{')) {
                try { $severity = [string](ConvertFrom-Json -InputObject $line -ErrorAction Stop).level } catch { }
            }
            if (-not $severity -and $line -match '\[(INFO|WARN|WARNING|ERROR|CRITICAL)\]') { $severity = $Matches[1] }
            if ($severity) {
                $severity = $severity.ToUpperInvariant()
                if ($logLevels.Contains($severity)) { $logLevels[$severity]++ }
            }
        }
    }
    if ($null -ne $summaryJunit) {
        $junitSuites = @($summaryJunit.SelectNodes("//testsuite"))
        if ($junitSuites.Count -gt 0) {
            $junitTotalDuration = 0.0
            foreach ($suite in $junitSuites) { $junitTotalDuration += [double]$suite.GetAttribute("time") }
            $junitDurationSeconds = [Math]::Round($junitTotalDuration, 2)
        }
    }
    $summary = [ordered]@{
        schemaVersion = 1
        status = if ($resultCode -eq 0) { "passed" } else { "failed" }
        failurePhase = $failurePhase
        failure = $failureMessage
        candidate = $candidateSha
        worktree = $qualificationMode
        testKind = if (-not $TestGrep) { "live-product-qualification" } elseif ($trafficCount -gt 0) { "live-api-diagnostic" } else { "live-ui-diagnostic" }
        durationSeconds = [Math]::Round($qualificationStopwatch.Elapsed.TotalSeconds, 2)
        phaseDurationsSeconds = $phaseTimings
        playwright = [ordered]@{ executed = $junitCaseCount; passed = $junitPassedCount; skipped = $junitSkippedCount; failed = $junitFailedCount; durationSeconds = $junitDurationSeconds }
        routeCoverage = [ordered]@{ audited = (-not [bool]$TestGrep); activeRoutes = $activeRoutes.Count; routesWithApiContracts = $apiRequiredRoutes.Count; uiOnlyRoutes = $activeRoutes.Count - $apiRequiredRoutes.Count }
        realServices = [ordered]@{ postgres = $postgresStarted; kafka = $kafkaStarted; roninApi = $apiReady; workerImage = $workerImageId }
        apiTraffic = [ordered]@{ events = $trafficCount; correlatedHttpLogs = ($trafficCount - $uncorrelatedTraffic.Count); uncorrelated = $uncorrelatedTraffic.Count; outcomes = $apiOutcomes; evidence = $evidenceFiles.Traffic }
        applicationLogLevels = $logLevels
        caches = [ordered]@{ pythonDependencies = if ($pythonCacheHit) { "hit" } else { "miss" }; webDependencies = if ($npmCacheHit) { "hit" } else { "miss" } }
        evidenceDirectory = $evidenceRoot
        evidenceFiles = [ordered]@{ junit = $evidenceFiles.Junit; browserLog = $evidenceFiles.BrowserLog; serverOut = $evidenceFiles.ServerOut; serverErr = $evidenceFiles.ServerErr; workerOut = $evidenceFiles.WorkerOut; workerErr = $evidenceFiles.WorkerErr; pythonFreeze = (Join-Path $evidenceRoot "live-python-freeze.txt") }
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidenceRoot "qualification-summary.json") -Encoding utf8
    Write-Output "Summary: $(Join-Path $evidenceRoot 'qualification-summary.json')"
    $liveOutcome = if ($resultCode -eq 0) { "PASS" } else { "FAIL" }
    $apiOutcomeSummary = if ($trafficCount -gt 0) {
        (($apiOutcomes.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", ")
    } else {
        "no API traffic captured"
    }
    $logErrorCount = [int]$logLevels.ERROR + [int]$logLevels.CRITICAL
    $routeSummary = if (-not $TestGrep) {
        "$($activeRoutes.Count) active routes audited ($($apiRequiredRoutes.Count) API-backed)"
    } else {
        "route-wide audit not run for filtered diagnostics"
    }
    Write-Output ("Live qualification: {0}; pytest {1}/{2} passed, {3} skipped, {4} case failures; {5}; real API ready={6}, events={7} ({8}); log errors/critical={9}; elapsed={10}s." -f `
        $liveOutcome, $junitPassedCount, $junitCaseCount, $junitSkippedCount, $junitFailedCount,
        $routeSummary, [bool]$apiReady, $trafficCount, $apiOutcomeSummary, $logErrorCount,
        [Math]::Round($qualificationStopwatch.Elapsed.TotalSeconds, 2))
    Write-Output "Interpretation: static Playwright tests are UI-only; this live runner starts Ronin and reports API-backed evidence separately."
    if ($resultCode -ne 0) {
        Write-Output "Runner failure at '$failurePhase': $failureMessage"
    }
}

exit $resultCode
