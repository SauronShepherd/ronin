# Cloud Studio - AWS Emulator as secondary reference

**Decision:** 2026-11-13. **Status:** documented reference; runtime **missing**.

## Non-regression baseline

- Keep in-memory as default and Floci as proven external qualification backend.
- Keep Floci Compose digest, S3/ML tests, Terraform tests and current CI intact.
- LocalStack remains optional. Do not add advertised resource capabilities yet.
- AWS Emulator is for development/CI, not production or security certification.

## Phases, dependencies and completion gates

### AWS-0 - decision (documented)

Contract: EmulatorBackend and CloudTopology unchanged. These documents record
Floci retention and a secondary candidate. No runtime or provider qualification
is claimed. No existing Ronin task is closed by documentation alone.

### AWS-1 - local boot and trust (missing)

Files: examples/cloud-studio/compose.aws-emulator.yaml,
examples/cloud-studio/Dockerfile.aws-emulator and setup documentation.
Pin official release/checksum, restrict host networking to loopback, use
EMULATOR_TELEMETRY=off in tests, trust self-signed TLS without disabling
verification, pass health and teardown checks with no AWS account or outbound
AWS endpoints. Risks: no prebuilt official image assumed; heavyweight builds,
TLS, volatile state and dependency licenses.

### AWS-2 - backend adapter (missing)

Files: python/studio_cloud/backends.py, engine.py, plugin.py,
tests/test_cloud_studio.py. Reuse existing EmulatorBackend, CloudTopology,
Terraform exporter and /v1/cloud-studio lifecycle. Support optional
RONIN_CLOUD_STUDIO_BACKEND=aws-emulator after boot, with safe endpoint,
ephemeral mock credentials, bounded timeouts and explicit unsupported
operations. Do not silently reuse Floci authentication assumptions.
Acceptance: no Floci/default regression; OpenAPI/SDK/Studio parity if changed.

### AWS-3 - conformance (missing)

Files: tests/integration/test_s3_json_connector_real.py,
tests/integration/test_ml_s3_artifact_store_real.py, new focused tests,
Terraform/OpenTofu fixtures and versioned operation matrix. Compare S3
read/write/retry/cleanup; SQS send/receive/ack; DynamoDB conditional ops;
Lambda invoke/event and Terraform plan/apply/refresh/destroy where supported.
Record exact SHA, image/package digest, versions, expected effects, negative
errors, recovery and zero mandatory skips; report partial/unsupported honestly.
AWS-emulated behavior is not evidence for real AWS or vendor migration.

### AWS-4 - possible replacement (blocked)

Files: tools/cloud_studio_emulator_compare.py, comparative receipts and ADR.
Only promote AWS Emulator over Floci after **100% of mandatory Floci-passing
scenarios** pass with **zero required skips/failures** on the same Ronin SHA,
including negative/restart/cleanup/idempotency and Terraform behavior;
resource budgets and network isolation must pass, rollback to Floci must be
proven and maintainers must approve the change in a separate PR/ADR.
Failure preserves Floci as preferred.

### AWS-VER - independent qualification (missing)

Files: CI job, docs/qualification receipts, license/NOTICE review and
security checks. Preserve Floci CI and evidence. Complete separate supply
chain, reproducibility and exact-SHA checks; no claim of AWS real security.

## Mandatory completion protocol

Every phase: scope -> implement -> tests -> fix and rerun if failing ->
commit/push to authorized branch on pass -> verify remote CI -> report
accepted RPV1 tasks/91 and separate Public v1 release qualification.
This decision changes neither implemented task counts nor 0/13 release status.

Sources: https://github.com/aws/aws-emulator ;
https://github.com/aws/aws-emulator/releases ;
https://docs.aws.amazon.com/emulator/latest/userguide/what-is-service.html .
Licenses upstream: CC0-1.0, and Apache-2.0 for vendor/.
