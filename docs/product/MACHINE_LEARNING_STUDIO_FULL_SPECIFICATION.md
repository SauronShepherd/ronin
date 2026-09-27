# Machine Learning Studio — Full Functional, Architectural and Technical Specification

**Status:** Implemented and operational within the provider-neutral scope defined by Ronin
**Version:** 1.0
**Plugin ID:** `com.sauronshepherd.ronin.ml-studio`
**Display name:** Machine Learning Studio
**Canonical package:** `studio_ml`
**Primary contracts:** `ronin.ml-lab/v1`, `ronin.ml-pipeline-ir/v1`, `ronin.ml-backend/v1`, `ronin.ml-remote-adapter/v1`

## 1. Purpose and scope

Machine Learning Studio (MLS) is Ronin's open-source, local-first workspace for
classical machine learning. It lets users define reproducible experiments,
profile and validate tabular data, train local models, compare trials, register
artifacts, promote model versions, score new rows, and inspect provenance.

The module intentionally separates the ML domain from any particular execution
library. Scikit-learn is the first local implementation, but the Lab, registry,
artifact and API contracts do not depend on scikit-learn. A deployment can replace
the implementation with another local library or a remote provider adapter while
preserving the same Lab and model lifecycle.

### In scope

- Classification and regression over numeric tabular features.
- Unsupervised clustering with deterministic K-Means.
- Local classical algorithms: logistic regression, linear regression, decision
  trees, random forests and gradient boosting.
- Deterministic training, validation, quality gates and bounded search.
- Grid, random and bounded Bayesian-style trial comparison.
- Content-addressed model artifacts and immutable provenance.
- Model registry, candidate/champion promotion, model cards and batch scoring.
- Capability discovery and provider-neutral local/remote backend contracts.
- Ronin plugin discovery, permissions, HTTP routes and browser UI.
- Local asynchronous execution through the Ronin execution coordinator.

### Explicit non-goals

- Deep learning, GPU orchestration or notebook replacement.
- Silent upload of datasets or credentials to external providers.
- Treating an arbitrary pickle or executable model file as a safe default.
- Claiming that an MLflow or Spark server exists merely because an adapter is
  installed. Provider URLs, credentials and endpoint semantics remain deployment
  configuration.

## 2. Product concepts

MLS uses separate entities so that an experiment definition, an execution and an
operational model cannot be confused.

| Entity | Meaning | Mutability |
|---|---|---|
| Lab | Reproducible experiment definition | Versioned; a run captures an immutable snapshot |
| Dataset reference | Governed asset and revision used as input | Immutable reference |
| Run | One execution of a Lab | Append-only lifecycle |
| Trial | One parameter configuration evaluated inside a search | Immutable evidence |
| Artifact | Content-addressed bytes produced by a backend | Immutable |
| Registered model | Stable logical model name | Mutable catalogue metadata |
| Model version | Artifact plus signature, provenance and evidence | Immutable |
| Stage | Candidate, champion or archived lifecycle state | Controlled transition |
| Deployment | Runtime consumer of a selected model version | External/operational reference |

The minimum promotion path is:

```text
Lab draft -> validated Lab -> Run -> Trial(s) -> Artifact
       -> Registered model version (candidate) -> evaluation evidence
       -> champion -> batch/online consumer
```

## 3. User experience

The UI exposes a new `Machine Learning Studio` section in the Ronin shell.

### 3.1 Lab designer

The designer supports:

1. Lab ID, name, project and description.
2. Workspace and dataset asset/revision selection.
3. Task selection: classification, regression or clustering.
4. Target selection for supervised tasks.
5. Ordered feature selection and ignored-column handling.
6. Backend selection based on capability discovery.
7. Seed, test fraction and algorithm parameters.
8. Quality/profile execution before training.
9. Explicit run and compare actions.

The UI may provide a guided baseline, but every implicit default is visible in
the resulting Lab and run evidence. Advanced users can inspect and export the
canonical JSON representation.

### 3.2 Experiment and comparison views

The comparison view displays:

- trial parameters;
- primary and secondary metrics;
- direction of optimization;
- deterministic ranking and tie breaking;
- failed, pruned and completed trials;
- runtime and artifact references where available.

Search is bounded by `max_trials`, a deterministic seed and a declared parameter
space. The optimizer cannot silently change the metric or validation policy.

### 3.3 Registry and model card

