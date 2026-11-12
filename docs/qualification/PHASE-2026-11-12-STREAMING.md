# Phase receipt — streaming contracts and real broker journey — 2026-11-12

## Candidate

- Source candidate used by the live run: `52a378db46bc07951d8050ebf620481723586ba6`.
- The run was explicitly classified by the runner as `DIRTY-WORKTREE DIAGNOSTIC`; it is not a clean release-candidate claim.

## Evidence

- Local streaming contracts:
  `tests/test_stream_scheduler_bridge.py`, `test_stream_table.py`, `test_streaming_bundle.py`, `test_streaming_health.py`, `test_streaming_kafka.py`, `test_streaming_runtime.py`, and `test_streaming_windows.py` — **32 passed**.
- Real filtered live journey:
  `tools/run_live_product_qualification.ps1 -TestGrep streaming -AllowDirtyWorktree`
  — status `passed`, Playwright **1/1**, duration 64.62s.
- Real services: `kafka=true` (Redpanda), `roninApi=true`, PostgreSQL intentionally false for the streaming-only profile.
- API traffic: **38 events**, all **38 correlated** to structured HTTP logs; outcomes 34 OK and 4 expected WARN; 0 uncorrelated events.
- Application logs: 92 INFO, 4 expected WARNING, 0 ERROR, 0 CRITICAL.
- Cleanup completed successfully.

## Scope boundary

This qualifies the local streaming contract and a real Redpanda/API journey. It does not close all P11 operational evidence, PostgreSQL-backed streaming persistence, multi-provider certification, or clean candidate aggregation.

## Result

PASS for the selected streaming contract and real-broker diagnostic. P11 and Public V1 remain incomplete; official release-qualified progress remains `0/13 (0%)`.
