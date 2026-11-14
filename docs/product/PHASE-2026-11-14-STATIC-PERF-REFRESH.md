# Static and performance gate refresh

Date: 2026-11-14  
Baseline: `f8fe5b3eeb5e7d92f14022f967454d894db75828`  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Gates executed

The tracked-source scope was explicitly limited to `python`, `tests` and
`tools` so user-owned untracked snapshots could not contaminate the result.

- `python -m ruff check python tests tools`: passed.
- `python -m ruff format --check python tests tools`: **921 files already formatted**.
- `python -m pytest -q tests/perf`: **5 passed, 0 failed** in 9.75s.

The official ledger remains **0/13 (0%), NO-GO**.
