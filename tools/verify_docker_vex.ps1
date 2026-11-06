param(
    [string]$ImageRef = "ronin:qualification",
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDirectory,
    [string]$VexPath = "docker/qualification-image-vex.openvex.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$evidenceRoot = [IO.Path]::GetFullPath($EvidenceDirectory)
$repoPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($evidenceRoot.Equals($repoRoot, [StringComparison]::OrdinalIgnoreCase) -or $evidenceRoot.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Image scan evidence must be outside the checkout: $evidenceRoot"
}
if (Test-Path -LiteralPath $evidenceRoot) {
    if (@(Get-ChildItem -LiteralPath $evidenceRoot -Force).Count -gt 0) {
        throw "Evidence directory is not empty; use a new unique path: $evidenceRoot"
    }
} else {
    New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
}

$vexFullPath = if ([IO.Path]::IsPathRooted($VexPath)) {
    [IO.Path]::GetFullPath($VexPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $repoRoot $VexPath))
}
if (-not (Test-Path -LiteralPath $vexFullPath -PathType Leaf)) {
    throw "-VexPath must name an existing VEX file."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI is required." }
$scoutVersionOutput = (& docker scout version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) { throw "Could not determine Docker Scout version." }
$scoutVersionMatch = [regex]::Match($scoutVersionOutput, '(?m)^version:\s*(?<version>v?\d+\.\d+\.\d+)')
if (-not $scoutVersionMatch.Success) { throw "Docker Scout version output was not recognized." }

$inspectOutput = & docker image inspect $ImageRef 2>&1
if ($LASTEXITCODE -ne 0) { throw "Could not inspect image '$ImageRef': $inspectOutput" }
$image = @($inspectOutput | ConvertFrom-Json)[0]
$repoDigest = @($image.RepoDigests)[0]
if ($repoDigest -and $repoDigest -match '^(?<name>.+)@(?<digest>sha256:[0-9a-f]{64})$') {
    $imageName = $Matches.name
    $imageDigest = $Matches.digest
    $imageDigestKind = "registry-manifest-digest"
} else {
    # Locally qualified builds are intentionally not pushed to a registry. Bind
    # their VEX statements to Docker's immutable image-config ID instead.
    $imageDigest = [string]$image.Id
    $imageName = $ImageRef -replace ':[^/:]+$', ''
    $imageDigestKind = "local-image-config-digest"
    if ($imageDigest -notmatch '^sha256:[0-9a-f]{64}$' -or -not $imageName) {
        throw "Image '$ImageRef' has no valid immutable registry digest or local image ID."
    }
}
$imagePurl = "pkg:docker/$imageName@$imageDigest"
$vex = Get-Content -Raw -LiteralPath $vexFullPath | ConvertFrom-Json
$author = [string]$vex.author
if (-not $author) { throw "OpenVEX document must name its author." }
$expectedVulnerabilities = @("CVE-2026-107891", "CVE-2026-119586", "CVE-2026-4738")
$vexStatements = @($vex.statements)
$statementVulnerabilities = @($vexStatements | ForEach-Object { [string]$_.vulnerability.name })
if (
    $statementVulnerabilities.Count -ne $expectedVulnerabilities.Count -or
    (@($statementVulnerabilities | Sort-Object) -join ",") -ne
    (@($expectedVulnerabilities | Sort-Object) -join ",")
) {
    throw "OpenVEX must contain exactly the reviewed vulnerability statements."
}
foreach ($statement in $vexStatements) {
    if ($statement.status -ne "not_affected" -or $statement.justification -ne "vulnerable_code_not_present") {
        throw "OpenVEX statements must explicitly justify that vulnerable code is not present."
    }
    $productMatches = @($statement.products | Where-Object { $_.'@id' -eq $imagePurl })
    if ($productMatches.Count -ne 1) {
        throw "OpenVEX must bind each vulnerability exactly once to this image digest: $imagePurl"
    }
}

$rawReport = Join-Path $evidenceRoot "docker-scout-raw.sarif.json"
$vexReport = Join-Path $evidenceRoot "docker-scout-vex-applied.sarif.json"
$vexEvidence = Join-Path $evidenceRoot "qualification-image-vex.openvex.json"
Copy-Item -LiteralPath $vexFullPath -Destination $vexEvidence
$vexSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $vexEvidence).Hash.ToLowerInvariant()
$summaryPath = Join-Path $evidenceRoot "docker-scout-summary.json"
$scoutImage = "local://$ImageRef"

