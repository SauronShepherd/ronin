# Qualification receipt — Helm/kind deployment current

- Date: 2026-11-13
- Source checkout: `3199c34bc770ac04354d4ba4d3733d1806c5f55e`
- Image: `ronin:qualification-docker-3199c34` (`sha256:8acd6943f82969f357458185d3eb9f6c17d1c4e1c40f0f8b213e03862ab275b2`).
- Runner: `tools/run_helm_qualification.ps1 -ImageRef ronin:qualification-docker-3199c34 -AllowDirtyWorktree`.
- Result: **PASS** — Helm lint, secret boundary, kind cluster, image load, install/readiness, upgrade revision 2, rollback revision 1, health/API, queued job persistence and pod-restart persistence all passed; cleanup passed.
- Docker dependency evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-current-3199c34-20261113062646`.
- Helm evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-current-3199c34-tag-20261113063605`.
- Qualification boundary: dirty-worktree diagnostic; supported-platform breadth, clean-candidate release aggregation, external provider claims and legal gates remain open.
