# Machine Learning Studio — build plan de bajo nivel

## Estado del plan

**Avance de implementación técnica estimado: 76%. Cualificación release: 0% (0/14).** El primer porcentaje refleja el trabajo funcional integrado y cualificado en dominio, persistencia, compiler/runner, API, UI y retención; el segundo sólo cuenta los 14 gates de release y no equivale al avance de implementación. P8 continúa parcial: la limpieza global segura sigue deshabilitada y la ejecución configurable cubre DAGs v2 de candidatos para clasificación/regresión; la extensión a clustering está en cualificación. Los porcentajes se actualizarán al integrar cada incremento y al pasar su cualificación exact-head.

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

Este slice no cierra el executor completo: sólo las seis etapas locales existentes son ejecutables; `register` y grafos configurables siguen rechazándose. El retry durable reutiliza etapas previas únicamente si coinciden pipeline, request, runtime y outputs de dependencia. PR #447 cerró la identidad del runtime y la invalidación downstream (sección 25), PR #448 integró la promoción directa tras registro (sección 23) y PR #449 integró retry selectivo observable (sección 26). Siguen abiertos grafos configurables y una política de retención/materialización integrada con productores y referencias; P8 continúa parcial y release-qualified permanece en **0% (0/14)**.

## 22. Materialización de resultados ML durables

**Progreso técnico: 4/4 criterios implementados y cualificados en PR #441; integrado en `main@97c1ee44e4aed0a8902ef4e546b10bb684001cb8`.** La qualification exact-head post-merge de esta base sigue en ejecución; la qualification exact-head del PR pasó.

| Criterio técnico | Evidencia |
| --- | --- |
| Materializar artefacto tabular al terminar el Job | `ExperimentResult.model.artifact_bytes` se escribe con rol `model` y media type de tabular; el payload durable incluye su referencia content-addressed. |
| Materializar el artefacto canónico K-Means | Centroides y schema se serializan en JSON determinista, se guardan con media type dedicado y se conserva el digest. |
| Verificar lo almacenado antes de éxito terminal | El coordinator compara el digest declarado, verifica rol/tipo/tamaño, ejecuta `ArtifactStore.verify()` y lee los bytes de vuelta para comprobar el SHA-256. |
| Acotar y rechazar salidas inconsistentes | Los modelos superan el límite de 64 MiB o digest incorrecto hacen fallar el Job antes de persistir un resultado exitoso; tests cubren el rechazo sin escribir artefactos. |

