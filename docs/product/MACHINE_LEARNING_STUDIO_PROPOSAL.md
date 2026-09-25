# Machine Learning Studio — propuesta de producto y arquitectura

**Estado:** propuesta objetivo para el plugin open-source de Ronin  
**Versión:** 0.2  
**Fecha:** 2026-09-19  
**Ámbito:** machine learning clásico, tabular y local-first; no sustituye notebooks ni pretende ser una plataforma de deep learning en la primera versión.

## 1. Resumen ejecutivo

Machine Learning Studio (MLS) será un plugin vertical de Ronin para diseñar, ejecutar, comparar, documentar y operar experimentos de machine learning clásico. La experiencia principal será un **Lab**: un espacio reproducible que conecta datasets versionados, preparación de datos, definición de features, tareas de predicción o clustering, ejecuciones, métricas, artefactos, evaluaciones y modelos registrados.

La UI debe ofrecer una ruta visual de baja fricción, parecida a los mejores conceptos de Dataiku —Flow, Visual ML, comparación de modelos, despliegue del modelo guardado y retraining— pero con un núcleo más pequeño y explícitamente vendor-neutral. La ejecución no se acoplará a scikit-learn. El contrato público será `MLBackend`; la primera implementación será `local.sklearn`, ejecutada en un worker local y produciendo artefactos portables no ejecutables por defecto. En el futuro podrán existir `local.sparkml`, `local.xgboost`, `remote.ronin`, `mlflow.adapter` o adaptadores de servicios administrados sin cambiar los manifiestos de los labs.

El objetivo no es esconder la complejidad científica. MLS debe convertirla en decisiones visibles y auditables: qué datos entraron, cómo se dividieron, qué transformaciones se aplicaron, qué métrica se optimizó, qué restricciones se respetaron, qué versión de código y entorno se usó y por qué un modelo fue promovido.

## 2. Decisiones de producto

### 2.1 La unidad de trabajo es el Lab

Un Lab es una definición versionada, no una sesión efímera de navegador. Contiene:

1. Identidad, nombre, descripción, owner y etiquetas.
2. Dataset de entrada y revisiones concretas.
3. Esquema observado y contrato esperado.
4. Preparación reproducible.
5. Task ML: prediction, clustering o ranking futuro.
6. Lista de modelos candidatos y espacios de búsqueda.
7. Estrategia de split y validación.
8. Métrica primaria, métricas secundarias y restricciones.
9. Perfil de runtime.
10. Política de calidad, fairness y aceptación.
11. Historia de ejecuciones y modelo champion opcional.

La UI puede crear una definición desde un asistente, pero debe guardar siempre el JSON canónico. El usuario debe poder exportarlo, versionarlo y revisarlo en Git.

### 2.2 Lab, Run, Trial, Model Version y Deployment no son sinónimos

- **Lab:** intención reproducible y configuración.
- **Run:** una ejecución de un Lab con snapshots concretos.
- **Trial:** una variante de hiperparámetros dentro de un Run.
- **Model artifact:** bytes inmutables producidos por un backend.
- **Registered model:** nombre estable que agrupa versiones.
- **Model version:** artifact + signature + evidencia + stage.
- **Deployment:** una referencia operativa a una versión, batch o endpoint.

Esta separación evita el error común de tratar “el mejor score de una tabla” como un modelo operable.

### 2.3 Local-first, portable-by-default

La ruta inicial debe funcionar con una instalación local y sin credenciales cloud. La dependencia opcional de ML debe aislarse en el extra `ml`. Las tareas pesadas se ejecutan mediante el runtime de jobs de Ronin; el request HTTP nunca entrena en el hilo del servidor.

La portabilidad se consigue guardando:

- manifiesto del Lab;
- snapshot de dataset y schema fingerprint;
- source revision;
- runtime snapshot y dependencias;
- parámetros y semillas;
- métricas y plots;
- artifact digest;
- signature de entrada/salida;
- versión de contrato del backend.

## 3. Hallazgos de la investigación y decisiones derivadas

### 3.1 Pasada 1 — Dataiku Flow y Visual ML

Dataiku separa el diseño y exploración del modelo en un Lab de su despliegue al Flow como Saved Model, acompañado por una receta de entrenamiento que permite retraining. También presenta el proyecto como un grafo de datasets, recetas y modelos. MLS adopta la separación `Lab -> Registered Model -> Deployment`, pero con un DAG explícito y portable, no con una representación propietaria.

