# Qualification receipt — split Terraform HCL generation

- Date: 2026-11-13
- Source checkout: `2ba083b3`
- Backend: Floci 2.1.0 pinned image
- Terraform: **1.13.5**
- Result: **PASS**.

Cloud Studio now writes the Terraform contract into `main.tf` (tool/provider
requirements), `provider.tf` (endpoint and local credentials configuration),
and `resources.tf` (topology resources). The real Floci runner accepted this
split layout and completed `plan`, `apply`, `refresh`, `destroy`, data-plane
S3/SQS verification, and empty-state verification successfully.

Boundary: this qualifies HCL generation and the pinned Floci lane only. It
does not qualify AWS, AWS Emulator, full provider parity, or a Public v1
family. Official status remains **0/13 (0%), NO-GO**.
