# Phase 2026-11-12 — Release-evidence contracts

## Scope

Validate the fail-closed evidence aggregator and the generated release-case inventory before attempting any aggregate release verdict.

## Candidate

- Base source: `f0d098b9` (`test: refresh supply chain qualification`)
- Worktree tracked state: clean before execution; user-owned untracked artifacts remain outside the candidate
- Profile under test: `release_required` remains independently gated and is not claimed green by this phase

## Tests

```text
$env:PYTHONPATH='python'
python -m pytest -q tests/test_release_evidence.py tests/test_release_case_inventory.py
```

Result: **PASS — 40 passed, 0 failed, 0 skipped, 7.44 s**.

The selection covers exact-commit/profile binding, duplicate gate rejection, timestamp and execution-scope fail-closed behavior, artifact rehashing, aggregate CLI behavior, and release-case parsing/classification invariants.

## Qualification result

The release-evidence contract phase passes. It does not create a release verdict: the complete `release_required` bundle is still unavailable and the license/legal, product decision, provider, manual review, rollback/recovery, and complete Public v1 family gates remain open. Public v1 remains **0/13 (0%) — NO-GO**.

