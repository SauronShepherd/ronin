# Phase 2026-11-14 — Full Python suite and Docker contract refresh

## Scope

Re-run the complete local Python test gate after the container CLI base-image
security refresh and reconcile any stale executable contract.

## Candidate and policy

- Candidate before this phase: `fa80549d8c3ddd0a384e981ad5fb94378e20c49b`.
- Work was performed directly on `main`; no branch or worktree was created.
- GitHub Actions is intentionally absent and was not introduced.
- User-owned untracked artifacts were preserved and excluded from the commit.

## Finding and correction

The first full run exposed one stale test expectation: the Docker contract still
required `docker:29.10.0-rc.1-cli-alpine3.24` and its old digest, while the
Dockerfiles had already moved to `29.10.0-rc.2` to address CVE-2026-97054.
The test was updated to require the current immutable rc.2 digest:

`sha256:231dcc6a1ff0bf3e4b267ac308eafb19ae8d616839240ee03731a65c13525971`.

## Evidence

- Initial full run: 4,591 passed, 80 skipped, 1 failed; the sole failure was
  the stale Docker CLI assertion.
- Focused regression after correction: 1 passed.
- Final full run: **4,592 passed, 80 skipped, 0 failed** in 499.47 seconds.
- `git diff --check`: passed.
- `python tools/generate_public_v1_status.py --check`: passed.

## Result

Technical phase **PASS**. This does not change the product release decision:
the official Public v1 ledger remains `0/13`, `0%`, `NO-GO`, because the
separate human, provider, candidate-bound and family-journey gates remain open.
