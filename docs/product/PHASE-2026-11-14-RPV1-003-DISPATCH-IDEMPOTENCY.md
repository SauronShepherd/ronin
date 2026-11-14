# Phase receipt — RPV1-003 dispatch idempotency

## Status

**PASS — IMPLEMENTATION SUBPHASE** for completed runner dispatch replay.

## Changes

- The runner broker now keeps a bounded completed-execution cache.
- A repeated request with the same execution ID and canonical request digest
  returns the stored result without invoking the executor again.
- Reusing an execution ID with a different request returns a typed `409`
  `execution_replay_mismatch` response and never executes the request.
- Cache size is bounded by `RunnerBrokerConfig.completed_cache_size`.

## Evidence

- Broker security/conformance tests: `21 passed`.
- The HTTP replay test observed identical response bytes and
  `execute_count == 1` for two identical dispatches.
- The mismatched replay returned HTTP `409` while `execute_count` remained `1`.
- Ruff and `git diff --check`: passed.
- No GitHub Actions were used or added.

## Boundary

Crash recovery, lease fencing across workers, and remote/provider conformance
remain separate gates. Public v1 remains **0/13 active families, 0%, NO-GO**.
