# Phase receipt — RPV1-800 telemetry filter boundary

## Status

**PASS** for the implemented RPV1-800 query-boundary slice on candidate
`5eafddf1d37619521b20cf28dc42a74c4e88ef3e`.

## Change

- `SqliteTelemetryStore.latest_metric` now applies attribute filters in the
  bounded SQL candidate query before `LIMIT 10000`.
- JSON-path filter keys are validated before query construction; values remain
  bound parameters.
- Added a regression with 10,001 newer metrics from another workspace proving
  that a target workspace metric is not hidden by the global candidate limit.

## Evidence

- Observability/FinOps suite: **17 passed, 0 failed**.
- Full Python regression (`python -m pytest --ignore=tests/perf -q`):
  **4581 passed, 80 skipped, 0 failed** in 404.48 s.
- Ruff check, Ruff format check and `git diff --check`: **passed**.

## Boundaries

This closes only the implemented RPV1-800 query-boundary slice. It does not
claim full telemetry adoption across every service, OTLP collector
certification, or release qualification. Public v1 remains **0/13 active
families, 0%, NO-GO**, with `release_status=incomplete` and
`qualification_status=qualification_pending`.

Policy: qualification was manual and local; no GitHub Actions, branch or
worktree was used.
