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
| Checkpoints durables de etapas PipelineIR | Implementado para las seis etapas locales | `runner.py`, `orchestration.py`, round-trip local y recuperación PostgreSQL tras reabrir el servicio |
| Identidad de runtime y dependencias en checkpoints/resultados | Integrada y exact-head cualificada en `main@c2df903` | Hashes de fuentes ejecutables, Python, dependencias, backend, opciones y outputs upstream; runtimes o dependencias distintas invalidan checkpoints afectados |
| Materialización del modelo en ejecución durable | Implementada para tabular y K-Means | `JobStoreExecutionStore.materialize_result_artifact()`, verificación de lectura/digest y referencia persistida en el resultado |
| Registro de resultados de ejecuciones durables | Registro y promoción directa exact-head cualificados en `main@c2df903` | `POST /v1/ml-studio/executions/{run_id}/register` valida estado, tamaño, digest, workspace/Lab y registra Experiment, MLRun y versión candidata con firma; la acción de éxito promueve con motivo y autorización existentes |
| Reintento selectivo de ejecuciones fallidas | Integrado y exact-head cualificado en `main@c2df903` | `POST .../retry` crea un hijo desde una etapa elegida, restaura checkpoints anteriores y permite seguimiento UI |
| ArtifactStore S3-compatible para lifecycle ML | Exact-head cualificado en `main@6507b97` | Input durable >1 MiB y materialización de modelo por `S3ArtifactStore`; lectura, digest y qualification LocalStack pasaron CI y Docker |
| Limpieza manual de artifacts sin referencias | Exact-head cualificada en `main@33a7b45` | Conjunto vivo vacío rechazado por defecto; vaciado completo requiere `allow_empty_live_set=True`; limpieza global automática sigue deshabilitada por falta de barrera entre stores |
| Primitiva PostgreSQL de coordinación de retención | Candidato probado contra PostgreSQL 16 en Docker; sin integración de productores | Locks compartidos para escritores y exclusivo para recolección, timeout fail-closed; 12 tests pasan. El recolector automático sigue deshabilitado hasta instrumentar todos los productores y stores |
| Lectura y descarga de artifacts de modelos | Integradas y exact-head cualificadas en `main@c2df903` | Endpoint `GET .../artifact` con `ml-studio:read`, aislamiento por workspace y bloques Base64 verificados; UI reconstruye y descarga el archivo tras validar tamaño, digest y secuencia |
| Provenance y registry base | Implementado | `service.py`, `provenance.py`, persistence tests |
| HTTP control plane y autorización | Implementado | `test_ml_studio_http.py` |
| OpenAPI base ML Studio | Implementado | `api/openapi-v1.json`, contract test |
| UI Labs/quality/run básica | Implementado | `features.js`, Chromium browser audit |
| Grid trials y ranking determinista | Parcial | `optimization.py` y `POST .../search`; `seed`, `C` y `max_iter` se aplican en logística; tie-breakers ordenados y direccionales exact-head cualificados en `main@a8e1120` |
| Random trials | Implementado | muestreo determinista y bounded por `random_seed` |
| Bayesian trials | Implementado y exact-head cualificado en `main@cc0ad8f` | surrogate discreto, Expected Improvement, propuestas de memoria acotada y parada por paciencia/mejora reciente |
| Compare API y ranking de trials | Implementado y exact-head cualificado en `main@ba3106b` | API, formulario UI, tie-breakers direccionales, máximo de ocho y rechazo de campos desconocidos; OpenAPI y parser mantienen el mismo contrato |
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
La ejecución duradera reutiliza etapas exitosas sólo cuando coinciden su identidad de
runtime y los outputs de sus dependencias; una etapa recalculada invalida sus
dependientes obsoletos. Todavía no admite grafos configurables, `register` como etapa
ejecutable; el retry selectivo desde una etapa elegida está integrado y exact-head cualificado en `main@c2df903`.
El resultado durable conserva una referencia verificada del modelo en ArtifactStore.
El candidato local añade el registro de una ejecución como versión candidata por una
API protegida, la lectura HTTP autorizada en bloques y la descarga verificada desde la
UI. PR #447 añadió identidad de runtime/dependencias y su invalidación downstream,
PR #448 añadió la promoción directa al finalizar el registro, y PR #449 añadió el retry
selectivo. Los seis workflows exact-head post-merge de `main@c2df903` pasaron; la suite
web local completa dio 79/79 en PR #448 y 80/80 con el retry de PR #449. La qualification
ML contra S3-compatible real también pasó en Docker y en los seis workflows exact-head
de `main@6507b97`.
