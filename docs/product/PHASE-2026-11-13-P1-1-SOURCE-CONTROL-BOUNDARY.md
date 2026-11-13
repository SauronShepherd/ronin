# Receipt — P1.1 source-control boundary

Date: 2026-11-13  
Phase: P1.1 — workspace/project Git source boundary  
Status: **PASS (subfase)**

## Scope

The existing source-control implementation was verified for credential-free
URI validation, local-origin binding, safe subdirectory resolution, detached
checkout, fetch and fast-forward policies, dirty-worktree rejection, source
revision evidence, and workspace/project HTTP isolation.

## Evidence

```text
python -m pytest -q \
  tests/test_git_source.py \
  tests/test_project_manifest.py \
  tests/integration/test_workspace_project_http_api.py \
  tests/integration/test_http_submit_status.py
```

Result: **152 passed, 1 skipped, 0 failed** in 87.38s. The one skip is the
Windows symlink case requiring developer privileges and is not treated as a
pass. Ruff format and lint across `python tests tools packages docker` passed.

## Boundary

This closes only P1.1 source-control boundary verification. Remote-provider
certification, full authoring journeys, PostgreSQL restart evidence, and the
complete P1 family gate remain open. Public v1 remains **0/13, 0%, NO-GO**.
