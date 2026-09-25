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

1. Resolver refs de datasets contra `CatalogStore`.
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

