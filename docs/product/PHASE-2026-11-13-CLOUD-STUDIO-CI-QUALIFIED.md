# Receipt — Cloud Studio Terraform/Floci CI qualification

Date: 2026-11-13  
Phase: Cloud Studio — Terraform/OpenTofu  
Status: **PASS**

## Authoritative remote evidence

GitHub Actions run `43469297016` completed successfully for the published
candidate. All required jobs passed:

- Cloud Studio Terraform / Floci — `init`, `plan`, `validate`, `apply`,
  refresh, destroy and residual-resource checks.
- Python quality / 3.11 — canonical quality gates.
- Python quality / 3.12 — canonical quality gates.
- Chromium non-live regression.

The Floci job used Terraform `1.13.5`, AWS provider `6.65.0`, the pinned Floci
image, and the generated multiplatform provider lock. The provider lock
contains both Windows and Linux checksums, which resolved the prior CI-only
apply failure.

## Scope boundary

This closes the Cloud Studio Terraform CI item in `BUILD_PLAN_CLOUD_STUDIO.md`.
It does not claim AWS Emulator qualification, public-v1 family qualification,
or release readiness. The official public-v1 ledger remains conservative at
`0/13` active families and `NO-GO`.
