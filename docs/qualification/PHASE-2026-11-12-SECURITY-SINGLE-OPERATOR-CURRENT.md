# P13 — Single-operator security and audit regression

**Date:** 2026-11-12  
**Candidate SHA:** `6d4d16776acfba3d54efbaa0c58efd5d5901b884`

## Command and result

```text
python -m pytest -q \
  tests/test_audit.py tests/test_grant_survivor_boundaries.py \
  tests/test_grant_scope_projection.py tests/test_grants.py \
  tests/test_security_redaction.py tests/test_security_policy.py \
  tests/test_secret_resolvers.py tests/test_mutation_audit.py \
  tests/test_runner_broker_security.py tests/test_mounted_file_secrets.py \
  tests/test_postgres_audit_store_unit.py
```

Result: **302 passed, 2 skipped, 0 failed** in 10.54s.

The suite covers bearer/grant boundaries, scope projection and survivors,
security policy, secret redaction/resolution, audit integrity, mutation audit,
runner-broker security and mounted-file secret constraints.

The two skips are host capabilities: POSIX mode bits are not authoritative on
Windows and symlink creation is unavailable. They are not converted to passes.

## Boundary

This qualifies the local single-operator security/audit regression surface. It
does not claim OIDC, user/group administration, multi-user authorization or an
external secret-provider certification; those remain Ronin Pro or separate
provider/release gates. Public v1 remains **0/13 (0%)**.

