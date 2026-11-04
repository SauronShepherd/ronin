function Get-RoninTestPythonEnvironment {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$CheckoutRoot,
        [string]$RequirementsLock = "requirements-test.lock"
    )

    $checkout = [IO.Path]::GetFullPath($CheckoutRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $hostPython = (Get-Command python -ErrorAction Stop).Source
    $pythonVersion = (& $hostPython --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3\.') {
        throw "Could not identify the host Python interpreter for the locked test environment."
    }

    $lockPath = Join-Path $checkout $RequirementsLock
    if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
        throw "The hash-locked test dependency file is missing: $lockPath"
    }
    $lockHash = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $projectPath = Join-Path $checkout "pyproject.toml"
    $projectHash = (Get-FileHash -LiteralPath $projectPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $fingerprintInput = [string]::Join("`n", @(
        "schema=2", "repository=$checkout", "python=$hostPython", "version=$pythonVersion",
        "requirements=$lockHash", "project=$projectHash"
    ))
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $fingerprint = ([BitConverter]::ToString(
            $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($fingerprintInput))
        ).Replace("-", "")).ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }

    $cacheRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Ronin\qualification-cache\python"
    New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
    $environmentPath = Join-Path $cacheRoot $fingerprint
    $cacheMarker = Join-Path $environmentPath ".ronin-qualification-cache.json"
    $python = Join-Path $environmentPath "Scripts\python.exe"
    $lockFile = Join-Path $cacheRoot "$fingerprint.lock"
    $lockStream = $null
    $lockDeadline = (Get-Date).AddMinutes(2)
    while ($null -eq $lockStream) {
        try {
            $lockStream = [IO.File]::Open(
                $lockFile,
                [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite,
                [IO.FileShare]::None
            )
        } catch [IO.IOException] {
            if ((Get-Date) -ge $lockDeadline) {
                throw "Timed out waiting for the shared qualification environment cache lock: $lockFile"
            }
            Start-Sleep -Milliseconds 250
        }
    }

    try {
        $cacheHit = $false
        if ((Test-Path -LiteralPath $cacheMarker -PathType Leaf) -and (Test-Path -LiteralPath $python -PathType Leaf)) {
            try {
                $marker = Get-Content -Raw -LiteralPath $cacheMarker | ConvertFrom-Json
                if (
                    $marker.fingerprint -eq $fingerprint -and
                    $marker.lockSha256 -eq $lockHash -and
                    $marker.projectSha256 -eq $projectHash
                ) {
                    & $python -m pip check *> $null
                    $cacheHit = $LASTEXITCODE -eq 0
                }
            } catch {
                $cacheHit = $false
            }
        }

        if (-not $cacheHit) {
            if (Test-Path -LiteralPath $environmentPath) {
                $cachePrefix = [IO.Path]::GetFullPath($cacheRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
                $resolvedEnvironment = [IO.Path]::GetFullPath($environmentPath)
                if (-not $resolvedEnvironment.StartsWith($cachePrefix, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Refusing to replace an environment outside the qualification cache: $resolvedEnvironment"
                }
                Remove-Item -LiteralPath $resolvedEnvironment -Recurse -Force
            }

            Write-Host "Creating hash-locked Python test environment from $RequirementsLock."
            & $hostPython -m venv $environmentPath | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "Could not create the cached locked Python test environment." }
            & $python -m pip install --disable-pip-version-check --no-compile --require-hashes -r $lockPath | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "Could not install hash-locked test dependencies from $RequirementsLock." }
            & $python -m pip install --disable-pip-version-check --no-build-isolation --no-deps --editable $checkout | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "Could not install Ronin into the cached locked test environment." }
            & $python -m pip check | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "The cached locked Python test environment is inconsistent." }
            [ordered]@{
                fingerprint = $fingerprint
                python = $pythonVersion
                lockSha256 = $lockHash
                projectSha256 = $projectHash
            } | ConvertTo-Json | Set-Content -LiteralPath $cacheMarker -Encoding utf8
        }

        $cacheStatus = if ($cacheHit) { "HIT" } else { "MISS" }
        Write-Host "Python test environment: $cacheStatus [$($fingerprint.Substring(0, 12))] from $RequirementsLock."
        return $python
    } finally {
        $lockStream.Dispose()
    }
}

Export-ModuleMember -Function Get-RoninTestPythonEnvironment
