# Phase receipt — RTEST-BLK-084

## Status

**PASS** for the scheduler backfill preview/create contract-alignment slice.

## Finding

Backfill preview accepted timestamps containing seconds or microseconds and rounded them to minute boundaries, while `BackfillRequest` creation correctly rejected non-minute-aligned UTC ranges. This allowed preview and creation to disagree about the same request.

## Change

`preview_backfill` now rejects seconds or microseconds with the same minute-alignment contract used by backfill creation, while retaining the incremental bounded scan introduced for the preview memory guard.

## Evidence

- Scheduler runtime and HTTP tests: **10 passed**.
- Ruff and formatting checks: **passed**.
- Canonical CI run `43569806763`: **success**, all four jobs green (Python 3.11, Python 3.12, Chromium non-live regression, Cloud Studio Terraform / Floci).
- Published implementation SHA: `c96cddc28527062b5b4bf2acfee0261492bf2b4c`.

## Boundary

This receipt does not claim daemon recovery, PostgreSQL/provider qualification, or public-v1 family qualification. Official public-v1 status remains **0/13 active families, 0%, NO-GO**, with `release_status=incomplete` and `qualification_status=qualification_pending`.