& docker scout cves --format sarif --output $rawReport $scoutImage
if ($LASTEXITCODE -ne 0) { throw "Docker Scout raw scan failed; see $rawReport" }
& docker scout cves --vex-location $vexEvidence --vex-author $author --format sarif --output $vexReport $scoutImage
if ($LASTEXITCODE -ne 0) { throw "Docker Scout VEX scan failed; see $vexReport" }

function Read-SarifFindings([string]$Path) {
    $document = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    foreach ($run in $document.runs) {
        foreach ($result in $run.results) {
            $message = [string]$result.message.text
            $cveMatch = [regex]::Match($message, '(?m)^\s*Vulnerability\s*:\s*(?<id>\S+)\s*$')
            $packageMatch = [regex]::Match($message, '(?m)^\s*Package\s*:\s*(?<purl>\S+)\s*$')
            [pscustomobject]@{
                id = if ($cveMatch.Success) { $cveMatch.Groups["id"].Value } else { [string]$result.ruleId }
                package = if ($packageMatch.Success) { $packageMatch.Groups["purl"].Value } else { "" }
                level = [string]$result.level
            }
        }
    }
}

$rawFindings = @(Read-SarifFindings $rawReport)
$vexFindings = @(Read-SarifFindings $vexReport)
$expectedFindings = @(
    [pscustomobject]@{
        id = "CVE-2026-107891"
        package = "pkg:apk/alpine/musl@1.2.6-r3?os_name=alpine&os_version=3.24"
    }
    [pscustomobject]@{
        id = "CVE-2026-119586"
        package = "pkg:apk/alpine/sqlite@3.53.4-r0?os_name=alpine&os_version=3.24"
    }
    [pscustomobject]@{
        id = "CVE-2026-4738"
        package = "pkg:apk/alpine/zlib@1.3.2-r1?os_name=alpine&os_version=3.24"
    }
)
if ($rawFindings.Count -ne $expectedFindings.Count) {
    throw "Raw scan finding count differs from the reviewed set; review $rawReport before accepting this image."
}
foreach ($expectedFinding in $expectedFindings) {
    $matchingFindings = @(
        $rawFindings | Where-Object {
            $_.id -eq $expectedFinding.id -and $_.package -eq $expectedFinding.package
        }
    )
    if ($matchingFindings.Count -ne 1) {
        throw "Raw scan does not match the reviewed finding $($expectedFinding.id); review $rawReport."
    }
}
if ($vexFindings.Count -ne 0) {
    throw "Docker Scout still reports vulnerabilities after applying the digest-bound VEX; review $vexReport."
}

$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not identify source HEAD." }
$gitStatus = @(git -C $repoRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw "Could not determine worktree state." }
$summary = [ordered]@{
    schema = "ronin.docker-scout-vex-qualification/v1"
    status = "passed"
    qualification_mode = "diagnostic; candidate binding is not claimed"
    source_commit = $gitHead
    worktree_clean = ($gitStatus.Count -eq 0)
    scanner = "Docker Scout $($scoutVersionMatch.Groups['version'].Value)"
    scanned_at_utc = [DateTime]::UtcNow.ToString("o")
    image_ref = $ImageRef
    image_id = [string]$image.Id
    image_digest = [string]$imageDigest
    image_digest_kind = $imageDigestKind
    image_purl = $imagePurl
    scout_vex_author = $author
    vex_path = [IO.Path]::GetRelativePath($repoRoot, $vexFullPath)
    vex_sha256 = $vexSha256
    vex_evidence_file = $vexEvidence
    raw_findings = $rawFindings
    vex_findings = $vexFindings
    vex_suppressed_reviewed_findings = $rawFindings.Count
    security_review_required = $true
    security_review_accepted = $false
    release_security_gate_closed = $false
    raw_sarif = $rawReport
    vex_sarif = $vexReport
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8
Write-Output "Docker Scout VEX qualification passed for $imagePurl."
Write-Output "Raw findings: $($rawFindings.Count); findings after explicit VEX author: $($vexFindings.Count)."
Write-Output "Evidence: $evidenceRoot"
