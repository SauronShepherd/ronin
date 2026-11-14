# Live API/browser clean-candidate qualification

Date: 2026-11-14  
Candidate: `30cad9f0b1ad9decc5efadfb8d56fa80abc26234`  
Mode: **CLEAN-CANDIDATE QUALIFICATION**  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

The official `tools/run_live_product_qualification.ps1` ran from a clean
detached worktree with isolated PostgreSQL, Redpanda, Chromium and the real
Docker worker image.

Result: **33 passed, 0 skipped, 0 failed** in 125.59s.

- 25 active routes audited; 24 API-backed and 1 explicitly UI-only.
- **280 real API events**, all correlated with structured HTTP logs.
- 263 OK and 17 expected WARN responses.
- 0 server/network errors and `real API ready=True`.
- Ingestion discovery, authorization, watermark progression, bundle round-trip,
  single-operator scope, notebook worker execution and route coverage passed.

Evidence: `%TEMP%\ronin-live-clean-evidence-30cad9f-r2`.

The earlier same-SHA attempt had one browser startup timeout on `projects`; the
fresh isolated rerun passed all 33 cases and is the authoritative receipt.
This gate does not close all 13 Public v1 families or human release decisions.
