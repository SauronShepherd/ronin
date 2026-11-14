# Live API/browser qualification after scope fix

Date: 2026-11-14  
Pre-fix baseline: `9bfe83a1eb655606e22af22a7c70ee06be4751f2`  
Mode: **DIRTY-WORKTREE DIAGNOSTIC before commit**  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Findings and fix

The first clean-candidate live run exposed two real scope defects:

1. ML Studio fetched `/v1/ml-studio/backends` without `workspace_id`, causing
   a 403 and disabling the Run sample control.
2. Data Engineering fetched `/v1/data-engineering/health` without
   `workspace_id`, causing an unexpected `plugin_workspace_scope_required` 403.

The Studio calls now carry the active workspace explicitly. The affected static
ML mock route was widened to match the query-bearing URL.

## Gate executed

The official `tools/run_live_product_qualification.ps1` ran with PostgreSQL,
Redpanda, Chromium and the real Docker worker image.

Result: **33 passed, 0 skipped, 0 failed**; 25 active routes audited, 24
API-backed; **278 real API events**, all correlated with structured HTTP logs;
0 server/network errors; 261 OK and 17 expected WARN events.

Evidence: `%TEMP%\ronin-live-diagnostic-fixed-20261114`.

This closes the live API/browser diagnostic gate for the fixed code, but does
not by itself close all 13 Public v1 families, provider certification, human
visual review or release governance.
