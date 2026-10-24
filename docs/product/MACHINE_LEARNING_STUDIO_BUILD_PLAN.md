# Machine Learning Studio — build plan de bajo nivel

**Alcance vigente (2026-10-24):** Ningún nivel de Ronin incluye GenAI, RAG ni ejecución de agentes. Las coding-agent skills se consumen externamente. Multiusuario, su administración y despliegue pertenecen a Ronin Pro. El progreso agregado de release Public v1 es 0% (0/13 familias activas); las referencias históricas de este plan a 0/14 conservan el denominador anterior.

## Estado del plan

**Estado actual verificado en la consolidación derivada de `main@e01bb411870e1c1661bea37d88247e8648606952`:** la implementación técnica del alcance provider-neutral está completada y los checks exact-head de CI, Docker, seguridad, web, cobertura y artefactos pasan. La auditoría del plan ejecutó también las superficies candidatas de PipelineIR v3, etapas plugin, deployment/serving, drift, suites de calidad, features, bundles y MLflow. El avance de release público sigue en **0% (0/13 familias activas)** porque depende de recorridos de producto, proveedores externos y decisiones humanas que este repositorio no puede certificar. La limpieza automática global de artefactos continúa deshabilitada. El límite de PipelineIR v2 es 24 nodos, las cuadrículas algoritmo×preprocesador se limitan a ocho combinaciones y clustering conserva su selector separado.

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

1. Resolver refs de datasets contra `CatalogStore`; el resolver acotado de CSV/JSONL está implementado para quality, ejecución síncrona, ejecución asíncrona, pipelines y reintentos. El criterio quedó integrado y cualificado en el PR #512.
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

`discover_artifact_references()` ya construye el snapshot de las nueve familias desde los stores reales y falla cerrado ante errores o topes excedidos. `collect_unreferenced()` requiere ahora un store paginado y límites explícitos; termina de leer el inventario antes de borrar, por lo que un inventario incompleto o sobre el tope no produce borrados parciales. PR #482 hace que una lista viva vacía falle por defecto; borrar todo requiere un booleano explícito. Esto evita que una omisión accidental de referencias vacíe el store, pero la primitiva todavía confía en el conjunto vivo del llamador. El test de LocalStack protege input y modelo en una llamada manual. La lectura de seis stores no tiene transacción distribuida: la limpieza automática global permanece deshabilitada hasta definir e implementar una barrera de consistencia y una revalidación segura ante escrituras concurrentes. P8 sigue parcial y release-qualified permanece en **0% (0/14)**.

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

**Progreso técnico: 5/5 criterios implementados y cualificados en PR #471; integrado en `main@e20733d`. Los checks del PR y los seis workflows post-merge exact-head pasaron, incluido Docker. Avance global integrado: 77%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Compilar candidatos de K-Means en un DAG fijado | `candidate_cluster_counts` compila de 2 a 8 ramas con `k` único entre 2 y 32; el grafo conserva perfil, quality gate y preparación compartidos. |
| Seleccionar con un criterio que penalice complejidad | La selección usa Calinski-Harabasz y maximiza la puntuación; no usa inertia sola, que tiende a premiar más clusters. Empates resuelven por ID del nodo train. |
| Rechazar configuraciones inválidas antes de entrenar | El runner valida forma/configuración completa y comprueba cada `k` contra el tamaño de filas antes de iniciar cualquier candidato. |
| Hacer durable y auditable la selección | El endpoint fija el PipelineIR v2; el resultado y checkpoint conservan métrica y puntuación de selección además de inertia y digest del modelo. |
| Conservar compatibilidad y contratos públicos | PipelineIR v1 y ejecuciones anteriores conservan sus payloads; OpenAPI limita cantidad y rango de `k` y declara Calinski-Harabasz. |

Las pruebas focalizadas de clustering, runner, servicios, API durable y OpenAPI pasan **48/48**. La suite local completa pasa **3833 tests y omite 54**; mypy pasa sobre 457 archivos, Ruff, formato, snapshot OpenAPI y `git diff --check` pasan. Docker local pasa **21 tests y omite 2** por falta de DSN PostgreSQL en Windows; la aceptación estricta pasa **15/15**. PR #471 pasó matrices 3.11/3.12, calidad, seguridad, Release, status consistency y Docker (**9m25s**); los seis workflows post-merge exact-head de `main@e20733d` pasaron, incluido Docker. El alcance no añade algoritmo externo, selección de features ni hyperparameter search; P8 permanece parcial y release-qualified en **0% (0/14)**.


## 44. Selección de candidatos en la interfaz de ML Studio

**Progreso técnico: 5/5 criterios implementados y cualificados; PR #472 integrado en `main@47e16fa` y los seis workflows post-merge exact-head pasaron. Avance global integrado: 78%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Elegir un algoritmo o comparar candidatos supervisados | La tabla de Labs ofrece selección múltiple de algoritmos; uno conserva el flujo de ejecución individual y dos o más envían `candidate_algorithms`. |
| Comparar candidatos K-Means desde el mismo flujo | Para clustering, la tabla ofrece conteos `k` múltiples y requiere al menos dos; la UI envía `candidate_cluster_counts`. |
| Mantener un payload correcto para cada tarea | El generador de muestra no agrega target cuando el Lab de clustering no lo define y sólo envía parámetros soportados. |
| Hacer accesibles las opciones | Los controles múltiples incluyen nombres accesibles y una instrucción visible para la cantidad mínima. |
| Verificar interacción de navegador | Playwright comprueba los cuerpos durable para selección de algoritmos y conteos; la suite web completa pasa **82/82** en un worker. |

El recorrido añadido con Playwright pasa aislado y dentro de la suite completa. El primer pase paralelo dio **81/82** por timeout transitorio en Debugger Studio; el test pasó aislado y la repetición serial pasó **82/82**. PR #472 pasó Web y Docker; los seis workflows post-merge exact-head de `main@47e16fa` también pasaron. Este incremento no cambia la API ni altera la selección individual existente; P8 permanece parcial y release-qualified en **0% (0/14)**.


## 45. Acotar memoria y presupuesto de búsqueda de hiperparámetros

**Progreso técnico del incremento: 5/5 criterios implementados y cualificados; PR #473 integrado en `main@1994778` y los seis workflows post-merge exact-head pasaron. Avance global integrado: 79%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Evitar expandir cuadrículas completas | El modo `grid` consume `itertools.product` de forma perezosa y detiene la generación en `max_trials`. |
| Muestrear espacios grandes de forma acotada | Los modos `random` y `bayesian` eligen índices únicos reproducibles sobre la cardinalidad del producto y decodifican sólo las pruebas elegidas. |
| Limitar la propuesta Bayesian | El conjunto de candidatos se limita a un máximo de 1000 pruebas, incluso cuando el espacio cartesiano tiene miles de millones de combinaciones. |
| Validar presupuesto y estructura en runtime | `max_trials` se limita a 1..1000; se rechazan tipos incorrectos, parámetros vacíos/duplicados y semillas inválidas. |
| Probar cardinalidad, determinismo y API durable | Tests cubren un espacio de 1000³, unicidad/reproducibilidad y la ejecución API de plugin. |



## 46. Identidad y semillas deterministas para trials

**Progreso técnico del incremento: 4/4 criterios implementados y cualificados; PR #475 integrado en `main@7df81a7` y los seis workflows post-merge exact-head pasaron. Avance global integrado: 80%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Repetir identidad de trial por parámetros y semilla de búsqueda | `trial_id` deriva del JSON canónico de parámetros y `SearchSpec.random_seed`; resultados con métricas distintas conservan la misma identidad de configuración. |
| Variar seed reproduciblemente entre configuraciones | Si no se declara `seed` como parámetro, cada trial deriva un seed scikit-learn de 32 bits desde la semilla de búsqueda y el `trial_id`. Un parámetro `seed` explícito conserva su precedencia. |
| Hacer estable el registro durable | `MLRunId` y `ModelVersion` se forman con el identificador del trial, no con su posición en la respuesta. |
| Verificar repetición y separación entre runs | Tests prueban identidad/seed estables al repetir, semillas diferentes entre configuraciones y ejecuciones API repetibles. |

La primera iteración focalizada detectó que al insertar el derivador de seed se había desplazado la indentación de los métodos `Trial.metric()`/`to_payload()`; se corrigió y el conjunto relevante pasó **37/37**. La suite completa pasó **3849 tests con 54 omitidos**; Ruff, formato, mypy (455 archivos) y `git diff --check` pasan. Docker local pasó **21 tests con 2 omitidos** por falta de `RONIN_POSTGRES_TEST_DSN`; la aceptación estricta pasó **15/15**. PR #475 pasó matrices Python 3.11/3.12, calidad, seguridad, Release, Status consistency, Web y Docker qualification (**9m24s**, con PostgreSQL, worker Docker real y aceptación estricta). Los seis workflows post-merge exact-head de `main@7df81a7` también pasaron, incluido Docker.


## 47. Validación anticipada del espacio de búsqueda