The registry view lists model IDs, versions and stages. A model card includes:

- model and version identity;
- framework/backend and artifact schema;
- input and output signature;
- source run and execution reference;
- dataset and revision references;
- artifact reference and SHA-256 digest;
- effective parameters and metrics;
- limitations and evaluation evidence;
- current stage.

Promotion requires an explicit reason and is an atomic registry transition.

### 3.4 Scoring

The scoring form accepts a registered model ID/version and rows. The server:

1. resolves the registered version;
2. loads the artifact from the artifact store or accepts an explicitly supplied
   base64 artifact for controlled local use;
3. verifies the artifact digest;
4. validates the feature signature and row limit;
5. dispatches to the declared artifact decoder;
6. returns predictions without executing untrusted code.

For K-Means, predictions are integer cluster assignments. For supervised models,
predictions are labels or numeric values according to the model signature.

## 4. Functional requirements

### 4.1 Lab lifecycle

- A Lab must have a unique ID in its workspace.
- A Lab must reference a governed dataset asset/revision.
- Feature names must be unique.
- A supervised target must not also be a feature.
- Clustering Labs must not define a target.
- `test_fraction` must be strictly between zero and one.
- A run must capture the Lab definition and source revision used at execution.
- Unsupported task/backend/algorithm combinations fail before training.

### 4.2 Quality and data validation

The quality service profiles rows and validates:

- required columns;
- missing values;
- numeric convertibility;
- target presence and cardinality;
- empty datasets;
- feature/target collisions;
- task-specific minimums.

The result contains deterministic profile metadata, failures, warnings and a
pass/fail decision. A failed quality gate prevents training and is retained as
run evidence.

### 4.3 Training

Training is deterministic when the backend and algorithm support the declared
seed. It must return:

- task and algorithm;
- effective hyperparameters;
- feature and output signatures;
- metrics;
- canonical artifact bytes;
- artifact schema/version;
- provenance metadata.

The request path never performs unbounded training in the HTTP server thread.
Training runs through the local coordinator or a remote adapter.

### 4.4 Search and optimization

Supported search modes are:

- `single`: one explicit configuration;
- `grid`: Cartesian product of bounded values;
- `random`: deterministic sampling with a seed;
- `bayesian`: bounded discrete surrogate/expected-improvement proposals.

Every search declares metric, direction, maximum trials, seed and parameter
space. Duplicate trial parameter signatures are rejected or skipped
deterministically. Results are rankable and exportable.

### 4.5 Registry and artifact governance

Artifacts are content-addressed and immutable. A registered model version stores
the artifact reference and digest, but not arbitrary executable state. Registry
operations are workspace-scoped and auditable.

Allowed stage transitions are:

```text
candidate -> champion
candidate -> archived
champion  -> archived
```

Promotion must not mutate the bytes of an existing version. Champion resolution
returns exactly one current champion or a typed not-found error.

## 5. Logical architecture

```text
Ronin UI shell
  -> HTTP/plugin route surface
Machine Learning Studio plugin
  -> domain and Lab services
  -> quality/profile service
  -> backend registry and capability gate
  -> local execution coordinator
  -> tracking/registry application services
  -> artifact store and model scoring
Backends
  -> local.sklearn-compatible implementation
  -> JSON remote adapter boundary
  -> MLflow/Spark provider descriptors
Ronin host
  -> workspace/catalog and authorization
  -> execution/job runtime
  -> artifact storage
  -> audit and plugin lifecycle
```

### 5.1 Package responsibilities

| Module | Responsibility |
|---|---|
| `studio_ml.domain` | Lab, feature and task invariants |
| `studio_ml.services` | Lab storage/application operations |
| `studio_ml.quality` | Profiling and quality gates |
| `studio_ml.runtime` | Canonical supervised training and prediction |
| `studio_ml.clustering` | Dependency-light K-Means fitter, inertia and prediction |
| `studio_ml.backends` | Capabilities, contexts, registry and backend protocols |
| `studio_ml.runner` | Capability-gated local experiment execution |
| `studio_ml.orchestration` | Async queued/running/succeeded/failed/cancelled lifecycle |
| `studio_ml.optimization` | Search spaces, trials and deterministic ranking |
| `studio_ml.provenance` | Immutable ML run records |
| `studio_ml.service` | Registry, artifact persistence and verified inference |
| `studio_ml.remote` | Remote lifecycle and JSON transport adapters |
| `studio_ml.plugin` | Manifest, permissions and HTTP/plugin route handlers |
| `web/js/features.js` | Machine Learning Studio UI behavior |

