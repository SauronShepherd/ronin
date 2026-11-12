# Phase receipt — Trino real-service runner refresh — 2026-11-12

## Candidate and service

- Source: `36de441281c5a97cc2d5538d1db93002498f8079`
- Worktree: clean detached candidate
- Image: `trinodb/trino@sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f`
- Service version: `484`

## Finding and correction

The first real run reached Trino and passed both tests, but the PowerShell
runner exited with failure while capturing normal JVM warnings from `docker
logs`. The runner now explicitly loads `System.Net.Http` and captures service
logs under a non-terminating error preference, while retaining a strict failure
check for container removal.

## Gate result

```text
2 passed in 23.70s
Trino real-service tests: 2/2 passed, 0 skipped/failed.
test_exit_code: 0
cleanup_status: succeeded
```

The JUnit, timing, transcript, container log and JSON summary were emitted in
the external evidence directory:
`C:\Users\angel.alvarez\AppData\Local\Temp\ronin-trino-evidence-20261112182130`.

## Decision

PASS for the pinned Trino transport gate and runner cleanup. This is provider
transport evidence only; it does not qualify the full QueryFlux asynchronous
worker/cancel/recovery contract or Public v1 family. Public v1 remains **0/13
(0%) — NO-GO**.
