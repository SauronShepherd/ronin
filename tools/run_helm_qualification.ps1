param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [Parameter(Mandatory = $true)]
    [string]$ImageRef,
    [Parameter(Mandatory = $true)]
    [string]$DockerEvidenceDirectory,
    [string]$HelmPath = "helm",
    [string]$KindPath = "kind",
    [string]$KubectlPath = "kubectl",
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
    throw "Helm evidence must be outside the checkout: $evidenceRoot"
}
if (Test-Path -LiteralPath $evidenceRoot) {
    if (@(Get-ChildItem -LiteralPath $evidenceRoot -Force).Count -gt 0) {
        throw "Evidence directory is not empty; use a unique path: $evidenceRoot"
    }
} else {
    New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
}

function Resolve-Executable([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return [IO.Path]::GetFullPath($Path)
    }
    $command = Get-Command $Path -ErrorAction Stop
    return $command.Source
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

function Add-Phase([string]$Name, [string]$Status) {
    $script:phases[$Name] = $Status
    Write-Output ("{0}: {1}" -f $Name, $Status)
}

function Get-HelmRevisionRecords($Value) {
    if ($null -eq $Value) { return }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        foreach ($item in $Value) { Get-HelmRevisionRecords $item }
        return
    }
    $revisionProperty = $Value.PSObject.Properties["revision"]
    if ($null -ne $revisionProperty) {
        $Value
        return
    }
    foreach ($property in $Value.PSObject.Properties) {
        Get-HelmRevisionRecords $property.Value
    }
}