The plugin depends on Ronin contracts and ports, not on private implementation
details of another plugin. Optional third-party libraries remain behind backend
boundaries.

## 6. Backend abstraction

### 6.1 Capability discovery

Each backend declares a stable ID and capabilities:

```json
{
  "backend_id": "local.sklearn",
  "display_name": "Local scikit-learn",
  "tasks": ["classification", "regression", "clustering"],
  "algorithms": [
    "logistic_regression", "linear_regression",
    "decision_tree_classifier", "decision_tree_regressor",
    "random_forest_classifier", "random_forest_regressor",
    "gradient_boosting_classifier", "gradient_boosting_regressor", "kmeans"
  ],
  "supports_prediction": true,
  "supports_artifacts": true,
  "supports_explainability": false
}
```

The capability gate is advisory for discovery but authoritative before execution:
the backend still validates the request and returns a typed failure for an
unsupported pair.

### 6.2 Training and prediction contexts

`TrainingContext` carries workspace, dataset, run and artifact namespace
references. `PredictionContext` carries model identity, expected features and
row limits. Neither context contains credentials or live clients; both are safe
to serialize into audit data.

The `MLBackend` contract requires a stable `backend_id`, capabilities and a
training operation. Optional adapters additionally expose prediction, polling,
cancellation and inspection operations.

### 6.3 Remote adapters

The remote contract models:

```text
submit(request) -> remote run reference
poll(run reference) -> status/artifact result
cancel(run reference) -> terminal/cancellation status
predict(model reference, rows) -> predictions
```

`RemoteExecutionController` retries transient submit errors according to a
bounded policy. Configuration, validation and capacity errors are not retried.
`JsonRemoteBackend` maps a transport-neutral JSON protocol into the backend
contract. MLflow and Spark adapters provide declared provider identities and
capabilities; the actual base URL, authentication and endpoint semantics are
deployment configuration.

## 7. Canonical artifacts

### 7.1 General rules

An artifact is canonical JSON when a declarative representation is available.
Serialization uses stable key ordering and compact encoding. Its SHA-256 digest
is recorded in the run and registry. Artifact decoders validate schema, task,
algorithm, feature metadata and parameter types before prediction.

Pickle is not the default artifact format and is not loaded by the canonical
local predictor.

### 7.2 Supervised artifacts

Supported artifact families include:

- `logistic_regression` with coefficients, intercept, classes and feature list;
- `linear_regression` with coefficients and intercept;
- decision tree artifacts with child indices, split features, thresholds and
  leaf values;
- random forest artifacts containing declarative tree ensembles and aggregation
  metadata;
- gradient boosting artifacts containing stages, learning rate, initialization,
  class metadata and declarative trees.

### 7.3 K-Means artifact

Canonical identifier: `ronin.ml-kmeans/v1`.

```json
{
  "schema": "ronin.ml-kmeans/v1",
  "algorithm": "kmeans",
  "centroids": [[0.05], [9.95]],
  "iterations": 3
}
```

The predictor converts input rows to numeric feature vectors and assigns the
nearest centroid using deterministic squared Euclidean distance. Ties resolve to
the lowest centroid index. The run records inertia and the registry signature
declares an integer `cluster` output.

## 8. API and plugin surface

The plugin manifest declares the `ml-studio` UI entry and permissions:

- `ml-studio:read`;
- `ml-studio:write`;
- `ml-studio:execute`.

Representative routes are:

| Method | Route | Purpose |
|---|---|---|
| GET | `/v1/ml-studio/backends` | Discover backend capabilities |
| GET/POST | `/v1/ml-studio/labs` | List/create Labs |
| GET | `/v1/ml-studio/labs/{lab_id}` | Read a Lab |
| POST | `/v1/ml-studio/labs/{lab_id}/compile` | Compile/validate Lab |
| POST | `/v1/ml-studio/labs/{lab_id}/quality` | Profile and validate rows |
| POST | `/v1/ml-studio/labs/{lab_id}/runs` | Run a Lab synchronously |
| POST | `/v1/ml-studio/labs/{lab_id}/executions` | Submit async execution |
| GET | `/v1/ml-studio/executions/{run_id}` | Read execution status |
| POST | `/v1/ml-studio/executions/{run_id}/cancel` | Cancel execution |
| POST | `/v1/ml-studio/labs/{lab_id}/compare` | Rank supplied trials |
| POST | `/v1/ml-studio/labs/{lab_id}/search` | Execute bounded search |
| GET | `/v1/ml-studio/models` | List registered models |
| POST | `/v1/ml-studio/models/{model_id}/{version}/promote` | Promote a candidate |
| POST | `/v1/ml-studio/models/{model_id}/{version}/predict` | Verify and score rows |
| GET | `/v1/ml-studio/models/{model_id}/{version}/card` | Return model card |

