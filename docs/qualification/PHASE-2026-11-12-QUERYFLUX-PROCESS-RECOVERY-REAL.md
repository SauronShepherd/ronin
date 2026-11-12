# Phase receipt — QueryFlux real worker process recovery — 2026-11-12

## Candidate and service

- Source: `cd2a345de24b4f9ef82027b5eebf8edf305cc383`
- Trino image: `trinodb/trino@sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f`
- Trino version: `484`
- Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-trino-recovery-evidence-20261112195612`

## Gate result

```text
test_trino_real_prepared_scalar_bindings: passed
test_trino_real_result_byte_budget_accepts_exact_limit_and_rejects_one_byte_less: passed
test_queryflux_worker_runner_real_trino_persists_terminal_evidence: passed
test_queryflux_real_worker_process_sigkill_reclaims_without_duplicate: passed
Tests: 4/4 passed, 0 skipped, 0 failed
Process recovery: SIGKILL -> lease expiry -> replacement reclaim -> succeeded
Lifecycle: terminal succeeded and durable evidence reference present
Cleanup: succeeded; Trino container and worker processes removed
TRINO_RECOVERY_EXIT=0
```

## Decision

PASS for real QueryFlux/Trino worker process recovery without duplicate
execution. The QueryFlux implementation line now has its real provider,
durable lifecycle, evidence, cancellation boundary, async create and process
recovery gates. Public v1 remains **0/13 (0%) — NO-GO** until the full family
matrix and remaining release gates close.
