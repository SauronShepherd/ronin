# ML Backend Contract v1

Canonical identifier: `ronin.ml-backend/v1`.

An adapter exposes a stable `backend_id`, display name, capability declaration,
and a training operation receiving an `ExperimentRequest` and row sequence. A
capability declaration contains `tasks`, `algorithms`, `hyperparameters`,
`artifact_formats`, and `resource_profiles`,
`supports_prediction`, `supports_artifacts`, and
`supports_explainability`. Capability discovery is advisory; the backend still
validates every request and must return a typed error for unsupported pairs.

The current local adapter advertises classification, regression and clustering;
its algorithms are `logistic_regression`, `linear_regression`,
`decision_tree_classifier`, `decision_tree_regressor`,
`random_forest_classifier`, `random_forest_regressor`, `kmeans`,
`gradient_boosting_regressor` and `gradient_boosting_classifier`. It advertises
prediction and artifact support but not explainability. Backend identifiers are
stable routing keys and must not encode environment-specific paths or
credentials.

`hyperparameters` names the bounded provider-controlled knobs accepted by the
adapter; it does not grant clients permission to send arbitrary estimator
options. `artifact_formats` lists media types the adapter can materialize and
`resource_profiles` lists deployment profiles it can execute. An adapter must
reject parameters or profiles outside its declaration before starting work.

An implementation must produce a serializable model artifact, effective
hyperparameters, input signature, metrics, and provenance sufficient to replay
or reject prediction. Remote adapters may implement the same contract without
changing Lab or Registry services. Adding a capability is compatible; removing
one requires an adapter version or a migration policy for existing labs.

`BackendRegistry` is the process-local resolver. Registration is explicit,
duplicate IDs are rejected, and listing is sorted by `backend_id`; this makes
startup composition and contract tests deterministic.

The SDK-level value objects are `TrainingContext` (dataset, workspace, run and
artifact namespace), `PredictionContext` (model identity and row limit), and
`ModelInspection` (signature, framework, artifact schema and limitations).
They deliberately contain references and policy, not credentials or live
clients, so they can cross process boundaries and be serialized in audit data.