Dynamic plugin routes are registered by the plugin host; core OpenAPI route
consistency checks cover the host's static surface, while plugin contracts
document the dynamic ML routes.

## 9. Persistence and provenance

The durable composition provides:

- Lab store backed by SQLite or the configured storage port;
- execution store with reopenable lifecycle snapshots;
- ML registry for experiments, runs, models and evaluations;
- local content-addressed artifact store;
- workspace-scoped authorization and audit context.

Every run records, at minimum:

- run and experiment IDs;
- execution reference and source revision;
- dataset asset/revision;
- task, algorithm and effective parameters;
- metrics;
- artifact references/digests;
- backend identity;
- feature and output signatures where applicable.

Rows and secrets are not copied into provenance records unless an explicitly
scoped artifact policy permits it.

## 10. Security requirements

- All routes enforce workspace and permission checks.
- Dataset references are identifiers, not arbitrary filesystem paths.
- Artifact references are content-addressed and verified before inference.
- Canonical predictors reject malformed, unsupported or incompatible artifacts.
- Row limits bound prediction memory use.
- Remote URLs and headers are supplied through deployment configuration, never
  persisted in Lab manifests.
- Secrets are not included in model cards, run parameters or UI payloads.
- Untrusted executable artifacts require an explicit isolated runtime policy.
- Plugin registration rejects duplicate IDs, routes, commands and capabilities.
- Cancellation is idempotent and does not erase completed evidence.

## 11. Execution state machine

```text
queued -> running -> succeeded
                  -> failed
                  -> cancelled
queued -> cancelled
```

Submission is idempotent by `run_id`. A terminal persisted snapshot is returned
instead of starting a duplicate execution. The local coordinator uses bounded
worker concurrency. A remote adapter maps provider states into the same terminal
contract.

## 12. Testing and release gates

The implementation is covered by:

- domain and contract tests;
- SQLite persistence/reopen tests;
- backend capability and duplicate-registration tests;
- quality-gate tests;
- runtime and canonical-artifact security tests;
- decision tree, random forest, gradient boosting and K-Means tests;
- remote protocol, retry, transport and provider-adapter tests;
- plugin route/permission/observability tests;
- registry, promotion, model-card and scoring tests;
- async coordinator lifecycle tests;
- browser audit across nine shell routes, including Machine Learning Studio.

Recommended release commands:

```powershell
python -m pytest -q tests -k ml
ruff check python/studio_ml
python -m json.tool api/openapi-v1.json > $null
python tools/route_consistency.py
python tools/browser_audit.py http://127.0.0.1:8765/
python -m pytest -q
```

Environment-dependent tests may be skipped when Docker, PostgreSQL, symlink
privileges or external provider endpoints are unavailable. Such skips must be
reported explicitly and must not be counted as passing evidence for that
environment.

## 13. Operations

### Local startup

The standard Ronin local composition wires the Lab store, execution store,
registry and local artifact store. The plugin is discovered through the Python
entry point and contributes its manifest, routes and UI entry.

### Observability

Operators should monitor:

- queued/running/failed execution counts;
- training duration and row counts;
- artifact size and digest failures;
- quality-gate failure rates;
- backend capability or capacity errors;
- scoring latency and rejected input counts;
- remote retry and cancellation rates.

Telemetry must avoid raw row values and secret material.

### Recovery

- Reopen the durable execution store to recover terminal snapshots.
- Re-submit an idempotent run ID only when the existing snapshot is absent.
- Never overwrite an artifact at an existing digest.
- Resolve the registered model version by digest before re-serving it.
- Archive invalid candidates rather than deleting provenance.

## 14. Extension guide

To add a new backend:

