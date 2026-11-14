# Helm/kind manual real qualification diagnostic

Date: 2026-11-14  
Source baseline: `30bd79d6300bb307e87e9d9121946129b1d42a05`  
Mode: **DIRTY-WORKTREE DIAGNOSTIC**  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

The official `tools/run_helm_qualification.ps1` was run against the exact
Docker evidence for the same source SHA and image digest.

Result: **all phases passed**, including:

- Helm lint and rendered Secret boundary (4 resources; token confined to Secret).
- kind cluster creation, image load and Helm install.
- Deployment readiness, upgrade to revision 2 and rollback to revision 1.
- Health endpoint, Studio and authorized jobs API.
- Persistent queued job creation, deployment restart and same-job persistence.
- Isolated cluster cleanup.

Evidence JSON records `result=passed`, Helm `v4.3.1`, Docker strict acceptance
`15/15`, and image `sha256:d17e79237c3c4f909f2293a5a199f166b50cf2405389b8cd5b340b4c05a0c388`.
Evidence is outside the checkout at:
`%TEMP%\ronin-helm-manual-20261114-30bd79d-r2`.

Because user-owned untracked artifacts remain in the worktree, this is not
clean-candidate release evidence. The official ledger remains **0/13 (0%),
NO-GO**.
