# Helm/kind qualification — current candidate

**Date:** 2026-11-12  
**Candidate SHA:** `0f985c3bb5c0d2e98eea7ba2e122f8fc72b66c0e`  
**Image:** `ronin:qualification-0f985c3`  
**Image ID:** `sha256:181015ee20d25bacd02c99902b6ff357364bf0ccd0e0722be4c8d806a89c34af`

## Gates

Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-qualification-0f985c3-20261112222802`  
Docker evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-0f985c3-20261112222448`

- Helm lint: **passed**.
- Secret rendering boundary: **passed**; token confined to a Kubernetes Secret.
- kind cluster creation and immutable image load: **passed**.
- Helm install/readiness: **passed**.
- Upgrade to revision 2: **passed**.
- Rollback to revision 1: **passed**.
- Health endpoint and authorized Studio/jobs API: **passed**.
- Queued job persisted across pod restart with the same job ID: **passed**.
- Cleanup: **passed**; isolated kind cluster removed.

## Decision

Helm/kind deployment and rollback phase: **PASS** for this candidate.

This is local deployment evidence, not production Kubernetes or multi-user
qualification. Public v1 remains **0/13 (0%) — NO-GO** pending complete
families and the remaining release/provider/human gates.