$helm = Resolve-Executable $HelmPath
$kind = Resolve-Executable $KindPath
$kubectl = Resolve-Executable $KubectlPath
$candidateSha = (git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $candidateSha -notmatch "^[0-9a-f]{40}$") {
    throw "Could not identify the source revision."
}
$workingTreeStatus = @(git -C $repoRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw "Could not determine worktree status." }
if ($workingTreeStatus.Count -gt 0 -and -not $AllowDirtyWorktree) {
    throw "Refusing release qualification with a dirty worktree. Use -AllowDirtyWorktree only for diagnostics."
}
$qualificationMode = if ($workingTreeStatus.Count -gt 0) { "DIRTY-WORKTREE DIAGNOSTIC" } else { "CLEAN-CANDIDATE QUALIFICATION" }
$dockerEvidenceRoot = [IO.Path]::GetFullPath($DockerEvidenceDirectory)
if (-not (Test-Path -LiteralPath $dockerEvidenceRoot -PathType Container)) {
    throw "Docker evidence directory does not exist: $dockerEvidenceRoot"
}
$dockerEvidencePrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($dockerEvidenceRoot.StartsWith($dockerEvidencePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Docker qualification evidence must be outside the checkout."
}
$dockerLogPath = Join-Path $dockerEvidenceRoot "docker-qualification.log"
$dockerStrictPath = Join-Path $dockerEvidenceRoot "v01-acceptance-strict.json"
if (-not (Test-Path -LiteralPath $dockerLogPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $dockerStrictPath -PathType Leaf)) {
    throw "Docker evidence must include the qualification transcript and strict v0.1 receipt."
}
$dockerLog = Get-Content -Raw -LiteralPath $dockerLogPath
if (-not $dockerLog.Contains("Source HEAD: $candidateSha") -or
    -not $dockerLog.Contains("Qualification mode: $qualificationMode")) {
    throw "Docker qualification evidence does not match this source SHA and worktree mode."
}
$dockerAcceptance = [regex]::Match(
    $dockerLog,
    "Docker integration acceptance: PASS; \d+ tests, 0 skipped, 0 failed; Ronin image (sha256:[0-9a-f]{64}) \(built from checkout\);"
)
if (-not $dockerAcceptance.Success) {
    throw "A full Docker integration acceptance receipt with a zero-skip result is required."
}
$strictReceipt = Get-Content -Raw -LiteralPath $dockerStrictPath | ConvertFrom-Json
if ($strictReceipt.strict_success -ne $true -or $strictReceipt.passed -ne 15 -or
    $strictReceipt.total_expected -ne 15 -or $strictReceipt.skipped -ne 0 -or
    $strictReceipt.failed -ne 0 -or $strictReceipt.missing -ne 0 -or
    $strictReceipt.errors -ne 0 -or $strictReceipt.xfailed -ne 0) {
    throw "Docker evidence does not contain strict v0.1 acceptance 15/15 without skips or failures."
}
$dockerImageId = $dockerAcceptance.Groups[1].Value
$imageTagSeparator = $ImageRef.LastIndexOf(":")
$imagePathSeparator = $ImageRef.LastIndexOf("/")
if ($imageTagSeparator -le $imagePathSeparator -or $ImageRef.Contains("@")) {
    throw "ImageRef must include an explicit tag (digest-only references are not accepted)."
}
$imageId = (docker image inspect $ImageRef --format "{{.Id}}").Trim()
if ($LASTEXITCODE -ne 0 -or $imageId -notmatch "^sha256:[0-9a-f]{64}$") {
    throw "The supplied Ronin image is missing or does not resolve to an immutable ID: $ImageRef"
}
if ($imageId -ne $dockerImageId) {
    throw "Supplied Ronin image ID does not match the full Docker acceptance evidence."
}
if (Select-String -Path (Join-Path $repoRoot "deploy\helm\ronin\values.yaml"), (Join-Path $repoRoot "deploy\helm\ronin\values.schema.json") -Pattern "multiUser" -Quiet) {
    throw "Public Helm values/schema must not expose Ronin Pro multi-user settings."
}

$runId = [guid]::NewGuid().ToString("N").Substring(0, 10)
$clusterName = "ronin-qa-$($candidateSha.Substring(0, 8))-$runId".ToLowerInvariant()
$kubeContext = "kind-$clusterName"
$namespace = "ronin-qualification"
$port = Get-FreeLoopbackPort
$runRoot = Join-Path ([IO.Path]::GetTempPath()) "ronin-helm-$runId"
$valuesPath = Join-Path $runRoot "values.yaml"
$transcriptPath = Join-Path $evidenceRoot "helm-qualification.log"
$receiptPath = Join-Path $evidenceRoot "helm-qualification.json"
$phases = [ordered]@{}
$forward = $null
$failure = $null
$cleanupStatus = "not-needed"
$healthStatus = $null
$studioStatus = $null
$jobsStatus = $null
$restartJobId = $null
$restartPersistence = $false
$upgradeRevision = $null
$rollbackStatus = $null
$renderedResourceCount = 0
$tokenConfinedToSecret = $false
$token = [guid]::NewGuid().ToString("N")
$tokenScopes = '{"version":1,"grants":[{"version":1,"actions":["read","list","events","submit","execute","cancel","evidence:read"],"resource":{"kind":"project","identifier":"examples/demo"},"constraints":{}}]}'

Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
try {
    Write-Output "Source: $candidateSha ($qualificationMode)"
    Write-Output "Helm: $(& $helm version --short)"
    Write-Output "Ronin image: $imageId"
    Write-Output "Docker acceptance receipt: $dockerEvidenceRoot (strict 15/15)"

    $existingClusters = @(& $kind get clusters)
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect kind clusters." }
    if ($existingClusters -contains $clusterName) { throw "Refusing to reuse cluster '$clusterName'." }
    New-Item -ItemType Directory -Path $runRoot | Out-Null
    @"
image:
  repository: $($ImageRef.Substring(0, $ImageRef.LastIndexOf(':')))
  tag: $($ImageRef.Substring($ImageRef.LastIndexOf(':') + 1))
  pullPolicy: IfNotPresent
server:
  replicas: 1
  token: $token
  tokenScopes: '$tokenScopes'
  bindPolicy: insecure-plaintext-network
"@ | Set-Content -LiteralPath $valuesPath -Encoding utf8

    & $helm lint (Join-Path $repoRoot "deploy\helm\ronin") --values $valuesPath
    if ($LASTEXITCODE -ne 0) { throw "Helm lint failed." }
    Add-Phase "helm_lint" "passed"

    $rendered = (& $helm template ronin (Join-Path $repoRoot "deploy\helm\ronin") `
        --namespace $namespace --values $valuesPath | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Helm template failed." }
    $documents = @($rendered -split "(?m)^---\s*$" | Where-Object { $_.Trim() })
    $secretDocuments = @($documents | Where-Object { $_ -match "(?m)^kind:\s*Secret\s*$" })
    $otherDocuments = @($documents | Where-Object { $_ -notmatch "(?m)^kind:\s*Secret\s*$" })
    $encodedToken = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($token))
    $tokenConfinedToSecret = $secretDocuments.Count -gt 0 -and
        @($otherDocuments | Where-Object { $_.Contains($token) -or $_.Contains($encodedToken) }).Count -eq 0
    if (-not $tokenConfinedToSecret) { throw "Rendered token was absent from Secret or leaked to a non-Secret resource." }
    $renderedResourceCount = $documents.Count
    Add-Phase "helm_render_secret_boundary" "passed ($renderedResourceCount resources; token confined to Secret)"
    $rendered = $null
    $documents = $null

    $null = & $kind create cluster --name $clusterName --wait 180s
    if ($LASTEXITCODE -ne 0) { throw "Could not create isolated kind cluster '$clusterName'." }
    Add-Phase "kind_cluster" "passed ($clusterName)"

    & $kind load docker-image $ImageRef --name $clusterName
    if ($LASTEXITCODE -ne 0) { throw "Could not load the Ronin image into kind." }
    Add-Phase "load_ronin_image" "passed ($imageId)"

    & $helm upgrade --install ronin (Join-Path $repoRoot "deploy\helm\ronin") `
        --kube-context $kubeContext --namespace $namespace --create-namespace --values $valuesPath
    if ($LASTEXITCODE -ne 0) { throw "Helm install/upgrade failed." }
    Add-Phase "helm_install" "passed"

    $deployment = (& $kubectl --context $kubeContext get deployments -n $namespace `
        -o jsonpath="{.items[0].metadata.name}").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $deployment) { throw "Ronin deployment is missing." }
    & $kubectl --context $kubeContext rollout status "deployment/$deployment" `
        -n $namespace --timeout=180s
    if ($LASTEXITCODE -ne 0) {
        & $kubectl --context $kubeContext get pods -n $namespace -o wide
        & $kubectl --context $kubeContext describe pods -n $namespace
        throw "Ronin deployment did not become ready."
    }
    $replicas = (& $kubectl --context $kubeContext get deployment $deployment -n $namespace `
        -o jsonpath="{.spec.replicas}").Trim()
    $deployedImage = (& $kubectl --context $kubeContext get deployment $deployment -n $namespace `
        -o jsonpath="{.spec.template.spec.containers[0].image}").Trim()
    if ($LASTEXITCODE -ne 0 -or $replicas -ne "1" -or $deployedImage -ne $ImageRef) {
        throw "Deployment must use exactly one replica and the supplied Ronin image."
    }
    $resourceInventory = & $kubectl --context $kubeContext get pods,services,pvc,secrets `
        -n $namespace -o wide 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "Could not capture Kubernetes resource inventory." }
    $resourceInventory | Set-Content -LiteralPath (Join-Path $evidenceRoot "kubernetes-resources.txt") -Encoding utf8
    Add-Phase "deployment_readiness" "passed"

    & $helm upgrade ronin (Join-Path $repoRoot "deploy\helm\ronin") `
        --kube-context $kubeContext --namespace $namespace --reuse-values `
        --description "Ronin qualification upgrade rehearsal"
    if ($LASTEXITCODE -ne 0) { throw "Helm upgrade rehearsal failed." }
    $historyPayload = (& $helm history ronin --kube-context $kubeContext --namespace $namespace -o json | ConvertFrom-Json)
    # Helm 4 wraps JSON history in a `history` property; Helm 3 emitted the
    # revisions directly. Normalize both forms before enforcing the upgrade gate.
    $history = @(Get-HelmRevisionRecords $historyPayload)
    if ($LASTEXITCODE -ne 0 -or $history.Count -lt 2) {
        throw "Helm upgrade rehearsal did not create a second release revision."
    }
    $upgradeRevision = [int](($history | Sort-Object { [int]$_.revision } | Select-Object -Last 1).revision)
    if ($upgradeRevision -lt 2) { throw "Helm history did not expose a valid upgrade revision." }
    Add-Phase "helm_upgrade" "passed (revision $upgradeRevision)"

    & $helm rollback ronin 1 --kube-context $kubeContext --namespace $namespace --wait --timeout 180s
    if ($LASTEXITCODE -ne 0) { throw "Helm rollback to revision 1 failed." }
    & $kubectl --context $kubeContext rollout status "deployment/$deployment" `
        -n $namespace --timeout=180s
    if ($LASTEXITCODE -ne 0) { throw "Deployment did not become ready after Helm rollback." }
    $rollbackStatus = "passed"
    Add-Phase "helm_rollback" "passed (restored revision 1)"

    $service = (& $kubectl --context $kubeContext get services -n $namespace `
        -o jsonpath="{.items[0].metadata.name}").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $service) { throw "Ronin Service is missing." }
    $forward = Start-Process -FilePath $kubectl -ArgumentList @(
        "--context", $kubeContext, "port-forward", "-n", $namespace,
        "service/$service", "${port}:8080"
    ) -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $evidenceRoot "port-forward.log") `
        -RedirectStandardError (Join-Path $evidenceRoot "port-forward-error.log")
    $deadline = (Get-Date).AddSeconds(45)
    do {
        if ($forward.HasExited) { throw "kubectl port-forward exited with code $($forward.ExitCode)." }
        try {
            $health = Invoke-WebRequest "http://127.0.0.1:$port/healthz" -UseBasicParsing -TimeoutSec 2
            if ($health.StatusCode -eq 200) { $healthStatus = $health.StatusCode }
        } catch {
            Start-Sleep -Seconds 1
        }
    } while ($null -eq $healthStatus -and (Get-Date) -lt $deadline)
    if ($null -eq $healthStatus) { throw "Ronin /healthz did not return HTTP 200." }
    Add-Phase "health_endpoint" "passed (HTTP $healthStatus)"

    $studio = Invoke-WebRequest "http://127.0.0.1:$port/studio/" -UseBasicParsing -TimeoutSec 10
    $studioStatus = $studio.StatusCode
    if ($studioStatus -ne 200) { throw "Studio did not return HTTP 200." }
    $jobs = Invoke-RestMethod "http://127.0.0.1:$port/v1/jobs?project=examples%2Fdemo&limit=10" `
        -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 10
    $jobsStatus = 200
    Add-Phase "studio_and_authorized_api" "passed (Studio HTTP $studioStatus; jobs API HTTP $jobsStatus)"

    $submitBody = '{"project":"examples/demo","target":"notebooks/etl","parameters":{"limit":7}}'
    $submittedResponse = Invoke-WebRequest "http://127.0.0.1:$port/v1/jobs" -UseBasicParsing -Method Post `
        -Headers @{ Authorization = "Bearer $token"; "Idempotency-Key" = "helm-$runId" } `
        -ContentType "application/json" -Body $submitBody -TimeoutSec 10
    if ($submittedResponse.StatusCode -ne 201) { throw "Job submit did not return HTTP 201." }
    $submittedJob = $submittedResponse.Content | ConvertFrom-Json
    $restartJobId = [string]$submittedJob.id
    if (-not $restartJobId) { throw "Job submit response omitted the job ID." }
    $beforeRestart = Invoke-RestMethod "http://127.0.0.1:$port/v1/jobs/$restartJobId" `
        -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 10
    if ($beforeRestart.state -ne "queued") { throw "New Helm smoke job did not start queued." }
    Add-Phase "persistent_job_create" "passed (HTTP 201; job remains queued without a worker)"

    Stop-Process -Id $forward.Id -Force
    $forward = $null
    & $kubectl --context $kubeContext rollout restart "deployment/$deployment" -n $namespace
    if ($LASTEXITCODE -ne 0) { throw "Could not restart the Ronin deployment." }
    & $kubectl --context $kubeContext rollout status "deployment/$deployment" `
        -n $namespace --timeout=180s
    if ($LASTEXITCODE -ne 0) { throw "Ronin deployment did not recover after restart." }
    Add-Phase "deployment_restart" "passed"

    $forward = Start-Process -FilePath $kubectl -ArgumentList @(
        "--context", $kubeContext, "port-forward", "-n", $namespace,
        "service/$service", "${port}:8080"
    ) -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $evidenceRoot "port-forward-restart.log") `
        -RedirectStandardError (Join-Path $evidenceRoot "port-forward-restart-error.log")
    $deadline = (Get-Date).AddSeconds(45)
    $persistedJob = $null
    do {
        if ($forward.HasExited) { throw "Restarted kubectl port-forward exited with code $($forward.ExitCode)." }
        try {
            $persistedJob = Invoke-RestMethod "http://127.0.0.1:$port/v1/jobs/$restartJobId" `
                -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 3
        } catch {
            Start-Sleep -Seconds 1
        }
    } while ($null -eq $persistedJob -and (Get-Date) -lt $deadline)
    if (-not $persistedJob -or $persistedJob.id -ne $restartJobId -or $persistedJob.state -ne "queued") {
        throw "Submitted job was not durable across the Kubernetes pod restart."
    }
    $restartPersistence = $true
    Add-Phase "persistent_job_after_restart" "passed (same queued job ID survived pod restart)"
} catch {
    $failure = $_.Exception.Message
    Write-Warning $failure
} finally {
    if ($forward -and -not $forward.HasExited) { Stop-Process -Id $forward.Id -Force }
    try {
        try { $remainingClusters = @(& $kind get clusters 2>&1) } catch { $remainingClusters = @("No kind clusters found.") }
        if ($LASTEXITCODE -ne 0 -and -not (($remainingClusters -join " ") -match "No kind clusters found")) { throw "Could not inspect kind clusters during cleanup." }
        if ($remainingClusters -contains $clusterName) {
            & $kubectl --context $kubeContext delete namespace $namespace `
                --ignore-not-found=true --wait=true 2>$null | Out-Null
            & $kind delete cluster --name $clusterName
            if ($LASTEXITCODE -ne 0) { throw "Could not delete isolated kind cluster '$clusterName'." }
        }
        try { $remainingClusters = @(& $kind get clusters 2>&1) } catch { $remainingClusters = @("No kind clusters found.") }
        if ((($LASTEXITCODE -ne 0 -and -not (($remainingClusters -join " ") -match "No kind clusters found")) -or $remainingClusters -contains $clusterName)) {
            throw "Isolated kind cluster remains after cleanup."
        }
        $cleanupStatus = "passed"
        Add-Phase "cleanup" "passed; isolated cluster removed"
    } catch {
        $cleanupStatus = "failed: $($_.Exception.Message)"
        Write-Warning $cleanupStatus
        if (-not $failure) { $failure = $cleanupStatus }
    }
    Remove-Item -LiteralPath $valuesPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $runRoot -Force -ErrorAction SilentlyContinue
    $receipt = [ordered]@{
        schema = "ronin.helm-qualification/v1"
        candidate_sha = $candidateSha
        qualification_mode = $qualificationMode
        image_ref = $ImageRef
        image_id = $imageId
        docker_evidence_directory = $dockerEvidenceRoot
        docker_candidate_sha = $candidateSha
        docker_strict_acceptance = "15/15"
        bind_policy = "insecure-plaintext-network"
        helm_version = (& $helm version --short | Out-String).Trim()
        cluster = $clusterName
        rendered_resource_count = $renderedResourceCount
        token_confined_to_secret = $tokenConfinedToSecret
        health_status = $healthStatus
        studio_status = $studioStatus
        authorized_jobs_status = $jobsStatus
        restart_job_id = $restartJobId
        restart_persistence = $restartPersistence
        upgrade_revision = $upgradeRevision
        rollback_status = $rollbackStatus
        phases = $phases
        cleanup = $cleanupStatus
        result = if ($failure) { "failed" } else { "passed" }
        failure = $failure
    }
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding utf8
    Stop-Transcript | Out-Null
}

if ($failure) { throw "Helm qualification failed. Evidence: $evidenceRoot" }
Write-Output "Helm qualification passed. Evidence: $evidenceRoot"
