# Phase receipt — RPV1-804 anomaly numeric safety

## Status

**PASS** for the implemented anomaly numeric-safety slice on candidate
`d0e36cb42db5a5838768a4d9419ddfd07e7a17a8`.

## Change

- `detect_anomaly` now computes medians with an overflow-resistant midpoint
  for even-sized samples.
- Non-finite or numerically unstable intermediate values are rejected rather
  than converted into a false `within threshold` result.
- Boolean thresholds and boolean history values are rejected explicitly.
- Added coverage for extreme finite values and invalid boolean inputs.

## Evidence

- Anomaly/FinOps/observability focused suite: **26 passed, 0 failed**.
- Full Python regression (`python -m pytest --ignore=tests/perf -q`):
  **4588 passed, 80 skipped, 0 failed** in 385.65 s.
- Ruff check, Ruff format check and `git diff --check`: **passed**.

## Boundaries

This closes only the implemented RPV1-804 numeric-safety slice. It does not
claim complete Cost Control UI qualification, provider forecasts, or release
qualification. Public v1 remains **0/13 active families, 0%, NO-GO**, with
`release_status=incomplete` and `qualification_status=qualification_pending`.

Policy: qualification was manual and local; no GitHub Actions, branch or
worktree was used.
