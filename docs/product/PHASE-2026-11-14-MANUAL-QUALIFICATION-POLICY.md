# Phase receipt — manual qualification policy

## Status

**PASS** for the repository automation-policy and local regression slice.

## Change

- Removed every active GitHub Actions workflow from `.github/workflows/`.
- Added `docs/operations/MANUAL_RELEASE_AND_UPLOAD_RUNBOOK.md` with the
  approved local validation, commit, push, image-build and upload procedure.
- Updated publication and workflow-contract tests to assert the manual-only
  policy instead of requiring automation files.
- Added explicit job-timeout configuration immediately before removing the
  workflows; it is historical in Git and has no active effect now.

## Evidence

- Full local Python suite: **4574 passed, 80 skipped, 0 failed** in 496.94 s.
- Focused publication-policy suite: **6 passed**.
- Ruff and format checks for changed tests and scheduler code: **passed**.
- `git diff --check`: **passed**.
- Published commits: `daa94efd` (workflow removal), `8b4825f3` (manual runbook),
  `dba1a119` (manual-policy tests).

## Boundaries

No GitHub Actions or remote automation is used as qualification evidence. The
skips require explicitly configured local services or POSIX capabilities and
remain open until run manually. Public v1 remains **0/13 active families, 0%,
NO-GO**, with `release_status=incomplete` and
`qualification_status=qualification_pending`.
