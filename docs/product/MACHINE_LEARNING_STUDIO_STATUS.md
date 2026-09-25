# Machine Learning Studio — estado verificable

Este documento evita confundir el núcleo operativo implementado con las capacidades
planificadas de una plataforma ML completa.

| Área | Estado | Evidencia |
|---|---|---|
| Plugin discovery, manifest y permisos | Implementado | `python/studio_ml/plugin.py`, tests de plugin |
| Labs y pipeline IR | Implementado | `domain.py`, `services.py`, tests de dominio/SQLite |
| Backend local intercambiable | Implementado | `backends.py`, `runner.py`, tests de runner |
| Contratos versionados lab/IR/backend | Implementado | `docs/contracts/ml-*-v1.md` |
| Capability discovery de adapters | Implementado | `BackendCapabilities`, `/v1/ml-studio/backends` |
| Contextos de backend e inspección | Implementado | `TrainingContext`, `PredictionContext`, `ModelInspection` |
| Capability gate antes de entrenar | Implementado | `LocalExperimentRunner` rechaza task/algoritmo no anunciado |
| Logistic/Linear Regression | Implementado | `runtime.py`, tests de runtime |
| Profiling y quality gates | Implementado | `quality.py`, endpoint `/quality`, tests de calidad |
| Ejecución asíncrona | Implementado | `orchestration.py`, API execution tests |
| Persistencia durable de lifecycle/result payload | Implementado | `SqliteExecutionStore`, reopen test |
| Provenance y registry base | Implementado | `service.py`, `provenance.py`, persistence tests |
| HTTP control plane y autorización | Implementado | `test_ml_studio_http.py` |
| OpenAPI base ML Studio | Implementado | `api/openapi-v1.json`, contract test |
| UI Labs/quality/run básica | Implementado | `features.js`, Chromium browser audit |
| Grid trials y ranking determinista | Parcial | `optimization.py` y `POST .../search`; `seed`, `C` y `max_iter` se aplican en logística |
| Random trials | Implementado | muestreo determinista y bounded por `random_seed` |
| Bayesian trials | Implementado | surrogate discreto, Expected Improvement, rondas y stopping policy bounded |
| Compare API y ranking de trials | Implementado | API, formulario UI y rendering del ranking |
| Model registry list/promotion | Implementado | endpoints, registro opcional de trials y E2E con evaluación aprobada |
| Model card API | Implementado | `GET .../models/{model_id}/{version}/card` devuelve provenance, digest y firma |
| Registry/promotion UI | Implementado | lista modelos, model card y promoción con reason |
| Score como flujo UI | Implementado | endpoint y formulario de scoring verificados en Chromium |
| Decision Tree clásico | Implementado | artifact declarativo y predicción sin pickle |
| Random Forest clásico | Implementado | ensemble declarativo de árboles y agregación local |
| Gradient Boosting regresión | Implementado | ensemble declarativo con learning rate e inicialización |
| Gradient Boosting clasificación binaria | Implementado | prior log-odds, árboles declarativos y sigmoid |
| K-Means core y runner | Implementado | fitter, `run_clustering` y artifact `ronin.ml-kmeans/v1` |
| Gradient Boosting multiclase | Implementado | artifact por etapa/clase, reconstrucción de decision function y pruebas |
| K-Means integrado en registry síncrono | Implementado | `run_lab` persiste artifact content-addressed, run, métricas y provenance |
| K-Means scoring, registro y promoción síncrona | Implementado | artifact `ronin.ml-kmeans/v1`, firma `cluster`, registro candidato y predicción con digest verificado |
| K-Means en flujo asíncrono | Implementado | coordinator local, lifecycle terminal y payload de resultado verificados |
| Remote/MLflow/Spark adapters | Implementado como abstracción | adapters JSON configurables, retry/cancel/poll/predict y capacidades declaradas; la URL/semántica concreta del proveedor se configura por despliegue |
| Remote adapter v1 contract | Implementado | `docs/contracts/ml-remote-adapters-v1.md`, tipos, errores, transporte y adapters de proveedor |

La suite específica ML Studio, los contratos y la auditoría E2E deben permanecer verdes.
El módulo está completo dentro del alcance provider-neutral definido por el build plan;
la conexión a un endpoint remoto concreto es configuración de despliegue, no código
pendiente del módulo.
