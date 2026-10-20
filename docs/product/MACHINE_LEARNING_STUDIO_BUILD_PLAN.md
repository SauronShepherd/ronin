# Machine Learning Studio — build plan de bajo nivel

## 0. Principios de ejecución

Este plan convierte la propuesta en cambios pequeños, verificables y reversibles. Cada fase debe dejar el repositorio compilable y los contratos versionados. No se debe empezar por una UI rica que invente datos: primero se construyen dominio, ports, persistencia, worker y API; después la UI consume contratos reales.

## 1. Fase 0 — baseline y decisiones congeladas

### Tareas

1. Confirmar que `repo-analysis` es el árbol de implementación y registrar el estado actual del worktree.
2. Añadir ADR para el nombre público Machine Learning Studio y los IDs técnicos `ml-studio`.
3. Confirmar que el plugin usa `studio_core.plugins.PluginManifest`, `PluginContext`, `RouteContribution`, `JobContribution` y `UiContribution`.
4. Confirmar que todas las rutas pasan por `plugin_routes_enabled` y autorización del host.
5. Añadir `docs/contracts/ml-lab-v1.md`, `ml-pipeline-ir-v1.md`, `ml-backend-v1.md`.
6. Definir compatibilidad: `plugin_api=1.0`, `ml-lab/v1`, `ml-pipeline-ir/v1`, `ml-backend/v1`.

### Criterio de salida

Un test de arquitectura verifica que el plugin sólo importa ports públicos y que el manifest aparece en el inventario de plugins.

## 2. Fase 1 — dominio inmutable

### Archivos

- `python/studio_core/ml.py`: ampliar contratos existentes sin romper `Experiment`, `MLRunRecord` y `RegisteredModelVersion`.
- `python/studio_ml/domain.py`: `Lab`, `LabVersion`, `TrainingRequest`, `PipelineIR`, `Trial`, `QualityGate`, `DriftPolicy`.
- `python/studio_ml/schemas.py`: parseo exacto, límites, canonical JSON.
- `python/studio_ml/errors.py`: errores tipados.

### Implementación

1. Crear value objects `LabId`, `LabVersionId`, `TrialId`, `QualitySuiteId`, `DeploymentId`.
2. Implementar validación común de texto, IDs, finite floats y collections únicas.
3. Hacer que `LabVersion` sea inmutable y contenga el manifest ya validado.
4. Implementar `PipelineIR` con DAG acíclico, IDs únicos, dependencies existentes y sin ciclos.
5. Añadir serialización round-trip exacta para todos los objetos.
6. Rechazar campos extra en los boundaries HTTP y aceptar sólo campos definidos en el schema.
7. Añadir pruebas de propiedades para orden canónico, duplicados, ciclos, límites y valores NaN/inf.

### Criterio de salida

100% de los objetos de dominio tienen validación, payload canónico y tests de round-trip; no hay importación de scikit-learn en `studio_core`.

## 3. Fase 2 — ports de almacenamiento y servicios

### Ports

Añadir a `python/studio_storage/ports.py`:

```python
class MLLabStore(Protocol): ...
class MLRunStore(Protocol): ...
class MLQualityStore(Protocol): ...
class MLModelStore(Protocol): ...
```

Cada método debe recibir `WorkspaceId`, usar IDs de dominio y aceptar `now` donde haya mutación. Ningún port expone SQL, cursor o ORM.

### Servicios

Implementar:

- `LabService.create/replace/get/list/validate/compile`;
- `RunService.create/cancel/retry/get/compare`;
- `QualityService.put_suite/validate/get_result`;
- `ModelService.register/promote/resolve/score`.

Las mutaciones deben ser idempotentes. El conflicto de idempotency key se devuelve como error estable si el body no coincide con el request original.

### Criterio de salida

Mocks de ports permiten probar todos los servicios sin SQLite ni backend ML.

## 4. Fase 3 — SQLite y migraciones

### Tareas

1. Crear `python/studio_storage/migrations/00xx_ml_studio.sql`.
2. Añadir constraints de estado y unique keys.
3. Almacenar manifest/evidence como canonical JSON UTF-8.
4. Guardar métricas en tabla normalizada y plots como ArtifactRefs.
5. Implementar paginación por cursor estable `(created_at, id)`.
6. Implementar optimistic concurrency por `version` o `updated_at` y devolver conflict cuando proceda.
7. Añadir migración down sólo si el sistema actual lo exige; preferir forward-only para producción.

