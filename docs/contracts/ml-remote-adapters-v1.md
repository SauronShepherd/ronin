# ML Remote Adapter Contract v1

Canonical identifier: `ronin.ml-remote-adapter/v1`.

Remote adapters (MLflow, Spark, or another managed trainer) must implement the
same logical lifecycle as the local adapter without leaking provider clients
into Lab or Registry services:

1. resolve a backend capability declaration;
2. submit a bounded training request with `TrainingContext`;
3. return a run identity and durable artifact reference;
4. poll or receive a terminal result with effective parameters, metrics,
   signature, framework and provenance;
5. validate prediction input against the registered signature.

The request must contain a dataset reference, immutable lab version, backend
ID, algorithm, numeric limits, timeout and idempotency key. Credentials are
resolved by the host and are never serialized into a lab, request, artifact,
or model card. Provider errors map to stable classes: `configuration_error`,
`validation_error`, `capacity_error`, `transient_error`, and
`permanent_training_error`.

Adapters must enforce both a wall-clock timeout and a maximum trial/resource
budget. Retries are allowed only for `transient_error` and must reuse the same
idempotency key. A remote artifact is accepted only after digest verification;
the registry stores the provider reference as provenance, not as the model
payload. Promotion and scoring remain provider-neutral.

The current release implements the contract types and local adapter only.
MLflow and Spark implementations remain future adapters and must pass the
capability, provenance, artifact-digest, cancellation, retry, and prediction
signature conformance suites before being advertised as available.
The SDK representations are `RemoteTrainingRequest`, `RemoteTrainingResult`,
and the provider-neutral `Remote*Error` hierarchy. They contain no credentials
or provider clients and are safe to persist as audit metadata.

The executable adapter surface is `RemoteMLBackend`: `submit`, `poll`,
`cancel`, and `predict`. A fake implementation is covered by the conformance
test suite; provider adapters must satisfy the same runtime-checkable protocol.

`RemoteRetryPolicy` standardizes bounded exponential backoff. It is applied
only to errors whose `retryable` property is true and must reuse the original
idempotency key.

`RemoteExecutionController` is the provider-neutral lifecycle helper. It
retries only `RemoteTransientError`, delegates polling and cancellation, and
never changes the request identity between attempts.

`MLflowBackend` and `SparkBackend` are the concrete provider adapters. Their
transport is injected intentionally: deployment code supplies the authenticated
HTTP/RPC client, while tests can use a deterministic fake transport. Their
stable IDs and advertised capabilities are part of discovery and provenance.

For simple HTTP deployments, `urllib_json_transport` supplies the transport
with explicit URL-scheme validation, timeout and caller-provided headers.
