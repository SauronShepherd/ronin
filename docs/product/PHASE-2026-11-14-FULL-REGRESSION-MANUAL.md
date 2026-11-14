# Phase receipt — full manual regression

## Status

**PASS — LOCAL REGRESSION GATE** for the current source candidate.

## Evidence

- Command: `python -m pytest --ignore=tests/perf -q`.
- Result: **4577 passed, 80 skipped, 0 failed** in `539.59s`.
- The skipped tests are explicitly opt-in or environment-bound checks for real
  Docker, PostgreSQL, S3/Azure, Trino, OTLP, SDP, symlink privileges and other
  external providers. They remain open qualification gates and are not counted
  as passes.
- Candidate base before this receipt: `849f8b244b9a580d7441d97ac539f0699b222666`.
- No GitHub Actions were used or added.

## Boundary

This is a broad local regression gate, not a release qualification claim. The
manual provider/Docker gates already recorded separately must remain bound to
their exact candidate and be rerun after any material product change. Public v1
remains **0/13 active families, 0%, NO-GO**.
