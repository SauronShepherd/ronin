# Phase receipt — RPV1-003 runner protocol conformance

## Status

**PASS — IMPLEMENTATION SLICE** for the provider-neutral `ronin/runner/v1`
fixture checker.

## Changes

- Strengthened the independent Go checker in
  `tools/runner_protocol_check.go`.
- It now rejects missing required fields, unknown envelope fields, invalid
  identifiers, non-object payloads, invalid optional identifiers, and
  unsorted/duplicate/invalid capabilities.
- Canonical-byte verification remains independent of the Python validator.

## Evidence

- `go run tools/runner_protocol_check.go tests/golden/runner_protocol_v1.json`:
  `runner protocol fixtures: ok (2)`.
- Negative fixture with missing `request_id`: rejected with
  `runner envelope is missing required fields`.
- Python protocol tests: `26 passed`.
- `git diff --check`: passed.
- No GitHub Actions were used or added.

## Boundary

This closes the independent envelope/fixture-checker slice only. Duplicate
dispatch execution, lease fencing under crash, remote worker conformance and
provider/runtime qualification remain separate acceptance work. Public v1
remains **0/13 active families, 0%, NO-GO**.
