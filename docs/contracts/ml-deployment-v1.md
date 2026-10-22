# ML deployment v1

`ronin.ml-deployment/v1` represents a workspace-scoped serving deployment pinned to
one registered model version and its lowercase SHA-256 artifact digest. Creating a
deployment verifies the bytes through `ArtifactStore` before persisting `status=ready`
and `readiness=ready`; the current champion is never resolved implicitly.

Routes:

- `POST /v1/ml-studio/deployments` creates an idempotent deployment from
  `deployment_id`, `model_id`, `version` and an optional provider-neutral endpoint.
- `GET /v1/ml-studio/deployments` and `GET .../{deployment_id}` read workspace-scoped
  state. `GET .../{deployment_id}/health` returns readiness, the pinned digest and
  bounded request/error telemetry.
- `POST .../{deployment_id}/predict` verifies the pinned digest and serves local
  inference through the existing declarative artifact path. It accepts at most
  100,000 rows and never follows a changed champion.
- `POST .../{deployment_id}/rollback` transitions the deployment to
  `rolled_back`/`unready` without changing registry model stages.
- Scheduler jobs of type `ml-studio.deployment.v1` accept the same workspace,
  deployment, model, version and endpoint identity and return a
  `ronin.ml-deployment-task-result/v1` envelope. The task is idempotent and
  verifies the artifact digest before reporting readiness.

Deployment identity, model version, artifact reference and digest are immutable.
Retries of the same create request are idempotent; reuse with a different pin is a
conflict. Telemetry updates preserve the pin and are bounded. Provider-specific
network serving remains an adapter concern; this contract covers the local,
digest-verified serving path.
