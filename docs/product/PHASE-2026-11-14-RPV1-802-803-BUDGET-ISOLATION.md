# Phase receipt — RPV1-802/803 budget and notification isolation

## Status

**PASS** for the implemented FinOps isolation slice on candidate
`a48520ff49385027631285f2e8657fc204613cc5`.

## Change

- Migrated `finops_budgets` from a global `budget_id` primary key to the
  composite key `(workspace_id, budget_id)`.
- Added a non-destructive startup migration for existing SQLite stores.
- Budget upserts now scope conflicts to the owning workspace, preventing one
  workspace from overwriting another workspace's budget with the same ID.
- `BudgetEvaluation` carries workspace identity and budget notification IDs and
  attributes now include it, preventing cross-workspace notification
  suppression.
- Added isolation coverage for identical budget IDs in two workspaces.

## Evidence

- FinOps/observability focused suite: **22 passed, 0 failed**.
- Full Python regression (`python -m pytest --ignore=tests/perf -q`):
  **4583 passed, 80 skipped, 0 failed** in 331.17 s.
- Ruff check, Ruff format check and `git diff --check`: **passed**.

## Boundaries

This closes only the implemented RPV1-802/803 identity-isolation slice. It
does not claim concurrent alert CAS, complete pricing/reconciliation,
PostgreSQL parity, or release qualification. Public v1 remains **0/13 active
families, 0%, NO-GO**, with `release_status=incomplete` and
`qualification_status=qualification_pending`.

Policy: qualification was manual and local; no GitHub Actions, branch or
worktree was used.