**Progreso técnico del incremento: 4/4 criterios implementados y cualificados; PR #476 integrado en `main@6507b97` y los seis workflows post-merge exact-head pasaron. Avance global integrado: 81%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Validar la búsqueda completa antes de iniciar training | Se comprueba toda la lista de valores configurados antes del loop, incluso valores que no llegarían a consumirse por el límite de trials. |
| Rechazar parámetros incompatibles con el Lab | La búsqueda supervisada permite `seed` y, para clasificación, `C`/`max_iter`; clustering y cualquier parámetro de regresión distinto de `seed` fallan antes de entrenar. |
| Acotar dominios peligrosos o inválidos | `seed` debe ser entero no negativo, `max_iter` entero 1..100000 y `C` numérico finito en (0, 1000000]. |
| Evitar ejecución parcial por un valor inválido tardío | Tests espían al runner y prueban que un valor inválido al final del dominio, nombres desconocidos y seeds inválidos dejan cero ejecuciones. |

Las pruebas focalizadas de optimización y ejecución API pasaron **41/41**; la suite completa pasó **3853 tests y omitió 54**. Ruff, formato, mypy (455 archivos) y `git diff --check` pasaron. Docker local pasó **21 tests y omitió 2** sin `RONIN_POSTGRES_TEST_DSN`; la aceptación estricta pasó **15/15**. PR #476 pasó CI 3.11/3.12, calidad, seguridad, Release, Status consistency, Web y Docker qualification (**9m45s**, con PostgreSQL, S3-compatible LocalStack, worker Docker real y aceptación estricta); los seis workflows post-merge exact-head de `main@6507b97` también pasaron.


## 48. Parada bayesiana por falta de mejora reciente

**Progreso técnico del incremento: 4/4 criterios implementados y cualificados; PR #477 integrado en `main@cc0ad8f` y los seis workflows post-merge exact-head pasaron. Avance global integrado: 82%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Medir paciencia sobre la secuencia reciente de trials | La política compara el mejor resultado actual con el mejor anterior a los últimos `patience` trials, respetando `maximize` y `minimize`. |
| Aplicar la política en el endpoint de búsqueda | Bayesian search acepta `stop_policy` con `max_trials`, `patience` y `min_improvement`; el loop termina antes de proponer otra configuración cuando se cumple. |
| Rechazar límites inválidos | Se rechazan bools como enteros, contadores no enteros, mejoras negativas, NaN/inf y claves desconocidas. |
| Mantener memoria acotada y propuestas actuales | Se conserva sólo una candidata pendiente y se recalcula después de cada observación, en vez de acumular lotes obsoletos. |

La cobertura focalizada pasó **47/47** y verifica umbrales en ambas direcciones, validación de tipos y parada efectiva del endpoint. La suite completa pasó **3859 tests y omitió 54**; Ruff, formato, mypy (457 archivos), `git diff --check` y el ledger público pasaron. Docker local pasó **21 tests y omitió 2** sin DSN PostgreSQL; la aceptación estricta pasó **15/15**. PR #477 pasó CI 3.11/3.12, calidad, seguridad, Release, Status consistency, Web y Docker qualification (**9m40s**, con PostgreSQL, S3-compatible LocalStack, worker Docker real y aceptación estricta); los seis workflows post-merge exact-head de `main@cc0ad8f` también pasaron.


## 49. Criterios de desempate configurables en la comparación de trials

**Progreso técnico del incremento: 4/4 criterios implementados y cualificados; PR #478 integrado en `main@a8e1120` y los seis workflows post-merge exact-head pasaron. Avance global integrado: 83%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Aplicar objetivo y criterios secundarios en orden | Ranking estable: métrica primaria, tie-breakers configurados con dirección propia y `trial_id` como último desempate. |
| Evitar comparaciones parciales | Search valida que la métrica primaria y todos los desempates existen para la tarea antes de iniciar training; ranking rechaza métricas faltantes, no numéricas o no finitas. |
| Rechazar configuraciones ambiguas | No se permiten métricas repetidas, el objetivo primario como tie-breaker ni direcciones distintas de `maximize`/`minimize`. |
| Exponer la configuración al consumidor | Compare/search API devuelve y consume los desempates; la UI permite configurar métricas y dirección. |

La suite focalizada de optimización y ejecución API pasó **53/53**; Playwright pasó **82/82**. Las suites Python completas de CI pasaron en 3.11 y 3.12. La suite local previa pasó **3864 tests y omitió 54**; un test HTTP ajeno al cambio falló por EOF en una de las cuatro solicitudes del servidor local y pasó **1/1** al repetirse aislado. Otro test asíncrono de ejecución de candidatos superó el timeout dentro de una ejecución cargada, y pasó **1/1** al repetirse aislado. OpenAPI, consistencia de rutas y superficie de Studio pasaron **37/37**, junto con el snapshot OpenAPI, la consistencia de 171 rutas y la superficie publicada. Ruff, formato, mypy (457 archivos), ledger y `git diff --check` pasan. Docker local pasó **21 tests y omitió 2** por falta de DSN PostgreSQL; la aceptación estricta pasó **15/15**. PR #478 pasó CI 3.11/3.12, quality, security, release, status consistency, web y Docker qualification (**9m31s**, PostgreSQL, LocalStack, worker Docker real y aceptación estricta); los seis workflows post-merge exact-head de `main@a8e1120` también pasaron.

## 50. Acotar y cerrar el contrato de tie-breakers

**Progreso técnico del incremento: 4/4 criterios implementados y cualificados; PR #480 integrado en `main@ba3106b` y los seis workflows post-merge exact-head pasaron. Avance global: 84%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Limitar el costo de rankings configurables | Se aceptan como máximo ocho tie-breakers tanto en `SearchSpec` como en las APIs; OpenAPI declara el mismo límite. |
| Mantener el esquema estricto | Cada elemento sólo admite `metric` y `direction`, igual que el contrato OpenAPI `additionalProperties: false`. |
| Fallar antes de entrenar | Search rechaza campos desconocidos y configuraciones sobre el límite antes de ejecutar el runner. |
| Cubrir ambos puntos de entrada | Pruebas de compare, search y dominio cubren campos extra y el límite máximo. |

Este ajuste se encontró al comparar el parser de Python con el esquema OpenAPI añadido en PR #478: el esquema prohibía claves extra, pero el handler las aceptaba. La batería focalizada pasó **64 pruebas**; Ruff, formato, snapshot OpenAPI y mypy (457 archivos) pasan. PR #480 pasó CI, Web, Security, Release, Status consistency y Docker qualification (**9m30s**); los seis workflows post-merge exact-head de `main@ba3106b` también pasaron. La cualificación Docker local pasó **21 pruebas**, omitió dos pruebas PostgreSQL por falta de DSN local y superó la aceptación estricta **15/15**.

## 51. Opt-in explícito para limpiar un inventario sin referencias vivas

**Progreso técnico del incremento: 3/3 criterios implementados y cualificados; PR #482 integrado en `main@33a7b45` y los seis workflows post-merge exact-head pasaron. Avance global: 85%; release-qualified: 0% (0/14).**

| Criterio | Implementación |
| --- | --- |
| Evitar borrar todo por una lista viva vacía accidental | `collect_unreferenced()` rechaza el conjunto vacío antes de paginar o borrar. |
| Permitir vaciado total sólo con intención explícita | `allow_empty_live_set=True` autoriza borrar todos los objetos del inventario completo y acotado. |
| Rechazar una opción ambigua o mal tipada | El opt-in acepta exclusivamente valores booleanos y los tests prueban el rechazo de texto. |

La cobertura focalizada de artefactos y referencias pasó **26 pruebas**; Ruff, formato, mypy y `git diff --check` pasan. Docker local pasó **21 pruebas**, omitió dos pruebas PostgreSQL por falta de DSN y superó la aceptación estricta **15/15**. PR #482 pasó CI Python 3.11/3.12 y Docker qualification (**9m32s**); los seis workflows post-merge exact-head de `main@33a7b45` también pasaron. Esta guarda reduce el riesgo de la operación manual, pero no ofrece consistencia temporal entre los seis stores ni habilita la limpieza global automática.

## 52. Primitiva PostgreSQL para coordinar productores y recolección

**Estado del fundamento: implementado en candidato y probado contra PostgreSQL 16 en Docker. Avance global del Studio: permanece en 85%; esta primitiva no activa ni cualifica la recolección global.**

| Criterio del fundamento | Evidencia |
| --- | --- |
| Permitir publicación concurrente entre productores | `PostgresArtifactReferenceBarrier.writer()` adquiere el advisory lock compartido de sesión en una conexión dedicada. |
| Excluir publicaciones mientras se calcula y borra | `collector()` adquiere el lock exclusivo; un timeout PostgreSQL acotado hace fallar cerrado si la coordinación tarda más de 30 s por defecto. |
| Probar exclusión entre procesos y liberación | Tests unitarios cubren modo de lock, timeout y liberación ante excepciones; una prueba de integración verifica que el recolector espera a los escritores y que nuevos escritores esperan al recolector. Los 12 tests pasan contra PostgreSQL 16 efímero en Docker. |

