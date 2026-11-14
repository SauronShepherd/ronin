# pip-audit dependency surfaces — current candidate

Date: 2026-11-14  
Candidate: `7530a6fc34cbb13691ca397493e61f944b3a8a2e`  
Policy: local/manual qualification only; GitHub Actions is intentionally absent.

## Gates executed

With pip-audit 2.10.1, strict mode and hash verification:

- `requirements-test.lock`: **0 known vulnerabilities**.
- `docker/requirements-runtime.lock`: **0 known vulnerabilities**.
- `docker/pip-bootstrap.lock`: **0 known vulnerabilities**.

JSON reports are retained under:
`C:\Users\angel.alvarez\Downloads\ronin-pip-audit-surfaces-7530a6fc`.

## Qualification boundary

This closes the test/runtime/bootstrap dependency scanning slice. It does not
replace the open license/legal review, container SBOM evidence, or full Public
v1 family qualification. The official ledger remains **0/13 (0%), NO-GO**.