### Criterio de salida

Migración limpia desde una base vacía, migración sobre base existente, rollback de proceso sin corrupción y tests de concurrencia.

## 5. Fase 4 — compiler y runner

### Compiler

1. Resolver refs de datasets contra `CatalogStore`; un resolver acotado de CSV/JSONL ya está implementado en el candidato actual para quality, ejecución síncrona y ejecución asíncrona. Falta la cualificación exact-head y extender la materialización a pipelines/reintentos antes de dar por cerrado el criterio global.
2. Resolver backend contra `BackendRegistry`.
3. Resolver runtime profile.
4. Generar nodes `profile`, `quality`, `prepare`, `train`, `evaluate`, `select`, `register`.
5. Calcular pipeline digest.
6. Persistir IR antes de crear el Run.

### Runner

1. Registrar job type `ml-studio.pipeline.v1`.
2. Crear payload con `run_id`, `pipeline_digest`, `node_id`, `attempt`, `resource_policy`.
3. Materializar inputs read-only.
4. Crear workdir efímero y limpiar al finalizar salvo policy de debug.
5. Emitir eventos heartbeat y progress bounded.
6. Guardar outputs mediante `ArtifactStore.put_bytes`.
7. Verificar digests antes de escribir referencias.
8. En cancelación, cerrar backend, marcar node y conservar evidencia parcial.

### Criterio de salida

Un pipeline sintético con tres nodos se ejecuta localmente, puede cancelarse, reintentarse y recuperar outputs por digest.

## 6. Fase 5 — backend abstraction y scikit-learn

### Contrato

Extender `python/studio_ml/backends.py` con:

- `BackendCapabilities`;
- `TrainingContext`;
- `TrainingResult`;
- `PredictionContext`;
- `ModelInspection`;
- `BackendRegistry`.

### Adaptador local

1. Mantener el runtime existente como implementación base.
2. Separar preparación de datos del algoritmo mediante un `PreprocessorSpec`.
3. Añadir Logistic Regression, Linear Regression, Decision Tree, Random Forest, Gradient Boosting y K-Means cuando los tests de determinismo estén listos.
4. Rechazar algoritmos no compatibles con task.
5. Guardar parámetros efectivos y defaults expandidos.
6. Calcular métricas con split explícito.
7. Producir artifact declarativo cuando sea posible; si no, marcar loader requerido y riesgo.
8. Añadir `predict` que valide signature antes de inferencia.

### Criterio de salida

El mismo `LabVersion` puede ejecutarse con el adapter local y un fake backend en tests, sin cambiar el servicio.

## 7. Fase 6 — profiling y quality gates

### Profiling

Implementar contadores bounded: rows, columns, nulls, distinct approximate/exact, min/max/quantiles, histogramas, top categories, duplicate rate y target distribution. Nunca incluir valores completos por defecto.

### Quality

1. Crear schema para Expectations.
2. Implementar validadores nativos sencillos.
3. Asociar severidad `info`, `warning`, `failure`.
4. Ejecutar Checkpoint antes de prepare y opcionalmente antes de score.
5. Persistir `ValidationResult` como evidence.
6. Permitir suites reutilizables y versionadas.

### Criterio de salida

Un dataset con nulls y target único detiene el training con error explicable y evidencia navegable.

## 8. Fase 7 — comparación y optimización

1. Crear `SearchSpec` con mode `single`, `grid`, `random`, `bayesian` opcional.
2. Validar el espacio antes de lanzar trials.
3. Crear deterministic trial IDs y seeds derivadas de `(run_seed, trial_id)`.
4. Ejecutar trials en paralelo sólo si el resource policy lo permite.
5. Implementar pruning cooperativo mediante heartbeat/metric callback.
6. Comparar sólo runs con mismo task, target, evaluation protocol y dataset contract.
7. Mostrar intervalo o repetición cuando CV lo permita.
8. Resolver empates por métrica secundaria, coste y simplicidad, en ese orden configurable.

### Criterio de salida