El PR [#441](https://github.com/SauronShepherd/ronin/pull/441) pasó CI Python 3.11/3.12, calidad, seguridad, verificación, ledgers y Docker qualification (**8m54s**, PostgreSQL, worker Docker real y aceptación estricta). En Windows, la suite completa pasó **3752 tests con 51 omitidos**; la cobertura de `studio_storage/artifacts.py` subió a **80,263%**, por lo que el baseline con margen de 2,1 puntos se actualizó de 77,30% a 78,17% tanto en `coverage-storage-files` como en `coverage-storage-files-full`. La puerta local por archivo pasó para 54 módulos.

La salida durable expone URI, digest, media type y tamaño. PR #443 registra las ejecuciones exitosas en MLRun/versiones candidatas, #445 integra el registro en Studio, #446 añade lectura HTTP autorizada y descarga UI acotada, #447 fija resultados/checkpoints al runtime y las dependencias, #448 integra promoción directa tras el registro y #449 integra retry selectivo. Siguen abiertos cualificación con ArtifactStore remoto, política de retención integrada con todos los productores/referencias y limpieza administrada de artefactos. P8 permanece parcial y release-qualified sigue en **0% (0/14)**.

## 23. Registro de resultados de ejecuciones durables

**Progreso técnico: 3/3 criterios implementados y exact-head cualificados en `main@c2df903`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Registrar sólo una ejecución exitosa con artifact materializado | `POST /v1/ml-studio/executions/{run_id}/register` exige estado `succeeded`, metadatos completos y ArtifactStore disponible; revalida tamaño y SHA-256 antes de escribir en el registry. |
| Crear procedencia y versión candidata idempotentes | Registra Experiment y MLRun ligados al Lab/dataset, luego el model version con digest, firma inferida y referencia content-addressed; el registry hace idempotentes escrituras idénticas y rechaza conflictos. |
| Promover directamente el candidato recién registrado | El formulario de éxito conserva una acción Promote candidate que reutiliza `mlPromote()`, pide el motivo obligatorio y llama al endpoint existente protegido por autorización. |

Las pruebas de API verifican el flujo tabular, la firma/digest/procedencia y el rechazo de ejecuciones aún activas; Playwright recorre registro y promoción hasta `champion`. El handler requiere autorización `ml-studio:write`; el contenido del artifact no se sirve por este endpoint. PR #448 pasó localmente el flujo focalizado (**3/3**), la suite web completa (**79/79**) y todos los checks requeridos; los seis workflows exact-head post-merge de `main@a5d6a24` también pasaron. PR #449 cerró el retry selectivo; la qualification S3-compatible de la sección 27 está en curso. P8 sigue parcial y release-qualified permanece en **0% (0/14)**.

## 24. Lectura HTTP autorizada de artifacts de modelos

**Progreso técnico: 6/6 criterios implementados y exact-head cualificados en `main@c2df903`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Autorizar por permiso de lectura y workspace | `GET /v1/ml-studio/models/{model_id}/{version}/artifact` usa `ml-studio:read` y busca la versión dentro del `WorkspaceId` autenticado. |
| Verificar la referencia antes de revelar bytes | El digest debe ser SHA-256 válido; el ArtifactStore recupera por ref+digest y el handler vuelve a verificar digest y límite de 64 MiB. |
| Acotar transferencia y permitir reanudación | Responde Base64 en bloques de hasta 512 KiB, con offset, next_offset, tamaño total, digest y media type para reconstrucción/reanudación. |
| Rechazar rangos ambiguos o fuera de límites | Parámetros desconocidos/duplicados, offset inválido o longitudes fuera de rango fallan antes de responder. |
| Descargar desde la UI sin cargar el artifact entero en una respuesta | La UI solicita bloques acotados, valida identidad, metadatos y continuidad de offsets y sólo crea el archivo al completar el tamaño declarado. |
| Probar la reconstrucción del artifact en navegador | Playwright simula un artifact de dos bloques, verifica ambos offsets, el nombre descargado y el estado de éxito. |

Las pruebas de API cubren reconstrucción por varios bloques, aislamiento por workspace, rango, límites y corrupción. Playwright verifica el flujo de descarga desde el registry; OpenAPI documenta parámetros y respuesta. PR #446 y PR #447 pasaron sus checks Docker/CI; los seis workflows exact-head post-merge de `main@c2df903` también pasaron. La qualification contra ArtifactStore S3-compatible se está añadiendo en la sección 27. P8 continúa parcial y release-qualified permanece en **0% (0/14)**.

## 25. Identidad de runtime y dependencias para checkpoints ML

**Progreso técnico: 6/6 criterios implementados; cualificación exact-head aprobada en `main@c2df903`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Calcular identidad estable del ejecutor | SHA-256 de runner, dominio, compiler, orquestación, runtime, calidad, clustering y registry de backends. |
| Incluir entorno y backend efectivo | Huella incluye versión completa de Python, versiones de paquetes ML, clase/backend y fingerprint opcional declarado por el proveedor. |
| Incluir opciones de ejecución | Parameters, clusters y max_iterations forman parte de la huella; la misma request con opciones distintas no reutiliza outputs. |
| Descartar checkpoints de otro runtime | Tests guardan checkpoints obsoletos y comprueban que el training vuelve a ejecutarse; la caché sólo se guarda si la identidad es estable. |
| Persistir procedencia del output | La huella de runtime queda en el checkpoint de selección y en el payload durable `ExperimentResult`/`ClusteringResult`. |
| Invalidar outputs downstream cuando cambia una dependencia | Cada checkpoint incorpora un digest canónico de las salidas de sus nodos upstream; la discrepancia descarta y vuelve a calcular esa etapa y sus dependientes. |

El PR #447 (`main@6db8573`) pasó **164 tests ML/API**, Ruff, formato, mypy del runner y CI 3.11/3.12. Docker qualification verificó PostgreSQL, worker real y aceptación estricta; después del merge pasaron los seis workflows exact-head de `main@6db8573`, `main@a5d6a24` y `main@c2df903`. La huella es deliberadamente conservadora: cualquier cambio en los módulos ejecutables invalida los checkpoints, y un backend sin código fuente o fingerprint declarado no reutiliza caché. La suite también prueba que alterar un output intermedio impide restaurar su evaluación y selección antiguas. PR #449 cierra retry selectivo observable. Queda una política explícita de retención integrada con todos los productores y referencias. P8 sigue parcial y release-qualified permanece en **0% (0/14)**.

## 26. Reintentos selectivos observables de ejecuciones ML

**Progreso técnico: 6/6 criterios implementados y cualificados exact-head en `main@c2df903`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Reintentar sólo una ejecución fallida del workspace autenticado | `POST /v1/ml-studio/executions/{run_id}/retry` requiere `ml-studio:execute`, comprueba el workspace y rechaza jobs activos, exitosos, cancelados o de otro tipo. |
| Crear una ejecución hija idempotente | El body fija un nuevo `run_id` y una etapa; el snapshot durable conserva `retry_of_run_id` y `retry_from_stage`, y el store rechaza reusar el ID con otra petición. |
| Limitar el punto de reanudación a etapas presentes y soportadas | OpenAPI y backend permiten `profile`, `quality_gate`, `prepare`, `train`, `evaluate` y `select`; IDs vacíos, sin recortar, demasiado largos o con controles se rechazan. |
| Reutilizar checkpoints previos a la etapa elegida | El hijo carga los checkpoints del job padre sólo si mantienen identidad de pipeline, request, runtime y dependencias; descarta el punto seleccionado y las etapas posteriores. |
| Exponer la operación en Studio | Ante un job fallido, la UI solicita ID y etapa, crea el retry y continúa observando el hijo por el flujo de ejecución existente. |
| Verificar backend, contrato y navegador | Suite focalizada durable/HTTP/OpenAPI: **28 passed**; Playwright focalizado: **1 passed**; suite web completa: **80 passed**. La prueba de orquestación verifica fallo y éxito al reintentar desde `train`, conservación del profiling y dos llamadas de entrenamiento. |

La suite Python completa pasó **3.766 tests con 51 omitidos**. Ruff, formato, mypy focalizado, snapshot OpenAPI y diff check pasan. El PR #449 (`main@c2df903`) pasó CI Python 3.11/3.12, Web, Security, Release, Status consistency y Docker qualification (**8m33s**, PostgreSQL, worker Docker real y aceptación estricta); los seis workflows post-merge exact-head también pasaron. La ejecución local del script Docker en Windows Desktop no cualificó por limitaciones de bind mount/Compose y falta de DSN, por lo que la evidencia Linux de CI es la calificación del candidato. P8 continúa parcial y release-qualified permanece en **0% (0/14)**.


## 27. Qualification ML con ArtifactStore S3-compatible

**Progreso técnico: 4/4 criterios implementados y cualificados exact-head en `main@68a3c0f9118458eaa49a5090877133b8226eb989`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Validar input durable de más de 1 MiB contra un servicio S3-compatible | El Job guarda el snapshot de filas por `S3ArtifactStore` y el worker recupera sus bytes desde LocalStack en Docker; el journey usa un bucket efímero por test. |
| Materializar y leer el modelo desde almacenamiento remoto | El resultado tabular durable conserva URI `s3://`, digest y media type; el test lee de vuelta bytes y compara SHA-256. |
| Aplicar retención sólo con referencias vivas completas | La colección conserva el input aún referenciado por el Job y el modelo; elimina únicamente un objeto de prueba marcado como no referenciado. |
| Automatizar la qualification en Docker CI | El Docker workflow usa LocalStack 4.3.0 fijado por digest y ejecuta el journey dedicado con credenciales locales sin secretos externos. |

El test de lifecycle y los contratos del adapter S3 pasaron **15/15** contra LocalStack en Docker. PR #450 pasó los checks del PR y los seis workflows post-merge exact-head de `main@6dc051ec18d8c54cb61bab37aba59a72f8dc843a`; PR #451 hizo lo mismo en `main@1edb11a5123bf9ef3c29b7eb2d6d189cc459b8ea`, y PR #452 en `main@68a3c0f9118458eaa49a5090877133b8226eb989`. La qualification Docker de #452 duró **9m12s** e incluyó PostgreSQL, worker real y aceptación estricta. El endpoint LocalStack es efímero y el bucket queda aislado por test. P8 sigue parcial; release-qualified permanece en **0% (0/14)**.

## 28. Selección de algoritmos en ejecuciones durables

**Progreso técnico: 4/4 criterios implementados y cualificados exact-head en `main@68a3c0f9118458eaa49a5090877133b8226eb989`.**

| Criterio técnico | Evidencia |
| --- | --- |
| Compilar una selección compatible con la tarea | `compile_lab_pipeline()` valida algoritmo/tarea y fija la selección en parámetros canónicos de PipelineIR. |
| Ejecutar el algoritmo fijado en el job | `LocalExperimentRunner` usa el valor de PipelineIR al crear `TrainingSpec`; las pruebas verifican el algoritmo del resultado. |
| Evitar ejecución silenciosa por adaptadores heredados | Si el runner no puede ejecutar un pipeline personalizado, el coordinator falla cerrado; no vuelve al algoritmo predeterminado. |
| Exponer y cualificar la selección | OpenAPI enumera los algoritmos, Studio ofrece selector por tarea y Playwright verifica el request; CI, Web, Security, Release, Status consistency y Docker pasaron exact-head. |

PR [#452](https://github.com/SauronShepherd/ronin/pull/452) añade la selección para classification/regression y conserva K-Means para clustering. El digest completo de PipelineIR también forma parte de la huella de checkpoints, por lo que una selección distinta no reutiliza outputs de otra configuración. P8 continúa parcial y release-qualified sigue en **0% (0/14)**.

## 29. Preprocesamiento numérico reproducible

**Progreso técnico: 4/4 criterios implementados y cualificados exact-head en `main@cee103b9c37ebedddd7364499d276639809b6a1b`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Separar preparación de datos del algoritmo | `TrainingSpec` admite `identity` y `standard_scale`; el runner lee la opción de PipelineIR. |
| Ajustar parámetros sólo con el conjunto de entrenamiento | Media y desviación se calculan después del split; columnas constantes usan escala 1 y no generan NaN/inf. |
| Persistir la transformación para inferencia segura | Artefactos canónicos v3 guardan la transformación; el lector mantiene compatibilidad con artefactos v2 y valida forma, finitud y escalas positivas. |
| Exponerlo de forma durable y verificable | La API/OpenAPI y Studio permiten seleccionar preprocesador; pruebas cubren regresión, ensembles, entrada manipulada y selección fijada por PipelineIR. |

PR [#453](https://github.com/SauronShepherd/ronin/pull/453) pasó Python 3.11/3.12, Playwright 80/80 y Docker qualification en **9m36s**, con PostgreSQL, worker real y aceptación estricta. Los seis workflows post-merge —CI, Web, Security, Release, Status consistency y Docker qualification— pasaron exact-head; Docker terminó en **9m32s**. Los transformadores se ajustan sólo con filas de entrenamiento; el artefacto v3 es declarativo y el lector conserva compatibilidad con v2. P8 permanece parcial y release-qualified continúa en **0% (0/14)**.

## 30. Codificación one-hot de features categóricas

**Progreso técnico: 4/4 criterios implementados y cualificados exact-head en `main@6b6a479722df30276b1b725bb3936aa50370f7f6`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Usar roles categóricos declarados por el Lab | El runner fija en PipelineIR el preprocesador `one_hot` y pasa sólo las columnas con rol `categorical`. |
| Ajustar vocabulario sin filtrar datos de evaluación | El vocabulario se aprende únicamente de las filas de entrenamiento; categorías no vistas generan un vector de ceros. |
| Acotar y validar expansión | Vocabularios ordenados limitan cada columna a 256 valores y la salida a 4096 features; se rechazan valores categóricos mayores que 1024 caracteres. |
| Persistir y verificar para inferencia | El artefacto v3 guarda vocabularios canónicos y valida su forma; API, OpenAPI, Studio, ejecución durable y Playwright incluyen el preprocesador. |

PR [#454](https://github.com/SauronShepherd/ronin/pull/454) pasó las matrices Python 3.11/3.12, Web, Security, Release, Status consistency y Docker. Docker qualification terminó en **8m23s** en el PR y en **8m22s** exact-head. La batería local focalizada pasó **63 pruebas**; Playwright completó **78/80** y las dos pruebas de navegación intermitentes pasaron al repetirse aisladas. Los vocabularios de categorías se ajustan sólo con el split de entrenamiento, quedan persistidos en artefactos v3 y asignan vector cero a categorías desconocidas. P8 permanece parcial y release-qualified continúa en **0% (0/14)**.

## 31. Candidato: imputación numérica reproducible

**Progreso técnico: 4/4 criterios implementados y cualificados exact-head en `main@fcce4c673997d8c93fe12d22bd2aff2d3002591d`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Permitir valores ausentes con una elección explícita | `median_impute` acepta `null` y celdas CSV vacías en features numéricas; los demás preprocesadores mantienen su rechazo estricto. |
| Ajustar imputación sin filtrar la evaluación | Las medianas se calculan sólo con filas de entrenamiento; una columna totalmente ausente en entrenamiento se rechaza con error explicable. |
| Reutilizar la transformación al inferir | El artefacto v3 guarda una mediana finita por feature y la predicción reemplaza ausentes con esos valores persistidos. |
| Conectarlo al flujo durable y al contrato público | PipelineIR, runner, API, OpenAPI y Studio exponen `median_impute` únicamente para Labs numéricos; hay cobertura de runtime, runner y API. |

La verificación local pasó **69 pruebas Python focalizadas y 81/81 Playwright**. PR [#455](https://github.com/SauronShepherd/ronin/pull/455) pasó CI Python 3.11/3.12, Web, Security, Release, Status consistency y Docker qualification (**8m19s**). Los seis workflows post-merge exact-head de `main@fcce4c673997d8c93fe12d22bd2aff2d3002591d` también pasaron; Docker terminó en **9m20s**. Ruff, formato, mypy, OpenAPI, ledger de capacidades, sintaxis JavaScript y `git diff --check` pasan. El artefacto v3 fija una mediana finita por feature y la reutiliza en inferencia; se rechazan columnas sin valor de entrenamiento. P8 permanece parcial y release-qualified continúa en **0% (0/14)**.

## 32. Candidato: retención de artefactos con referencias vivas

**Estado: parcial; inventario y planificación completos; borrado manual acotado en curso; limpieza automática global aún bloqueada por la consistencia entre stores.**

| Requisito | Criterio de diseño |
| --- | --- |
| Descubrir referencias sin depender del llamador | Enumerar revisiones del catálogo, snapshots de archivos locales, evidencia y checkpoints durables, MLRun records, versiones registradas, salidas de conectores, revisiones de ingeniería de datos y exports sintéticos. Una fuente incompleta debe impedir el barrido. |
| Preservar objetos vivos durante carreras concurrentes | Separar inventario de candidatos de borrado; volver a comprobar referencias inmediatamente antes de eliminar y hacer la operación idempotente. |
| Operación observable y acotada | Exponer primero un plan dry-run con digest, rol, edad y fuente; paginar el inventario y limitar objetos por ciclo. |
| No borrar datos generales al limpiar resultados ML | Identificar roles y productores de cada objeto; no eliminar un digest sólo porque una referencia de ML dejó de existir si otro producto lo usa. |

`discover_artifact_references()` ya construye el snapshot de las nueve familias desde los stores reales y falla cerrado ante errores o topes excedidos. `collect_unreferenced()` requiere ahora un store paginado y límites explícitos; termina de leer el inventario antes de borrar, por lo que un inventario incompleto o sobre el tope no produce borrados parciales. La primitiva sigue confiando en el conjunto vivo del llamador. El test de LocalStack protege input y modelo en una llamada manual. La lectura de seis stores no tiene transacción distribuida: la limpieza automática global permanece deshabilitada hasta definir e implementar una barrera de consistencia y una revalidación segura ante escrituras concurrentes. P8 sigue parcial y release-qualified permanece en **0% (0/14)**.

## 33. Candidato: componer codificación categórica e imputación numérica

**Progreso técnico: 4/4 criterios implementados y cualificados exact-head en `main@24218a7f1e29c74242266900a6adf1262c9d5382`.**

| Criterio técnico | Evidencia local |
| --- | --- |
| Aceptar Labs mixtos con categorías y números ausentes | La nueva opción `one_hot_median_impute` acepta `null`/celdas vacías numéricas y conserva validación estricta de columnas categóricas. |
| Evitar fuga de datos para ambas transformaciones | Medianas y vocabularios se ajustan independientemente sólo sobre el split de entrenamiento. |
| Persistir una transformación reproducible | Artefactos v3 guardan vocabularios categóricos y medianas por nombre de columna; predicción reproduce ambas etapas y rechaza metadata inválida. |
| Exponerlo al flujo durable y al usuario | PipelineIR, runner, API, OpenAPI y Studio ofrecen la opción; runtime, runner, endpoint durable y Playwright tienen cobertura. |

La verificación local pasó **72 pruebas Python focalizadas**. La suite Playwright completa registró **80/81** en la primera corrida; el único timeout ocurrió en una prueba de Synthetic Studio y pasó al repetirse aislada (**1/1**). PR [#456](https://github.com/SauronShepherd/ronin/pull/456) pasó Python 3.11/3.12, Web, Security, Release, Status consistency, verificación, calidad y Docker. Los seis workflows post-merge exact-head también pasaron; Docker terminó en **10m03s**, con cobertura PostgreSQL, worker real y aceptación estricta. La integración no modifica la semántica de `one_hot` ni de `median_impute` elegidas por separado. P8 sigue parcial y release-qualified permanece en **0% (0/14)**.

## 34. Inventario dry-run para retención de artefactos

**Progreso técnico: primera etapa cualificada en `main@58911b4d19dd922de31f08e47c6b82db5e7cb32e`; la agregación de las nueve familias quedó implementada en PR #460 y cualificada exact-head en `main@d1c44a59e64bf49a8033231c4b9047a00e41e361`.**

| Criterio | Evidencia local |
| --- | --- |
| Exigir el conjunto conocido de fuentes | `plan_unreferenced()` requiere revisiones de catálogo, salidas de conectores, revisiones de ingeniería de datos, resultados y checkpoints durables, archivos locales, MLRun, versiones registradas y exports sintéticos; rechaza fuentes desconocidas. |
| Fallar cerrado ante cobertura incompleta | Una fuente ausente devuelve `all_required_sources_supplied=false` y ningún candidato. Un inventario que supera el límite también devuelve cero candidatos. |
| Limitar el inventario | Usa páginas cuando el store implementa `PagedArtifactStore`, con tamaño de página, máximo de páginas y máximo de objetos configurables y validados. |
| Hacer el primer paso no destructivo | El plan lista digests candidatos ordenados y no llama a `delete`; las pruebas verifican que candidatos y objetos vivos siguen presentes. |

La batería focalizada de artifacts/paginación pasó **38 pruebas** y la suite Python completa pasó **3791 pruebas, 52 omitidas**. Ruff, formato, mypy, `git diff --check` y el gate portátil de cobertura (**54 archivos**) pasan. Los tests elevaron la cobertura de `artifacts.py` de 78.17% a 86.18%, por encima del piso de 80%; se quitó su baseline legacy de ambos gates de Makefile. PR [#457](https://github.com/SauronShepherd/ronin/pull/457) y los seis workflows post-merge exact-head de `main@58911b4` pasaron; Docker terminó en **8m20s** con cobertura PostgreSQL, worker real y aceptación estricta. El inventario de productores encontró nueve familias en `put_bytes()`; PR #460 añadió el snapshot automático completo, cualificado en `main@d1c44a59e64bf49a8033231c4b9047a00e41e361`. La limpieza global permanece deshabilitada por la consistencia temporal entre stores. P8 sigue parcial y release-qualified permanece en **0% (0/14)**.

## 35. Descubrimiento de referencias de catálogo y ML

**Progreso técnico: 4/4 criterios implementados y cualificados exact-head en `main@87e34810f606a1ee325b353cba100d568fb02255`.**

| Criterio | Evidencia local |
| --- | --- |
| Enumerar revisiones completas del catálogo | `CatalogStore.list_revisions()` queda en el port y en SQLite/PostgreSQL; la búsqueda recorre todas las workspaces, assets y revisiones. |
| Preservar inputs de archivos locales | Las referencias `artifact://sha256/...` de assets `file` se registran además como fuente `local_files`. |
| Enumerar referencias del registry ML | Se recogen artifact refs/runtime snapshots de MLRun y se validan refs/digests de cada versión registrada. |
| Mantener el fallo cerrado para fuentes pendientes | El snapshot cubre cuatro de nueve familias; al pasarlo al planner, las otras cinco ausentes impiden devolver candidatos. |

La cobertura focalizada pasa **21 pruebas**; la integración real PostgreSQL está añadida al gate Docker. PR #458 y sus seis workflows post-merge exact-head, incluido Docker, pasaron en `main@87e34810f606a1ee325b353cba100d568fb02255`. Esta etapa descubre cuatro familias; PR #459 y #460 completaron las nueve, pero la retención global sigue deshabilitada mientras falte consistencia temporal entre fuentes independientes.

## 36. Descubrimiento de evidencia y checkpoints de jobs durables

**Progreso técnico: 3/3 criterios implementados; PR #459 y los seis workflows post-merge exact-head, incluido Docker, pasaron en `main@ba25baa253c300377695ea2c970a938be68be3a0`.**

| Criterio | Evidencia local |
| --- | --- |
| Recorrer jobs y todos sus runs con límites | El descubridor pagina globalmente el `JobStore`, incluye runs históricos, acota páginas y número total de runs, y rechaza cursores repetidos o inventarios que exceden los topes. |
| Conservar evidencia durable disponible | Se agregan evidencias disponibles de ArtifactStore sólo cuando URI y digest coinciden; evidencia tombstoned/missing no se trata como referencia viva. |
| Cubrir resultados y checkpoints persistidos | Se inspecciona JSON de resultados celulares y se separan `ml-node-checkpoint` de otros resultados; JSON o pares URI/digest inválidos fallan cerrado. |

La suite focalizada pasa **49 pruebas**, con **2 integraciones PostgreSQL omitidas** sin `RONIN_POSTGRES_TEST_DSN`; la prueba de inventario PostgreSQL queda incorporada al gate Docker. Ruff, formato, mypy de almacenamiento y `git diff --check` pasan. Esta etapa cubre dos familias; PR #460 completa el descubrimiento de las nueve.

## 37. Descubrimiento de conectores, Data Engineering y exports sintéticos

**Progreso técnico: 4/4 criterios implementados y cualificados en PR #460 y los seis workflows post-merge exact-head de `main@d1c44a59e64bf49a8033231c4b9047a00e41e361`.**

| Criterio | Evidencia local |
| --- | --- |
| Recoger salidas de conectores comprometidas | `SqliteConnectorCheckpointStore.list_committed_outputs()` excluye placeholders, detecta pares incompletos y está limitada; el descubridor valida URI/digest. |
| Cubrir cada revisión de Data Engineering | SQLite y PostgreSQL enumeran proyectos/pipelines y revisiones históricas con `LIMIT max+1`; sobrepasar el tope genera error en vez de snapshot parcial. La prueba Docker detectó y corrigió un `FOR UPDATE` inválido sobre `MAX(revision)`, serializando ahora escrituras con la fila de estado del pipeline. |
| Conservar exports sintéticos persistidos | Se recorren runs y exports registrados, validando cada par URI/digest dentro de topes de runs y exports. |
| Formar las nueve fuentes requeridas | `discover_artifact_references()` ejecuta los seis enumeradores, combina las nueve familias y falla completo ante error o fuente faltante. |

La suite focalizada pasa **32 pruebas**, con **1 integración PostgreSQL omitida** localmente por no tener DSN; la integración se ejecuta en Docker. Ruff, formato, mypy y `git diff --check` pasan. El agregador no ofrece una transacción distribuida sobre los seis stores: la vista previa sigue siendo no destructiva y la eliminación global permanece deshabilitada hasta definir una política de consistencia temporal entre productores.

## 38. Topes de lectura para el descubrimiento de referencias

**Estado: implementado y cualificado en PR #461 y los seis workflows post-merge exact-head de `main@518880fdb30d2ecd1ec08a221c699afd29eb6be4`.**

| Criterio | Evidencia |
| --- | --- |
| Acotar las fuentes que antes leían colecciones completas | Workspaces, assets y revisiones de catálogo, runs ML y modelos registrados aceptan límites; SQLite/PostgreSQL leen como máximo `limit + 1` y rechazan overflow sin entregar un snapshot parcial. |
| Aplicar topes globales al snapshot agregado | El descubridor limita workspaces, assets, revisiones, runs y modelos; cada fuente conserva sus topes configurables y falla cerrado. |
| Cubrir adapters y regresiones | Tests SQLite verifican resultados bajo el tope y errores por overflow; la integración PostgreSQL prueba el límite de runs en el gate Docker. |

La suite focalizada pasa **31 tests**, con **7 integraciones PostgreSQL omitidas** en Windows sin DSN; la suite completa pasó **3809 tests y omitió 54**. Mypy de `studio_storage` y `studio_ml`, Ruff, el ledger de capacidades y `git diff --check` pasan. Los gates de cobertura midieron mejoras por esta cobertura: `workspaces.py` de 61,62% a 65,10% y, al incluir las integraciones, `postgres_core.py` de 37,61% a 41,51%. El baseline de workspaces se actualizó a la cobertura medida; el de PostgreSQL quedó en 41,40% para evitar comparar el porcentaje real con el valor redondeado al alza. El gate PostgreSQL/Docker incorporó el test con dos runs ligados a un dataset válido, cobertura completa de PostgreSQL, worker real y aceptación estricta (**8m23s**). Los seis workflows post-merge exact-head de `main@518880f` pasaron. El plan de retención sigue en modo preview; estos topes previenen inventarios parciales o sin cota, pero no eliminan la carrera entre fuentes independientes.

## 39. Paginación local de artefactos con memoria acotada

**Estado: integrado en PR #462 y cualificado en los seis workflows post-merge exact-head de `main@4469f3e984cb3596e88584b1387bb4fbe81eb256`.**

| Criterio | Evidencia |
| --- | --- |
| Evitar cargar el inventario completo por página | `LocalArtifactStore.list_digests_page()` conserva sólo `page_size + 1` digests usando selección incremental sobre el árbol; ya no llama a `list_digests()`. |
| Mantener recorrido estable entre páginas | El cursor opaco guarda el último digest de la página y la lectura siguiente filtra lexicográficamente, sin offsets que cambien al borrar objetos anteriores. |
| Proteger el contrato de paginación | La prueba prohíbe materializar el inventario completo, recorre dos páginas y comprueba cursor inválido; el planner continúa fallando cerrado al exceder topes. |

La suite focalizada de artifacts/paginación pasa **13 tests**; la suite Python completa pasa **3810 tests y omite 54** por integraciones externas no configuradas y limitaciones de Windows. Ruff, formato, mypy de `artifacts.py`, ledger de capacidades y `git diff --check` pasan. Los checks del PR y los seis workflows exact-head post-merge pasan; Docker incluye PostgreSQL, worker real y aceptación estricta. El recorrido mantiene memoria O(page size), aunque sigue escaneando nombres de archivo para localizar la página siguiente.

## 40. Borrado de artifacts tras inventario acotado

**Estado: integrado en PR #464 y cualificado en los seis workflows post-merge exact-head de `main@de0091d8ea4caa0b58e00f47bc0c3405d1016ade`.**

| Criterio | Evidencia |
| --- | --- |
| Evitar leer todos los digests a la vez | `collect_unreferenced()` exige `PagedArtifactStore`, pagina el inventario y limita páginas y objetos (10 000 por defecto). |
| Evitar borrado parcial ante inventario incompleto | Primero valida y termina el recorrido completo; sólo después empieza a borrar candidatos. Overflow, cursores inválidos/repetidos o stores sin paginación fallan antes de borrar. |
| Mantener explícito el límite de seguridad | La lista viva sigue siendo responsabilidad del llamador; esto acota la operación, pero no hace atómica la observación de seis fuentes ni permite activar limpieza global automática. |

Las pruebas focalizadas pasan **25 tests**, incluyendo inventario paginado sin `list_digests()`, overflow de objetos, tope de páginas y rechazo de stores sin paginación; Ruff, formato, mypy de `retention.py` y `git diff --check` pasan. La suite local registró **3813 pasadas y 54 omitidas**, con un timeout de 15 s en `test_step_03_validate_accepts_demo_project`; al repetir ese test aislado pasó (**1/1**). CI, Release, Security, Status consistency y Docker del PR pasaron; los seis workflows post-merge exact-head de `main@de0091d` también, con PostgreSQL, worker real y aceptación estricta.

## 41. Lecturas acotadas de evidencia y resultados de jobs

**Estado: integrado en PR #466 y cualificado en los seis workflows post-merge exact-head de `main@f1a068f94772b36950538ce8c18c8db10309dc81`.**

| Criterio | Evidencia |
| --- | --- |
| No materializar toda la evidencia de un run | SQLite, PostgreSQL y memoria ofrecen lecturas `limit + 1`; el descubridor impone el máximo de 100 refs por run. |
| Limitar resultados celulares | Las lecturas de resultados usan `LIMIT limit + 1`, fallan cerrado si el run supera 10 000 resultados o el presupuesto total de 100 000. |
| Cubrir adapters reales y fallos de overflow | Tests verifican topes por run y globales; la integración PostgreSQL prueba que `limit=0` sólo lee un registro centinela. |

Las pruebas focalizadas de descubrimiento y JobStore pasan **46 tests**; Ruff, formato, mypy focalizado y `git diff --check` pasan. La suite local completa registró **3817 pasadas y 54 omitidas**, más un `FailedHealthCheck` transitorio de Hypothesis por generación lenta en `test_lexical_order_equals_chronological_order`; el test pasó aislado (**1/1**). Las matrices CI Python 3.11/3.12 pasaron. Docker qualification pasó en **9m34s**, incluyendo S3-compatible storage, PostgreSQL, worker Docker real y aceptación estricta. Los seis workflows post-merge exact-head de `main@f1a068f` también pasaron. P8 sigue parcial y la cualificación release permanece en **0% (0/14)**.


## 42. DAG v2 de candidatos de clasificación y regresión

**Progreso técnico del incremento: 100% (5/5 criterios y cualificación exact-head completados). Integrado por PR #470 en `main@cf7618b`; los seis workflows post-merge exact-head pasaron. Avance global estimado: 76%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Mantener compatibilidad con pipelines v1 | `PipelineIR/v1` conserva su payload exacto; la configuración por nodo se limita a `PipelineIR/v2`. |
| Ejecutar varios candidatos en un grafo fijado | El compiler construye perfil, quality gate y prepare compartidos, de 2 a 8 ramas train/evaluate y un select que depende de todas. |
| Elegir un resultado reproducible | La selección usa métrica y dirección explícitas, valida compatibilidad con la tarea y desempata por ID de nodo. `mean_squared_error` usa `minimize` por defecto. |
| Exponerlo en ejecuciones durables | El endpoint acepta `candidate_algorithms`, `selection_metric` y `selection_direction`; OpenAPI limita nombres, cardinalidad y opciones. El digest del PipelineIR v2 queda fijado en el Job y checkpoints. |
| Rechazar planes parciales o inválidos antes de entrenar | El runner valida la forma completa del DAG, parejas train/evaluate, dependencias, tareas, métricas y algoritmos soportados por el backend antes de ejecutar nodos. |


Las pruebas focalizadas ML, plugin durable y OpenAPI pasan **71/71**; el contrato Docker pasa **5/5**. La suite completa pasó **3824 tests con 54 omitidos**; mypy cubrió 457 archivos, Ruff, formato, snapshot OpenAPI y las puertas de cobertura pasaron. La cualificación real Docker pasó **23 tests, 0 fallos y 2 omitidos**; la puerta estricta de aceptación pasó **15/15** (15 esperados, sin faltantes ni inesperados). La imagen calificó con ID inmutable `sha256:94d0bc18af7162d92fd3ffcd625e2c4e7af2c02e797e93afc4d52812c2c365bd`. El PR #470 y los seis workflows post-merge exact-head de `main@cf7618b` pasaron. Este incremento no habilita DAGs arbitrarios, clustering configurable, registros dentro del grafo, etapas definidas por plugins ni búsqueda de hiperparámetros. P8 sigue parcial y la cualificación release permanece en **0% (0/14)**.


## 43. Selección de candidatos de clustering en PipelineIR v2

**Progreso técnico: implementado y cualificado localmente; pendiente de CI y merge. Avance global integrado: 76%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Compilar candidatos de K-Means en un DAG fijado | `candidate_cluster_counts` compila de 2 a 8 ramas con `k` único entre 2 y 32; el grafo conserva perfil, quality gate y preparación compartidos. |
| Seleccionar con un criterio que penalice complejidad | La selección usa Calinski-Harabasz y maximiza la puntuación; no usa inertia sola, que tiende a premiar más clusters. Empates resuelven por ID del nodo train. |
| Rechazar configuraciones inválidas antes de entrenar | El runner valida forma/configuración completa y comprueba cada `k` contra el tamaño de filas antes de iniciar cualquier candidato. |
| Hacer durable y auditable la selección | El endpoint fija el PipelineIR v2; el resultado y checkpoint conservan métrica y puntuación de selección además de inertia y digest del modelo. |
| Conservar compatibilidad y contratos públicos | PipelineIR v1 y ejecuciones anteriores conservan sus payloads; OpenAPI limita cantidad y rango de `k` y declara Calinski-Harabasz. |

Las pruebas focalizadas de clustering, runner, servicios, API durable y OpenAPI pasan **48/48**. La suite local completa pasa **3833 tests y omite 54**; mypy pasa sobre 457 archivos, Ruff, formato, snapshot OpenAPI y `git diff --check` pasan. Docker qualification pasa **21 tests y omite 2** por falta de DSN PostgreSQL en Windows; la aceptación estricta pasa **15/15**. Queda pendiente la cualificación Linux exact-head del PR. El alcance no añade algoritmo externo, selección de features ni hyperparameter search; P8 permanece parcial y release-qualified en **0% (0/14)**.
