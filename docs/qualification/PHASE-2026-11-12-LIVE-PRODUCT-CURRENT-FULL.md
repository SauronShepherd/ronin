# Qualification receipt — full live product current candidate

- Date: 2026-11-12
- Source checkout: `20d3d9a6b63e4f0756ed5d4d5b2260ebdaa682ae`
- Runner: `tools/run_live_product_qualification.ps1` with worker image `ronin:qualification`, immutable ID `sha256:8c7ae4e685aa5c4fb58085a62442dc18a7cbee34814c93d8b639b230cd7e4f52`.
- Result: **33/33 Playwright passed, 0 skipped, 0 failed**; 25 active routes audited (24 API-backed and 1 UI-only); 278 real API events fully correlated with structured HTTP logs; 0 unexpected authorization gaps and 0 server/network errors.
- Scope: live Runs, ingestion, Projects Bundle round-trip, authorization warning paths, Notebook Docker-worker execution, and all active Studio routes.
- Runtime: isolated PostgreSQL 16.4 and streaming broker services; cleanup completed successfully.
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-live-evidence-20d3d9a-rerun`.
- Boundary: this closes the current full live-product diagnostic on this candidate, but does not by itself close all 13 Public v1 capability families or human release approvals.
