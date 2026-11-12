# Phase receipt — QueryFlux worker runner on real Trino — 2026-11-12

## Candidate and service

- Source: `cca3973a0c4b35e9168e1d58359157efb0bf1abb`
- Trino image: `trinodb/trino@sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f`
- Trino version: `484`
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-trino-qf-evidence-20261112193106`

## Gate result

```text
test_trino_real_prepared_scalar_bindings: passed
test_trino_real_result_byte_budget_accepts_exact_limit_and_rejects_one_byte_less: passed
test_queryflux_worker_runner_real_trino_persists_terminal_evidence: passed
Tests: 3/3 passed, 0 skipped, 0 failed
Cleanup: succeeded; Trino container removed
TRINO_QF_EXIT=0
```

## Decision

PASS for the real Trino/QueryFlux transport, worker runner, lifecycle terminal
state and durable evidence reference on one clean candidate SHA. Process
restart/recovery and the public asynchronous create route remain outstanding.
Public v1 remains **0/13 (0%) — NO-GO**.
