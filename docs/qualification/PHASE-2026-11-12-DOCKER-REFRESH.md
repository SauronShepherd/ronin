# Phase receipt — real Docker qualification refresh — 2026-11-12

## Candidate and image

- Source candidate used by the runner: `d92316aa0d852ecf3d8e25ea0e7f45d506fa6130`.
- Worktree mode: `DIRTY-WORKTREE DIAGNOSTIC` because pre-existing untracked user artifacts remain in the checkout.
- Executed image: `sha256:113b4ec22b9ddadc1f391f1abcfa24bbbdc201a77c574d58e4c28f79d8b1baa9`.
- Selected services: PostgreSQL + Docker worker, Floci/S3, and Azurite/Azure Blob.

## Evidence

- Real Docker integration acceptance: **27 passed, 0 skipped, 0 failed** in 243.05s.
- Frozen v0.1 strict acceptance: **15/15 passed**, 0 skipped/failures, `strict_success=true`.
- Covered real worker execution and SIGKILL lease recovery, PostgreSQL-backed workflow execution, S3/ML artifact retention, S3 connector retry, Azure Blob discovery/read/replay, Docker isolation/resource limits, appliance backup/restore, and the frozen v0.1 journey.
- No leftover cancellation or timeout containers were reported.

## Cleanup observation

The runner's resource-observation summary recorded `timeout_state=failed` / `kernel.container.timeout` for the intentional timeout-container measurement and marked the final measurement unavailable; the functional timeout test itself passed and no timeout containers remained. This is retained as a warning and prevents treating this dirty diagnostic as a complete clean release gate.

## Result

PASS for the 27 functional Docker tests and 15/15 strict acceptance cases, with the cleanup-observation warning above. This is not clean candidate-bound release evidence; Public V1 remains `0/13 (0%)`.