**Decisión:** el modelo no se considera “production-ready” al finalizar el entrenamiento. Debe pasar evaluación y promoción.

### 3.2 Pasada 2 — MLflow Tracking y Registry

MLflow organiza runs, parameters, metrics, artifacts, experiments y modelos, y requiere un store persistente para integrar tracking con registry. MLS adopta esas entidades, pero las enlaza a `AssetRef`, `ProjectId`, `ExecutionRef` y `ArtifactStore` de Ronin para que la gobernanza no dependa de MLflow.

**Decisión:** el tracking nativo es un port de Ronin; MLflow será un adaptador, no el dominio.

### 3.3 Pasada 3 — Kubeflow Pipelines

KFP demuestra que una pipeline debe separar parámetros pequeños, artifacts, componentes, control de flujo, caché, retries y recursos. El concepto es útil aunque MLS no necesite Kubernetes. La pipeline de MLS debe compilar a un IR interno con nodos tipados y edges por artifacts.

**Decisión:** cada paso de preparación, profiling, train, evaluate y register es un `NodeSpec`; el backend de ejecución decide si se ejecuta en proceso, subprocess, contenedor o worker remoto.

### 3.4 Pasada 4 — Metaflow

Metaflow distingue parámetros de ejecución, configuración de despliegue y artifacts persistidos. Esto evita que una opción operativa se mezcle con el resultado de un paso. MLS separará `LabConfig`, `RunParameters` y `ProducedArtifact`.

**Decisión:** no serializar objetos Python arbitrarios como configuración; todo input público debe tener schema y digest.

### 3.5 Pasada 5 — DVC Experiments

DVC aporta la idea de experimentar sin llenar el repositorio con ramas o copias y de comparar params, metrics, plots, datasets y modelos. MLS conservará el vínculo al source revision y permitirá exportar resultados a archivos estándar, pero no asumirá que Git es el único store.

**Decisión:** toda comparación debe poder exportarse a JSON/CSV/Markdown; cada ejecución tendrá `comparison_key` y filtros reproducibles.

### 3.6 Pasada 6 — Calidad y contratos de datos

Great Expectations usa Expectations, Suites, Batches, Validations y Checkpoints reutilizables. MLS necesita una versión ligera y nativa: `DataContract`, `ExpectationSuite`, `ValidationRun` y `QualityGate`. La validación debe ejecutarse antes de training y opcionalmente antes de scoring.

**Decisión:** la calidad es una condición de ejecución declarativa, no una pestaña decorativa. Un gate `failure` detiene el Run; `warning` deja evidencia pero permite continuar si la política lo autoriza.

### 3.7 Pasada 7 — Optimización de hiperparámetros

Optuna separa Study, Trial, Sampler y Pruner, y permite cortar trials poco prometedores. MLS debe exponer esa misma separación en el contrato, pero empezar con grid/random deterministas y un adapter Optuna opcional.

**Decisión:** el optimizador nunca decide silenciosamente la métrica. El Lab declara objetivo, dirección, límites, presupuesto, seed, concurrencia y regla de desempate.

### 3.8 Pasada 8 — Drift y observabilidad

Evidently muestra la diferencia entre un reporte exploratorio y una suite operacional de drift. MLS debe guardar distributions y checks sin convertir todos los snapshots en datos personales. Drift es evidencia para una decisión de retraining, no una orden automática.

**Decisión:** `DriftPolicy` puede abrir un `RetrainingRecommendation`; sólo un scheduler autorizado crea el Run.

### 3.9 Pasada 9 — Seguridad de artefactos y plugins

El contrato de plugin de Ronin distingue entry points confiables de workers aislados. Un modelo serializado con pickle puede ejecutar código al cargarlo. Por eso el backend debe declarar `artifact_safety`; el runtime debe preferir formatos declarativos y cargar modelos sólo en un worker con allowlist.

**Decisión:** prohibir pickle como formato predeterminado de publicación. Si un backend lo necesita, el artifact queda marcado `executable_untrusted`, requiere perfil aislado y no puede promoverse a serving sin una policy explícita.

### 3.10 Pasada 10 — UX de principiante y salida profesional

El asistente debe producir un baseline con pocas decisiones, pero permitir inspeccionar cada decisión y editar el JSON avanzado. Un usuario experto debe poder exportar la pipeline y sustituir nodos por código. La UX se divide en `Guided`, `Compare`, `Inspect` y `Operate`.

