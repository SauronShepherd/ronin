# Ronin ML contract map

Documented contracts from the supplied analysis:

- `ronin.ml-lab/v1`
- `ronin.ml-pipeline-ir/v1`
- `ronin.ml-pipeline-ir/v2`
- `ronin.ml-pipeline-ir/v3`
- `ronin.ml-backend/v1`
- `ronin.ml-remote-adapter/v1`

Implemented areas described by the current analysis include durable JobStore execution, governed dataset snapshots, ArtifactStore-backed large inputs and outputs, PipelineIR execution/checkpoints, deterministic candidate search, model registration/promotion, selective retry, local model deployment, S3-compatible lifecycle qualification, quality suites, feature definitions, and drift policies.

Still distinguish from full qualification: real MLflow interoperability, production remote providers, network serving/provider qualification, arbitrary plugin-defined stages beyond declared contracts, and Public v1 release qualification.
