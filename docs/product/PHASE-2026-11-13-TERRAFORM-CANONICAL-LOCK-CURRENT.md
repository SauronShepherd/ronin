# Receipt — Terraform canonical provider lock

Date: 2026-11-13  
Phase: Cloud Studio / Terraform CI qualification  
Status: implemented locally; remote qualification pending

## Change

The generated Terraform workspace now receives a tracked canonical
`.terraform.lock.hcl` for the exact provider contract (`hashicorp/aws 6.65.0`)
before `terraform init`. The lock contains the provider's multiplatform `h1`
and `zh` hashes, preventing an incomplete runner-generated lock from reaching
`terraform plan` in CI.

## Evidence

- Cloud Studio focused tests: `42 passed`
- Ruff: clean
- Full Python suite: `4563 passed, 80 skipped, 0 failed`
- Full-suite duration: `423.11s`

## Scope and remaining gate

This receipt does not claim Floci CI or public-family qualification. The
GitHub Actions Cloud Studio job must pass with this change before the CI item
in `BUILD_PLAN_CLOUD_STUDIO.md` can be marked complete.
