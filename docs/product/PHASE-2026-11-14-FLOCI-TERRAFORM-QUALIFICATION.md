# Cloud Studio / Floci qualification — current candidate

Date: 2026-11-14  
Candidate: `ab7717bcc29f16a33d4152d6d2f991a844fd8827`  
Policy: local/manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

Floci was started from the repository's isolated Compose fixture. The strict
qualification was then run with Terraform 1.13.5, downloaded from the official
HashiCorp release archive (SHA-256 of the ZIP:
`73F97943C93F268AE2C645B2A737D552175AA64D00A5C8B8F5CCC5831C033C8A`).

Result:

- Floci health: HTTP 200.
- Terraform version: **1.13.5**.
- AWS provider: **6.65.0**.
- Terraform validate, plan, apply, refresh and destroy: **PASS**.
- Synthetic S3 bucket and SQS queue created and destroyed successfully.
- Final Terraform state: empty.
- Residual resources: none.
- Evidence: `C:\Users\angel.alvarez\Downloads\ronin-floci-qualification-ab7717bc-terraform-1135.json`.

## Qualification boundary

This closes the local Cloud Studio/Floci implementation and qualification
slice. It does not qualify external cloud providers, legal review, or all 13
Public v1 capability families. The official ledger remains **0/13 (0%),
NO-GO**.