La tabla de comparación reproduce el mismo ranking al repetir el Run con idénticos inputs.

## 9. Fase 8 — registry, model card y promoción

1. Registrar únicamente artifact verificado y signature completa.
2. Generar model card con intended use, limitations, dataset, features, metrics, fairness, owner y provenance.
3. Stage transitions: candidate -> champion, candidate -> archived, champion -> archived.
4. Impedir dos champions simultáneos salvo policy explícita por scope.
5. Requerir `ml-studio:promote` y reason no vacío.
6. Crear endpoint de score batch que resuelva model version inmutable.
7. No borrar artifacts de modelos promovidos por un delete de metadata.

### Criterio de salida

Un modelo champion puede resolverse, validarse por signature y ejecutar batch scoring con evidencia de entrada y salida.

## 10. Fase 9 — API y OpenAPI

1. Añadir schemas OpenAPI para cada endpoint.
2. Añadir rutas al registry del plugin, no a la lista core salvo compatibilidad requerida.
3. Mapear permisos y workspace scope.
4. Implementar query validation, cursor bounds, duplicate query rejection y error envelope.
5. Añadir idempotency para create lab/run/register/promote.
6. Añadir contract tests contra el handler y OpenAPI.

### Criterio de salida

El servidor rechaza bodies incompletos, extra fields, IDs inválidos, permisos ausentes y dataset refs no visibles.

## 11. Fase 10 — UI

### Orden de implementación

1. Registrar nav contribution y route `#mlstudio`.
2. Implementar Labs list con loading/error/empty states.
3. Implementar Lab wizard guardado contra API real.
4. Implementar schema/profile table y quality badges.
5. Implementar Flow SVG/DOM accesible con nodes seleccionables.
6. Implementar Train form basado en backend capabilities.
7. Implementar run timeline y trial table.
8. Implementar compare view con filtros y export JSON/CSV.
9. Implementar model card y promote dialog con reason.
10. Implementar Operate batch score y drift report.

La UI no debe renderizar una métrica o modelo si el backend no lo ha devuelto. Los botones de capacidades futuras aparecen como planned y no como acciones falsas.

## 12. Fase 11 — adaptadores posteriores

### `local.xgboost`

Plugin o backend opcional, con licencia/dependency audit, capabilities propias y artifact safety declarada.

### `remote.ronin`

Envía PipelineIR firmado al runner remoto; recibe events y ArtifactRefs. Nunca envía secrets en el IR.

### `mlflow.adapter`

Escribe tracking y modelos en MLflow, pero conserva el Run y ModelVersion nativos de Ronin. La operación debe poder leer evidencia si MLflow está indisponible.

### `sparkml`

Sólo cuando exista runtime profile distribuido, connector de datos y una política de coste. No se añade como dependencia base.

## 13. Testing y gates

- Unit: value objects, schema, state machines, compiler, metric aggregation.
- Property: canonical JSON, DAG acyclic, cursors, metric finiteness, idempotency.
- Contract: plugin manifest, ports, backend capabilities, OpenAPI.
- Integration: SQLite, ArtifactStore, job runner, cancellation, retry.
- E2E: create workspace -> project -> dataset -> lab -> quality -> train -> compare -> register -> promote -> score.
- Security: permission matrix, path traversal, secret redaction, untrusted artifact loader, network denial.
- Reproducibility: same manifest/snapshot/runtime produces same pipeline digest and metrics within defined tolerance.
- Performance: profile bounded dataset, list runs pagination, compare 1k trials, artifact streaming.
- Mutation: state transition guards, authorization conditions and error handling.

No phase se considera terminada si sólo funciona mediante mocks de UI.

## 14. Rollout y migraciones

### Alpha local

Feature flag `ml_studio_enabled=false` por defecto. Activar sólo rutas de labs y backend local. No activar promotion ni serving fuera de desarrollo.

### Beta

Activar quality, compare, registry y batch score. Añadir telemetry de errores, latencia y tamaño de datasets sin capturar datos de filas.

### Public v1

Activar por defecto en builds que incluyan el extra `ml`, con graceful degradation si scikit-learn no está instalado. El plugin debe mostrar “backend unavailable” y cómo instalar el extra.

### Compatibilidad

