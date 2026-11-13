# Qualification receipt — Docker integration and strict v0.1 current

- Date: 2026-11-13
- Source checkout: `597eb581b60ffda7615fdda5ab4292b24865227f`
- Runner: `tools/run_docker_qualification.ps1 -ImageTag ronin:qualification-docker-597eb58 -EvidenceDirectory <evidence> -AllowDirtyWorktree`.
- Runtime image: `sha256:96eacacc698efc6420e60b054fe23f2a86c65c766cb89db13f0e4b1df296f5de`.
- Result: **27/27 Docker integration tests passed, 0 skipped, 0 failed**; **strict v0.1 acceptance 15/15 passed, 0 skipped, 0 failed**.
- Fixtures: isolated PostgreSQL, Docker worker, Floci/S3, Azurite/Azure Blob, worker crash/reclaim, appliance backup/restore, and frozen v0.1 journey.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-current-597eb58-20261113062026`.
- Qualification boundary: this is a dirty-worktree diagnostic because preserved user artifacts remain in the checkout; it is not clean release-candidate evidence. Full-family release decisions, external provider breadth, supported-platform coverage and legal gates remain open.
