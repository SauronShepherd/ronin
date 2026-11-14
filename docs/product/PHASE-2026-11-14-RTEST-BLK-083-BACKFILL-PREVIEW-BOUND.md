# RTEST-BLK-083 — Scheduler backfill preview bound

Date: 2026-11-14  
Status: **PASS for the incremental backfill-preview generation slice; installed/external Scheduler qualification remains open.**

## Finding

`preview_backfill()` materialized the complete minute window, up to one million instants, before checking whether the number of matching fires exceeded `max_runs`.

## Change

The preview now walks the bounded minute window incrementally and raises as soon as `max_runs + 1` matches are observed. It retains the one-million-minute scan ceiling and fails explicitly when that ceiling is exceeded, without allocating the full window.

## Evidence

- Scheduler backfill runtime tests: **8 passed**.
- Related HTTP/UI/store tests: **6 passed**.
- Ruff check/format for changed files: passed.
- CI exact candidate `43569332067`: Python 3.11 success, Python 3.12 success, Chromium non-live success, Cloud Studio Terraform/Floci success.
- Published source SHA: `3e7f8d34bc10fb21e47c29214a5b381a5e443872`.

## Boundary

This closes only the preview-generation memory bound. It does not qualify daemon recovery, multi-workspace scheduling, PostgreSQL, installed wheels, providers or any Public v1 family. Public v1 remains **0/13 families, 0%, NO-GO**.
