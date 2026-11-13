# Single-operator security and audit regression — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `01e202f15fedf0e5d7b4dd5a4d213be7cf306c7f`

## Gate

Command:

```text
python -m pytest -q tests/test_audit.py tests/test_grant_survivor_boundaries.py tests/test_grant_scope_projection.py tests/test_grants.py tests/test_security_redaction.py tests/test_security_policy.py tests/test_secret_resolvers.py tests/test_mutation_audit.py tests/test_runner_broker_security.py tests/test_mounted_file_secrets.py tests/test_postgres_audit_store_unit.py
```

Result: **302 passed, 2 skipped, 0 failed** in 83.46 seconds.

The skips are host capabilities: POSIX mode bits are not authoritative on
Windows and symlink creation is unavailable. They are not promoted to passes.

## Decision

Local single-operator security/audit phase: **PASS**. The evidence does not
claim OIDC, multi-user authorization or external secret-provider certification;
those remain separate gates. Public v1 remains **0/13 (0%) — NO-GO**.
