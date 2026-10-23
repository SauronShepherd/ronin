---
name: ronin-machine-learning
description: "Use when a coding agent is developing or validating Ronin Machine Learning Studio, PipelineIR, durable ML execution, model artifacts, registry, evaluation, promotion, retry, deployment, or ML portability. Trigger for Ronin ML Lab work, PipelineIR v1/v2/v3 compatibility, candidate search, artifact identity, checkpoints, model registration, or deployment flows. Do not invent a `ronin ml` CLI: verify the OpenAPI/SDK or repository contract first, keep workspace and artifact digests bound, and separate implemented behavior from provider or release qualification."
---

# Ronin Machine Learning

Ronin ML currently exposes product surfaces primarily through API/SDK/plugin contracts. Do not invent a `ronin ml` command.

## Workflow
1. Verify the OpenAPI snapshot with `scripts/verify_openapi.py --openapi PATH` before proposing API-driven actions.
2. Identify the exact ML contract version used by the task: Lab v1, PipelineIR v1/v2/v3, backend v1, or remote-adapter v1.
3. Preserve workspace, Lab digest, PipelineIR digest, runtime/dependency identity, dataset snapshot identity, and artifact SHA-256 across durable execution.
4. For candidate search, keep search spaces bounded and deterministic; preserve seed/trial identity and tie-break ordering.
5. Treat checkpoints as reusable only when runtime/dependency/upstream-output identity matches.
6. Register or promote models only after verifying terminal success and artifact identity. Promotion requires the existing authorization/reason gate.
7. Treat deployment creation, rollback, and external-provider operations as sensitive mutations.

## Compatibility rules
- PipelineIR v3 does not retroactively replace v1/v2. Use the version declared by the artifact/request.
- Plugin-defined stages require the plugin contract and isolation policy; do not treat arbitrary code as a built-in stage.
- MLflow metadata exchange is not proof of full MLflow interoperability.
- LocalStack/S3-compatible qualification is not proof of a production cloud provider.
- A model artifact that loads successfully is not proof that a proprietary training recipe was reproduced.
- Never claim P8 release qualification from isolated ML tests or green CI.

## References
Read `references/ml-contracts.md` for the current documented ML boundaries and known qualification gaps.
