# Phase receipt — real OTLP collector refresh — 2026-11-12

## Candidate and service

- Source: `e374f6285ea26ceb106974dfcbf93dae737ce455`
- Worktree: clean detached candidate
- Image: `otel/opentelemetry-collector-contrib@sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621`
- Protocol: OTLP/HTTP on loopback

## Finding and correction

The runner used the same PowerShell native-log capture pattern that had caused
false failures in the Trino lane. It now captures benign collector stderr
diagnostics without weakening the strict container-removal check.

## Gate result

```text
1 passed in 15.75s
OTLP real-service tests: 1/1 passed, 0 skipped/failed.
test_exit_code: 0
cleanup_status: succeeded
```

The external evidence directory contains the collector config, JUnit, timing
report, transcript, container log and JSON summary:
`C:\Users\angel.alvarez\AppData\Local\Temp\ronin-otlp-evidence-20261112182852`.

## Decision

PASS for the real OTLP collector transport lane covering traces, metrics and
logs. This does not qualify full observability adoption, FinOps receipts,
provider alerting or Public v1 family completion. Public v1 remains **0/13
(0%) — NO-GO**.
