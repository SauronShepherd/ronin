# Qualification receipt — full Helm/kind current diagnostic

- Date: 2026-11-13
- Source checkout: `21ef64b8228dbc900d96a7320291c6c00f3f56a3`
- Qualification mode: **DIRTY-WORKTREE DIAGNOSTIC**; preserved user artifacts and the user-owned public status edit were present.
- Helm: `v4.3.1`; isolated kind cluster on `kindest/node:v1.37.0`.
- Image: `ronin:qualification`, digest `sha256:6338f0c994c3ea954edd391bdd33cb9ab5ca640e43db4f739d510b8424c88e9d`.
- Docker dependency: matching full current evidence at `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-full-current-20261113082906`, strict v0.1 `15/15`.
- Result: **all Helm phases passed**: lint, Secret boundary, isolated kind cluster, image load, install/readiness, upgrade revision 2, rollback revision 1, health, Studio/authorized API, queued job persistence after pod restart, and cleanup.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-full-current-20261113083304`.
- Boundary: current exact-HEAD diagnostic evidence, not clean-candidate release evidence; multi-replica/multi-node HA and the complete Public v1 family journeys remain open.
