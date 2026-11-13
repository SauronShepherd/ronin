# Receipt — Terraform multiplatform provider lock

Date: 2026-11-13  
Phase: Cloud Studio / Terraform CI qualification  
Status: implemented locally; remote qualification pending

## Finding and correction

The Floci CI job reached `plan` successfully but `apply` rejected the AWS
provider package because the generated lock lacked the Linux `h1` checksum.
The tracked lock was regenerated with Terraform `providers lock` for
`windows_amd64` and `linux_amd64`, retaining the exact AWS provider version
`6.65.0` and all registry hashes.

## Evidence before this correction

- GitHub Actions run `43468202978`: Python 3.11/3.12 and Chromium passed.
- Floci health, Terraform plan, and Terraform validate passed.
- Floci apply failed only on the missing Linux provider checksum.

## Remaining gate

The next GitHub Actions run must pass the real Floci `plan`, `validate`,
`apply`, refresh, destroy, and residual-resource checks before the CI item is
marked complete. No public-family qualification is claimed by this receipt.