Las secciones 53–59 instrumentan productores de conectores, ML, Data Engineering, worker, catálogo/archivos locales y exports sintéticos. La sección 60 unifica descubrimiento, inventario y borrado bajo `collector()`, pero no lo programa ni configura la composición: el llamador aún debe pasar el mismo DSN PostgreSQL a todos los escritores. Quedan por cubrir Jobs/evidencia/checkpoints fuera de ML y revisar cualquier referencia adicional antes de habilitar cleanup global. La limpieza global automática permanece deshabilitada hasta cualificar el commit exact-head y completar el cableado productivo.

## 53. Mantener el lock del productor de conectores hasta el checkpoint

**Estado del slice: implementado en candidato y validado con 48 tests dirigidos. Avance global: 85%; el recolector global continúa deshabilitado.**

| Criterio | Evidencia |
| --- | --- |
| Compartir un contrato de barrera entre storage y productores | `ArtifactReferenceBarrier` declara leases `writer()` y `collector()`; PostgreSQL implementa ambos. |
| Proteger el intervalo crítico de sync | `IngestionSyncService.execute()` admite barrera opcional y conserva el lock desde `destination.write()` hasta `commit_output_then_checkpoint()`. El lease se libera si cualquiera de los dos pasos falla. |
| Verificar el orden de publicación y referencia | Una prueba de sync comprueba `lock → artifact → reference → unlock`; suites de sync, checkpoints, registry, capabilities y PostgreSQL pasan **48/48**. |

La composición local ya cablea la misma instancia de barrera al adapter HTTP de
ingesta y al servicio de sync. El perfil PostgreSQL protege bytes, destino y
checkpoint dentro del mismo lease; SQLite conserva el flujo local. No cubre los
otros productores ni hace segura la recolección global por sí sola.

## 54. Proteger artefactos de ejecuciones durables de ML

**Estado del slice: instrumentado en candidato; 30 tests ML dirigidos pasan. Avance global: 85%; la recolección global sigue deshabilitada.**

| Criterio | Evidencia |
| --- | --- |
| Proteger inputs grandes hasta crear el Job que los referencia | `JobStoreExecutionStore.create()` mantiene el lease desde `ArtifactStore.put_bytes()` hasta `submit()` durable. |
| Proteger checkpoints de nodo hasta guardar su referencia | `save_node_checkpoint()` mantiene el lease durante la materialización y `worker_put_cell_result()`. |
| Proteger el modelo final hasta completar el Job | `finish_claim_with_result()` cubre materialización verificada y commit de `ml-result`. |
| Compartir la coordinación en perfil PostgreSQL | La composición local inyecta una instancia `PostgresArtifactReferenceBarrier` en el host de plugins; el perfil SQLite conserva el modo actual sin barrera. |

La prueba de regresión observa que el artefacto y su submit quedan dentro del mismo lease; las suites de ejecución ML y orchestration pasan **30/30**, Ruff y mypy focalizado pasan. Las secciones 53, 55, 56 y 57/58 cubren conectores, revisiones de Data Engineering, evidencias/checkpoints del worker, catálogo/archivos y exports sintéticos. La recolección global sigue deshabilitada hasta completar la cualificación del candidato y revisar cualquier productor nuevo.

## 55. Proteger revisiones de Data Engineering hasta su commit durable

**Estado del slice: implementado en candidato y cubierto por 45 tests dirigidos conjuntos. Avance global: 85%; recolección automática global deshabilitada.**

`RevisionApplication.import_sdp()` ahora admite la barrera compartida y mantiene el lease durante la escritura de project YAML, documentos de pipeline, metadata y `RevisionRecordStore.save()`. El plugin y la composición PostgreSQL pasan la instancia común; SQLite conserva el comportamiento existente. Una prueba verifica el orden `lock → artefactos → referencia → unlock`. Las suites de Data Engineering, conectores y ejecución ML pasan **45/45**; Ruff y mypy focalizado pasan. Las secciones 57/58 completan catálogo/archivos locales y exports sintéticos; aún faltan Jobs/evidence/checkpoints fuera de ML y cualquier productor adicional.

## 56. Proteger evidencias y checkpoints del worker durable

**Estado del slice: PR #489 integrado en `main@77bf1c1` y cualificado en los seis workflows post-merge exact-head. Avance global: 85%; recolección global deshabilitada hasta cualificar el candidato y revisar productores nuevos.**

`DurableWorkerExecution` mantiene el lease compartido desde la escritura del artefacto hasta el commit de evidencia/checkpoint y resultado, también para resultados del scheduler. `LocalWorkerRuntime` y `BrokerWorkerRuntime` inyectan la barrera PostgreSQL cuando usan el perfil PostgreSQL; la adquisición asíncrona evita bloquear el event loop y libera la sesión si se cancela durante la adquisición.

La barrera pasó tests de liberación y cancelación; una prueba de integración confirmó que PostgreSQL 16 impide entrar al colector exclusivo mientras el writer async publica. Ruff, formato, mypy y `git diff --check` pasan. La suite amplia local terminó con **3.927 pasadas y 17 omitidas**; la cualificación de ejecución real pasó **7/7** contra contenedores Docker y una base PostgreSQL limpia, la aceptación estricta v0.1 pasó **15/15** y la integración S3 con LocalStack pasó **1/1**. PR #489 se integró en `main@77bf1c1`; CI, Security, Release, Status consistency, Web y Docker post-merge exact-head pasaron. Las secciones 57/58 cubren Catalog/local files y exports sintéticos. Aún faltan productores de Jobs/evidence/checkpoints fuera de ML y cualquier productor adicional antes de habilitar limpieza global.

## 57. Coordinar ingesta de archivos con referencias del catálogo

**Estado del slice: PR #490 integrado en `main@2475bc9`; los seis workflows post-merge exact-head pasaron. Avance global: 85%.**

`LocalFileConnector.ingest()` acepta una barrera opcional y mantiene el writer lease desde `ArtifactStore.put_bytes()` hasta completar assets, revisiones y lineage en el catálogo. Sin barrera conserva el flujo SQLite/local actual. La prueba de orden valida `lock → artifact → assets → revisions → lineage → unlock`, además de la resolución del dataset existente.

La suite focalizada de ingesta y plugin sintético pasa **30 pruebas**, con un skip de symlink porque Windows no concede ese privilegio. En el árbol combinado posterior, la suite amplia pasó **3.930 pruebas y omitió 17**; Ruff, formato, mypy y `git diff --check` pasan. PR #490 pasó Docker qualification y los seis workflows post-merge exact-head.

## 58. Coordinar el export de Synthetic Data Studio

**Estado del slice: PR #490 integrado en `main@2475bc9`; los seis workflows post-merge exact-head pasaron. Avance global: 85%.**

El plugin recibe la barrera común de `PluginContext` y protege el intervalo de `GovernStudioService.export()` —que persiste la referencia del export— hasta la materialización física con `ArtifactStore.put_bytes()`. La prueba comprueba el orden `lock → durable reference → artifact → unlock`; un fallo en el bloque también libera el lease.

La limpieza global sigue deshabilitada. Siguen pendientes productores no inventariados o que no comparten una transacción/lease desde bytes hasta referencia, junto con demostrar que la composición de servidor pasa el mismo PostgreSQL de coordinación a todas las rutas soportadas.

## 59. Proteger registros manuales de modelos ML

**Estado del slice: PR #491 integrado en `main@7b427aa`; los seis workflows post-merge exact-head pasaron. Avance global: 85%.**

Las rutas síncronas de ML que escriben un modelo directamente sin crear antes un Job —`persist_clustering_result()`, `register_clustering_model()` y `train_register_tabular()`— aceptan la barrera opcional y conservan el lease desde `put_bytes()` hasta persistir la referencia de run/model. `MachineLearningStudioPlugin` inyecta la misma barrera de `PluginContext` usada por el perfil PostgreSQL.

Una prueba de regresión verifica el orden `lock → artifact → run reference → model reference → unlock`. Suites de seguridad de artefactos, API de ML y registro end-to-end pasan **42/42**; la suite amplia combinada pasa **3.930 pruebas y omite 17**. PR #491 pasó CI, Security, Release, Status consistency, Web y Docker; los seis workflows post-merge exact-head de `main@7b427aa` también pasaron. El cleanup global continúa apagado mientras haya otros productores sin lease común.

## 60. Unificar snapshot, inventario y borrado bajo el collector lease

**Estado del slice: PR #492 integrado en `main@83da3e7`; los seis workflows post-merge exact-head pasaron. Avance global: 85%; limpieza automática global deshabilitada.**

`collect_referenced_artifacts()` exige la barrera exclusiva y ejecuta dentro de un solo `collector()` el descubrimiento completo de las fuentes actualmente soportadas, la validación de límites/inventario paginado y la eliminación. Si cualquier fuente falla o el inventario supera sus límites, no elimina nada; si el conjunto vivo está vacío, exige `allow_empty_live_set=True`. La API no programa recolección automática.