1. Implement the backend protocol and stable `backend_id`.
2. Declare exact tasks, algorithms, artifact safety and prediction support.
3. Validate every request independently of discovery metadata.
4. Produce a versioned, serializable artifact contract.
5. Implement digestable artifacts and verified prediction.
6. Add capability, training, prediction, failure and security tests.
7. Register the backend explicitly in composition.
8. Document dependency/licensing and deployment requirements.

To add an algorithm to the local backend:

1. Add it to the capability declaration only when implementation is complete.
2. Define its `TrainingSpec` validation rules.
3. Define artifact encoding and strict decoding.
4. Add metrics and task-specific quality requirements.
5. Add deterministic and malformed-artifact tests.
6. Update the Lab/UI algorithm selector and model-card limitations.
7. Update the status matrix and contract documentation.

To add a UI workflow:

1. Add a permission-aware plugin route or consume an existing route.
2. Keep state in canonical API payloads, not browser-only state.
3. Add loading, empty, error and success states.
4. Add browser selectors to the audit harness.
5. Check focus order, no horizontal overflow and console cleanliness.

## 15. Compatibility and versioning

Contract identifiers are versioned independently:

- `ronin.ml-lab/v1` — Lab shape and invariants;
- `ronin.ml-pipeline-ir/v1` — compiled pipeline representation;
- `ronin.ml-backend/v1` — backend capability and training boundary;
- `ronin.ml-remote-adapter/v1` — remote lifecycle and error mapping;
- `ronin.ml-kmeans/v1` — K-Means artifact;
- `ronin.ml-model-card/v1` — model-card payload.

Adding optional fields or capabilities is backward-compatible. Changing the
meaning of an existing field, task, artifact schema or stage transition requires
a new contract version or an explicit migration. A backend ID is a routing key
and must remain stable across compatible releases.

## 16. Current implementation statement

The module is complete within the provider-neutral scope: local classical ML,
deterministic K-Means, backend abstraction, remote adapter contracts, durable
registry/artifacts, scoring, UI, asynchronous execution, tests and documentation
are implemented and verified. A concrete MLflow, Spark or managed-service URL is
deployment configuration and is intentionally not hard-coded into the open-source
plugin.

## 17. Product improvement roadmap

The following improvements extend the completed core. They are intentionally
separated from the current implementation statement and should be delivered as
versioned increments with their own contracts and acceptance tests.

### 17.1 Additional classical algorithms

Add the following algorithms behind the existing capability gate:

- Support Vector Classification and Regression (`svm_classifier`, `svm_regressor`),
  including kernel, C, gamma, epsilon and probability calibration policies.
- k-Nearest Neighbours classification/regression (`knn_classifier`,
  `knn_regressor`), including distance metric, weighting and deterministic tie
  breaking.
- Naive Bayes variants for text/count and continuous numeric inputs.
- PCA and Truncated SVD as first-class unsupervised transformation nodes.
- Elastic Net, Ridge and Lasso for regularized linear baselines.
- Isolation Forest and Local Outlier Factor for anomaly detection.

Each addition must provide a declarative artifact or explicitly declare why a
loader is required, publish capabilities, define feature constraints, expose
effective hyperparameters in the model card and include malformed-artifact and
prediction-equivalence tests.

### 17.2 Production provider integrations

Turn the provider-neutral remote adapters into optional, tested integrations:

- MLflow Tracking and Model Registry adapter with experiment/run mapping,
  artifact URI handling, stage/tag mapping and server capability probing.
- Spark ML adapter with explicit Spark Connect or REST transport, serialized
  PipelineModel handling and cluster resource declarations.
- XGBoost/LightGBM adapters with license/dependency qualification and safe
  artifact policies.
- Optional managed-service adapters for providers selected by the deployment,
  never enabled implicitly by the local plugin.

Each provider integration must define authentication injection, timeout and
retry policy, idempotency behavior, cancellation semantics, rate-limit handling,
network egress policy, data residency implications and a provider-specific E2E
test suite. A provider adapter is not release-ready until a real qualification
environment has passed; mocked JSON transport tests alone are insufficient.

### 17.3 Advanced clustering and unsupervised workflows

Extend K-Means into a complete unsupervised workflow:

