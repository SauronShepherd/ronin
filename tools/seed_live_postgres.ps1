param(
    [Parameter(Mandatory = $true)]
    [string]$ComposeProject,
    [string]$Database = "ronin_test",
    [string]$User = "ronin"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$fixture = Join-Path $repoRoot "web-tests\fixtures\live-postgres.sql"
if (-not (Test-Path -LiteralPath $fixture -PathType Leaf)) {
    throw "Live PostgreSQL fixture was not found: $fixture"
}

Push-Location $repoRoot
try {
    Get-Content -Raw -LiteralPath $fixture |
        docker compose -p $ComposeProject exec -T postgres psql `
            -v ON_ERROR_STOP=1 -U $User -d $Database
    if ($LASTEXITCODE -ne 0) {
        throw "Could not seed the isolated PostgreSQL database '$Database'."
    }
    $verification = docker compose -p $ComposeProject exec -T postgres psql `
        -v ON_ERROR_STOP=1 -U $User -d $Database -tAc `
        "SELECT count(*) FROM public.ui_page_accounts WHERE id = 1 AND email = 'a@example.test';"
    if ($LASTEXITCODE -ne 0 -or $verification.Trim() -ne "1") {
        throw "The PostgreSQL fixture verification failed for '$Database'."
    }
    Write-Output "Seeded PostgreSQL live-browser fixture in '$Database'."
} finally {
    Pop-Location
}
