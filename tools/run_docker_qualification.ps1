param(
    [string]$ImageTag = "ronin:qualification",
    [string]$ImageId,
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [string]$TestFilter,
    [switch]$KeepImage,
    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = "Stop"

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return $listener.LocalEndpoint.Port
    } finally {
        $listener.Stop()
    }
}

function Get-DockerImageId([string]$Reference) {
    $raw = (& docker image inspect $Reference --format '{{.Id}}' 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $raw -notmatch '^sha256:[0-9a-f]{64}$') {
        return $null
    }
    return $raw
}

function Remove-OwnedQualificationImage {
    param(
        [Parameter(Mandatory = $true)] [string]$BuiltImageId,
        [Parameter(Mandatory = $true)] [string]$ImageTag,
        [Parameter(Mandatory = $true)] [string]$OwnerRunId,
        [string]$PreexistingImageId
    )

    $owner = (& docker image inspect $BuiltImageId `
        --format '{{ index .Config.Labels "org.ronin.qualification.run" }}' 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the built Ronin qualification image '$BuiltImageId' during cleanup."
    }
    if ($owner -ne $OwnerRunId) {
        throw "Refusing to delete Ronin image '$BuiltImageId': ownership label '$owner' does not match qualification run '$OwnerRunId'."
    }

    # A worker test can launch child containers from the qualification image.
    # Remove only descendants of this run's owned image before removing the image
    # itself; an image still referenced by a container must never be reported as
    # cleaned up.
    $ownedContainers = @(& docker ps -a --filter "ancestor=$BuiltImageId" --format "{{.ID}}" 2>$null |
        Where-Object { $_.Trim() })
    if ($LASTEXITCODE -ne 0) {
        throw "Could not enumerate containers based on owned Ronin image '$BuiltImageId'."
    }
    if ($ownedContainers.Count -gt 0) {
        & docker rm --force --volumes $ownedContainers 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not remove containers based on owned Ronin image '$BuiltImageId'."
        }
        $remainingContainers = @(& docker ps -a --filter "ancestor=$BuiltImageId" --format "{{.ID}}" 2>$null |
            Where-Object { $_.Trim() })
        if ($LASTEXITCODE -ne 0 -or $remainingContainers.Count -gt 0) {
            throw "Containers based on owned Ronin image '$BuiltImageId' remain after cleanup."
        }
    }

    & docker image rm --force $BuiltImageId 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not remove owned Ronin qualification image '$BuiltImageId'."
    }
    if (Get-DockerImageId $BuiltImageId) {
        throw "Owned Ronin qualification image '$BuiltImageId' still exists after cleanup."
    }

    # A caller may deliberately reuse a tag that existed before this run. The
    # run owns the newly built image, not the caller's old image; restore the
    # old tag so cleanup does not destroy pre-existing local state.
    if ($PreexistingImageId) {
        & docker tag $PreexistingImageId $ImageTag 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Owned image was removed, but the pre-existing image '$PreexistingImageId' could not be restored as '$ImageTag'."
        }
    }
}

$cleanupFailures = [System.Collections.Generic.List[string]]::new()
function Add-CleanupFailure([string]$Message) {
    $script:cleanupFailures.Add($Message)
    Write-Warning $Message
}

$checkout = [IO.Path]::GetFullPath((Get-Location).Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
$candidateSha = (git -C $checkout rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $candidateSha -notmatch '^[0-9a-f]{40}$') {
    throw "Could not identify the exact source candidate."
}
$workingTreeStatus = @(git -C $checkout status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw "Could not determine whether the worktree is clean." }
if ($workingTreeStatus.Count -gt 0 -and -not $AllowDirtyWorktree) {
    throw "Refusing release qualification with a dirty worktree. Use -AllowDirtyWorktree only for diagnostics; its evidence is not release-candidate evidence."
}
$qualificationMode = if ($workingTreeStatus.Count -gt 0) { "DIRTY-WORKTREE DIAGNOSTIC" } else { "CLEAN-CANDIDATE QUALIFICATION" }
$evidenceRoot = [IO.Path]::GetFullPath($EvidenceDirectory)
$checkoutPrefix = $checkout + [IO.Path]::DirectorySeparatorChar
if (
    $evidenceRoot.Equals($checkout, [StringComparison]::OrdinalIgnoreCase) -or
    $evidenceRoot.StartsWith($checkoutPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw "Docker qualification evidence must be outside the checkout: $evidenceRoot"
}
if (Test-Path -LiteralPath $evidenceRoot) {
    $existing = Get-ChildItem -LiteralPath $evidenceRoot -Force
    if ($existing.Count -gt 0) {
        throw "Evidence directory is not empty; use a new candidate/run path: $evidenceRoot"
    }
} else {
    New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
}

$transcript = Join-Path $evidenceRoot "docker-qualification.log"
$junitReport = Join-Path $evidenceRoot "v01-acceptance.xml"
$acceptanceEvidence = Join-Path $evidenceRoot "v01-acceptance-strict.json"
$postgresLog = Join-Path $evidenceRoot "postgres-qualification.log"
$flociLog = Join-Path $evidenceRoot "floci-s3-qualification.log"
$azuriteLog = Join-Path $evidenceRoot "azurite-qualification.log"
$pytestOutput = Join-Path $evidenceRoot "docker-pytest-output.log"
$cleanupReceiptPath = Join-Path $evidenceRoot "docker-cleanup.json"
$runId = [guid]::NewGuid().ToString("N").Substring(0, 10)
$postgresContainerName = "ronin-docker-pg-$($candidateSha.Substring(0, 8))-$runId".ToLowerInvariant()
$flociProject = "ronin-docker-s3-$($candidateSha.Substring(0, 8))-$runId".ToLowerInvariant()
$azuriteProject = "ronin-docker-azure-$($candidateSha.Substring(0, 8))-$runId".ToLowerInvariant()
$postgresPort = Get-FreeLoopbackPort
$flociPort = Get-FreeLoopbackPort
$azuritePort = Get-FreeLoopbackPort
$postgresPassword = [guid]::NewGuid().ToString("N")
$postgresDsn = "postgresql://ronin:$postgresPassword@127.0.0.1:$postgresPort/ronin_test"
$savedPostgresTestDsn = [Environment]::GetEnvironmentVariable("RONIN_POSTGRES_TEST_DSN", "Process")
$savedFlociEnvironment = @{}
foreach ($name in @("RONIN_FLOCI_PORT", "RONIN_TEST_S3_ENDPOINT", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "RONIN_AZURITE_PORT", "RONIN_AZURITE_ENDPOINT", "RONIN_AZURITE_ACCOUNT", "RONIN_AZURITE_ACCOUNT_KEY")) {
    $savedFlociEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$postgresStarted = $false
$flociStarted = $false
$azuriteStarted = $false
$imageWasBuiltFromCheckout = $false
$preexistingImageId = $null
$resolvedImageId = $null
$imageCleanupStatus = "not-required"
$needsPostgres = -not $TestFilter -or $TestFilter -match 'postgres|appliance|worker|docker|v01_journey'
$needsFloci = -not $TestFilter -or $TestFilter -match 's3_json|ml_s3_artifact'
$needsAzurite = -not $TestFilter -or $TestFilter -match 'azure_blob'
$flociCompose = Join-Path (Get-Location) "examples\cloud-studio\compose.floci.yaml"
$azuriteCompose = Join-Path (Get-Location) "examples\connectors\compose.azurite.yaml"
Import-Module (Join-Path $PSScriptRoot "qualification_python.psm1") -Force
$python = Get-RoninTestPythonEnvironment -CheckoutRoot $checkout

# Real-worker acceptance starts fresh Python processes, so bind child imports
# to the source tree that is being qualified.
$pythonPathEntries = @(
    (Join-Path (Get-Location) "python")
    (Join-Path (Get-Location) "packages\pyronin\src")
)
if ($env:PYTHONPATH) {
    $pythonPathEntries += $env:PYTHONPATH
}
$env:PYTHONPATH = [string]::Join([IO.Path]::PathSeparator, $pythonPathEntries)
$env:RONIN_REAL_DOCKER_QUALIFICATION = "1"
$env:RONIN_HOST_WORKSPACE = (Get-Location).Path

Start-Transcript -LiteralPath $transcript -Force | Out-Null
try {
    Write-Output "Source HEAD: $candidateSha"
    Write-Output "Qualification mode: $qualificationMode"
    if ($ImageId) {
        if (-not $TestFilter) { throw "-ImageId is allowed only with -TestFilter; full qualification must build from this checkout." }
        if ($ImageId -notmatch '^sha256:[0-9a-f]{64}$') { throw "-ImageId must be an immutable sha256 digest." }
        $resolvedImageId = $ImageId
        Write-Output "Filtered diagnostic reuses caller-supplied image $resolvedImageId; the current checkout's Docker image is not qualified."
    } else {
        $preexistingImageId = Get-DockerImageId $ImageTag
        docker build --file docker/Dockerfile `
            --label "org.ronin.qualification.run=$runId" `
            --tag $ImageTag .
        if ($LASTEXITCODE -ne 0) {
            throw "Docker image build failed with exit code $LASTEXITCODE"
        }
        $imageWasBuiltFromCheckout = $true
        $resolvedImageId = Get-DockerImageId $ImageTag
        if (-not $resolvedImageId) {
            throw "Docker qualification image did not resolve to an immutable image id"
        }
    }

    if ($needsPostgres) {
        docker run --detach --name $postgresContainerName `
            --publish "127.0.0.1:${postgresPort}:5432" `
            --env "POSTGRES_USER=ronin" `
            --env "POSTGRES_PASSWORD=$postgresPassword" `
            --env "POSTGRES_DB=ronin_test" `
            postgres:16.4-alpine
        if ($LASTEXITCODE -ne 0) {
            throw "Could not start the isolated PostgreSQL 16.4 Docker-worker qualification service."
        }
        $postgresStarted = $true
        $postgresDeadline = (Get-Date).AddSeconds(90)
        do {
            docker exec $postgresContainerName pg_isready -U ronin -d ronin_test | Out-Null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $postgresDeadline)
        if ($LASTEXITCODE -ne 0) {
            throw "The isolated PostgreSQL Docker-worker qualification service did not become ready."
        }
    }

    # Qualify S3 adapters against digest-pinned local Floci only when selected.
    if ($needsFloci) {
        $env:RONIN_FLOCI_PORT = [string]$flociPort
        $env:RONIN_TEST_S3_ENDPOINT = "http://127.0.0.1:$flociPort"
        $env:AWS_DEFAULT_REGION = "us-east-1"
        $env:AWS_ACCESS_KEY_ID = "ronin-qualification"
        $env:AWS_SECRET_ACCESS_KEY = "ronin-qualification"
        $flociStarted = $true
        docker compose -p $flociProject -f $flociCompose up -d floci
        if ($LASTEXITCODE -ne 0) {
            throw "Could not start isolated Floci for real S3 connector qualification."
        }
        $flociDeadline = (Get-Date).AddSeconds(90)
        $flociReady = $false
        do {
            try {
                $response = Invoke-WebRequest -Uri $env:RONIN_TEST_S3_ENDPOINT -UseBasicParsing -TimeoutSec 2
                $flociReady = $response.StatusCode -lt 500
            } catch {
                if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -lt 500) {
                    $flociReady = $true
                } else {
                    Start-Sleep -Milliseconds 500
                }
            }
        } while (-not $flociReady -and (Get-Date) -lt $flociDeadline)
        if (-not $flociReady) {
            throw "The isolated Floci S3-compatible service did not become ready."
        }
        Write-Output "Floci S3 integration endpoint ready: $env:RONIN_TEST_S3_ENDPOINT"
    }

    if ($needsAzurite) {
        $env:RONIN_AZURITE_PORT = [string]$azuritePort
        $env:RONIN_AZURITE_ENDPOINT = "http://127.0.0.1:$azuritePort"
        $env:RONIN_AZURITE_ACCOUNT = "devstoreaccount1"
        # Azurite's documented development account key is public emulator data,
        # not a credential for an Azure account or any remote service.
    $env:RONIN_AZURITE_ACCOUNT_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
        $azuriteStarted = $true
        docker compose -p $azuriteProject -f $azuriteCompose up -d azurite
        if ($LASTEXITCODE -ne 0) {
            throw "Could not start isolated Azurite for real Azure Blob connector qualification."
        }
        $azuriteDeadline = (Get-Date).AddSeconds(90)
        $azuriteReady = $false
        do {
            try {
                $response = Invoke-WebRequest -Uri $env:RONIN_AZURITE_ENDPOINT -UseBasicParsing -TimeoutSec 2
                $azuriteReady = $response.StatusCode -lt 500
            } catch {
                if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -lt 500) {
                    $azuriteReady = $true
                } else {
                    Start-Sleep -Milliseconds 500
                }
            }
        } while (-not $azuriteReady -and (Get-Date) -lt $azuriteDeadline)
        if (-not $azuriteReady) {
            throw "The isolated Azurite Blob service did not become ready."
        }
        Write-Output "Azurite Blob integration endpoint ready: $env:RONIN_AZURITE_ENDPOINT"
    }
    $env:RONIN_DOCKER_QUALIFICATION_IMAGE = $resolvedImageId
    $env:RONIN_DOCKER_QUALIFICATION_EVIDENCE = $evidenceRoot
    $env:RONIN_POSTGRES_TEST_DSN = $postgresDsn

    $pytestArguments = @(
        "-v", "--durations=15",
        "tests/integration/test_docker_container_executor_real.py",
        "tests/integration/test_worker_runtime_real.py",
        "tests/integration/test_s3_json_connector_real.py",
        "tests/integration/test_ml_s3_artifact_store_real.py",
        "tests/integration/test_azure_blob_connector_real.py",
        "tests/integration/test_postgres_appliance_backup_real.py",
        "tests/e2e/test_v01_journey.py",
        "--junitxml=$junitReport"
    )
    if ($TestFilter) {
        $pytestArguments += @("-k", $TestFilter)
        Write-Output "Filtered Docker diagnostic: pytest -k '$TestFilter'. Infrastructure is selected by suite: PostgreSQL for worker/database cases, Floci for S3 cases, and Azurite for Azure Blob cases. A filtered run is diagnostic only; strict v0.1 acceptance is omitted."
    } else {
        Write-Output "Docker acceptance scope: real Docker worker/runtime, PostgreSQL-backed journeys and appliance backup/restore, S3 connector and ML artifacts against Floci, Azure Blob JSONL against Azurite, and strict v0.1 journeys. Per-test progress and the slowest cases are recorded below."
    }
    & $python -m pytest @pytestArguments 2>&1 |
        ForEach-Object { "$_" -replace [regex]::Escape($postgresDsn), "postgresql://<redacted>" } |
        Tee-Object -FilePath $pytestOutput
    if ($LASTEXITCODE -ne 0) {
        throw "Docker acceptance tests failed with exit code $LASTEXITCODE"
    }

    [xml]$junit = Get-Content -Raw -LiteralPath $junitReport
    $skipped = $junit.SelectNodes("//testcase/skipped").Count
    $failed = $junit.SelectNodes("//testcase/failure | //testcase/error").Count
    if ($skipped -gt 0 -or $failed -gt 0) {
        throw "Docker qualification requires zero skips and failures; JUnit reported $skipped skipped and $failed failed."
    }
    $testCount = $junit.SelectNodes("//testcase").Count
    if ($testCount -eq 0) {
        throw "Docker qualification selected zero test cases; an empty selection cannot pass."
    }
    $executedCases = @($junit.SelectNodes("//testcase") | ForEach-Object { $_.GetAttribute("classname") + "::" + $_.GetAttribute("name") })
    $junitDuration = 0.0
    foreach ($suite in @($junit.SelectNodes("//testsuite"))) {
        $junitDuration += [double]$suite.GetAttribute("time")
    }
    $dockerRunKind = if ($TestFilter) { "filtered Docker diagnostic" } else { "Docker integration acceptance" }
    $imageAction = if ($imageWasBuiltFromCheckout) { "built from checkout" } else { "reused" }
    $fixtureNames = @()
    if ($needsPostgres) { $fixtureNames += "PostgreSQL + Docker worker" }
    if ($needsFloci) { $fixtureNames += "Floci/S3" }
    if ($needsAzurite) { $fixtureNames += "Azurite/Azure" }
    $fixtureSummary = if ($fixtureNames.Count -gt 0) { $fixtureNames -join ", " } else { "none" }
    Write-Output ("{0}: tests completed; {1} tests, {2} skipped, {3} failed; Ronin image {4} ({5}); selected fixtures: {6}; pytest {7}s; cleanup pending." -f `
        $dockerRunKind, $testCount, $skipped, $failed, $resolvedImageId, $imageAction, $fixtureSummary, [Math]::Round($junitDuration, 2))
    foreach ($caseName in $executedCases) { Write-Output "Executed: $caseName" }
    Write-Output "Docker pytest console output: $pytestOutput"

    if ($TestFilter) {
        Write-Output "Diagnostic only: strict v0.1 acceptance was not evaluated; run without -TestFilter for the full gate."
    } else {
        & $python -m tools.v01_acceptance_gate `
            $junitReport `
            "--evidence-json=$acceptanceEvidence"
        if ($LASTEXITCODE -ne 0) {
            throw "Strict Docker acceptance gate failed with exit code $LASTEXITCODE"
        }
        Write-Output ("Docker integration acceptance: PASS; {0} tests, 0 skipped, 0 failed; Ronin image {1} ({2}); selected fixtures: {3}; pytest {4}s; cleanup pending." -f `
            $testCount, $resolvedImageId, $imageAction, $fixtureSummary, [Math]::Round($junitDuration, 2))
        Write-Output "Docker qualification evidence: $evidenceRoot"
    }
} finally {
    if ($azuriteStarted) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            docker compose -p $azuriteProject -f $azuriteCompose logs azurite 2>&1 |
                Set-Content -LiteralPath $azuriteLog -Encoding utf8
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Could not save logs for isolated Azurite project '$azuriteProject'."
            }
            docker compose -p $azuriteProject -f $azuriteCompose down --volumes --remove-orphans 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Add-CleanupFailure "Could not remove isolated Azurite project '$azuriteProject'."
            }
        } catch {
            Add-CleanupFailure "Azurite cleanup for '$azuriteProject' raised an error: $($_.Exception.Message)"
            try {
                docker compose -p $azuriteProject -f $azuriteCompose down --volumes --remove-orphans 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Add-CleanupFailure "Retry could not remove isolated Azurite project '$azuriteProject'."
                }
            } catch {
                Add-CleanupFailure "Retry of Azurite cleanup for '$azuriteProject' raised an error: $($_.Exception.Message)"
            }
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    if ($flociStarted) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            docker compose -p $flociProject -f $flociCompose logs floci 2>&1 |
                Set-Content -LiteralPath $flociLog -Encoding utf8
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Could not save logs for isolated Floci project '$flociProject'."
            }
            docker compose -p $flociProject -f $flociCompose down --volumes --remove-orphans 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Add-CleanupFailure "Could not remove isolated Floci project '$flociProject'."
            }
        } catch {
            Add-CleanupFailure "Floci cleanup for '$flociProject' raised an error: $($_.Exception.Message)"
            try {
                docker compose -p $flociProject -f $flociCompose down --volumes --remove-orphans 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Add-CleanupFailure "Retry could not remove isolated Floci project '$flociProject'."
                }
            } catch {
                Add-CleanupFailure "Retry of Floci cleanup for '$flociProject' raised an error: $($_.Exception.Message)"
            }
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    if ($postgresStarted) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            # Windows PowerShell promotes stderr from native executables to
            # NativeCommandError records. PostgreSQL's Alpine image can emit
            # the harmless "locale: not found" notice on stderr during logs;
            # that must not abort this finally block before container cleanup.
            $ErrorActionPreference = "Continue"
            docker logs $postgresContainerName 2>&1 | Set-Content -LiteralPath $postgresLog -Encoding utf8
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Could not save logs for isolated PostgreSQL container '$postgresContainerName'."
            }
            docker rm --force --volumes $postgresContainerName 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Add-CleanupFailure "Could not remove isolated PostgreSQL container '$postgresContainerName'."
            }
        } catch {
            Add-CleanupFailure "Docker cleanup for isolated PostgreSQL container '$postgresContainerName' raised an error: $($_.Exception.Message)"
            try {
                docker rm --force --volumes $postgresContainerName 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Add-CleanupFailure "Retry could not remove isolated PostgreSQL container '$postgresContainerName'."
                }
            } catch {
                Add-CleanupFailure "Retry of PostgreSQL cleanup for '$postgresContainerName' raised an error: $($_.Exception.Message)"
            }
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    if ($imageWasBuiltFromCheckout) {
        if ($KeepImage) {
            $imageCleanupStatus = "kept-by-operator"
            Write-Warning "Ronin qualification image '$ImageTag' ($resolvedImageId) was kept by explicit -KeepImage; remove it after the dependent qualification lane finishes."
        } else {
            try {
                if (-not $resolvedImageId) {
                    $resolvedImageId = Get-DockerImageId $ImageTag
                }
                Remove-OwnedQualificationImage `
                    -BuiltImageId $resolvedImageId `
                    -ImageTag $ImageTag `
                    -OwnerRunId $runId `
                    -PreexistingImageId $preexistingImageId
                $imageCleanupStatus = "succeeded"
                Write-Output "Ronin qualification image cleanup: removed owned image $resolvedImageId."
            } catch {
                $imageCleanupStatus = "failed"
                Add-CleanupFailure "Ronin qualification image cleanup failed: $($_.Exception.Message)"
            }
        }
    } elseif ($ImageId) {
        $imageCleanupStatus = "caller-supplied-image-left-intact"
        Write-Output "Ronin qualification image cleanup: caller-supplied image left intact."
    } else {
        $imageCleanupStatus = "build-did-not-produce-owned-image"
        Write-Output "Ronin qualification image cleanup: no owned image was produced."
    }
    $cleanupReceipt = [ordered]@{
        schema = "ronin.docker-cleanup/v1"
        run_id = $runId
        image_tag = $ImageTag
        image_id = $resolvedImageId
        image_built_from_checkout = $imageWasBuiltFromCheckout
        image_cleanup = $imageCleanupStatus
        postgres_container = $postgresContainerName
        postgres_started = $postgresStarted
        floci_project = $flociProject
        floci_started = $flociStarted
        azurite_project = $azuriteProject
        azurite_started = $azuriteStarted
        status = if ($cleanupFailures.Count -gt 0) {
            "failed"
        } elseif ($imageCleanupStatus -eq "kept-by-operator") {
            "passed-with-explicit-retention"
        } elseif ($imageCleanupStatus -eq "build-did-not-produce-owned-image") {
            "not-applicable"
        } else {
            "passed"
        }
        failures = @($cleanupFailures)
    }
    try {
        $cleanupReceipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $cleanupReceiptPath -Encoding utf8
    } catch {
        Add-CleanupFailure "Could not write Docker cleanup receipt '$cleanupReceiptPath': $($_.Exception.Message)"
    }
    if ($cleanupFailures.Count -gt 0) {
        Write-Output ("Docker qualification cleanup: FAILED ({0})." -f ($cleanupFailures -join "; "))
    } elseif ($imageCleanupStatus -eq "kept-by-operator") {
        Write-Output "Docker qualification cleanup: PASS for temporary resources; image intentionally retained by -KeepImage."
    } else {
        Write-Output "Docker qualification cleanup: PASS."
    }
    [Environment]::SetEnvironmentVariable("RONIN_POSTGRES_TEST_DSN", $savedPostgresTestDsn, "Process")
    foreach ($name in $savedFlociEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedFlociEnvironment[$name], "Process")
    }
    Stop-Transcript | Out-Null
}

if ($cleanupFailures.Count -gt 0) {
    throw ("Docker qualification cleanup failed: " + ($cleanupFailures -join "; "))
}
if ($KeepImage -and $imageWasBuiltFromCheckout) {
    Write-Output "Docker qualification: PASS; temporary resources cleaned and image retained only for the explicit downstream hand-off."
} elseif (-not $imageWasBuiltFromCheckout) {
    Write-Output "Docker qualification: PASS; tests and runner-owned resources cleaned, caller-supplied image preserved."
} else {
    Write-Output "Docker qualification: PASS; tests and owned resources cleaned."
}
