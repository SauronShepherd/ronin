# RTEST-BLK-090 — Compilation report/outbox atomicity

Date: 2026-11-14  
Status: **PASS for the SQLite compilation transaction slice; installed/external qualification remains open.**

## Finding

Data Engineering validation persisted the compilation report and its completion event through two independent SQLite connections. A failure between those writes could leave durable report state without the corresponding outbox event.

## Change

Added `SqliteCompilationStore.save_report_and_enqueue()` with explicit `BEGIN`, `COMMIT` and rollback handling, and changed `validate_pipeline()` to use it. The existing independent report and outbox APIs remain available for their separate use cases.

## Evidence

- Compilation/plugin focused suite: **31 passed**.
- Data Engineering HTTP integration: **4 passed**.
- Ruff check/format for changed files: passed.
- CI exact candidate `43568328524`: Python 3.11 success, Python 3.12 success, Chromium non-live success, Cloud Studio Terraform/Floci success.
- Published source SHA: `cebaf9aed52390bf85bb8b8ab3d8051bf3f03742`.

## Boundary

This closes only the local SQLite report/outbox atomicity slice. It does not qualify PostgreSQL, installed wheels, external providers, human review or any Public v1 family. Public v1 remains **0/13 families, 0%, NO-GO**.
