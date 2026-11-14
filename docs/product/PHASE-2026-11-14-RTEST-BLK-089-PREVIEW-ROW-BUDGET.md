# RTEST-BLK-089 — Data Engineering preview row budget

Date: 2026-11-14  
Status: **PASS for the bounded local-preview row-budget slice; installed/external Data Engineering qualification remains open.**

## Finding

The preview engine applied `row_limit` independently to every node and retained every node's output. A graph with many nodes could therefore materialize approximately `nodes × row_limit` rows without a global bound.

## Change

`preview_pipeline()` now accepts a validated `max_total_rows` budget (default `10000`) and limits cumulative materialized output across the graph. When the budget truncates a result, the response exposes diagnostic `RONIN-DE-PREVIEW-ROW-BUDGET`. The plugin endpoint validates and forwards the new field.

## Evidence

- `test_preview_engine_applies_global_row_budget_with_visible_diagnostic`: passed.
- Data Engineering plugin and HTTP integration selection: **22 passed in 10.39s**.
- Ruff check/format for changed files: passed.
- Data Engineering Chromium journeys: **11 passed in 40.9s**.
- CI exact candidate `43567180115`: Python 3.11 success, Python 3.12 success, Chromium non-live success, Cloud Studio Terraform/Floci success.
- Published source SHA: `8bc138a1536ecba0bb2b9a29c4b1636dce58b64d`.

## Boundary

This closes only the local-preview row-budget contract. It does not qualify installed wheels, external providers, PostgreSQL/streaming lanes, human review or any Public v1 family. Public v1 remains **0/13 families, 0%, NO-GO**.
