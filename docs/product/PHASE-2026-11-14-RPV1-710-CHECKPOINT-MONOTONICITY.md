# Phase receipt — RPV1-710 checkpoint monotonicity

## Status

**PASS** for the implemented RPV1-710 checkpoint-safety slice on candidate
`44fa6982f4784467a93afe7b10ee2453f15cfbb4`.

## Change

- `SqliteStreamCheckpointStore.compare_and_set` now rejects offsets that move
  backwards relative to the expected checkpoint.
- Existing checkpoint partitions cannot be silently removed by a transition.
- Rejected transitions are fail-closed and leave the durable checkpoint
  unchanged.
- Added regression coverage for offset regression and partition removal.

## Evidence

- Streaming conformance slice: **18 passed, 0 failed**.
- Full Python regression (`python -m pytest --ignore=tests/perf -q`):
  **4582 passed, 80 skipped, 0 failed** in 450.25 s.
- Ruff check, Ruff format check and `git diff --check`: **passed**.

## Boundaries

This closes only the implemented RPV1-710 checkpoint-safety slice. It does not
claim exactly-once processing, distributed stateful streaming, or provider
certification. RPV1-712 remains missing. Public v1 remains **0/13 active
families, 0%, NO-GO**, with `release_status=incomplete` and
`qualification_status=qualification_pending`.

Policy: qualification was manual and local; no GitHub Actions, branch or
worktree was used.
