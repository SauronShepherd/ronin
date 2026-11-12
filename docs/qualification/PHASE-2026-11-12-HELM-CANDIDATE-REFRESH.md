# Phase 2026-11-12 — Helm/kind candidate refresh

## Scope

Qualify the Helm deployment path on an isolated kind cluster using the exact Docker candidate already qualified by the Docker gate.

## Candidate binding

- Clean checkout: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-clean-5e8a57e`
- Source HEAD: `5e8a57e11db5360ddd10b642845da49c7290f6c8`
- Docker evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-5e8a57e`
- Docker image ID: `sha256:46f6b99641ca7497ab15a4c6f4c987ce9aaa296441a718afe672bdc691f4c920`
- Helm image reference: `ronin:qualification-5e8a57e` (explicit local tag resolving to the immutable ID above)
- Helm: `v4.3.1+gc0d08d0`
- Kind node: `kindest/node:v1.37.0`
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-qualification-5e8a57e`

## Execution

```text
pwsh -NoProfile -File tools/run_helm_qualification.ps1 \
  -EvidenceDirectory C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-qualification-5e8a57e \
  -ImageRef ronin:qualification-5e8a57e \
  -DockerEvidenceDirectory C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-5e8a57e
```

Result: **PASS, exit code 0**.

Passed phases: Helm lint, rendered Secret boundary, isolated kind cluster, image load and digest verification, install, readiness, upgrade, rollback, health endpoint, Studio/authorized API, persistent job creation, deployment restart, persistence of the same queued job after restart, and isolated-cluster cleanup.

## Qualification boundary

This closes the Helm/kind candidate-refresh phase. It does not claim production Kubernetes or multi-user Public v1 support; those remain outside the approved Public v1 scope. Public v1 remains **0/13 (0%) — NO-GO** pending complete capability families and independent release gates.