**Decisión:** ningún valor automático se oculta: split, imputación, encoding, seed, scoring, filas descartadas y warnings aparecen en la evidencia del Run.

## 4. Arquitectura lógica

```text
UI shell
  ├─ Lab designer
  ├─ Flow graph
  ├─ Dataset profile / quality
  ├─ Experiment comparison
  ├─ Model card / promotion
  └─ Scoring / drift
        │ HTTP contracts
ML Studio plugin
  ├─ application services
  ├─ domain models and state machines
  ├─ backend registry
  ├─ pipeline compiler
  ├─ tracking and registry ports
  ├─ quality and policy ports
  └─ route/job/event contributions
        │ host contracts only
Ronin core
  ├─ workspace/project/catalog
  ├─ artifact store
  ├─ job scheduler and worker broker
  ├─ runtime profiles
  ├─ authorization/audit
  └─ plugin lifecycle
```

### 4.1 Dependencias permitidas

`studio_ml` puede depender de `studio_core`, `studio_storage`, `studio_orchestrator`, `studio_execution` y contratos del host. No puede importar implementaciones privadas de otro plugin. Los adaptadores de scikit-learn, Optuna, MLflow, Spark o XGBoost viven debajo de `studio_ml.backends.*` o en plugins separados.

### 4.2 Puertos principales

```python
class MLBackend(Protocol):
    backend_id: str
    contract_version: str

    def capabilities(self) -> BackendCapabilities: ...
    def validate(self, request: TrainingRequest) -> ValidationReport: ...
    def train(self, context: TrainingContext) -> TrainingResult: ...
    def predict(self, context: PredictionContext) -> PredictionResult: ...
    def inspect(self, artifact: ArtifactRef) -> ModelInspection: ...

class DatasetReader(Protocol):
    def schema(self, ref: AssetRef) -> DatasetSchema: ...
    def sample(self, ref: AssetRef, limit: int) -> TableSample: ...
    def scan(self, ref: AssetRef, projection: tuple[str, ...]) -> RowStream: ...

class ExperimentStore(Protocol):
    def put_lab(...): ...
    def put_run(...): ...
    def put_trial(...): ...
    def compare_runs(...): ...

class ModelRegistry(Protocol):
    def register(...): ...
    def promote(...): ...
    def resolve_stage(...): ...

class QualityEvaluator(Protocol):
    def validate(self, suite: ExpectationSuite, dataset: AssetRef) -> ValidationResult: ...
```

El protocolo debe ser capability-based: un backend que no soporta clustering no se registra como si lo soportara. `BackendCapabilities` declara tasks, data types, sparse support, probability output, incremental fit, explainability, native artifact safety y resource needs.

## 5. Dominio y esquemas canónicos

### 5.1 Lab manifest

```json
{
  "schema": "ronin.ml-lab/v1",
  "id": "churn-lab",
  "name": "Customer churn baseline",
  "project_id": "crm",
  "backend": {"id": "local.sklearn", "constraint": ">=1,<2"},
  "input": {
    "dataset": {"asset_id": "customers", "revision": "sha256:..."},
    "target": {"column": "churn", "task": "classification"},
    "features": [{"column": "age", "role": "numeric"}, {"column": "country", "role": "categorical"}]
  },
  "preparation": {
    "missing": {"numeric": "median", "categorical": "most_frequent"},
    "categorical": {"encoding": "one_hot", "handle_unknown": "ignore"},
    "scaling": "standard"
  },
  "validation": {
    "strategy": "stratified_random",
    "test_fraction": 0.2,
    "cv_folds": 5,
    "seed": 17
  },
  "candidates": [
    {"algorithm": "logistic_regression", "parameters": {"C": [0.1, 1.0, 10.0]}},
    {"algorithm": "random_forest", "parameters": {"n_estimators": [100, 300]}}
  ],
  "objective": {"metric": "roc_auc", "direction": "maximize", "min_value": 0.75},
  "quality_suite": "customer-training-v1",
  "runtime": {"profile_id": "local-cpu-small", "timeout_seconds": 1800},
  "policy": {"allow_network": false, "allow_untrusted_artifacts": false}
}
```

Rules: exact keys at public boundaries, canonical JSON ordering, no secrets, bounded strings/arrays, finite numeric values, explicit nulls, schema version required, and unknown fields rejected in v1.

### 5.2 Run state machine

