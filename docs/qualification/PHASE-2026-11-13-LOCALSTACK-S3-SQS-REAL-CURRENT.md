# Qualification receipt — real LocalStack S3+SQS cycle

- Date: 2026-11-13
- Source checkout: `7f7e87e1`
- Runner: `tools/cloud_studio_floci_qualification.py`
- Backend: LocalStack image pinned by
  `examples/cloud-studio/compose.localstack.yaml`
- Enabled services: `SERVICES=s3,sqs`
- Terraform: **1.13.5**
- Command timeout: **300 seconds**
- Result: **PASS for the declared S3+SQS scope**.

The reproducible runner completed with health HTTP 200, Terraform
`plan/apply/refresh/destroy`, and an empty final Terraform state. The S3 and
SQS resources were created and destroyed successfully; the SQS destroy took
approximately 42 seconds. The isolated Docker project and named volume were
removed during cleanup.

The earlier 120-second attempt remains a diagnostic showing why the explicit
timeout is required. This receipt does not claim LocalStack parity for
DynamoDB/Lambda or production support, and does not qualify AWS, AWS Emulator,
or a Public v1 family. Official status remains **0/13 (0%), NO-GO**.
