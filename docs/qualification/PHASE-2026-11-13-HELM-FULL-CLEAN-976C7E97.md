# Qualification receipt — full Helm qualification (clean candidate)

- Date: 2026-11-13
- Source checkout: `976c7e9704fc1df814dd2e082d26adb706c91d41`
- Qualification mode: **CLEAN-CANDIDATE QUALIFICATION**; temporary clean clone.
- Image: `ronin:qualification`, digest `sha256:701ef0c5891efe1fa24cfce28e143d67cb281827e9b5c96eccf63fa43a444134`.
- Result: **PASS** — Helm lint/render boundaries, kind v1.37.0, install/readiness, upgrade, rollback, health/API, queued-job persistence across restart, and cleanup.
- Helm: `v4.3.1+gc0d08d0`; evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-clean-helm-20261113090424`.
- Docker dependency: exact clean evidence, strict v0.1 acceptance 15/15.
- Boundary: this does not by itself qualify all 13 Public v1 families or alter the official 0/13 ledger.
