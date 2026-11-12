# P1 — Git source and VCS real qualification

**Date:** 2026-11-12  
**Candidate SHA:** `8408753d5cf4545233a40d43f40a19dee9e99486`

## Command and result

```text
python -m pytest -q tests/test_git_source.py tests/test_vcs_git.py
```

Result: **30 passed, 2 skipped, 0 failed** in 31.29s.

The tests use temporary real Git repositories and cover exact detached
checkouts, revision identity, remote fetch/update, fast-forward behavior,
dirty-tree refusal, divergent history, subdirectory confinement, symlink
rejection, clone cleanup and unsafe remote/subdirectory inputs.

The two skips are host-specific: POSIX executable-mode behavior and Windows
symlink creation without Developer Mode/privilege. They are not converted to
passes and require an appropriate POSIX/privileged runner for full platform
coverage.

## Boundary

This qualifies the local Git source/VCS contract. Remote-provider certification,
multi-user authorization and the complete installed P1 journey remain open;
P1 is not release-qualified and Public v1 remains **0/13 (0%)**.