- K-Means++ initialization and multiple deterministic restarts.
- MiniBatch K-Means for bounded large datasets.
- DBSCAN and HDBSCAN-style density clustering where dependencies permit.
- Agglomerative clustering with linkage and distance policies.
- Gaussian mixture models with covariance and convergence diagnostics.
- Cluster evaluation using silhouette, Calinski-Harabasz and Davies-Bouldin
  metrics.
- Automatic cluster-count search with a declared selection metric.
- Cluster profile tables showing feature distributions and representative rows.
- Model-card limitations for unstable or non-predictive clustering models.

Unsupervised Labs must support a no-target pipeline, registered cluster models,
batch scoring, cluster-label stability checks and an explicit policy for centroid
or cluster-ID changes between retraining runs.

### 17.4 Data preparation and connector expansion

Add reusable, inspectable preparation nodes for:

- typed casts and schema normalization;
- missing-value strategies and missingness indicators;
- categorical encoding and unknown-category policy;
- scaling, normalization and robust transformations;
- date/time extraction and timezone policy;
- text tokenization, n-grams and sparse matrix limits;
- outlier clipping and winsorization;
- leakage detection and post-target feature exclusion;
- class rebalancing and sampling policy.

Add governed connectors for Parquet, SQL databases, object storage and streaming
snapshots. Every connector must return an `AssetRef`, schema fingerprint, row
count policy and reproducible revision identifier. The UI must show connector
permissions and never expose raw credentials in Lab JSON.

### 17.5 Rich visual analytics

Add an analysis layer that is optional and bounded by privacy policy:

- distributions, missingness and cardinality charts;
- target balance and train/test split diagnostics;
- correlation and multicollinearity views;
- confusion matrix, ROC/PR curves and calibration plots;
- residual, predicted-vs-actual and error-segment views;
- feature importance and permutation importance where supported;
- partial dependence or equivalent explainability with capability declarations;
- 2D/3D PCA or UMAP projections for exploration;
- clustering scatter plots and centroid/profile overlays.

Charts must be derived from governed aggregates or sampled data, record the
sampling policy and preserve the same run/artifact provenance as numeric metrics.

### 17.6 Experiment governance and collaboration

Add collaborative product capabilities inspired by mature visual ML platforms:

- Lab branches and mergeable experiment definitions;
- comments and review decisions on runs and model cards;
- approval policies before champion promotion;
- reusable Lab templates and organization-level defaults;
- comparison dashboards across projects and time windows;
- export to Markdown, JSON, CSV and signed evidence bundles;
- scheduled retraining with approval gates;
- champion/challenger evaluation and rollback references.

These features must preserve the distinction between mutable collaboration
metadata and immutable run/artifact evidence.

### 17.7 Drift, monitoring and retraining

Implement operational monitoring as a policy-driven extension:

- feature and prediction distribution drift;
- schema and missingness drift;
- target/performance drift when labels arrive later;
- segment-level drift and fairness checks;
- alert thresholds with warning/failure severity;
- retraining recommendations linked to a Lab version;
- champion/challenger shadow scoring;
- model health dashboards and retention policies.

Monitoring must not automatically retrain or promote a model without an explicit
authorization policy. Raw production rows must remain outside ordinary telemetry.

### 17.8 Performance and scale

Add performance engineering in measured increments:

- streaming dataset scans rather than loading all rows in memory;
- artifact streaming and checksum verification during transfer;
- bounded parallel trial execution;
- cache keys for immutable dataset/profile/preparation stages;
- warm backend processes for repeated trials;
- sparse matrix support and feature-count limits;
- large-artifact compression and retention policies;
- benchmark suites for 10K, 100K and 1M-row representative datasets.

Every optimization must preserve deterministic seeds, artifact digests and
provenance. Benchmark results should be stored as release evidence rather than
used as unbounded performance claims.

### 17.9 CI, qualification and release hardening

Extend the current test matrix with:

- PostgreSQL registry and artifact-store qualification;
- real Docker worker execution and cancellation;
- provider integration qualification jobs;
- browser E2E against a live Ronin composition, not only static UI hosting;
- dependency/license and vulnerability scans for optional ML extras;
- compatibility tests across supported Python and scikit-learn versions;
- property-based artifact decoder tests;
- load tests for concurrent runs and scoring;
- migration tests for every contract version.

The release gate should publish a machine-readable evidence bundle containing
test counts, skipped-test reasons, lint/type results, browser audit output,
route consistency, artifact contract versions and dependency fingerprints.