No cambiar campos de `ronin.ml-lab/v1` en sitio. Crear v2 si se necesita alterar semántica. Mantener migradores explícitos `v1 -> v2` y conservar evidencia original.

## 15. Entregables finales

1. Código del plugin y backend local.
2. Schemas JSON/OpenAPI.
3. Migraciones SQLite y ports de storage.
4. Pipeline compiler y job handler.
5. UI completa de Labs, Flow, Train, Compare, Registry y Operate.
6. Model cards y evidence bundles.
7. Contract/e2e/security/reproducibility tests.
8. Docs de authoring de backends.
9. Ejemplo reproducible `examples/ml/churn`.
10. Runbook de troubleshooting y recuperación.

## 16. Definition of Done global

Machine Learning Studio está listo cuando un nuevo backend puede implementarse siguiendo el SDK sin modificar la UI ni los servicios de dominio, cuando un Lab exportado puede reproducirse en otra instalación con los mismos snapshots, cuando ningún artefacto no confiable se carga en el API process, cuando todas las transiciones de modelo quedan auditadas y cuando el camino de usuario completo funciona offline con evidencia verificable.

## 17. Estado del blocker RON-ML-002

**Progreso de implementación de RON-ML-002: 100% (5/5 criterios técnicos verificados).** Este porcentaje corresponde al blocker del coordinador ML y no al Definition of Done global de Machine Learning Studio.

| Criterio | Estado y evidencia |
| --- | --- |
| Aislar el mismo `run_id` entre workspaces | Verificado con IDs durables derivados de workspace + run y prueba SQLite compartida. |
| Reintentar sin crear otro Job | Verificado al reabrir SQLite: el Job terminal se devuelve por idempotency key y el recuento permanece en uno. |
| Impedir escrituras después de cancelar | Verificado en SQLite y PostgreSQL 16; la cancelación fuerza el intento terminal y limpia su lease antes de rechazar el write tardío. |
| Recuperar tras cierre/reapertura sin quedar bloqueado | Verificado con un Job pendiente, reapertura del servicio y finalización por el coordinador. |
| Usar el ciclo canónico del host sin duplicar el scheduler | La composición local inyecta `DurableExecutionService`; ML filtra `target=ml-studio.execute` y persiste resultados como checkpoints de `JobStore`. |

