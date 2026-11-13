# Qualification receipt — Docker integration and strict v0.1 current

- Date: 2026-11-13
- Source checkout: `3199c34bc770ac04354d4ba4d3733d1806c5f55e`
- Runner: `tools/run_docker_qualification.ps1 -ImageTag ronin:qualification-docker-3199c34 -EvidenceDirectory <evidence> -AllowDirtyWorktree`.
- Runtime image: `sha256:8acd6943f82969f357458185d3eb9f6c17d1c4e1c40f0f8b213e03862ab275b2`.
- Result: **27/27 Docker integration tests passed, 0 skipped, 0 failed**; **strict v0.1 acceptance 15/15 passed, 0 skipped, 0 failed**.
- Fixtures: isolated PostgreSQL, Docker worker, Floci/S3, Azurite/Azure Blob, worker crash/reclaim, appliance backup/restore, and frozen v0.1 journey.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-current-3199c34-20261113062646`.
- Qualification boundary: dirty-worktree diagnostic due preserved user artifacts; not clean release-candidate evidence.
