# Mypy and agent-skill installer conformance

Date: 2026-11-14  
Baseline before fix: `553b315c0c5d34512069db60428c138925a7a2a8`  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Finding and fix

Mypy reported an indexed assignment on a value inferred as `Collection[str]`
when updating the managed agent-skill manifest. The manifest JSON boundary is
now explicitly typed as `dict[str, Any]`, preserving the runtime behavior while
making the mutable schema honest to the type checker.

## Gates executed

- `python -m mypy python`: **386 source files, no issues found**.
- Ruff check on `python/studio_cli/agent_skills.py`: passed.
- Agent-skill installer/script tests: **14 passed, 0 failed**.

The official ledger remains **0/13 (0%), NO-GO**.
