# Phase 2026-11-12 — Helm/kind security-refresh candidate

## Candidate

- Source commit: `7b1bb1665f1fa0260e5bd0dc51f1df3c7d6fd536`
- Image: `ronin:qualification-7b1bb16`
- Image ID: `sha256:3ddae68e6a0c6f687f07326fae7c12cec1f623907cae8ba571f1865cb2a3dd26`
- Helm: `v4.3.1+gc0d08d0`
- kind node: `v1.37.0`

## Gates

- Docker evidence for the same source SHA: **27/27 passed; strict 15/15 passed**.
- Helm lint: passed.
- Secret boundary/render: passed; 4 resources, token confined to Secret.
- kind cluster creation and immutable image load: passed.
- Helm install and deployment readiness: passed.
- Helm upgrade: passed, revision 2 observed.
- Helm rollback: passed, revision 1 restored.
- `/healthz`: HTTP 200.
- Studio/API smoke: HTTP 200 / authorized jobs API HTTP 200.
- Queued job creation: HTTP 201.
- Deployment restart and durable queued job: passed; same job ID survived restart.
- Cleanup: passed; isolated kind cluster removed.

## Runner fixes exercised

- Helm 4 JSON history is normalized and revision 2 is asserted.
- Windows PowerShell `Invoke-WebRequest` uses `-UseBasicParsing` for noninteractive health/API checks.
- Expected `No kind clusters found` after cleanup is treated as an empty cluster set, while unrelated cleanup errors remain fatal.

## Decision

Helm/kind phase: **PASS**. The separate Trivy residual remains explicit: 0 critical/high/medium/low findings and one `UNKNOWN` Go stdlib finding awaiting upstream fixed version `1.27.4`; it is not suppressed.

Public v1 remains **0/13 (0%) — NO-GO** because the complete Public v1 evidence family is not yet closed.