Las suites de almacén, descubrimiento, barrera PostgreSQL y recolector guardado por advisory lock real pasaron **44/44** contra PostgreSQL 16. La suite amplia pasó **3.933 pruebas y omitió 17**; la ejecución real Docker/worker/replay **8/8**, la aceptación estricta v0.1 **15/15** y S3 con LocalStack **1/1**. PR #492 pasó Docker qualification (**9m45s**), y CI, Web, Security, Release, Status consistency y Docker post-merge exact-head de `main@83da3e7` pasaron. La limpieza global sigue deshabilitada. La siguiente auditoría encontró una referencia fuera del inventario: evidencia de QueryFlux devuelta por HTTP sin registro durable ni lease común.

## 61. Registrar referencias de evidencia QueryFlux para retención

**Estado: PR #493 integrado y cualificado en `main@fa8d22c`; los seis workflows post-merge exact-head pasaron. Prioridad: bloquea habilitar recolección global. Avance global: 85%.**

`queryflux_execute` exige un registro durable de referencia, y `execute_query` mantiene el writer lease desde `ArtifactStore.put_bytes()` hasta el commit de `(project_id, run_id, attempt_id, storage_ref, digest)`. La composición local crea el registro en SQLite o PostgreSQL; el descubrimiento acotado lo incorpora como una décima fuente requerida y falla cerrado si excede el máximo o encuentra digest/ref inconsistentes. La prueba del endpoint y del lease, el registro de referencias y la retención real en PostgreSQL cubren el nuevo camino.

La batería focalizada de QueryFlux, descubrimiento, retención y PostgreSQL pasa **61 pruebas**; la suite amplia pasa **3.937 pruebas y omite 16**. Ruff, formato, mypy de producto (459 archivos), y `git diff --check` pasan. PR #493 pasó Docker qualification (**10m03s**), CI, Web, Security, Release y Status consistency; los seis workflows post-merge exact-head de `main@fa8d22c` también pasaron. La auditoría del cableado encontró un store sintético en memoria dentro de la composición local; la limpieza global automática sigue apagada hasta hacer persistentes y enumerables todas las fuentes y verificar el llamador productivo.

## 62. Alinear el backend PostgreSQL del worker con el servidor

**Estado: PR #494 integrado en `main@2d8fc73`; los seis workflows post-merge exact-head pasaron, incluido Docker qualification (9m53s). Validación focalizada: 6/6. Avance global: 85%.**

La entrada `ronin worker` no pasaba `RONIN_POSTGRES_DSN` a `LocalWorkerRuntimeConfig`, aunque `ronin serve` sí abría PostgreSQL. En despliegues con `RONIN_STORAGE_BACKEND=postgres`, el servidor y el worker podían operar sobre bases distintas, eludiendo la barrera compartida de referencias de artefactos. El CLI ahora valida el backend igual que el servidor y construye la configuración del worker con el DSN; SQLite sigue siendo el valor predeterminado. Las pruebas cubren PostgreSQL con DSN obligatorio, propagación del DSN y configuración SQLite. Este cambio no habilita recolección automática.

## 63. Persistir el registro de exports sintéticos en la composición local

**Estado: PR #495 integrado; los seis workflows post-merge exact-head pasaron. Avance global: 85%.**

La composición local creaba `GovernStudioService()` sin store, por lo que `snapshot()` y `artifacts()` olvidaban los runs y referencias de exportación al reiniciar. Ahora inyecta la ruta de un `SqliteRunStore` persistente dentro del directorio de datos; el propio plugin crea y cierra el store. Una prueba genera y exporta una tabla, reconstruye la composición, verifica que el run y la referencia sobreviven y vuelve a leer los bytes por digest. También se corrigió `LocalServerComposition.stop()` para cerrar los sockets reservados si se construyó una composición que nunca se inició, y el coordinador ML detiene su polling antes de cerrar el store. El test de reinicio cubre la reutilización de puertos. Esto hace inventariable la fuente sintética local; no activa recolección automática ni resuelve otras fuentes aún ausentes en la composición.

## 64. Aplicar límites reales al inventario de exports sintéticos

**Estado: PR #496 integrado; los seis workflows exact-head pasaron, incluido Docker qualification. Avance global: 85%.**

La auditoría del inventario sintético detectó que `snapshot()` y `artifacts()` materializaban todos los runs/exports antes de comprobar los máximos, de modo que los límites no acotaban memoria. `GovernStudioService` y sus stores ahora aceptan `limit`, y el scanner solicita como máximo `límite + 1` para detectar una fuente que exceda o ignore el tope y fallar cerrado. Pruebas con `SqliteRunStore` y dobles que ignoran el límite confirman el comportamiento para runs y exports. No se habilita borrado global.

## 65. Usar checkpoints durables PostgreSQL para ingesta de conectores

**Estado: PR #497 integrado en `main@b3b3bae`; los checks del PR y Docker Linux pasaron. La [CI post-merge](https://github.com/SauronShepherd/ronin/actions/runs/39635072783) encontró una carrera en `test_cancel_of_terminal_job_is_safe` (3.12: se canceló un Future todavía en cola al cerrar el executor). [PR #499](https://github.com/SauronShepherd/ronin/pull/499) corrigió el cierre, pasó CI 3.11/3.12 y [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39637990524), y quedó cualificado en `main@ded20cd` por los seis workflows exact-head. Avance global: 85%.**

La composición local PostgreSQL exponía rutas de conectores pero no montaba `IngestionHTTPAdapter`; además, el perfil sólo disponía de checkpoints SQLite y el inventario de outputs sintéticos de una fuente distinta. `PostgresConnectorCheckpointStore` implementa el contrato CAS/fencing, recuperación de evidencia, salud e inventario acotado en PostgreSQL. La composición usa este store en el perfil PostgreSQL e inyecta la misma barrera de referencias que protege los bytes y el commit del checkpoint; SQLite conserva su store local. La prueba de integración verifica fencing obsoleto, persistencia tras reconstrucción, descubrimiento de digests y rechazo del inventario que supera el límite. La cualificación exact-head de `main@ded20cd`, que también cubre la corrección de la carrera de cierre, está ejecutándose.

## 66. Exponer la retención como operación manual y fail-closed

