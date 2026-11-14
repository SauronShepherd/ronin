# Phase receipt — manual supply-chain checks

## Status

**PASS** for the local supply-chain and static asset slice.

## Evidence

- `python tools/check_web_assets.py`: **53 Studio assets checked**.
- `python -m pip_audit -r requirements-test.lock --strict`: **no known
  vulnerabilities found**.
- `gitleaks git --no-banner --redact --log-opts='HEAD~50..HEAD'`: **49 commits
  scanned, no leaks found**, approximately 61.85 KB inspected.

## Boundary

The pip audit covers the locked test dependency surface and Gitleaks covers the
selected Git history range; this receipt is not a complete legal/license,
provenance, SBOM or external-provider certification. Public v1 remains **0/13
active families, 0%, NO-GO**.
