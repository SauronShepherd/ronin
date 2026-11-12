# Phase receipt — Helm/kind exact candidate refresh — 2026-11-12

## Candidate and service

- Source: `52e70dbab3550db4d762d9897d30a17082198abd`
- Image: `sha256:7f5d5f4717cb24f43e58eee2fedd1eb8d49c85524f13edb037ae1a3dc5805951`
- Helm: `4.3.1`
- kind node: `v1.37.0`
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-current-evidence-20261112190009`

## Gate result

```text
helm_lint: passed
helm_render_secret_boundary: passed
kind_cluster: passed
load_ronin_image: passed
helm_install: passed
deployment_readiness: passed
helm_upgrade: passed (revision 2)
helm_rollback: passed (restored revision 1)
health_endpoint: passed
studio_and_authorized_api: passed
persistent_job_create: passed
deployment_restart: passed
persistent_job_after_restart: passed
cleanup: passed; isolated cluster removed
HELM_EXIT=0
```

## Decision

PASS for the exact candidate Helm/kind install-upgrade-rollback and restart
persistence lane. This remains a single-operator local deployment contract;
it does not claim production Kubernetes, OIDC/RBAC multi-user support or full
Public v1 completion. Public v1 remains **0/13 (0%) — NO-GO**.
