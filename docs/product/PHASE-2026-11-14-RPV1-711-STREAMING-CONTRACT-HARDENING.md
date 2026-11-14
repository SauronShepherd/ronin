# Phase receipt — RPV1-711 streaming contract hardening

## Status

**PASS** for the implemented RPV1-711 contract slice on candidate
`3f57a7de37e2127f743b0f35ed662729be81a1a4`.

## Change

- `window_records` now fails closed when a record has no event timestamp;
  records are no longer silently discarded without an explicit DLQ policy.
- Late-record classification uses partition/offset keys rather than repeated
  record membership scans.
- `SqliteStreamTable.append` remains idempotent for identical replays but
  raises on a replay with a different timestamp, key or payload instead of
  silently ignoring divergent data.
- Added focused regression coverage for the three invariants.

## Evidence

- Focused streaming conformance: **34 passed, 0 failed**.
- Full Python regression (`python -m pytest --ignore=tests/perf -q`):
  **4580 passed, 80 skipped, 0 failed** in 685.79 s.
- Ruff check, Ruff format check and `git diff --check`: **passed**.

## Boundaries

This closes only the implemented RPV1-711 contract slice. It does not claim
Kafka/Flink/Kinesis/PubSub provider certification or close RPV1-711 as a
release-qualified family. RPV1-712 distributed stateful streaming remains
missing. Public v1 remains **0/13 active families, 0%, NO-GO**, with
`release_status=incomplete` and `qualification_status=qualification_pending`.

Policy: qualification was manual and local; no GitHub Actions, branch or
worktree was used.
