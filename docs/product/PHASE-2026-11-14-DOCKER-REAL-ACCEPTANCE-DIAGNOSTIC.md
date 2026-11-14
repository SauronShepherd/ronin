# Docker real acceptance — current candidate

Date: 2026-11-14  
Candidate: `12ed79a06bf0af7598c9034a073120ea2985df99`  
Policy: local/manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

Command:

```powershell
.\tools\run_docker_qualification.ps1 `
  -EvidenceDirectory C:\Users\angel.alvarez\Downloads\ronin-docker-qualification-12ed79a `
  -AllowDirtyWorktree
```

The real Docker qualification completed with:

- Docker integration scope: **27 passed, 0 skipped, 0 failed** in 167.38s.
- Strict v0.1 acceptance: **15/15 passed**, 0 skipped, 0 xfailed, 0 failed,
  0 errors, 0 missing, `strict_success=true`.
- Real services: PostgreSQL, Docker worker/runtime, Floci/S3, Azurite/Azure
  Blob, and PostgreSQL appliance backup/restore.
- Image digest: `sha256:955cf098ce7a6fccec0895d967847330a825629a6d31f69c2fa4f98d9520f033`.
- Evidence directory:
  `C:\Users\angel.alvarez\Downloads\ronin-docker-qualification-12ed79a`.

## Qualification boundary

The command required `-AllowDirtyWorktree` because the checkout contains
pre-existing untracked user artifacts that were intentionally preserved. This
therefore is a **real diagnostic PASS**, not clean-candidate release evidence.
No user artifacts were staged, moved, or deleted. A clean-candidate release
qualification must be repeated after the owner decides how those artifacts are
to be handled.

This receipt closes the local Docker acceptance implementation/test slice only.
It does not qualify all 13 Public v1 capability families or change the official
ledger: **0/13 (0%), NO-GO**.