```text
created -> queued -> preparing -> validating -> training -> evaluating
        -> succeeded -> registered -> promoted

Any active state -> cancelling -> cancelled
Any active state -> failed
succeeded -> superseded (only by explicit replacement relation)
```

Every transition records actor, timestamp, reason, execution id and event id. Retries create attempts under the same Run; they do not overwrite metrics or artifacts.

### 5.3 Trial state machine

`pending -> running -> completed | failed | pruned | cancelled`. A pruned Trial is a valid result and must be distinguishable from failure. The optimizer can only finish when its budget, timeout or stopping condition is met.

### 5.4 Metrics

Metric names are namespaced: `train.loss`, `validation.roc_auc`, `test.accuracy`, `quality.missing_rate`, `fairness.tpr_gap`. Each metric includes value, split, step, higher-is-better, source, and optional threshold result. Never compare metrics with different split semantics without a warning.

## 6. Execution model

1. API validates the Lab and creates an idempotent Run.
2. Compiler resolves dataset revisions, backend, runtime and quality suite.
3. Compiler emits a frozen `PipelineIR`.
4. Scheduler submits nodes to the existing job/runner infrastructure.
5. Worker materializes only permitted inputs into an isolated work directory.
6. Each node writes structured result JSON and content-addressed artifacts.
7. Tracker records events and metrics incrementally.
8. Evaluator executes gates and generates model card evidence.
9. Registry registration is a separate transaction after successful evaluation.
10. Promotion requires an explicit authorized command or policy-approved automation.

### 6.1 PipelineIR

```json
{
  "schema": "ronin.ml-pipeline-ir/v1",
  "pipeline_id": "sha256:...",
  "nodes": [
    {"id":"profile","kind":"profile","inputs":["dataset"],"outputs":["profile.json"]},
    {"id":"quality","kind":"quality_gate","depends_on":["profile"]},
    {"id":"prepare","kind":"prepare","depends_on":["quality"]},
    {"id":"train-001","kind":"train","depends_on":["prepare"]},
    {"id":"evaluate-001","kind":"evaluate","depends_on":["train-001"]},
    {"id":"select","kind":"select","depends_on":["evaluate-001"]}
  ],
  "parameters": {"seed": 17, "backend_id": "local.sklearn"},
  "resource_policy": {"cpu": 2, "memory_mb": 4096, "timeout_seconds": 1800}
}
```

Node cache keys are `hash(node_kind, canonical_config, input_digests, runtime_digest, backend_version)`. A cache hit must still emit a `node_reused` event and reference the original evidence.

## 7. API surface

All routes are plugin routes and must be permission-mapped by the host.

### Labs

- `GET /v1/ml-studio/labs?workspace_id=&project_id=&cursor=&limit=`
- `POST /v1/ml-studio/labs`
- `GET /v1/ml-studio/labs/{lab_id}`
- `PUT /v1/ml-studio/labs/{lab_id}`
- `POST /v1/ml-studio/labs/{lab_id}/validate`
- `POST /v1/ml-studio/labs/{lab_id}/compile`
- `POST /v1/ml-studio/labs/{lab_id}/runs`

### Runs and trials

- `GET /v1/ml-studio/runs/{run_id}`
- `GET /v1/ml-studio/runs/{run_id}/events`
- `GET /v1/ml-studio/runs/{run_id}/metrics`
- `GET /v1/ml-studio/runs/{run_id}/trials`
- `POST /v1/ml-studio/runs/{run_id}/cancel`
- `POST /v1/ml-studio/runs/{run_id}/retry`
- `GET /v1/ml-studio/compare?run_ids=`

### Data and quality

- `POST /v1/ml-studio/profiles`
- `GET /v1/ml-studio/profiles/{profile_id}`
- `GET /v1/ml-studio/quality-suites`
- `POST /v1/ml-studio/quality-suites`
- `POST /v1/ml-studio/quality-suites/{suite_id}/validate`

### Backends and models

- `GET /v1/ml-studio/backends`
- `GET /v1/ml-studio/backends/{backend_id}/capabilities`
- `GET /v1/ml-studio/models`
- `POST /v1/ml-studio/models/{model_id}/versions`
- `GET /v1/ml-studio/models/{model_id}/versions/{version}`
- `POST /v1/ml-studio/models/{model_id}/versions/{version}/promote`
- `POST /v1/ml-studio/models/{model_id}/versions/{version}/score`

Every mutating request supports an idempotency key. Public list endpoints use bounded limits and opaque cursors. Errors use the host error envelope and never expose subprocess traces or credential material.

