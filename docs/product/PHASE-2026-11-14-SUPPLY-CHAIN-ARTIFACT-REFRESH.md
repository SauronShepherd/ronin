# Supply-chain and artifact refresh

Date: 2026-11-14  
Baseline: `d1825c72a9cffffbdb8feac78c8e0bea06b3ac8a`  
Policy: manual qualification only; GitHub Actions is intentionally absent.

## Gates executed

- `gitleaks detect --source . --no-banner --redact`: **no leaks found**;
  2805 commits and approximately 18.34 MB scanned.
- `pip-audit -r requirements-test.lock --progress-spinner off`:
  **No known vulnerabilities found**.
- `python tools/artifact_qualification.py` in isolated build/install
  environments: package contract tests **90 passed, 0 failed**.

Artifact identity produced by the isolated qualification:

- sdist `pyronin-0.0.1a0.tar.gz`:
  `e5e9f1c5aad3b3906353901eaece324781579e3ef756cd9993d1cd662c31c8c6`
- wheel `pyronin-0.0.1a0-py3-none-any.whl`:
  `f503c4f52b526574bdde981b85d238feb7840cf5e821b4bdfc97bb69af2a2841`
- wheel RECORD:
  `f3492f0e84596ee776bd02a362e17d288d7e955a5f14ab1892e423143d5630e9`

## Qualification boundary

These checks do not constitute legal/license approval, SBOM/provenance signoff,
or complete Public v1 release qualification. The official ledger remains
**0/13 (0%), NO-GO**.
