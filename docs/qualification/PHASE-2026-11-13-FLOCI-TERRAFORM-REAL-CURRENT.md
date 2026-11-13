# Qualification receipt — real Floci/Terraform Cloud Studio cycle

- Date: 2026-11-13
- Source checkout: `30897a95`
- Backend: Floci `2.1.0` pinned image
  `sha256:f5aa8c18302cedb4f2385f5c4e455b3efc77fee6bf7b6e5d1712b2817ba102db`
- Terraform: **1.13.5** (`windows_amd64`)
- AWS provider contract: **6.65.0**
- Endpoint: `http://127.0.0.1:4566` (loopback only)
- Result: **PASS**.

## Evidence

The real qualification runner completed `plan`, `apply`, `refresh`,
`destroy`, and Terraform `state list` successfully. After apply, the actual
Floci data plane exposed both `s3://qualification-bucket` and
`sqs://qualification-queue`. After destroy, Terraform state was empty and the
Floci data-plane residual-resource list was empty. The isolated Docker project
and named volume were removed in the runner cleanup.

The first attempt was correctly rejected because the host Terraform was
1.16.2; this PASS uses the exact pinned 1.13.5 binary and is the only result
accepted for this receipt.

Boundary: this qualifies the pinned local Floci Terraform lane only. It does
not certify AWS, AWS Emulator, LocalStack parity, production tenancy, or a
Public v1 family. Official status remains **0/13 (0%), NO-GO**.
