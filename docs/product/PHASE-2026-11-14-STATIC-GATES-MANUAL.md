# Phase receipt — manual static gates and web budget

## Status

**PASS** for the local static gate slice after reconciling the web budget with
the current candidate.

## Evidence

- Ruff format: **941 files already formatted**.
- Ruff check: **passed**.
- OpenAPI snapshot: **passed**.
- Route consistency: **199 operations passed**.
- Studio surface: **128/241 published operations matched**.
- Studio web audit: **72 files, 0 failures**.
- Architecture gate and negative gates: **passed**.
- Dependency surfaces and capability status: **passed**.
- Agent skills validation: all 3 bundled skills valid.
- Mypy: **446 source files, no issues**.
- Web budget after ratchet: `2168035` asset bytes, `71` requests, `37`
  modules, `15` stylesheets, `5838` HTML bytes; `studio_budget --check`
  passes.

## Finding and resolution

The previous baseline was `2167975` bytes, while `e6b9e360` added escaped
Data Engineering rendering after that ratchet. The measured `+60` bytes were a
real candidate delta, not hidden test output; `docs/ui/web-budget.json` now
records the exact measured candidate budget.

## Boundary

This is local static evidence only. Provider, supply-chain, legal, human review
and Public v1 family qualification remain separate. Public v1 stays **0/13
active families, 0%, NO-GO**.