**Estado: [PR #498](https://github.com/SauronShepherd/ronin/pull/498) integrado en `main@714093c`; 8 pruebas del operador y 79 pruebas dirigidas de retención/conectores/PostgreSQL pasan. Docker qualification del PR pasó en 10m23s y la aceptación estricta pasó 15/15. Los seis workflows post-merge exact-head pasaron, incluidos [CI](https://github.com/SauronShepherd/ronin/actions/runs/39636907613), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39636907841), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39636907753), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39636907592), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39636907481) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39636907515). Avance global: 85%; el recolector global automático continúa deshabilitado.**

`ronin artifacts retention preview` descubre las fuentes de referencia conocidas y devuelve los candidatos sin mutar el store. El perfil SQLite sólo ofrece una vista previa que no sincroniza escritores concurrentes. La respuesta incluye `live_reference_count` y sólo declara `collection_ready` si el snapshot está coordinado, completo, revisado y contiene referencias vivas. `collect` exige `--confirm` y perfil PostgreSQL, usa el mismo advisory lease exclusivo que los productores, mantiene topes de inventario y conserva el rechazo de live set vacío salvo `--allow-empty-live-set`. Si el inventario de plugins no está disponible o contiene plugins fuera de la lista revisada, la colección falla cerrada y la vista previa los enumera. La operación no se agenda ni corre automáticamente. La integración PostgreSQL real y la ejecución del CLI en Docker pasan localmente; los seis workflows post-merge exact-head de `main@714093c` también pasaron.

## 67. Integrar checkpoints PostgreSQL durables de conectores

PR #497 integró la implementación descrita en la sección 65 como `main@b3b3bae`. Su Docker qualification del PR pasó; la CI 3.12 post-merge reveló la carrera de cierre de Synthetic Data descrita en la sección 69. PR #499 la corrigió y cualificó `main@ded20cd` en los seis workflows exact-head.

## 68. Estado de cualificación de retención

PR #496 (scanner de exports sintéticos acotado) quedó integrado en `main@216d7d4` con sus seis workflows exact-head aprobados. PR #497 añadió checkpoints PostgreSQL de conectores en `main@b3b3bae`; sus checks del PR pasaron, pero la CI post-merge encontró la carrera de cierre que arregla PR #499. PR #498 integró el CLI manual en `main@714093c`; Docker qualification pasó en 10m23s y los seis workflows exact-head también. PR #499 corrigió la carrera en `main@ded20cd`, pasó sus checks Python y Docker (10m15s, aceptación estricta 15/15), y los seis workflows post-merge exact-head también pasaron: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39639566313), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39639566445), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39639566286), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39639566104), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39639566434) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39639566281). La suite Docker local de Windows pasó 21 pruebas y la aceptación 15/15; dos pruebas específicas de worker PostgreSQL se omitieron sin DSN. Al ejecutarlas con el DSN del PostgreSQL Docker, dos pasaron y la prueba de recuperación tras `SIGKILL` no reutilizó tres checkpoints en Docker Desktop/Windows; la cualificación Linux de CI sí pasó. La auditoría de productores y fuentes se registra en la sección 70. La recolección automática global sigue apagada; sólo se permite la operación manual explícita con PostgreSQL, inventario acotado completo, writer/collector lease común y ningún plugin sin revisar. Avance global: **85%**; release-qualified: **0% (0/14)**.

## 69. Preservar Jobs sintéticos en cola al cerrar el servicio

La suite completa de CI post-merge de `main@b3b3bae` expuso una carrera: `LocalGenerationJobs.close()` usaba `shutdown(wait=True, cancel_futures=True)`, que podía cancelar una tarea todavía en cola mientras su fila durable seguía en estado `queued`. Al reabrir el store, el trabajo podía quedarse sin Future ejecutable y acabar en estado `cancelled` en lugar de completarse.

PR #499 cambió el cierre a `shutdown(wait=True)` para dejar drenar las tareas en cola y añadió una regresión determinista que comprueba tanto la conservación del Future como la fila durable. Los cuatro tests focalizados pasan localmente; CI 3.11 y 3.12 pasan, y [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39637990524) completa pasó en 10m15s con PostgreSQL, S3, worker real y aceptación estricta 15/15. El cambio se integró como `main@ded20cd`; también pasaron los seis workflows post-merge exact-head: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39639566313), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39639566286), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39639566104), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39639566434), [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39639566281) y [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39639566445). La prueba extendida de worker con `SIGKILL` pasó en Linux Docker qualification; en Docker Desktop/Windows no recuperó los tres checkpoints esperados, por lo que ese resultado local queda registrado como limitación de plataforma.

## 70. Mantener inventariado el grafo de productores de artefactos

La revisión estática del árbol de producto encontró **16 llamadas a `put_bytes()` en 14 funciones**. Los recorridos internos de conectores, revisiones de Data Engineering, QueryFlux, catálogo/archivos, jobs/checkpoints/resultados ML, modelos manuales, exports sintéticos y worker durable se cubren con los diez grupos de referencias requeridos por `discover_artifact_references()`. En los recorridos activos, el writer lease cubre la publicación de los bytes hasta el commit de la referencia; el CLI mantiene el collector lease durante snapshot, inventario y borrado. Los perfiles SQLite no ofrecen `collect`, y plugins no revisados o un inventario de plugins no disponible bloquean la recolección.

`tests/test_artifact_writer_inventory.py` añade una guarda AST: si se agrega o elimina una llamada productiva a `put_bytes()`, el inventario revisado debe actualizarse. También comprueba que `persist_pipeline_evidence()` —helper exportado sin caller interno actual y sin lease propio— no se conecte a una ruta de producto sin revisión explícita. La prueba pasa localmente junto con Ruff, formato y `git diff --check`. Esta auditoría respalda sólo la operación manual confirmada con PostgreSQL; no habilita borrado programado. El DAG configurable, `register` como etapa ejecutable y la integración con etapas definidas por plugins siguen pendientes; P8 conserva estado parcial.


## 71. Cualificar la auditoría del inventario de productores

PR [#500](https://github.com/SauronShepherd/ronin/pull/500) integró la guarda AST del inventario de escritores y esta actualización del plan como `main@2287f311c04397034bc94e03fbd82fbd5bc6db62`. Pasaron los seis workflows exact-head: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39643021688), [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39643021707), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39643021695), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39643021790), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39643021731) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39643021729). Docker ejecutó cobertura PostgreSQL, worker real y aceptación estricta.

El hito valida el inventario y la operación manual de retención; no cierra P8. Continúan pendientes la ejecución de DAGs configurables, `register` como etapa y la extensión de etapas por plugins. La recolección automática global sigue deshabilitada. Avance técnico: **85%**; release-qualified: **0% (0/14)**.


## 72. Exponer DAGs candidatos acotados por la API

PR [#502](https://github.com/SauronShepherd/ronin/pull/502) permite enviar un PipelineIR v2 al endpoint durable de ejecuciones. El request se limita a 20 nodos; el servidor completa y valida `lab_digest`, backend, tarea y seed contra el Lab actual, valida la forma y algoritmos contra el runner, y fija ese IR en el Job antes de ejecutar. Los grafos candidato admitidos conservan etapas compartidas de perfil/calidad/preparación, parejas train/evaluate y un único select. `register`, configuraciones incompatibles y runners que no pueden validar IR propio fallan antes de crear el Job.

La suite focalizada ML/dominio/orquestación/OpenAPI pasó **92 pruebas**; la suite local completa pasó **3.917 y omitió 59** por Docker/servicios externos y condiciones de Windows. Ruff, formato, mypy, snapshot OpenAPI y ledger pasan. Docker qualification del PR [terminó en 10m09s](https://github.com/SauronShepherd/ronin/actions/runs/39653870271), con PostgreSQL, worker real y aceptación estricta. PR #502 se integró como `main@eff4bdb3b3d2ed32b40cf48e59cbb567048df2a4`; pasaron exact-head [CI](https://github.com/SauronShepherd/ronin/actions/runs/39655444736), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39655444712), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39655444686), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39655444782), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39655444738) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39655444700). Avance técnico global: **86%**; release-qualified: **0% (0/14)**.

## 73. Cualificar ramas de preparación y recuperación de checkpoints

PR [#503](https://github.com/SauronShepherd/ronin/pull/503) permite que un DAG candidato use hasta ocho nodos `prepare` configurados independientemente, todos conectados al quality gate y consumidos por candidatos train/evaluate; el validador rechaza nodos no usados o mal conectados antes de crear el Job. Los checkpoints de preparación guardan el preprocesador y las columnas categóricas, y la recuperación interpreta los payloads antiguos que no los incluían con los valores de identidad.

La regresión ejecuta dos ramas de preparación y reanuda desde checkpoints intermedios, verificando que cada rama conserva el preprocesador correcto. Pasaron **96 pruebas focalizadas en Docker/Python 3.11**, incluyendo runner, dominio, API, orquestación, servicios, OpenAPI y capability matrix. PR #503 pasó Python 3.11/3.12 y Docker qualification (**9m47s**, PostgreSQL, worker Docker real y aceptación estricta); tras integrar `main@3ba0ab70a137f6019d85c8063148c2f873a913e6`, también pasaron exact-head [CI](https://github.com/SauronShepherd/ronin/actions/runs/39658934449), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39658934417), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39658934400), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39658934405), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39658934504) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39658934459). Avance técnico global: **87%**; release-qualified: **0% (0/14)**. La recolección automática global de artefactos continúa deshabilitada.


## 74. Cuadrículas acotadas de candidatos algoritmo×preprocesador

PR [#505](https://github.com/SauronShepherd/ronin/pull/505) habilita comparar combinaciones de algoritmos y preprocesadores en clasificación/regresión. El compiler rechaza listas incompatibles y cuadrículas de más de ocho combinaciones antes de crear el Job; el runner limita PipelineIR v2 a 24 nodos y clustering conserva su selector independiente. Studio envía ambas dimensiones y aplica el mismo límite en cliente.

La suite focalizada pasó **60 pruebas Python**, Ruff, formato y mypy; los **6 tests Playwright** pasaron dentro de `mcr.microsoft.com/playwright:v1.64.1-noble`. PR #505 pasó matrices Python 3.11/3.12 y Docker qualification (**9m50s**). Integrado en `main@ad53878fac49330d29824dabf1f27e4c4bd2d9d8`; pasaron los seis workflows exact-head: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39700960235), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39700960229), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39700960325), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39700960259), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39700960249) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39700960231). Avance técnico: **89%**; release-qualified: **0% (0/14)**. La selección genérica de algoritmos/preprocesadores ya está cubierta; siguen pendientes `register` ejecutable, formas arbitrarias de DAG y etapas definidas por plugins. La limpieza automática global de artefactos continúa deshabilitada.

## 75. Registrar el modelo seleccionado en la ejecución durable

PR [#509](https://github.com/SauronShepherd/ronin/pull/509) añadió el nodo terminal `register` a PipelineIR v2. El compilador del API y Studio lo habilita para pipelines estándar y cuadrículas; el runner valida la dependencia única desde `select`, y el coordinador registra el modelo bajo el lease que protege la publicación del artefacto y el commit del resultado. Los reintentos son idempotentes cuando modelo, versión y artefacto coinciden, y fallan ante conflictos. La UI puede solicitarlo durante la ejecución durable y presenta el modelo registrado.

Pasaron 93 pruebas Python focalizadas, Ruff, mypy, snapshot OpenAPI, 7 pruebas Playwright, 21 pruebas Docker, 2 pruebas Docker/PostgreSQL ejecutadas aparte y aceptación estricta v0.1 **15/15**. PR #509 pasó todos los checks. Integrado en `main@156d60784e8e0c5e23f1383c2cf96dc8860560e3`; pasaron los seis workflows post-merge exact-head: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39717965274), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39717965354), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39717965347), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39717965382), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39717965265) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39717965307). Avance técnico: **90%**; release-qualified: **0% (0/14)**.

## 76. Auditoría de optimización del ciclo de construcción

La auditoría paralela confirmó que PR #508 ejecuta en paralelo las lanes de Docker y reutiliza la instalación de Chromium en Web qualification. La comparación disponible pasó de **9m24s a 4m18s** para Docker (aproximadamente **54% menos tiempo**). En los seis workflows exact-head de `main@156d607`, CI terminó en **4m31s** y Docker qualification en **4m18s**. Dentro de CI, `test (3.11)` tardó **3m49s**, `test (3.12)` **4m15s**; en 3.12, `make test` consumió 192s y la instalación 42s.

La siguiente hipótesis es dividir la suite en **dos shards por versión de Python**. La estimación inicial es 2m30s–2m45s para CI, un ahorro de 1m30s–1m45s en ese workflow; el ahorro del camino exact-head total sería pequeño al principio porque Docker queda en 4m18s. Antes de adoptarlo, se deben medir duraciones, comprobar que cada node ID se ejecuta exactamente una vez y combinar cobertura dentro de cada versión de Python antes de ejecutar los mismos ocho umbrales de `make test`. Debe conservarse la evidencia de cobertura por versión. Validar al menos tres ejecuciones comparables, sin flakes ni fallos de fixtures/puertos; mantener las pruebas Docker y la aceptación 15/15.

La lane de CI conserva su ejecución serial actual y ahora captura `pytest-timings.json` (esquema v2) con SHA, ID/intento del workflow, versión de Python, shard, node IDs recolectados, node IDs ejecutados (incluidos reintentos/duplicados), duración de cada fase, indicador de flakes, tiempo de instalación, tiempo total desde la carga del plugin de timing, duración del cuerpo de la sesión y tiempo de startup/recolección; publica el artefacto por versión de Python y ejecución incluso si falla la suite. El tiempo de sesión usado para comparar lanes incluye la configuración y recolección que ocurren después de cargar el plugin. El comparador exige las tres duraciones de sesión coherentes y rechaza el esquema v1 para no mezclar métricas incompatibles. Si la suite termina correctamente pero falta el JSON, CI falla para evitar perder evidencia silenciosamente. Esta instrumentación prepara la comparación de tiempos sin activar shards. La decisión de adoptar la división sigue pendiente de tres ejecuciones comparables y de demostrar reparto exacto de node IDs, cobertura combinada y gates equivalentes.

`tools/pytest_shard_evidence.py` compara los artefactos baseline y shard de un SHA/versión de Python, exige por defecto tres ejecuciones exitosas de cada modo y exactamente dos shards por run, rechaza node IDs perdidos/duplicados, outcomes variables, retries flaky y resultados fallidos, y calcula la mediana del tiempo serial frente a la duración máxima estimada del shard concurrente, sumando instalación y sesión por lane. La combinación de cobertura y los ocho umbrales siguen siendo una cualificación separada y no quedan aprobados por este informe.

## 77. Requisitos para generalizar DAGs built-in con PipelineIR v3

No ampliar PipelineIR v2: su contrato actual falla antes de crear el Job si la topología no coincide con las formas de candidato admitidas. Diseñar PipelineIR v3 con un registro estático e inmutable de etapas built-in versionadas; cada etapa declara configuración canónica, entradas y salidas tipadas, cardinalidad, política de efectos, codec de checkpoint y executor. Mantener al principio el límite de 24 nodos y ejecución topológica estable y serial.

Validar antes de crear el Job todos los IDs, referencias y puertos, tipos, cardinalidades, ciclos, nodos inalcanzables, límites de tamaño y compatibilidad de versiones. Fijar en el Job el digest de pipeline, esquema y executor; verificarlo al reanudar. Los outputs/checkpoints deben conservar sus digests y fingerprints, y un retry debe invalidar el nodo fallido y descendientes cuando cambie cualquier fingerprint. El registro permanece terminal y usa la interfaz idempotente host con el writer lease actual. No serializar código ejecutable, imports ni comandos shell.

Mantener las etapas de plugins en un PR posterior al contrato v3: contribution namespaced y versionada, distribución fijada al Job, permisos explícitos, API de artefactos acotada y ejecución aislada con recursos/timeout/cancelación. No activar recolección automática global de artefactos hasta que estén inventariadas y protegidas todas las fuentes con referencias compartidas y eliminación fail-closed.

## 78. Implementar el contrato PipelineIR v3 y el executor de DAGs built-in

**Estado del candidato: implementación local sin ejecutar pruebas, builds, validadores ni Docker por instrucción del usuario. No integrado; el porcentaje global no cambia.**

La primera implementación añade nodos con referencias `node.output` tipadas y puertos/cardenalidades declarados en un registro built-in inmutable. Las versiones fijan configuración permitida, clase de efecto, executor y codec de checkpoints; el digest del registro incorpora hashes del código host y versiones de Python/dependencias, y se guarda en la identidad del Job para invalidar una reanudación con otro executor. El grafo permite ramas `prepare/train/evaluate` y joins en `select`, conserva `register` como side effect terminal administrado por el host y valida antes de cargar los datos o crear el Job. Se mantienen los contratos y payloads v1/v2.

La implementación incluye límites de 24 nodos, 48 aristas, fan-out 8, 16 KiB de configuración y 64 KiB de IR; valida referencias, tipos, parámetros ligados al Lab, configuración de tarea, nodos huérfanos y orden topológico determinista. Los checkpoints inline se limitan a 256 KiB y los externos a 128 MiB, para conservar modelos válidos de hasta 64 MiB. El runner consulta cancelación entre etapas; al cerrar el coordinador una ejecución durable conserva el Job y deja expirar el lease para permitir su recuperación. El snapshot de API expone sólo ID y tipo de etapa, y la UI envía `node:<id>` para reintentar una rama exacta. Los clientes pueden enviar un tipo desnudo para invalidar todas sus instancias; la UI evita la ambigüedad entre un tipo y un ID coincidente. La cobertura específica incluye clasificación/regresión con ramas y selección, clustering, rechazo antes del Job, identidad/recuperación de checkpoints, registro v3 durable y regresiones v1/v2. El incremento de porcentaje queda pendiente hasta integrar y cualificar el SHA exact-head con CI, Docker, Web, Security, Release y Status consistency.

Las entradas grandes, los checkpoints externalizados y la materialización de modelos exigen ahora una barrera de referencias para mantener el writer lease desde la escritura hasta el commit; si falta, la ejecución falla cerrada. Las excepciones de infraestructura del executor OCI se normalizan como fallos de etapa con contrato estable.

## 79. Registrar y ejecutar etapas aportadas por plugins (candidato implementado)

**Estado del candidato: implementación local sin ejecutar pruebas, builds, validadores ni Docker por instrucción del usuario. No integrado; el porcentaje global no cambia.**

El SDK y el registro de contribuciones del host ahora admiten etapas namespaced con versión, digest de la distribución instalada, imagen OCI fijada por digest, puertos tipados, configuración permitida, efecto, permisos y límites de CPU, memoria, procesos y timeout. Durante composición, el host compara el digest declarado con la distribución instalada antes de congelar el registro. El digest de todas las declaraciones contribuidas se incorpora al digest del registro v3 fijado en el Job. El host rechaza contribuciones fuera del manifest, colisiones, permisos no soportados y límites fuera de política.

PipelineIR v3 ya valida la identidad declarada, versión, puertos tipados, cardinalidad y configuración contra el registro congelado. El runner despacha etapas al executor OCI fijado por digest, con payload JSON acotado por stdin interactivo, sin red, montajes, credenciales ni root filesystem escribible. Los resultados de datos disponen de codec canónico de checkpoint ligado a la distribución e imagen fijadas; cancelación del Job y pérdida de lease se propagan al comando Docker. Los evaluadores plugin pueden producir `ml.metrics` con scores finitos ligados a un modelo train directo. `artifact:read` entrega sólo referencias upstream autorizadas; `artifact:write` acepta hasta ocho objetos y 512 KiB agregados. El executor rechaza antes de codificar modelos de entrada mayores de 512 KiB y mide incrementalmente las solicitudes hasta el límite de 1 MiB.

La escritura de bytes, su verificación, las referencias embebidas en el checkpoint y el guardado durable se ejecutan dentro del mismo writer lease. El inventario durable de Jobs ve las referencias aun cuando el checkpoint se externaliza como artefacto grande. No aumentar el progreso global ni declarar este hito terminado antes de cerrar la revisión del slice y cualificar el SHA exact-head con los gates requeridos.

## 80. Degradar con claridad cuando falta scikit-learn

El backend local detecta la presencia del paquete opcional sin importarlo durante el bootstrap. El endpoint `/v1/ml-studio/backends` informa `available` o `unavailable` y, cuando falta, devuelve el extra `ml` y la instrucción de instalación. La UI muestra el motivo y deshabilita controles de entrenamiento para Labs que usan ese backend; si no puede consultar capacidades, trata el estado como desconocido y también bloquea el entrenamiento hasta refrescar. El servidor valida tanto los pipelines compilados como los enviados por el cliente antes de resolver datos o crear el Job. Implementación local sin pruebas ni validadores por instrucción del usuario; el progreso técnico global no cambia.

Las entradas directas de clustering aplican la misma guarda de disponibilidad que las ejecuciones tabulares. El control plane traduce la dependencia opcional ausente a `503 ml_backend_unavailable` y un backend desconocido a `404 ml_backend_not_found`, conservando un contrato HTTP explícito cuando el plugin se invoca desde la API.

## 81. Publicar reportes de drift numérico por Lab

El endpoint con permiso `ml-studio:execute` compara ventanas explícitas de referencia y actuales para las features que el Lab declara como numéricas. Requiere una `DriftPolicy` v1 con ID, versión y umbrales finitos por feature para el cambio absoluto de media y varianza poblacional; limita cada ventana a 100.000 filas y devuelve la política, resúmenes, features que exceden umbral y las limitaciones del método. La política se conserva como JSON portable y también puede guardarse como versión inmutable en un catálogo por workspace/Lab; Studio permite cargar versiones guardadas y reutilizarlas entre sesiones. No persiste las filas ni inicia retraining o promoción. Studio ofrece el formulario desde cada Lab y muestra el reporte devuelto por el API. Implementación local sin pruebas, builds ni validadores por instrucción del usuario; el progreso técnico global no cambia.

## 82. Completar la evidencia de model cards

La model card obtiene del registro el dataset, parámetros, métricas, referencia de ejecución y revisión de código del run de origen, además de la firma y provenance del artefacto. Expone el uso previsto ligado a la tarea y declara explícitamente fairness como `not_assessed` y owner como desconocido cuando esa evidencia no existe; añade limitaciones si no puede recuperar el run. OpenAPI describe el payload versionado. Implementación local sin pruebas, builds ni validadores por instrucción del usuario; el progreso técnico global no cambia.

## 83. Filtrar y exportar comparaciones de trials

La tabla de comparación en Studio permite filtrar localmente por ID, parámetro o métrica y descargar el ranking completo como JSON o CSV. El CSV conserva los objetos de parámetros y métricas como celdas JSON con escape RFC-compatible; no crea una ruta de exportación en el servidor ni modifica evidencia durable. Implementación local sin pruebas, builds ni validadores por instrucción del usuario; el progreso técnico global no cambia.

## 84. Ejecutar suites de calidad versionadas

El contrato `ronin.ml-quality-suite/v1` limita suites a 64 expectativas únicas con reglas `not_null`, `numeric`, `min`, `max` y `min_distinct`; cada expectativa declara severidad warning/failure. Las referencias a columnas se validan contra el Lab antes de resolver filas o crear el Job. El endpoint de quality acepta una suite para previsualizar resultados. Las ejecuciones aceptan `quality_suite`, la convierten a PipelineIR v3, la fijan en la identidad del Job y evalúan el gate antes de prepare/train. Los resultados detallan cada expectativa y forman parte del checkpoint durable. La UI permite aplicar la suite seleccionada a nuevas ejecuciones; la persistencia de catálogo y recuperación entre sesiones se detalla en el hito 85. Implementación local sin pruebas, builds ni validadores por instrucción del usuario; el progreso técnico global no cambia.


## 85. Persistir suites de calidad entre sesiones

**Estado del candidato: implementado estáticamente; cualificación pendiente.** El catálogo versionado por workspace y Lab está disponible en stores in-memory, SQLite y PostgreSQL, con claves compuestas, inmutabilidad, orden creciente de versión y borrado en cascada con el Lab en stores relacionales. Las versiones se limitan a 1..2,147,483,647 para ajustarse al `INTEGER` compartido por SQLite/PostgreSQL. El store in-memory serializa lecturas y escrituras del catálogo para preservar la inmutabilidad y el avance monotónico bajo solicitudes concurrentes. Los endpoints de listar/guardar/obtener aplican scope de workspace y permisos diferenciados; Studio puede cargar versiones desde el servidor y guardar/usar una suite. Los conflictos de versión responden como HTTP 409 y las referencias ausentes como 404, sin añadir una importación de ML al arranque general del servidor. OpenAPI y `docs/contracts/ml-quality-suite-v1.md` documentan rutas y esquema. No se ejecutaron pruebas, builds, verificadores ni Docker por instrucción del usuario; el progreso técnico global no cambia.


## 86. Persistir políticas de drift versionadas

**Estado del candidato: implementado estáticamente; cualificación pendiente.** El catálogo aislado por workspace y Lab para `DriftPolicy` usa versiones inmutables de 1..2,147,483,647, avance monotónico y borrado en cascada al borrar el Lab en SQLite/PostgreSQL. El límite coincide con el tipo `INTEGER` usado por ambos stores. El store in-memory serializa lecturas y escrituras del catálogo para preservar la inmutabilidad y el avance monotónico bajo solicitudes concurrentes. Los endpoints de guardar/listar/recuperar aplican permisos read/write y validan que cada política cubra exactamente las features numéricas del Lab. Studio guarda y carga políticas desde el formulario de drift. OpenAPI y `docs/contracts/ml-drift-policy-v1.md` documentan los endpoints y el esquema. No se ejecutaron pruebas, builds, verificadores ni Docker por instrucción del usuario; el progreso técnico global no cambia.

### Cierre estático adicional del candidato

El endpoint `POST /v1/ml-studio/experiments` ya crea una identidad `Experiment`
durable y workspace-scoped mediante el registry, rechaza cuerpos incompletos y
mantiene la definición inmutable en SQLite y PostgreSQL. OpenAPI documenta la
entrada y la respuesta creada. `GET /v1/ml-studio/experiments` y
`GET /v1/ml-studio/experiments/{experiment_id}` completan el listado y la
reapertura workspace-scoped.

El transporte remoto aplica el timeout de la solicitud sin superar el timeout de
despliegue, limita el tamaño de la respuesta JSON y ejecuta el backoff exponencial
acotado sólo entre reintentos transitorios. Los resultados rechazan métricas con
NaN/Inf antes de entrar en el lifecycle. Estas correcciones son estáticas y aún
requieren cualificación exact-head; no se ejecutaron pruebas, builds, validadores
ni Docker por instrucción del usuario.

### Portabilidad del registry ML

El bundle de registry puede incluir los bytes de los artefactos de modelos cuando
se proporciona el `ArtifactStore`. Cada objeto `ml_artifact` conserva el digest
SHA-256 y la referencia de origen dentro de un payload `ronin.ml-artifact/v1`;
la planificación de importación verifica todos los bytes y la relación entre
modelo y artefacto antes de mutar el registry. La importación escribe los bytes
en el store de destino y remapea las referencias de runs y modelos. Sin un store
de artefactos se mantiene explícitamente el modo metadata-only, sin afirmar que
el bundle sea autosuficiente. El contrato está documentado en
`docs/contracts/ml-registry-bundle-v1.md`; la cualificación exact-head sigue
pendiente y no se ejecutaron pruebas ni Docker.

Las rutas de publicación tabular y K-Means calculan la identidad del artefacto
antes de escribirlo, detectan una versión de modelo ya publicada con la misma
firma y digest, y tratan runs/modelos idénticos como reintentos idempotentes. Un
conflicto de identidad se rechaza; el writer lease actual sigue cubriendo la
escritura del artefacto y las referencias. Los artefactos huérfanos de un fallo
intermedio permanecen sujetos a la política conservadora de retención y no se
borran automáticamente.

El contrato de capacidades `ronin.ml-backend/v1` expone ahora, además de tareas
y algoritmos, los nombres de hiperparámetros acotados, formatos de artefacto y
perfiles de recursos que cada adapter acepta. El servidor publica estas
capacidades en `/v1/ml-studio/backends`; los adapters local, MLflow y Spark
declaran sus perfiles y rechazan declaraciones duplicadas o vacías antes de
ser registrados. La cualificación exact-head sigue pendiente y no se ejecutaron
pruebas, builds, validadores ni Docker.

La interoperabilidad MLflow del subconjunto seguro ya tiene un sobre canónico
`ronin.mlflow-metadata/v1` para experimento, run, modelo opcional y flavor.
`export_mlflow_metadata()` e `import_mlflow_metadata()` preservan parámetros,
métricas, firma, revisiones de datasets y digests sin cargar código, pickle,
entornos ni URI de artefactos del proveedor; las relaciones run→experiment y
model→run se validan y los flavors fuera de `python_function`/`sklearn` se
rechazan explícitamente. La cualificación exact-head sigue pendiente y no se
ejecutaron pruebas, builds, validadores ni Docker.

## 87. Hacer durable el catálogo de FeatureDefinition en todos los perfiles

**Estado del candidato: implementado estáticamente; cualificación pendiente.**
`FeatureDefinition` valida versiones enteras dentro del rango compartido y enlaza
cada definición con un `AssetRef` exacto. Los stores in-memory, SQLite y
PostgreSQL rechazan sobrescrituras, exigen avance monotónico e implementan
listado/lectura por workspace. La composición local reutiliza el mismo store
ML para el plugin y conecta `FeatureDefinitionService` al control plane, de
modo que las rutas `/v1/ml-studio/features` funcionan en los perfiles SQLite y
PostgreSQL. OpenAPI y `docs/contracts/ml-feature-v1.md` describen el contrato.
No se ejecutaron pruebas, builds, validadores ni Docker por instrucción del
usuario.

El bundle ML ahora puede transportar también definiciones de features y
`ModelEvaluation` cuando se suministra el store de features o el registry
expone lecturas de evaluaciones. El inventario conserva dependencias
feature/run/model/evaluation, valida relaciones ausentes antes del commit y
requiere los stores destino antes de escribir artefactos. El modo metadata-only
continúa explícito. La cualificación exact-head sigue pendiente y no se
 ejecutaron pruebas, builds, validadores ni Docker.

La importación del bundle acepta ahora la `ArtifactReferenceBarrier` compartida.
En PostgreSQL el lease cubre la materialización de bytes, el remapeo de
referencias y los commits de registry/features, evitando que la retención
observe una importación a medias. SQLite y el modo metadata-only conservan la
operación sin barrera.

La importación del registry es ahora atómica tanto en SQLite como en
PostgreSQL: experiments, runs, modelos, evaluaciones y definiciones de features
comparten la misma transacción. PostgreSQL bloquea la fila del workspace para
serializar reintentos concurrentes y exige que el store de features pertenezca
al mismo DSN. Los tests reales con PostgreSQL cubren replay concurrente,
reapertura del store y rollback ante conflictos tardíos de modelo/feature,
dataset ausente y cancelación durante la escritura; la suite relacionada pasó
41/41 localmente en Windows/Python 3.13, conectada a PostgreSQL en Docker y con
`ResourceWarning` como error. Ruff, formato, mypy, architecture gate y
consistencia del ledger también pasan. El primer workflow exact-head ejecutó
3929 pruebas (14 omitidas), pero detectó que `postgres_ml.py` medía 76.16% y
superaba el margen del ratchet frente a 72.52%; el baseline se actualizó a
74.07%. La repetición pasó los gates exact-head de CI, Docker/PostgreSQL,
Security, Release y Status; PR #528 está integrado en
`main@72a89d06eaf33f604a613376e630a01c5b163dfd`. En post-merge, CI 3.12 y el
worker real Docker fallaron por una carrera POSIX de `Popen.poll()` con el child
watcher de asyncio. PR #529 corrigió la recolección del código de salida; CI
3.11/3.12, Docker/PostgreSQL y los seis workflows post-merge exact-head pasaron
en `main@313b8b87670e3f5cad8d641eeeb4f29cf0c31d63`. La importación ML y el
resto de Public v1 siguen parciales; el avance release-qualified permanece en
0% (0/13).

El flujo síncrono de ejecución acepta ahora de forma coherente la opción
`register` que ya consumía internamente el camino de clustering. El handler
valida el shape exacto y limita `model_id`, `version`, `run_id`,
`execution_ref` y `source_revision` antes de resolver datos o crear artefactos;
las filas siguen usando los límites compartidos de dataset. La cualificación
exact-head sigue pendiente y no se ejecutaron pruebas, builds, validadores ni
Docker.

La búsqueda de hiperparámetros reutiliza ahora el mismo resolver de datasets que
las ejecuciones y quality gates, aplicando límites de filas, columnas, bytes y
JSON canónico antes de lanzar trials. El cuerpo y la spec rechazan campos
extraños; el registro opcional limita sus identificadores. No se ejecutaron
pruebas, builds, validadores ni Docker.

## 88. Acotar superficies de búsqueda y registro durable

**Estado del candidato: implementado estáticamente; cualificación pendiente.**
Las specs de búsqueda limitan el número de parámetros y valores, la longitud de
identificadores y valores textuales, los nombres de métricas y los trials
materializados. `BayesianStopPolicy` comparte el tope de 1.000 trials. El
registro de modelos desde ejecuciones y el retry validan shape exacto, texto
recortado, longitud y caracteres de control antes de leer snapshots o artefactos.
Las opciones de compilación síncrona también acotan listas y nombres antes de
crear el pipeline. No se ejecutaron pruebas, builds, validadores ni Docker por
instrucción del usuario.
OpenAPI refleja los límites de ejecución, registro, retry, compare y search.
Las rutas de promoción, scoring, model card y descarga de artefactos comparten
el límite de 256 caracteres para sus identificadores y rechazan controles.
Labs y definiciones de features limitan también a 256 columnas y 256 caracteres
por campo textual; el contrato OpenAPI mantiene esos mismos topes.
El scope de workspace y los identificadores de Lab, run y experiment quedan
acotados antes de acceder a stores o al coordinador.
Scoring valida además el tipo de `artifact_base64`, batch IDs recortados y
offsets numéricos con una longitud máxima para evitar entradas ambiguas.
Quality, drift y los catálogos versionados validan los IDs de Lab y catálogo
antes de leer o escribir sus stores.

Los contratos de adapters remotos rechazan tipos no textuales, controles,
identidades largas, métricas duplicadas y resultados que convierten silenciosamente
identidades remotas inválidas.
Polling, cancelación y prediction comparten límites de identificador y tamaño;
el transporte exige timeouts finitos y un límite entero de respuesta.

## 89. Completar el contrato de deployment y serving local

**Estado actual: implementado; la cualificación de release sigue pendiente.**
`ModelDeployment` fija workspace, versión, referencia y digest del artefacto. La
creación verifica los bytes mediante `ArtifactStore` antes de marcar readiness,
persiste el estado en SQLite/PostgreSQL, expone health y telemetría acotada,
sirve predicciones contra el digest fijado y permite rollback sin alterar el
champion del registry. Las identidades de deployment son inmutables e
idempotentes; un pin distinto produce conflicto. El contrato está documentado en
`docs/contracts/ml-deployment-v1.md` y OpenAPI. El plugin registra además la
tarea durable `ml-studio.deployment.v1` para ejecutar el mismo pin desde el
scheduler. Las pruebas focalizadas de esta superficie se registran en la sección 91; la cualificación de release sigue pendiente.

## 90. Completar el recorrido de AI/ML Lab Studio

**Estado actual: implementado; la cualificación de release sigue pendiente.**
La superficie de Machine Learning Studio reúne creación de Labs, suites de
calidad, comparación y exportación de trials, registro/promoción, model cards,
descarga verificada de artefactos, scoring, drift y ahora el ciclo completo de
deployment: creación con pin de modelo, listado, health, predicción y rollback.
El cliente usa los contratos HTTP versionados y mantiene el workspace explícito.
Las pruebas focalizadas de esta superficie se registran en la sección 91; la cualificación de release sigue pendiente.

## 91. Cierre de la auditoría completa del plan

La instrucción anterior que dejó los hitos 78–90 como “implementados sin pruebas” ya no
aplica. La implementación existente se revisó contra sus contratos y se ejecutaron
431 pruebas focalizadas sobre PipelineIR v3, registro de etapas plugin, ejecución
aislada, deployment/rollback/predict, drift, suites de calidad, definiciones de
features, bundles, MLflow, backend degradation, HTTP y OpenAPI: **431 passed**.

La auditoría añadió `tests/test_ml_candidate_hardening.py`, que cubre el pin de
artefacto y la idempotencia de deployments, predicción contra el digest fijado,
rollback y telemetría, además del intercambio canónico y los límites del adaptador
de etapas plugin OCI. También se cerró el teardown del servidor HTTP del smoke test
para liberar explícitamente el socket en Windows y evitar falsos abortos de conexión.
En esta pasada se endureció `AsyncioCommandRunner` para consultar el código de salida
nativo en Windows cuando el callback del Proactor llega tarde bajo carga, evitando
timeouts falsos de comandos cortos. `LocalExecutionCoordinator` ahora despierta el
poller al recibir un trabajo, conservando el intervalo acotado como fallback y
evitando carreras en ejecuciones locales breves.
La evidencia de release público continúa en 0/13 familias activas según el alcance vigente (P9 GenAI queda fuera; multiusuario pertenece a Ronin Pro). Siguen pendientes las dependencias externas y decisiones humanas definidas en este plan.

La evidencia ejecutable de este cierre es: suite Python completa `3945 passed, 59
skipped` con cobertura de ramas; suite focalizada de candidato `431 passed`; suite
web Playwright `83 passed`; PostgreSQL aislado `46 passed`; Docker con PostgreSQL
limpio `23 passed` y acceptance estricto `15/15`; y la suite de rendimiento `3
passed`. Los skips restantes requieren servicios externos no configurados,
privilegios de symlink de Windows o la cualificación Docker dedicada ya cubierta por
el gate específico.

## Cierre de cualificación del candidato

La cualificación local actual volvió a ejecutar los gates Python, web, PostgreSQL y
Docker descritos arriba sin fallos. Este cierre no cambia el estado
de release público 0/14, que requiere evidencia de proveedores y decisiones fuera del
alcance del repositorio.
