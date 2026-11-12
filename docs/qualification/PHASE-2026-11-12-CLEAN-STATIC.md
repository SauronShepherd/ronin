# Phase receipt — clean candidate static gates — 2026-11-12

## Candidate

- Exact source SHA: `48086d60f9b99044839fd89a5e9a2cdf6ab7f57c`.
- Execution worktree: clean detached candidate worktree containing tracked files only.

## Evidence

- Ruff format check: **935 files already formatted**.
- Ruff lint: **All checks passed**.
- OpenAPI snapshot digest: `fe364bd58ac3044064cf4d2653c26e79b34586a5e3f25b75c7db02aa4059e2da`.
- Mypy: **no issues in 443 source files**.
- Architecture gate and deliberate-negative gate: passed.
- Route consistency: **197 operations** passed.
- Studio surface: passed (`128/239` published operations matched by the declared surface check).
- Web audit: 72 files, 0 failures.
- Web budget: passed.
- Dependency surfaces: passed.
- Public V1 capability ledger: valid.
- Agent skills validation: 3 skills valid, 0 errors.

An initial combined command used POSIX-style `PYTHONPATH=python` syntax in PowerShell; that command fragment did not execute. The affected route-consistency and skills checks were then rerun with `$env:PYTHONPATH='python'` and passed. No product failure was inferred from the shell syntax error.

## Result

PASS for the declared clean-candidate static gate set. This does not replace the full Python suite, browser, Docker/Helm, license, artifact, or human gates. Public V1 remains `0/13 (0%)`.
