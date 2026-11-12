# Phase 2026-11-12 — Trivy diagnostic (open)

## Scope

Run a pinned Trivy vulnerability scan against a freshly rebuilt Ronin image to complement the Docker Scout receipt.

## Execution

```text
docker build --file docker/Dockerfile --tag ronin:qualification-trivy-refresh .
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v "${TEMP}:/output" aquasec/trivy:0.76.1 image --scanners vuln \
  --format json --output /output/ronin-trivy-scan-refresh.json \
  ronin:qualification-trivy-refresh
```

- Trivy image: `aquasec/trivy:0.76.1`
- Candidate image: `ronin:qualification-trivy-refresh`
- Immutable image ID: `sha256:d9f436262a43c1c9934def9c3debf593e63350cf4056e2eb859968a66d1c75a5`
- Detected OS: Debian 12.15
- Packages detected: 123

## Result

**FAIL / OPEN — not a release gate pass.** Trivy reported 553 findings:

- 3 critical
- 150 high
- 214 medium
- 165 low
- 21 unknown

The earlier Scout PASS remains valid for Scout only and is not superseded by this diagnostic. Trivy findings must not be suppressed globally. The image uses pinned base digests and its current package set is not sufficiently current for a clean Trivy release gate; the next remediation cycle must update the Debian and Docker CLI bases (or replace the image composition), then rerun the full Docker/Helm/live qualification lanes.

## Decision

This receipt records an open security finding and does **not** close a satisfactory phase. Public v1 remains **0/13 (0%) — NO-GO**.
