# Helm single-node qualification — current candidate

Date: 2026-11-14  
Candidate: `ae3052f3f42402ddde0a4d3633eb32e0dc540a04`  
Policy: local/manual qualification only; GitHub Actions is intentionally absent.

## Gates executed

The Docker acceptance was rerun for the exact candidate before Helm:

- Docker integration: **27 passed, 0 skipped, 0 failed**.
- Strict v0.1 acceptance: **15/15 passed**.
- Image digest: `sha256:d051b3ff4ab1965f4b87c0b6cfbe7b95597e02165c533dcdb66ca57185f052e3`.
- Docker evidence: `C:\Users\angel.alvarez\Downloads\ronin-docker-qualification-ae3052f3`.

Helm/kind qualification:

- `helm lint`: passed.
- Rendered secret boundary: passed; token confined to Secret.
- kind cluster creation/readiness: passed.
- Image load by exact image ID: passed.
- Helm install: passed.
- Deployment readiness: passed.
- Helm upgrade to revision 2: passed.
- Helm rollback to revision 1: passed.
- Health endpoint and authorized Studio/jobs API: passed.
- Persistent queued job survived pod restart: passed.
- Isolated kind cluster cleanup: passed.
- Helm evidence: `C:\Users\angel.alvarez\Downloads\ronin-helm-qualification-ae3052f3-run2`.

## Qualification boundary

The run used `-AllowDirtyWorktree` because pre-existing untracked user
artifacts were intentionally preserved in the checkout. It is therefore a
**real diagnostic PASS**, not clean-candidate release evidence. No user
artifacts were staged, moved, or deleted. This qualifies the single-node local
Helm/deployment slice only; it does not qualify Ronin Pro multi-user or all 13
Public v1 capability families. The official ledger remains **0/13 (0%),
NO-GO**.
