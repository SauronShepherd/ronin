param(
    [string]$ImageTag = "ronin:qualification"
)

$ErrorActionPreference = "Stop"

docker build --file docker/Dockerfile --tag $ImageTag .
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
$imageId = docker image inspect $ImageTag --format '{{.Id}}'
if ($LASTEXITCODE -ne 0 -or -not $imageId -or $imageId -notmatch '^sha256:[0-9a-f]{64}$') {
    throw "Docker qualification image did not resolve to an immutable image id"
}

$env:RONIN_REAL_DOCKER_QUALIFICATION = "1"
$env:RONIN_DOCKER_QUALIFICATION_IMAGE = $imageId
$evidenceRoot = Join-Path (Get-Location) "qualification-evidence"
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$env:RONIN_DOCKER_QUALIFICATION_EVIDENCE = $evidenceRoot
$env:RONIN_HOST_WORKSPACE = (Get-Location).Path
$junitReport = Join-Path $evidenceRoot "v01-acceptance.xml"
$acceptanceEvidence = Join-Path $evidenceRoot "v01-acceptance-strict.json"
python -m pytest -q `
    tests/integration/test_docker_container_executor_real.py `
    tests/integration/test_worker_runtime_real.py `
    tests/e2e/test_v01_journey.py `
    "--junitxml=$junitReport"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

python -m tools.v01_acceptance_gate `
    $junitReport `
    "--evidence-json=$acceptanceEvidence"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
