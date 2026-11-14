# Security scans — current candidate

Date: 2026-11-14  
Candidate: `4dec2af0445e9e2b2debf60b6cd566a702544bfa`  
Policy: local/manual qualification only; GitHub Actions is intentionally absent.

## Gates executed

- Gitleaks **8.30.1**:
  `gitleaks dir . --no-banner --redact --report-format json`.
  Scanned approximately **233.22 MB**; **0 leaks found**.
- pip-audit **2.10.1** against `requirements-dev.lock`, with hash checking and
  strict mode: **0 known vulnerabilities** across the locked graph.
- Container vulnerability scan is recorded separately in
  `PHASE-2026-11-14-CONTAINER-SBOM-CVE-FIX.md`; the corrected image scan found
  **0 vulnerable packages**.

## Qualification boundary

This closes the local secret/dependency scanning slice. It does not constitute
legal license approval, human security acceptance, or qualification of all 13
Public v1 capability families. The official ledger remains **0/13 (0%),
NO-GO**.
