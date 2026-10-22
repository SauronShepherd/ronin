# Machine Learning Studio — estado verificable

Este documento evita confundir el núcleo operativo implementado con las capacidades
planificadas de una plataforma ML completa.

| Área | Estado | Evidencia |
|---|---|---|
| Plugin discovery, manifest y permisos | Implementado | `python/studio_ml/plugin.py`, tests de plugin |
| Labs y pipeline IR | Implementado | `domain.py`, `services.py`, tests de dominio/SQLite |
| Envío de DAG candidato por API | Implementado estáticamente en el candidato; cualificación pendiente | PipelineIR v3 durable con DAGs arbitrarios, `register` terminal y etapas namespaced de plugins; PipelineIR v2 mantiene compatibilidad con ramas prepare y cuadrículas de hasta ocho combinaciones/24 nodos |
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
| Servicio sync de conectores protegido por barrera opcional | Candidato; pendiente de cablear en composición | Si se inyecta `ArtifactReferenceBarrier`, el lock cubre `destination.write()` y el commit del checkpoint; 48 tests dirigidos pasan. No habilita limpieza global |
| Artefactos de ejecución ML durable coordinados con JobStore | Candidato; composición PostgreSQL inyecta la barrera compartida | Inputs, checkpoints de nodo y modelo final mantienen el lock hasta confirmar la referencia durable; 30 tests ML dirigidos pasan. No cubre Jobs/evidence globales ni otros productores |
| Revisiones de Data Engineering protegidas por barrera | Candidato; plugin y composición PostgreSQL inyectan la barrera | El lock abarca todos los artefactos de una revisión y su commit durable; 45 tests combinados pasan. Otros productores siguen sin instrumentar |
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
| Remote/MLflow/Spark adapters | Implementado como abstracción; cualificación pendiente | adapters JSON configurables, retry/cancel/poll/predict, backoff exponencial acotado, métricas finitas y capacidades declaradas; la URL/semántica concreta del proveedor se configura por despliegue |
| Bundle de registry ML | Implementado estáticamente; cualificación pendiente | Export/import de experimentos, features, evaluaciones, runs, modelos y, cuando se inyectan stores, bytes de artefactos con digest y remapeo de referencias; metadata-only sigue explícito |
| Publicación artifact→run→modelo | Implementada estáticamente; cualificación pendiente | Tabular y K-Means calculan digest/firma antes de publicar, aceptan reintentos idénticos y rechazan conflictos; el cleanup de huérfanos sigue deliberadamente conservador |
| Experimentos API | Implementado estáticamente; cualificación pendiente | POST crea de forma durable y GET/listado recuperan por workspace; conflictos de definición se rechazan |
| Remote adapter v1 contract | Implementado | `docs/contracts/ml-remote-adapters-v1.md`, tipos, errores, transporte y adapters de proveedor |
| MLflow metadata interchange | Implementado estáticamente; cualificación pendiente | `mlflow.py` exporta/importa el subconjunto canónico de experiment/run/model con flavors seguros; no carga código ni artefactos ejecutables |
| Feature definitions y dataset snapshots | Implementado estáticamente; cualificación pendiente | `FeatureDefinition` versionado e inmutable en in-memory/SQLite/PostgreSQL; composición local cablea el servicio al control plane y OpenAPI documenta las rutas |

La suite específica ML Studio, los contratos y la auditoría E2E deben permanecer verdes.
El módulo está completo dentro del alcance provider-neutral definido por el build plan;
la conexión a un endpoint remoto concreto es configuración de despliegue, no código
pendiente del módulo.
La ejecución duradera reutiliza etapas exitosas sólo cuando coinciden su identidad de
runtime y los outputs de sus dependencias; una etapa recalculada invalida sus
dependientes obsoletos. El candidato actual admite grafos configurables, `register` como
etapa ejecutable y etapas namespaced de plugins; la cualificación exact-head e integración
en `main` siguen pendientes. El retry selectivo desde una etapa elegida está integrado y
exact-head cualificado en `main@c2df903`.
El resultado durable conserva una referencia verificada del modelo en ArtifactStore.
El candidato local añade el registro de una ejecución como versión candidata por una
API protegida, la lectura HTTP autorizada en bloques y la descarga verificada desde la
UI. PR #447 añadió identidad de runtime/dependencias y su invalidación downstream,
PR #448 añadió la promoción directa al finalizar el registro, y PR #449 añadió el retry
selectivo. Los seis workflows exact-head post-merge de `main@c2df903` pasaron; la suite
web local completa dio 79/79 en PR #448 y 80/80 con el retry de PR #449. La qualification
ML contra S3-compatible real también pasó en Docker y en los seis workflows exact-head
de `main@6507b97`.