## 8. Persistence

The SQLite reference adapter should add migrations for:

- `ml_labs`: manifest JSON, schema, workspace/project, revision, status, timestamps.
- `ml_lab_versions`: immutable manifest versions and source revision.
- `ml_runs`: run identity, lab version, execution ref, state, attempt, runtime digest.
- `ml_trials`: trial parameters, state, objective, backend, started/finished times.
- `ml_metrics`: run/trial, name, value, split, step, threshold status.
- `ml_quality_suites`: suite JSON and version.
- `ml_validations`: suite, dataset revision, result JSON, status.
- `ml_models`: model id, owner, description, champion version.
- `ml_model_versions`: artifact ref/digest, signature, framework, stage, source run.
- `ml_deployments`: deployment target, model version, state, endpoint/batch config.
- `ml_drift_reports`: reference/current dataset, metric results, recommendation state.

Indexes: `(workspace_id, project_id, updated_at)`, `(lab_id, created_at)`, `(run_id, name, split)`, `(model_id, stage)`, unique `(idempotency_scope, idempotency_key)`. JSON is for immutable evidence and forward-compatible details; queryable identity and state fields remain columns.

## 9. UI information architecture

Navigation item: **Machine Learning Studio**.

Views:

1. **Labs** — cards/table, status, dataset revision, champion, last run.
2. **Lab overview** — Flow graph, quick actions, warnings and recent runs.
3. **Data** — schema, profile, sample, quality suite, leakage warnings.
4. **Prepare** — visual transformations with generated declarative spec.
5. **Task** — target, feature roles, split, metrics and constraints.
6. **Train** — candidate algorithms, search budget, backend and resources.
7. **Compare** — sortable metrics, confidence intervals, trial details, plots.
8. **Explain** — global importance, local explanation, limitations.
9. **Model card** — intended use, data, metrics, risks, owner and evidence.
10. **Operate** — promote, batch score, endpoint reference, drift and retraining.

The UI must render backend capabilities rather than hard-code algorithm lists. A backend can contribute a schema describing parameter widgets, validation rules and display labels. Any generated configuration has a “view JSON” and “copy as pipeline” action.

## 10. Security and safety

- Permission namespaces: `ml-studio:read`, `ml-studio:write`, `ml-studio:execute`, `ml-studio:promote`, `ml-studio:admin`.
- Dataset access is checked through workspace/catalog policy before a run is created.
- Secrets are SecretRefs only; backend config cannot contain credential values.
- Local execution defaults to network disabled, bounded CPU/RAM/time and a temporary workdir.
- Artifact loaders are allowlisted by backend and media type.
- User-supplied code is a separate capability and must run as isolated worker, never in the API process.
- Logs redact tokens, connection strings, row values and configured sensitive columns.
- Promotion records actor, reason, source run, evaluation and policy decision.
- Audit records include route invocation, run transitions, artifact writes and promotions.

## 11. Quality, fairness and leakage

The first quality layer should include row count, null rate, duplicate keys, type coercion, constant columns, target cardinality, class imbalance, train/test overlap, timestamp ordering and obvious target leakage heuristics. It should not claim to prove absence of leakage.

Optional fairness configuration names a sensitive column and groups, with metrics such as selection rate, TPR, FPR and absolute gaps. Fairness gates are warnings by default and failures only when the project policy explicitly requires it.

## 12. Observability and evidence

Every node emits start, progress, finish, warning and failure events. The evidence bundle contains:

- frozen Lab manifest;
- PipelineIR;
- dataset refs and fingerprints;
- environment/runtime snapshot;
- node logs and summaries;
- metrics JSON and plots;
- quality validation results;
- model card;
- artifact refs and digests;
- policy decisions.

Evidence must be content-addressed and immutable. The UI can show a compact summary but must link to raw canonical artifacts for auditability.

## 13. Scope boundaries

V1 supports numeric/categorical tabular classification and regression, local CPU execution, deterministic split, baseline preprocessing, comparison, registry and batch scoring. V1 does not promise distributed training, arbitrary Python in the server, online feature stores, deep learning, real-time autoscaling, automatic retraining without approval or privacy certification.

## 14. Success criteria

An operator can create a project, register a dataset revision, create a Lab, profile and validate the data, train at least two candidate baselines, compare metrics, inspect the evidence, register the selected artifact, promote it with authorization, and score another governed dataset — all offline and reproducibly from the Lab manifest.

