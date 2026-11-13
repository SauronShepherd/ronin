# Qualification receipt — single-operator security and audit current

- Date: 2026-11-13
- Source checkout: `794a26cba2b8ffa7fea584a6b27a17417654a841`
- Command: `python -m pytest -q tests/test_audit.py tests/test_grant_survivor_boundaries.py tests/test_grant_scope_projection.py tests/test_grants.py tests/test_security_redaction.py tests/test_security_policy.py tests/test_secret_resolvers.py tests/test_mutation_audit.py tests/test_runner_broker_security.py tests/test_mounted_file_secrets.py tests/test_postgres_audit_store_unit.py`.
- Result: **302 passed, 2 skipped, 0 failed** in 7.39 seconds.
- Skips: Windows cannot authoritatively exercise POSIX mode bits and symlink creation is unavailable; neither was promoted to pass.
- Scope: single-operator grants/scopes, audit mutation coverage, secret resolution/redaction, runner-broker security and PostgreSQL audit unit boundaries.
- Boundary: no claim for OIDC, multi-user authorization or external secret-provider certification; legal/security human acceptance and full release aggregation remain open.
