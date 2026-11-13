# Qualification diagnostic — Terraform validate/apply gate

- Date: 2026-11-13
- Scope: generated `variables.tf`, Terraform `validate` gate and real Floci qualification runner.
- Result: `terraform validate` passed and `terraform plan` passed against the existing AWS provider 6.65.0 installation.
- Failure: real `apply` exceeded the configured 300-second timeout; the subsequent fixture probe could not connect because Docker Desktop became unavailable. Cleanup recorded Terraform destroy/state-list with an empty state.
- Interpretation: this is diagnostic evidence only. It does not qualify Floci or any Public v1 family. The provider gate remains open for a fresh Docker-backed rerun.