La suite focalizada ML, HTTP, composición local y PostgreSQL pasó **139/139 en Windows** y **137/137 en Docker/Python 3.12** (dos tests condicionados por plataforma no se recogen en Linux). Las cinco pruebas del módulo PostgreSQL pasaron en Docker contra PostgreSQL 16; la carrera claim-cancel incluye 12 iteraciones. Ruff, formato, mypy completo de producto y la puerta de arquitectura pasan. El PR [#428](https://github.com/SauronShepherd/ronin/pull/428) se integró con squash en `main@b5d0701fee9d2e47c6c42eaca1766b1bf5e73e3e`; CI, Docker qualification, Web, Security, Release y Status consistency post-merge pasaron exact-head. Este blocker queda cerrado; el avance release-qualified global continúa en **0% (0/14)**.

## 18. Candidato: lectura de datasets gobernados por AssetRef

**Progreso del resolver AssetRef integrado: 100% (8/8 criterios, cualificado en `main@43654932b573a8e84339095323ed8a424a21cb23`).** **Límites de entradas inline: 100% (9/9 criterios técnicos, cualificados en `main@95d25d0e5fccebac66d5a52a814a6c4ad7036f82`).**

| Criterio técnico | Evidencia |
| --- | --- |
| Resolver asset y revisión desde el workspace del request | `tests/test_ml_datasets.py` verifica lectura autorizada y denegación entre workspaces. |
| Exigir `kind=dataset`, referencia y revisión consistentes | Casos de asset/revisión ausentes y assets no dataset en el resolver. |
| Verificar `artifact_ref`, `media_type`, `content_digest` y bytes SHA-256 | Casos negativos de referencia y digest; round-trip real con `LocalArtifactStore`. |
| Leer CSV/JSONL UTF-8 de forma estricta | Casos de headers, anchura, JSON inválido/no estándar, objetos y entrada vacía. |
| Aplicar límites de bytes, filas y columnas | Pruebas de límites y cobertura branch del resolver. |
| Aplicar los mismos límites a filas inline | `tests/test_ml_datasets.py` verifica filas, columnas, bytes, claves y valores canónicos. |
| Usar el snapshot al omitir filas en quality y ejecución síncrona/asíncrona | Test de plugin recorre los tres endpoints y compara filas entregadas. |
| Inyectar catálogo y artefactos en la composición local | `tests/test_local_composed.py` confirma los adaptadores SQLite y el artifact store compartido. |
| Documentar el contrato y request opcional de filas | `tests/test_openapi_snapshot.py` y snapshot OpenAPI actualizado. |

La lectura, la ejecución asíncrona y las filas inline respetan 64 MiB, 100000 filas y 1024 columnas; los cuerpos HTTP inline además tienen el límite de transporte de 1 MiB. Las filas inline deben usar claves string no vacías, sin espacios periféricos, y valores JSON canónicos. En ejecuciones durables, los inputs que superarían 1 MiB se guardan en `ArtifactStore`; el Job conserva sólo la referencia y metadatos del digest. Al reclamar el Job, el worker verifica referencia, tamaño y SHA-256, y el coordinador vuelve a comprobar el digest canónico del request antes de ejecutar. Las pruebas cubren reabrir SQLite entre submit y claim, ejecutar una solicitud >1 MiB con el coordinador durable y el recorrido de composición local AssetRef→Job→ArtifactStore→runner. El PR [#430](https://github.com/SauronShepherd/ronin/pull/430) se integró con squash en `main@43654932b573a8e84339095323ed8a424a21cb23`; el PR [#432](https://github.com/SauronShepherd/ronin/pull/432) cerró el bypass inline en `main@95d25d0e5fccebac66d5a52a814a6c4ad7036f82`. Ambos pasaron CI y Docker exact-head; los seis workflows post-merge del SHA actual pasaron. El compiler/runner global permanece abierto y no se afirma cualificación de release.

La composición local inyecta el catálogo SQLite o, en el perfil PostgreSQL, el store PostgreSQL compartido que implementa el contrato de catálogo; ambos perfiles inyectan el mismo `ArtifactStore` usado para materializar los archivos locales. Las pruebas cubren CSV/JSONL, aislamiento por workspace, digest y estructuras inválidas. Este incremento no declara cerrado el compiler/runner global: quedan la integración de snapshots en pipelines/reintentos, el contrato de features, algoritmos adicionales, MLflow/serving de red, journeys E2E y cualificación de producción. P8 continúa parcial y release-qualified permanece en **0% (0/14)**.

## 19. Candidato: fijar PipelineIR en ejecuciones asíncronas durables

**Progreso técnico: 5/5 criterios; cualificación exact-head de PR #434 completada; P8/release-qualified: 0% (0/14).**

| Criterio técnico | Evidencia |
| --- | --- |
| Compartir el compilador determinista entre `LabService.compile` y submit | `compile_lab_pipeline` produce la misma IR canónica y ligada al digest del Lab. |
| Persistir PipelineIR y digest en la identidad de submit | `ronin.ml-execution.v2` guarda `pipeline_json`, `pipeline_digest` y request digest dentro del Job durable. |
| Recuperar el snapshot y verificar pipeline, Lab y Job antes del runner | Tests de reapertura/composición y rechazo de digest inconsistente con la identidad durable de Job. |
| Conservar la compatibilidad de registros v1 | El lector admite parámetros `ronin.ml-execution.v1` y v2; los submits nuevos generan v2. |
| Liberar snapshots terminales y detectar alteraciones | Tests cubren cambio de pipeline en retry, manipulación de parámetros y limpieza al finalizar/cancelar. |

El PR [#434](https://github.com/SauronShepherd/ronin/pull/434) quedó en `main@2d3f7d3b43d0b3b9268a57860e19e707a57a02e8`. La suite completa de Windows pasó **3745 tests, 49 omitidos**; las pruebas focalizadas de persistencia y manipulación, los checks de calidad y la cualificación Docker exact-head pasaron. También pasaron los seis workflows post-merge de ese SHA. El pipeline queda reproduciblemente fijado y validado al recuperar un Job. El runner sigue ejecutando el flujo local existente directamente desde el Lab: la evaluación del DAG como plan ejecutable, el checkpoint/retry de nodos y la semántica de materialización todavía no están implementados. P8 permanece parcial; no se declara cualificación de release.

## 20. Candidato: ejecutar las etapas fijadas de PipelineIR

**Progreso técnico: 5/5 criterios; PR #436 integrado y cualificado exact-head; P8/release-qualified: 0% (0/14).**

| Criterio técnico | Evidencia local |
| --- | --- |
| Exponer un orden topológico estable que no dependa del orden serializado | `PipelineIR.execution_order()` y prueba con dos ramas independientes. |
| Ejecutar las seis etapas locales declaradas por IR | `LocalExperimentRunner.execute_pipeline()` interpreta profile, quality gate, prepare, train, evaluate y select. |
| Rechazar grafos incompletos y saltos en el contrato de etapas antes de entrenar | Pruebas de contrato verifican que falta de nodo soportado no ejecuta training; se exige digest de Lab y dependencia directa entre etapas. |
| Usar el mismo executor en rutas síncronas y asíncronas durables | `run()`, resultado de clustering y `LocalExecutionCoordinator` delegan el flujo a `execute_pipeline()`. |
| Preservar compatibilidad con runners de prueba/adaptadores y resultados de clustering | Suite ML/API/composición local focalizada: **51 passed**. |

El PR [#436](https://github.com/SauronShepherd/ronin/pull/436) quedó integrado como `main@18b2cdecc1380886edeba2a0ad16305be065fa43`. El full suite local pasó **3748 tests, 49 omitidos**; mypy global (457 archivos), la puerta de arquitectura, Ruff/formato y la suite focalizada también pasan. CI, Docker qualification (**8m20s** en el PR y **8m43s** post-merge), Web, Security, Release y Status consistency pasaron exact-head. El Docker gate cubrió PostgreSQL, worker Docker real y aceptación estricta. El grafo local soportado sigue siendo deliberadamente el conjunto fijo de seis etapas; `register` y etapas configurables aún no ejecutan. No hay checkpoints de nodo, retry selectivo, persistencia de outputs intermedios ni política de materialización; los reintentos durables todavía vuelven a ejecutar el Job entero. P8 permanece parcial y release-qualified sigue en **0% (0/14)**.

## 21. Checkpoints durables de etapas ML

**Progreso técnico: 6/6 criterios implementados; PR #438 y corrección de qualification #439 integrados en `main@92165f5dbf23b6153c62b0150d4e74e300ac1dd8`. Los seis workflows post-merge exact-head pasaron, incluido Docker qualification (run 39367136062, completado a las 04:07:53Z). P8 y release-qualified permanecen en 0% (0/14).**

| Criterio técnico | Evidencia |
| --- | --- |
| Reanudar etapas locales completadas | `LocalExperimentRunner.execute_pipeline()` carga checkpoints por nodo; `test_ml_runner.py` verifica que reanudar un pipeline omite `train`. |
| Vincular checkpoints con la identidad ejecutada | `JobStoreExecutionStore` comprueba `pipeline_digest`, `request_digest`, estado exitoso e identidad de nodo antes de restaurar; un ID de celda derivado del nodo evita colisiones. |
| Guardar datos sin deserialización ejecutable | Los resultados se codifican como JSON canónico y los artefactos declarativos del modelo como bytes Base64; no se usa pickle. Datos inválidos se tratan como cache miss. |
| Fijar escrituras al lease vigente | El checkpoint se guarda a través de `worker_put_cell_result`, que aplica el fencing del intento duradero. |
| Mantener checkpoints grandes verificables | `ArtifactStore` conserva payloads mayores que el límite inline y verifica rol, tipo, tamaño y SHA-256 al escribir y leer; sin store disponible se omite el checkpoint y la ejecución continúa. |
| Recuperar tras reinicio con PostgreSQL | `test_postgres_ml_node_checkpoint_survives_service_reopen` guarda un checkpoint, cierra el servicio, lo reabre y lo recupera; termina el Job para no dejar un lease expirable en la base compartida. |

El PR [#438](https://github.com/SauronShepherd/ronin/pull/438) añadió los checkpoints y se integró como `4fc7cbe3475ede0626975cd1f71bf97993b0e4bd`. El PR [#439](https://github.com/SauronShepherd/ronin/pull/439) corrigió la adaptación de `JobId` al reanudar una página PostgreSQL, cubrió filtros y cursor keyset en la integración real y elevó el baseline de cobertura de `postgres_jobs.py` a 73,01% después de medir 73,015%. Sus checks exact-head pasaron: Python 3.11/3.12, calidad, verificación, seguridad, ledgers y Docker qualification (**8m40s**, incluyendo PostgreSQL, worker real y aceptación estricta). En Windows, la suite de cobertura completa registró 3785 passed y 19 skipped, más dos fallos transitorios (conexión HTTP abortada y timeout al ejecutar CLI); ambos tests pasaron al repetirse focalizados. La primera ejecución Docker detectó un test que dejaba expirar el lease de un Job; el test ahora completa ese intento. En `main@92165f5dbf23b6153c62b0150d4e74e300ac1dd8`, los seis workflows post-merge exact-head —CI, Web, Security, Release, Status consistency y Docker qualification— pasaron; Docker terminó a las 04:07:53Z.

Este slice no cierra el executor completo: sólo las seis etapas locales existentes son ejecutables; `register` y grafos configurables siguen rechazándose. El retry durable todavía vuelve a reclamar y ejecutar el Job, reutilizando etapas exitosas sólo si coinciden los digests de pipeline, request y runtime. El candidato de la sección 25 enlaza la huella de código/dependencias/opciones con checkpoints y resultados. Aún faltan una política explícita de materialización y retención, invalidación aguas abajo, retry selectivo observable y el journey completo de ejecución→registro. P8 continúa parcial; release-qualified continúa en **0% (0/14)**.

## 22. Materialización de resultados ML durables

**Progreso técnico: 4/4 criterios implementados y cualificados en PR #441; integrado en `main@97c1ee44e4aed0a8902ef4e546b10bb684001cb8`.** La qualification exact-head post-merge de esta base sigue en ejecución; la qualification exact-head del PR pasó.

| Criterio técnico | Evidencia |
| --- | --- |
| Materializar artefacto tabular al terminar el Job | `ExperimentResult.model.artifact_bytes` se escribe con rol `model` y media type de tabular; el payload durable incluye su referencia content-addressed. |
| Materializar el artefacto canónico K-Means | Centroides y schema se serializan en JSON determinista, se guardan con media type dedicado y se conserva el digest. |
| Verificar lo almacenado antes de éxito terminal | El coordinator compara el digest declarado, verifica rol/tipo/tamaño, ejecuta `ArtifactStore.verify()` y lee los bytes de vuelta para comprobar el SHA-256. |
| Acotar y rechazar salidas inconsistentes | Los modelos superan el límite de 64 MiB o digest incorrecto hacen fallar el Job antes de persistir un resultado exitoso; tests cubren el rechazo sin escribir artefactos. |

El PR [#441](https://github.com/SauronShepherd/ronin/pull/441) pasó CI Python 3.11/3.12, calidad, seguridad, verificación, ledgers y Docker qualification (**8m54s**, PostgreSQL, worker Docker real y aceptación estricta). En Windows, la suite completa pasó **3752 tests con 51 omitidos**; la cobertura de `studio_storage/artifacts.py` subió a **80,263%**, por lo que el baseline con margen de 2,1 puntos se actualizó de 77,30% a 78,17% tanto en `coverage-storage-files` como en `coverage-storage-files-full`. La puerta local por archivo pasó para 54 módulos.

La salida durable expone URI, digest, media type y tamaño; el candidato actual añade el registro controlado de ejecuciones exitosas en MLRun y como versiones candidatas, pendiente de cualificación exact-head. Aún faltan lectura HTTP autorizada con aislamiento, integración UI y el recorrido hasta promoción. Continúan abiertos retry selectivo, invalidación aguas abajo, identidad de resultados ligada a versión de runner y una política de retención/limpieza de artefactos. P8 permanece parcial y release-qualified sigue en **0% (0/14)**.

## 23. Registro de resultados de ejecuciones durables

**Progreso técnico local: 2/2 criterios implementados; cualificación exact-head pendiente.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Registrar sólo una ejecución exitosa con artifact materializado | `POST /v1/ml-studio/executions/{run_id}/register` exige estado `succeeded`, metadatos completos y ArtifactStore disponible; revalida tamaño y SHA-256 antes de escribir en el registry. |
| Crear procedencia y versión candidata idempotentes | Registra Experiment y MLRun ligados al Lab/dataset, luego el model version con digest, firma inferida y referencia content-addressed; el registry hace idempotentes escrituras idénticas y rechaza conflictos. |

Las pruebas focalizadas verifican el flujo tabular, la firma/digest/procedencia y el rechazo de ejecuciones aún activas. El handler requiere autorización `ml-studio:write`; el contenido del artifact no se sirve por este endpoint. El candidato UI añade el formulario de registro al completar correctamente una ejecución y actualiza la lista de modelos tras el registro. Aún faltan probar el journey con servicios reales, promoción directa desde la ejecución, retry selectivo e invalidación aguas abajo. P8 sigue parcial y release-qualified permanece en **0% (0/14)**.

## 24. Lectura HTTP autorizada de artifacts de modelos

**Progreso técnico local: 6/6 criterios implementados; cualificación exact-head pendiente.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Autorizar por permiso de lectura y workspace | `GET /v1/ml-studio/models/{model_id}/{version}/artifact` usa `ml-studio:read` y busca la versión dentro del `WorkspaceId` autenticado. |
| Verificar la referencia antes de revelar bytes | El digest debe ser SHA-256 válido; el ArtifactStore recupera por ref+digest y el handler vuelve a verificar digest y límite de 64 MiB. |
| Acotar transferencia y permitir reanudación | Responde Base64 en bloques de hasta 512 KiB, con offset, next_offset, tamaño total, digest y media type para reconstrucción/reanudación. |
| Rechazar rangos ambiguos o fuera de límites | Parámetros desconocidos/duplicados, offset inválido o longitudes fuera de rango fallan antes de responder. |
| Descargar desde la UI sin cargar el artifact entero en una respuesta | La UI solicita bloques acotados, valida identidad, metadatos y continuidad de offsets y sólo crea el archivo al completar el tamaño declarado. |
| Probar la reconstrucción del artifact en navegador | Playwright simula un artifact de dos bloques, verifica ambos offsets, el nombre descargado y el estado de éxito. |

Las pruebas de API cubren reconstrucción por varios bloques, aislamiento por workspace, rango, límites y corrupción. Playwright verifica el flujo de descarga desde el registry; OpenAPI documenta parámetros y respuesta. PR #446 pasó Docker, Web y CI; la cualificación exact-head post-merge de `main@c0e716f` sigue en ejecución. La prueba con ArtifactStore remoto sigue pendiente. P8 continúa parcial y release-qualified permanece en **0% (0/14)**.

## 25. Identidad de runtime para checkpoints ML

**Progreso técnico local: 5/5 criterios implementados; cualificación Docker exact-head pendiente.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Calcular identidad estable del ejecutor | SHA-256 de runner, dominio, compiler, orquestación, runtime, calidad, clustering y registry de backends. |
| Incluir entorno y backend efectivo | Huella incluye versión completa de Python, versiones de paquetes ML, clase/backend y fingerprint opcional declarado por el proveedor. |
| Incluir opciones de ejecución | Parameters, clusters y max_iterations forman parte de la huella; la misma request con opciones distintas no reutiliza outputs. |
| Descartar checkpoints de otro runtime | Tests guardan checkpoints obsoletos y comprueban que el training vuelve a ejecutarse; la caché sólo se guarda si la identidad es estable. |
| Persistir procedencia del output | La huella de runtime queda en el checkpoint de selección y en el payload durable `ExperimentResult`/`ClusteringResult`. |

La suite focalizada ML/API de este candidato pasó **163 tests**; Ruff, formato y mypy del runner pasan. La huella es deliberadamente conservadora: cualquier cambio en los módulos ejecutables invalida los checkpoints, y un backend sin código fuente o fingerprint declarado no reutiliza caché. Quedan política explícita de retención, invalidación selectiva aguas abajo y reintentos selectivos observables. P8 sigue parcial y release-qualified permanece en **0% (0/14)**.

