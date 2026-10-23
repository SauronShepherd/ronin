# Plan completo de implementación y validación de Machine Learning Studio

## 1. Objetivo y definición de terminado

Este documento describe cómo llevar el alcance provider-neutral de Machine Learning
Studio desde un repositorio base hasta una implementación integrada, verificable y
documentada. Incluye backend, persistencia, ejecución durable, API, UI, adapters,
seguridad, Docker, pruebas automatizadas y revisión manual.

El plan se considera terminado cuando se cumplen simultáneamente estas condiciones:

1. Los contratos de dominio, almacenamiento, ejecución, backend y HTTP están
   versionados y tienen validación de entrada.
2. El flujo completo `workspace → dataset → lab → quality → train → compare →
   register → promote → score` funciona con stores locales y datos acotados.
3. La ejecución asíncrona conserva checkpoints, digests, evidencias, cancelación,
   reintentos e idempotencia tras reiniciar el proceso.
4. La UI consume contratos reales, muestra estados de carga/error/vacío y no inventa
   métricas, modelos ni capacidades.
5. Los gates estáticos, de seguridad, cobertura, rendimiento, Docker, API y web pasan.
6. Se completan diez pasadas consecutivas sin fallos ni hallazgos nuevos.
7. Toda la evidencia queda asociada al SHA exacto que se pretende integrar.

La cualificación técnica no implica por sí sola una release pública: certificaciones
de proveedores, obligaciones legales y decisiones de producto se registran aparte.

## 2. Reglas de trabajo

### 2.1 Secuencia

Implementar por capas: contratos, dominio, ports, persistencia, servicios, runner,
API y UI. Cada cambio debe mantener el repositorio compilable y dejar una prueba o
un criterio de aceptación que explique su comportamiento.

### 2.2 Límites de seguridad

- No cargar pickle ni código ejecutable desde artifacts no confiables.
- No incluir secretos en PipelineIR, logs, fixtures, snapshots ni bundles.
- Aplicar workspace y permisos antes de leer o escribir cualquier recurso.
- Rechazar campos desconocidos, controles, IDs excesivos, NaN e infinitos.
- Mantener límites de filas, columnas, bytes, trials, respuesta HTTP y memoria.
- Hacer fail-closed cualquier operación que no pueda verificar digest, firma o scope.

### 2.3 Reproducibilidad

Cada ejecución debe conservar manifest canónico, snapshot de entrada, pipeline digest,
runtime, dependencias, backend, opciones efectivas, seeds y digests de outputs.
Repetir la misma entrada debe producir el mismo ranking y métricas dentro de la
tolerancia documentada.

## 3. Preparación del entorno

### 3.1 Herramientas

Instalar Python soportado, Node.js/npm, Docker Compose, Git y las dependencias del
proyecto. Para las pruebas paralelas se necesita `pytest-xdist`; para UI se necesita
Chromium gestionado por Playwright.

### 3.2 Variables de prueba

Usar valores ficticios y aislados para PostgreSQL, S3-compatible/LocalStack y
proveedores remotos. Nunca reutilizar credenciales reales. Definir DSN, endpoints,
imagen de cualificación y rutas de evidencia mediante variables del entorno CI.

### 3.3 Baseline

Registrar antes de editar:

- SHA, rama, versión de Python/Node/Docker y sistema operativo.
- Estado del worktree y configuración de dependencias.
- Recuento de tests, skips y cobertura inicial.
- Estado de ledgers y OpenAPI.
- Disponibilidad de PostgreSQL, S3-compatible y Docker.

## 4. Implementación por fases

### Fase 0 — baseline y decisiones congeladas

**Qué hacer**

- Confirmar que el árbol de implementación y los IDs públicos son los correctos.
- Registrar ADR de nombre `ml-studio` y compatibilidad `plugin_api=1.0`.
- Confirmar uso exclusivo de `PluginManifest`, `PluginContext`, contribuciones de
  rutas/jobs/UI y `plugin_routes_enabled`.
- Crear o actualizar contratos `ml-lab-v1`, `ml-pipeline-ir-v1` y `ml-backend-v1`.

**Por qué**

Evita que el plugin dependa de APIs privadas o que la UI y el backend evolucionen
con nombres incompatibles.

**Salida**

Inventario de plugin, arquitectura y contratos versionados con un test que impida
imports privados y rutas fuera del mecanismo de autorización.

### Fase 1 — dominio inmutable y schemas

**Qué hacer**

- Definir `Lab`, `LabVersion`, `TrainingRequest`, `PipelineIR`, `Trial`,
  `QualityGate`, `DriftPolicy` y value objects de IDs.
- Validar texto, unicidad, colecciones, límites y números finitos.
- Hacer inmutable `LabVersion` y conservar el manifest ya validado.
- Validar DAG acíclico, dependencias existentes, IDs únicos y orden canónico.
- Rechazar campos extra en límites HTTP y producir errores tipados estables.
- Implementar serialización canónica y round-trip exacto.

**Por qué**

Los contratos inmutables permiten reproducir una ejecución y detectar cambios antes
de tocar stores, workers o proveedores.

**Salida**

Pruebas unitarias y de propiedades para ciclos, duplicados, orden, límites, NaN/inf,
campos extra y canonical JSON.

### Fase 2 — ports y servicios

**Qué hacer**

- Definir `MLLabStore`, `MLRunStore`, `MLQualityStore` y `MLModelStore` con
  `WorkspaceId`, IDs de dominio y `now` explícito en mutaciones.
- Implementar `LabService`, `RunService`, `QualityService` y `ModelService`.
- Hacer idempotentes create/replace/register/promote/retry.
- Detectar conflicto cuando una idempotency key se reutiliza con otro body.
- Mantener SQL, cursors y ORM fuera de los ports.

**Por qué**

Los servicios deben poder probarse con dobles de memoria antes de introducir SQLite,
PostgreSQL o un proveedor ML.

**Salida**

Tests de servicios con mocks que cubran permisos, scopes, conflictos, cancelación y
transiciones inválidas.

### Fase 3 — SQLite, PostgreSQL y migraciones

**Qué hacer**

- Crear migraciones forward-only con constraints de estado y claves únicas.
- Guardar manifests/evidence como canonical JSON UTF-8 y métricas normalizadas.
- Representar plots y modelos mediante `ArtifactRef`, no blobs sin digest.
- Implementar cursores estables `(created_at, id)` y optimistic concurrency.
- Mantener paridad SQLite/PostgreSQL en lifecycle, registros, features y deployments.
- Proteger publicación y recolección con la misma barrera de referencias.

**Por qué**

Una ejecución durable debe sobrevivir a reinicios y no puede publicar una referencia
antes de que sus bytes estén verificados.

**Salida**

Migración desde base vacía y existente, reconstrucción del servicio, concurrencia,
rollback de proceso sin corrupción y pruebas de fencing/leases.

### Fase 4 — compiler, orquestación y runner

**Qué hacer**

- Resolver datasets mediante `CatalogStore` con límites de tamaño y filas.
- Resolver backend, runtime profile y permisos antes de compilar.
- Generar etapas `profile`, `quality`, `prepare`, `train`, `evaluate`, `select` y
  `register`, incluyendo DAGs arbitrarios y etapas namespaced de plugins.
- Calcular y persistir `pipeline_digest` antes de crear el run.
- Crear payloads con run, node, attempt y resource policy.
- Emitir heartbeat/progress acotados y conservar eventos terminales.
- Guardar outputs con `ArtifactStore.put_bytes`, validar digest y limpiar workdir.
- En cancelación, cerrar el backend y conservar evidencia parcial.

**Por qué**

La compilación debe ser determinista y el runner debe poder reanudar solo las etapas
cuya identidad y dependencias siguen siendo válidas.

**Salida**

Pipeline sintético de tres etapas con ejecución, cancelación, retry selectivo,
recuperación de checkpoints y outputs verificables después de reabrir el servicio.

### Fase 5 — backend abstraction y runtime local

**Qué hacer**

- Implementar `BackendCapabilities`, contextos de training/prediction, inspección y
  `BackendRegistry`.
- Separar preparación de datos y algoritmo mediante `PreprocessorSpec`.
- Cubrir Logistic/Linear Regression, Decision Tree, Random Forest, Gradient Boosting
  y K-Means con artifacts declarativos cuando sea posible.
- Rechazar task/algoritmo no anunciado por capabilities.
- Expandir defaults y parámetros efectivos en provenance.
- Validar signature antes de `predict` y calcular métricas con split explícito.

**Por qué**

El servicio no debe conocer scikit-learn ni cambiar cuando se añade un fake, remote,
MLflow o Spark adapter.

**Salida**

El mismo `LabVersion` funciona con el backend local y un backend falso; los artifacts
se pueden leer y puntuar sin pickle.

### Fase 6 — profiling y quality gates

**Qué hacer**

- Calcular filas, columnas, nulls, cardinalidad, min/max, cuantiles, histogramas,
  categorías, duplicados y distribución del target con memoria acotada.
- Crear suites versionadas de expectations y severidades `info`, `warning`, `failure`.
- Ejecutar checkpoint antes de `prepare` y opcionalmente antes de score.
- Persistir `ValidationResult` como evidence navegable.
- Hacer que dataset vacío, target único, schema incompatible o límites excedidos
  detengan el training con un error explicable.

**Por qué**

Un modelo no debe entrenarse con datos inválidos ni depender de valores completos
que puedan exponer información sensible.

**Salida**

Pruebas de profiling bounded, suites reutilizables, bloqueo de training y lectura de
evidence por workspace.

### Fase 7 — búsqueda, comparación y optimización

**Qué hacer**

- Validar `SearchSpec` para `single`, `grid`, `random` y `bayesian` opcional.
- Acotar parámetros, valores, nombres y número total de trials antes de entrenar.
- Generar IDs y seeds desde `(run_seed, trial_id)`.
- Respetar resource policy y pruning cooperativo.
- Comparar solo resultados con mismo task, target, dataset contract y protocolo.
- Ordenar empates por métrica secundaria, coste y simplicidad según configuración.
- Mantener grids algoritmo×preprocesador dentro del máximo documentado.

**Por qué**

La optimización debe ser reproducible, finita y segura frente a espacios de búsqueda
maliciosos o accidentalmente ilimitados.

**Salida**

Dos ejecuciones idénticas producen el mismo ranking; Bayesian stopping y retry no
duplican trials ni alteran el orden estable.

### Fase 8 — registry, provenance y model cards

**Qué hacer**

- Registrar solo artifacts verificados con signature completa.
- Generar model card con uso, limitaciones, dataset, features, métricas, fairness,
  owner y provenance.
- Aplicar transiciones candidate/champion/archived y un solo champion por scope.
- Exigir permiso de promoción y reason no vacío.
- Resolver score contra una versión inmutable y no borrar bytes promovidos.
- Implementar descarga por bloques con validación de tamaño, digest y secuencia.

**Por qué**

El registry es un control de identidad y gobierno, no solo una tabla de nombres.

**Salida**

Registro, promoción, model card, descarga y batch score reproducibles con evidencia
de entrada y salida.

### Fase 9 — API, OpenAPI y SDK

**Qué hacer**

- Añadir schemas para labs, quality, executions, search, registry, scoring, drift,
  features y deployments.
- Registrar rutas mediante el plugin y aplicar `plugin_routes_enabled`.
- Validar workspace, permisos, cursor, límites, campos extra y errores RFC 9457.
- Añadir idempotencia a create lab/run/register/promote/deployment.
- Mantener OpenAPI, parser, handlers y SDK en paridad.
- Regenerar o actualizar el snapshot OpenAPI cuando cambie la superficie.

**Por qué**

El contrato público debe poder comprobarse sin depender de la implementación interna
ni de una UI concreta.

**Salida**

Contract tests contra handlers y OpenAPI para cuerpos válidos, inválidos, permisos,
scope, paginación, conflictos y errores.

### Fase 10 — UI de Machine Learning Studio

**Qué hacer**

Implementar en este orden:

1. Nav contribution y ruta `#mlstudio`.
2. Lista de Labs con loading/error/empty states.
3. Wizard de Lab conectado a API real.
4. Tabla de schema/profile y badges de quality.
5. Flow accesible con nodos seleccionables y estado de ejecución.
6. Formulario Train basado en capabilities del backend.
7. Timeline de run y tabla de trials.
8. Compare con filtros y exportación JSON/CSV.
9. Model card y diálogo de promoción con reason.
10. Scoring batch, drift, deployments, health, predict y rollback.

**Por qué**

El usuario debe ver solo capacidades anunciadas por el backend y poder recuperar un
estado tras error, refresh o navegación directa.

**Salida**

Auditoría de rutas, handlers, accesibilidad, journeys reales y ausencia de datos
inventados.

### Fase 11 — adapters posteriores

**Qué hacer**

- `remote.ronin`: enviar PipelineIR firmado sin secretos y recibir eventos/ArtifactRefs.
- `mlflow.adapter`: interoperar con el subconjunto seguro sin sustituir el registry.
- `local.xgboost`: dependency/licence audit, capabilities y artifact safety propios.
- `sparkml`: añadir solo con runtime distribuido, connector y política de coste.

**Por qué**

Los adapters son extensiones aisladas; no deben convertir una dependencia opcional en
un requisito del núcleo ni degradar la evidencia nativa de Ronin.

**Salida**

Contrato de cada adapter, clean-room test, timeout/backoff/cancel bounded y prueba de
indisponibilidad del proveedor sin perder evidencia local.

### Fase 12 — deployment y serving local

**Qué hacer**

- Fijar workspace, model version, ArtifactRef y digest en `ModelDeployment`.
- Verificar bytes antes de readiness y persistir estado en SQLite/PostgreSQL.
- Exponer health/readiness, prediction, telemetría limitada y rollback.
- Mantener idempotencia y rechazar un pin distinto para el mismo deployment.
- Integrar la tarea durable `ml-studio.deployment.v1` en el scheduler.

**Por qué**

Servir un modelo exige conservar exactamente el artifact aprobado, incluso si el
champion del registry cambia posteriormente.

**Salida**

Health, prediction, rollback y reinicio con el mismo digest; no se altera el champion.

### Fase 13 — seguridad, límites y observabilidad

**Qué hacer**

- Probar matriz de permisos por workspace, acción y estado.
- Redactar secretos y tokens en logs, errors, snapshots y evidence.
- Rechazar path traversal, SSRF, hosts privados, payloads enormes y artefactos no
  verificables.
- Instrumentar duración, retries, coste, bytes y estado sin datos sensibles.
- Mantener auditoría append-only para mutaciones administrativas.

**Por qué**

Los errores de autorización o de aislamiento son fallos de producto aunque el flujo
feliz funcione.

**Salida**

Security tests, evidence review y métricas bounded sin fugas de datos.

### Fase 14 — documentación, rollout y release

**Qué hacer**

- Sincronizar contratos, OpenAPI, capability matrix, status ledger, runbooks y ADRs.
- Documentar migraciones, rollback, backups, recuperación de worker y limpieza manual.
- Generar SBOM/provenance de wheel y sdist.
- Fijar el SHA candidato y conservar todos los artefactos de evidencia.
- Integrar mediante PR protegido; borrar ramas temporales después del merge.

**Por qué**

La implementación no es reproducible ni operable si el estado publicado contradice
el código o no existe un camino de recuperación.

**Salida**

Ledgers consistentes, paquete verificable, runbook revisado y `main` con el SHA que
pasó todas las gates.

## 5. Plan de pruebas automatizadas

### 5.1 Formato y análisis estático

Ejecutar desde la raíz y guardar salida en un directorio de evidencia:

```powershell
ruff format --check .
ruff check .
mypy python packages
python tools/generate_public_v1_status.py --check
```

Comprobar además arquitectura, rutas, inventario de plugins, OpenAPI, budgets de UI,
status ledger y negative gates mediante los targets equivalentes del `Makefile`.

### 5.2 Unit y contracts

```powershell
python -m pytest -q tests/test_ml_domain.py tests/test_ml_quality.py
python -m pytest -q tests/test_ml_orchestration.py tests/test_ml_http.py
python -m pytest -q tests/test_ml_provider_adapters.py tests/test_ml_tabular_runtime.py
python -m pytest -q tests/test_public_capability_matrix.py tests/test_generate_public_v1_status.py
```

Cubrir errores y estados terminales, no solo el camino feliz.

### 5.3 Suite Python completa

Primero ejecutar una pasada diagnóstica:

```powershell
python -m pytest -q --ignore=tests/perf
```

Después ejecutar cuatro workers con orden estable:

```powershell
python -m pytest -q -n 4 --dist=loadfile --ignore=tests/perf
```

Repetir la segunda orden diez veces. Una pasada cuenta solo si no hay fallos,
errores, xfails inesperados, warnings nuevos ni diferencias de evidencia.

### 5.4 Cobertura

```powershell
make coverage-storage-files
make coverage-storage-files-full
python -m pytest -q --cov --cov-branch --cov-report=term-missing --ignore=tests/perf
```

Comparar cada módulo con el baseline versionado. Si el porcentaje baja, corregir el
ratchet o añadir pruebas que cubran la nueva rama; nunca ocultar código con exclusiones.

### 5.5 Persistencia y migraciones

Ejecutar los tests SQLite, PostgreSQL y ArtifactStore. Verificar:

- base vacía y base con migraciones anteriores;
- reconstrucción del servicio y lectura de estados terminales;
- dos escritores y un recolector compitiendo por la barrera;
- leases, fencing, expiración y reintento idempotente;
- digest incorrecto, bytes truncados y referencias ausentes;
- paginación repetida sin saltos ni duplicados.

### 5.6 Orquestación y worker

Cubrir compilación, topological order, DAG inválido, checkpoint hit/miss,
invalidación downstream, cancelación, timeout, retry desde etapa seleccionada,
registro terminal y recuperación tras crash del proceso.

### 5.7 Backend y reproducibilidad

Para cada algoritmo y preprocessor comprobar capabilities, parámetros efectivos,
signature, artifact declarativo, `predict`, métricas finitas, seed, split, target
incompatible y dataset fuera de límites.

### 5.8 Optimización

Probar grid, random y Bayesian con límite de trials, espacios vacíos, duplicados,
seeds derivadas, pruning, paciencia, ranking direccional y tie-breakers. Ejecutar dos
veces con el mismo manifest y comparar IDs, orden, métricas y digests.

### 5.9 API y SDK

Para cada endpoint validar 2xx, 400, 401, 403, 404, 409, 413 y 422 cuando proceda.
Comprobar campos extra, cursors, límites, idempotencia, workspace isolation,
OpenAPI, respuesta RFC 9457 y equivalencia del SDK.

### 5.10 Seguridad

Ejecutar pruebas de permisos, path traversal, SSRF, DNS/IP privada, secret redaction,
untrusted artifact loader, network denial, límites de payload, control de concurrencia
y auditoría de mutaciones.

### 5.11 Rendimiento y estabilidad

```powershell
python -m pytest -q tests/perf
```

Medir profiling bounded, listado paginado, comparación de 1.000 trials, streaming de
artifacts y startup. Registrar p50/p95, memoria y límites; no convertir un benchmark
en un requisito sin baseline versionado.

### 5.12 Mutation y survivors

Ejecutar el target de mutation configurado por el repositorio. Revisar cada survivor
de transiciones, autorización, digest, errores y límites. Un survivor aceptado debe
tener una justificación escrita; no se debe bajar el umbral para silenciarlo.

## 6. Docker y proveedores locales

### 6.1 Configuración

```powershell
# compose.yaml valida también las variables de los perfiles opcionales. Define
# valores locales antes de pedir la configuración, aunque no vayas a iniciar AI.
$env:RONIN_TOKEN = "local-test-token"
$env:RONIN_RUNNER_BROKER_TOKEN = "local-runner-token"
$env:RONIN_AI_MODEL_DIR = (Join-Path $PWD ".cache\models")
$env:RONIN_AI_VLLM_MODEL = "qualification-unused"
New-Item -ItemType Directory -Force $env:RONIN_AI_MODEL_DIR | Out-Null
docker compose -f compose.yaml config
docker info
```

La primera orden valida interpolación y servicios. La segunda confirma que el daemon
está disponible; si falla, registrar la limitación y ejecutar Docker en CI o en otra
máquina autorizada.

### 6.2 Qualification

Construir la imagen de qualification, levantar PostgreSQL y el perfil S3-compatible,
ejecutar worker real, crash/restart, reconciliación, cobertura PostgreSQL y aceptación
estricta. Guardar logs, manifests, digests, reportes de cobertura y resultados de
composición en `qualification-evidence/` sin versionar secretos.

### 6.3 Casos mínimos

- ejecución de notebook/celda en contenedor real;
- Job y checkpoints persistidos en PostgreSQL;
- reinicio del worker sin duplicar trabajo;
- retry/cancel/timeout y estado terminal;
- S3 input/output, corrupción y limpieza segura;
- scheduler y evidencia de workflow;
- health/readiness y apagado ordenado.

## 7. Pruebas web automatizadas

```powershell
npm --prefix web-tests ci
npm --prefix web-tests test
```

Ejecutar Chromium headless contra la superficie completa y comprobar rutas, navegación,
mock de API, accesibilidad, historial, errores, descarga de artifacts, compare,
promoción, scoring, drift y deployment. Mantener el snapshot de accesibilidad y los
presupuestos de JS/CSS dentro de sus límites.

## 8. Test manual y visual de UI

### 8.1 Preparación

Usar datos sintéticos pequeños y un usuario con permisos controlados. Abrir la consola
del navegador, capturar screenshots por estado y registrar viewport, navegador, SHA,
fixtures y hora. No usar datos reales.

### 8.2 Recorrido principal

| ID | Pasos | Resultado esperado |
|---|---|---|
| UI-01 | Abrir `#mlstudio` sin sesión válida | Se muestra acceso denegado o login; no aparecen datos parciales. |
| UI-02 | Crear Lab con manifest válido | El wizard valida campos, guarda una versión y confirma el ID devuelto por API. |
| UI-03 | Introducir campo extra, ID largo o dataset invisible | Se muestra error útil; no se crea ninguna entidad. |
| UI-04 | Abrir Labs con red lenta | Loading estable, sin saltos; al terminar aparece lista, vacío o error real. |
| UI-05 | Ejecutar quality sobre CSV/JSONL | Aparecen profile, severidades y evidence enlazada al run. |
| UI-06 | Intentar training con quality failure | El botón queda bloqueado o el backend rechaza; se explica la causa. |
| UI-07 | Lanzar train y recargar la página | Timeline recupera estado real, progreso bounded y timestamps coherentes. |
| UI-08 | Cancelar y reintentar desde una etapa | Se conserva evidencia parcial y el hijo reutiliza solo checkpoints válidos. |
| UI-09 | Ejecutar grid/compare | Tabla muestra límite de candidatos, ranking reproducible y tie-breakers correctos. |
| UI-10 | Abrir model card y descargar artifact | Digest, tamaño, provenance y descarga coinciden; no se descarga contenido truncado. |
| UI-11 | Promover modelo | El diálogo exige reason; permisos y cambio de stage se reflejan tras refrescar. |
| UI-12 | Puntuar batch válido e inválido | El válido devuelve resultados ligados a model version; el inválido muestra error de signature. |
| UI-13 | Crear deployment, health, predict y rollback | El pin permanece fijo, health es legible y rollback no cambia el champion. |
| UI-14 | Simular API 401/403/404/409/500 | Cada error tiene mensaje contextual, recuperación o retry y no rompe el shell. |
| UI-15 | Navegar atrás/adelante y abrir deep links | La ruta conserva workspace, selección y carga correcta sin depender del historial previo. |

### 8.3 Accesibilidad

- Navegar todo con teclado y comprobar foco visible, orden lógico y escape de modales.
- Verificar nombres accesibles, roles, estados de botones, tablas y gráficos.
- Probar zoom 200%, contraste, reduced motion y lector de pantalla.
- Confirmar que los errores se anuncian y que no dependen solo del color.

### 8.4 Responsive y navegadores

Repetir UI-01–UI-15 en Chromium, Firefox y WebKit si están disponibles; probar 320,
768, 1024 y 1440 px. Comprobar que tablas, dialogs, flow y botones no se cortan ni
ocultan acciones críticas.

## 9. Iteración hasta diez pasadas limpias

Cada pasada debe seguir esta secuencia:

1. Confirmar SHA y worktree.
2. Ejecutar formato, lint, tipos, arquitectura, ledgers y OpenAPI.
3. Ejecutar suite Python controlada, coverage y rendimiento.
4. Ejecutar Node/Playwright y auditoría manual visual.
5. Ejecutar Docker qualification y proveedores locales.
6. Revisar logs, warnings, skips y evidencia.
7. Corregir la causa raíz, añadir o ajustar la prueba y documentar el cambio.
8. Reiniciar el contador si aparece cualquier fallo, flake no explicado, regresión,
   warning nuevo o discrepancia documental.

El contador termina en `10/10` solo cuando las diez pasadas consecutivas usan el mismo
commit candidato y los mismos criterios. Una prueba que pasa al reintentarse no borra
el fallo: exige aislar la causa y repetir la pasada completa.

## 10. Evidencia y trazabilidad

Conservar, fuera de Git o en el sistema de artefactos CI:

- comandos exactos y versiones;
- logs completos por suite y por pasada;
- cobertura por módulo y ratchets aplicados;
- snapshots OpenAPI, arquitectura, status y budgets;
- screenshots/manual checklist de UI;
- Docker compose, image digest, logs de servicios y reportes PostgreSQL/S3;
- SBOM, provenance, wheel/sdist y SHA candidato;
- relación entre cada criterio del plan y su prueba/evidencia.

No guardar tokens, cookies, DSN con credenciales ni payloads sensibles.

## 11. Integración y entrega

1. Crear una rama de trabajo desde `main` protegido.
2. Mantener commits pequeños y describir cada corrección.
3. Abrir PR con el SHA candidato, resumen de riesgos y enlaces de evidencia.
4. Esperar todos los checks obligatorios; no forzar merge con checks rojos.
5. Fusionar mediante la política del repositorio.
6. Actualizar `main` localmente y comprobar que el SHA fusionado es el cualificado.
7. Eliminar la rama local y remota de trabajo después del merge.
8. Verificar que no quedan ramas de feature, que el worktree está limpio y que los
   ledgers apuntan a un SHA válido.

## 12. Límites conocidos

- La cualificación provider-neutral no equivale a certificación de un proveedor remoto.
- La disponibilidad de Docker, PostgreSQL, LocalStack, Floci o servicios externos debe
  quedar reflejada en la evidencia, no asumirse.
- El release público permanece incompleto mientras falten journeys obligatorios,
  certificaciones, evidencias legales o decisiones humanas.
- Las pruebas manuales complementan, pero no sustituyen, los contratos automatizados.
- Un cambio posterior al SHA cualificado obliga a repetir las gates afectadas y el
  ciclo de diez pasadas.

## 13. Runbook ejecutable

Los bloques siguientes se ejecutan desde PowerShell y en el orden indicado. Este
documento solo los describe; no los ejecuta.

### 13.0 Orden de implementación y commits

Crear una rama y completar cada grupo como un commit revisable. No mezclar cambios
de UI con migraciones o cambios de contrato en el mismo commit.

| Commit | Ficheros principales | Acción concreta | Gate inmediato |
|---|---|---|---|
| 01 contratos | `python/studio_core/ml.py`, `python/studio_ml/domain.py`, `schemas.py`, `errors.py`, `docs/contracts/ml-*-v1.md` | Añadir value objects, validación estricta, DAG, canonical JSON y errores estables. | Unit/property de dominio y contratos. |
| 02 ports | `python/studio_storage/ports.py`, `python/studio_ml/services.py` | Definir stores y servicios idempotentes con workspace y `now`. | Tests de servicios con stores fake. |
| 03 persistencia | `python/studio_storage/migrations/`, stores SQLite/PostgreSQL | Añadir tablas, constraints, cursores, optimistic concurrency y barrera de artifacts. | Migración vacía/existente y concurrencia. |
| 04 compiler | `python/studio_ml/compiler.py`, `orchestration.py` | Resolver datasets/backends, generar DAG, persistir IR y digest. | DAG válido/ inválido y pipeline digest. |
| 05 runner | `python/studio_ml/runner.py`, `jobstore` adapters | Ejecutar nodos, checkpoints, heartbeat, cancelación, retry y artifacts. | Recovery tras reinicio y cancelación. |
| 06 backends | `python/studio_ml/backends.py`, `runtime.py`, `provenance.py` | Registrar capabilities, algoritmos, preprocessors, signatures y predict. | Runtime determinista y artifact verification. |
| 07 quality | `python/studio_ml/quality.py`, profiling y rutas quality | Implementar profile bounded, suites, severidades y evidence. | Dataset inválido bloquea training. |
| 08 search | `python/studio_ml/optimization.py`, compare services | Implementar grid/random/Bayesian, seeds, pruning y tie-breakers. | Ranking idéntico en dos ejecuciones. |
| 09 registry | registry/provenance, model cards, artifact routes | Registrar, promover, resolver champion y descargar por digest. | Transiciones, permisos y score. |
| 10 API | plugin routes, OpenAPI, SDK | Montar rutas, schemas, idempotencia, paginación y errores RFC 9457. | Contract tests handler/OpenAPI/SDK. |
| 11 UI | `web/js/features.js`, `web-tests/tests/` | Conectar Labs, quality, runs, compare, registry, score y deployment a API real. | Playwright y checklist manual. |
| 12 adapters | remote/MLflow/XGBoost/Spark contracts | Aislar dependencias opcionales, timeouts, retry, cancel y clean-room tests. | Provider unavailable sin perder evidencia local. |
| 13 serving | deployment stores, routes, scheduler adapter | Fijar artifact digest y probar health/predict/rollback. | Pin inmutable tras restart. |
| 14 release | docs, ledgers, SBOM, runbooks | Sincronizar documentación y generar evidencia del SHA candidato. | Gates exact-head y PR protegido. |

Para cada fila: editar los ficheros indicados, ejecutar el gate inmediato de la
sección correspondiente, revisar `git diff --check`, y crear un commit solo cuando
ese gate esté limpio. Si un gate falla, corregirlo antes de comenzar la fila siguiente.

### 13.1 Fijar el candidato y crear evidencia

```powershell
$ErrorActionPreference = "Stop"
$Repo = "C:\Users\angel.alvarez\Documents\ChatGPT\ronin\repo-analysis-ml-candidate-grid"
Set-Location $Repo
$Evidence = Join-Path $Repo "qualification-evidence"
New-Item -ItemType Directory -Force $Evidence | Out-Null
git status --short
git branch --show-current
git rev-parse HEAD | Tee-Object (Join-Path $Evidence "candidate-sha.txt")
python --version | Tee-Object (Join-Path $Evidence "python-version.txt")
node --version | Tee-Object (Join-Path $Evidence "node-version.txt")
npm --version | Tee-Object (Join-Path $Evidence "npm-version.txt")
docker --version | Tee-Object (Join-Path $Evidence "docker-version.txt")
```

**Éxito:** el worktree no contiene cambios inesperados, la rama es la prevista y el
SHA queda guardado. Si hay cambios locales, separarlos antes de continuar.

### 13.2 Crear el entorno e instalar dependencias

```powershell
if (-not (Test-Path .venv\Scripts\python.exe)) {
  py -3.11 -m venv .venv
}
& .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip freeze | Out-File (Join-Path $Evidence "pip-freeze.txt")
npm --prefix web-tests ci 2>&1 |
  Tee-Object (Join-Path $Evidence "npm-ci.log")
npx --prefix web-tests playwright install chromium
```

Si `.[dev]` no es un extra válido, instalar el lockfile o comando definido por el
repositorio y guardar igualmente `pip freeze`. No continuar con dependencias
resueltas parcialmente.

### 13.3 Gates estáticos, contratos y ledgers

```powershell
ruff format --check . 2>&1 | Tee-Object (Join-Path $Evidence "ruff-format.log")
ruff check . 2>&1 | Tee-Object (Join-Path $Evidence "ruff.log")
mypy python packages 2>&1 | Tee-Object (Join-Path $Evidence "mypy.log")
make quality 2>&1 | Tee-Object (Join-Path $Evidence "make-quality.log")
python tools/generate_public_v1_status.py --check 2>&1 |
  Tee-Object (Join-Path $Evidence "status-ledger.log")
```

**Éxito:** cada comando termina con código `0`; no hay warnings nuevos de formato,
tipado, arquitectura, OpenAPI, budgets ni status ledgers.

### 13.4 Unit, contratos, propiedades y suite completa

```powershell
python -m pytest -q `
  tests/test_ml_domain.py `
  tests/test_ml_quality.py `
  tests/test_ml_orchestration.py `
  tests/test_ml_http_transport.py `
  tests/integration/test_ml_studio_http.py `
  tests/test_ml_provider_adapters.py `
  tests/test_ml_tabular_runtime.py `
  tests/test_public_capability_matrix.py `
  tests/test_generate_public_v1_status.py `
  2>&1 | Tee-Object (Join-Path $Evidence "ml-contract-tests.log")

python -m pytest -q --ignore=tests/perf 2>&1 |
  Tee-Object (Join-Path $Evidence "suite-serial.log")
```

**Éxito:** no hay `FAILED`, `ERROR`, `XPASS` inesperado ni warning nuevo. Los skips
deben explicar qué dependencia externa falta.

### 13.5 Cobertura y rendimiento

```powershell
make coverage-storage-files 2>&1 |
  Tee-Object (Join-Path $Evidence "coverage-storage.log")
make coverage-storage-files-full 2>&1 |
  Tee-Object (Join-Path $Evidence "coverage-storage-full.log")
python -m pytest -q --cov --cov-branch --cov-report=term-missing `
  --ignore=tests/perf 2>&1 |
  Tee-Object (Join-Path $Evidence "coverage-full.log")
python -m pytest -q tests/perf 2>&1 |
  Tee-Object (Join-Path $Evidence "performance.log")
```

Comparar porcentajes y tiempos con los baselines versionados. No bajar thresholds ni
añadir exclusiones para ocultar una regresión.

### 13.6 Diez pasadas consecutivas

Usar cuatro workers y distribución estable. Una pasada solo cuenta si termina limpia;
un flake reinicia el contador desde uno.

```powershell
for ($Pass = 1; $Pass -le 10; $Pass++) {
  $Log = Join-Path $Evidence ("suite-pass-{0}.log" -f $Pass)
  python -m pytest -q -n 4 --dist=loadfile --ignore=tests/perf 2>&1 |
    Tee-Object $Log
  if ($LASTEXITCODE -ne 0) {
    throw "La pasada $Pass falló; corregir la causa y reiniciar desde la pasada 1."
  }
}
```

El recuento de tests, skips y warnings debe ser coherente entre las diez pasadas.

### 13.7 Docker y stores externos

```powershell
# Valores mínimos para que Compose pueda interpolar todos los perfiles.
$env:RONIN_TOKEN = "local-test-token"
$env:RONIN_RUNNER_BROKER_TOKEN = "local-runner-token"
$env:RONIN_AI_MODEL_DIR = (Join-Path $PWD ".cache\models")
$env:RONIN_AI_VLLM_MODEL = "qualification-unused"
$env:POSTGRES_DB = "ronin_qualification"
$env:POSTGRES_USER = "ronin"
$env:POSTGRES_PASSWORD = "ronin"
$env:RONIN_POSTGRES_PORT = "5432"
New-Item -ItemType Directory -Force $env:RONIN_AI_MODEL_DIR | Out-Null
docker info 2>&1 | Tee-Object (Join-Path $Evidence "docker-info.log")
docker compose -f compose.yaml config 2>&1 |
  Tee-Object (Join-Path $Evidence "compose-config.log")
docker compose -f compose.yaml config --services |
  Tee-Object (Join-Path $Evidence "compose-services.log")
```

Si `docker info` falla, la qualification debe trasladarse a un runner con Docker; no
se debe simular un resultado local.

Para PostgreSQL y un S3-compatible de prueba:

```powershell
$env:RONIN_POSTGRES_TEST_DSN = "postgresql://ronin:ronin@localhost:5432/ronin_qualification"
$env:RONIN_TEST_POSTGRES_DSN = $env:RONIN_POSTGRES_TEST_DSN
$env:RONIN_CONNECTOR_POSTGRES_DSN = $env:RONIN_POSTGRES_TEST_DSN
$env:RONIN_TEST_S3_ENDPOINT = "http://localhost:4566"
$env:RONIN_TEST_S3_BUCKET = "ronin-qualification"
docker compose -f compose.yaml up -d postgres
docker compose -f compose.yaml ps
python -m pytest -q `
  tests/integration/test_postgres_artifact_retention_barrier.py `
  tests/integration/test_postgres_workflow_store_real.py `
  tests/integration/test_ml_s3_artifact_store_real.py `
  2>&1 | Tee-Object (Join-Path $Evidence "postgres-artifact-tests.log")
docker compose -f compose.yaml logs --no-color |
  Out-File (Join-Path $Evidence "compose.log")
docker compose -f compose.yaml down -v
```

`compose.yaml` no incluye un servicio `localstack`. Para ejecutar la parte S3 hay que
levantar LocalStack por separado (o usar el servicio equivalente del runner de CI),
por ejemplo con `docker run --rm -d --name ronin-localstack -p 4566:4566 localstack/localstack:3`.
Si no se dispone de ese servicio, se deben ejecutar solo las pruebas PostgreSQL y
dejar la evidencia S3 como qualification pendiente; no se debe simular un resultado.

Para la qualification de ejecución real:

```powershell
$env:RONIN_REAL_DOCKER_QUALIFICATION = "1"
$env:RONIN_DOCKER_QUALIFICATION_EVIDENCE = Join-Path $Evidence "docker"
New-Item -ItemType Directory -Force $env:RONIN_DOCKER_QUALIFICATION_EVIDENCE | Out-Null
python -m pytest -q `
  tests/integration/test_docker_container_executor_real.py `
  tests/integration/test_worker_runtime_real.py `
  tests/integration/test_postgres_workflow_store_real.py::test_postgres_scheduler_daemon_replays_job_after_process_crash_without_duplicate `
  2>&1 | Tee-Object (Join-Path $Evidence "docker-runtime.log")
```

**Éxito:** Docker real, checkpoints, límites CPU/memoria, cancelación, reinicio del
worker y reconciliación terminan correctamente. Guardar image digest y logs.

### 13.8 Tests web automatizados

```powershell
npm --prefix web-tests test 2>&1 |
  Tee-Object (Join-Path $Evidence "playwright.log")
node --test web-tests/tests/*.test.mjs 2>&1 |
  Tee-Object (Join-Path $Evidence "web-node-tests.log")
```

Comprobar que pasan las rutas de Labs, quality, runs, compare, registry, scoring,
drift, deployments y errores HTTP. Revisar también consola del navegador, accesibilidad,
budgets y snapshots.

### 13.9 Arrancar la aplicación para la revisión manual

Consultar el comando de desarrollo oficial del repositorio antes de arrancar el
servidor:

```powershell
make help
```

Usar el target oficial, conservar su log y anotar la URL y el PID. No inventar una
URL ni un comando alternativo si el README o el Makefile define otro.

Para cada caso, abrir la ruta de Machine Learning Studio en una ventana limpia y
registrar `PASS`, `FAIL` o `BLOCKED` en `qualification-evidence/ui-manual.md`.

| ID | Acción manual | Debe comprobarse |
|---|---|---|
| UI-01 | Abrir sin sesión | Login/403; ningún dato privado parcial. |
| UI-02 | Abrir Labs vacío | Loading, empty state, CTA y consola sin errores. |
| UI-03 | Crear Lab válido y refrescar | ID real de API, persistencia y navegación correcta. |
| UI-04 | Enviar ID largo, campo extra y dataset invisible | Error visible; no se crea nada. |
| UI-05 | Ejecutar quality con nulls y target único | Profile, severidades, evidence y bloqueo explicable. |
| UI-06 | Lanzar training y recargar | Timeline, progress bounded y estado real recuperado. |
| UI-07 | Cancelar y reintentar desde una etapa | Checkpoints reutilizados solo cuando son válidos. |
| UI-08 | Abrir compare y exportar JSON/CSV | Ranking reproducible, límites y tie-breakers correctos. |
| UI-09 | Abrir model card, descargar y promover | Digest/provenance correctos y reason obligatorio. |
| UI-10 | Ejecutar score válido e inválido | Signature validada y error contextual en el inválido. |
| UI-11 | Crear deployment, health, predict y rollback | Pin fijo; rollback no cambia el champion. |
| UI-12 | Simular 401/403/404/409/500 | Mensaje útil, retry recuperable y shell estable. |
| UI-13 | Navegar con teclado | Foco visible, orden lógico, Escape y nombres accesibles. |
| UI-14 | Probar 320/768/1024/1440 px | Sin solapamientos, cortes ni acciones ocultas. |
| UI-15 | Repetir en Chromium/Firefox/WebKit | Resultado funcional equivalente y sin errores de consola. |

Capturar una screenshot por fallo, indicar URL, viewport, selector y respuesta HTTP.
Probar zoom 200%, contraste, reduced motion y lector de pantalla; los errores no
pueden depender solo del color.

### 13.10 Cerrar evidencia y preparar el PR

```powershell
git status --short
git diff --check
python tools/generate_public_v1_status.py --check
Get-ChildItem $Evidence -Recurse |
  Sort-Object FullName |
  Select-Object FullName,Length |
  Export-Csv (Join-Path $Evidence "manifest.csv") -NoTypeInformation
```

Revisar el manifest, retirar secretos y confirmar que todos los logs pertenecen al
SHA de `candidate-sha.txt`. Crear el PR desde una rama temporal:

```powershell
git switch -c codex/<nombre-corto>
git add <ficheros-cambiados>
git commit -m "<cambio explicable>"
git push -u origin codex/<nombre-corto>
gh pr create --base main --head codex/<nombre-corto> `
  --title "<título>" --body-file qualification-evidence/pr-body.md
gh pr checks <numero> --watch --interval 20
```

Fusionar solo con todos los checks obligatorios verdes. Después del merge, actualizar
el checkout y eliminar la rama temporal:

```powershell
git switch main
git pull --ff-only
git fetch origin --prune
git branch -D codex/<nombre-corto>
git push origin --delete codex/<nombre-corto>
git branch -a
git status --short
```

**Estado final:** solo `main` local/remota, worktree limpio, SHA fusionado igual al
SHA cualificado y evidencia disponible para cada gate. Estos comandos son instrucciones
para el operador; este documento no los ejecuta.

## 14. Plan de construcción detallado

Esta sección es la especificación de construcción. Cada casilla representa una tarea
de implementación concreta, con entradas, comportamiento y salida verificable. Las
tareas se ejecutan en orden; una tarea no se marca como terminada por tener clases
vacías o un mock que no ejerce el contrato real.

### 14.1 Estructura objetivo del código

Mantener estas responsabilidades separadas:

```text
python/studio_core/ml.py              contratos compartidos sin dependencias ML
python/studio_ml/domain.py            value objects y entidades inmutables
python/studio_ml/schemas.py           parseo externo y límites
python/studio_ml/errors.py            errores tipados y códigos estables
python/studio_ml/compiler.py          resolución de refs y generación de PipelineIR
python/studio_ml/orchestration.py     lifecycle durable y scheduling de nodos
python/studio_ml/runner.py            ejecución de un nodo y materialización
python/studio_ml/backends.py          capabilities, registry y ports de backend
python/studio_ml/runtime.py           algoritmos locales y artifacts declarativos
python/studio_ml/quality.py           profiling, suites y validation results
python/studio_ml/optimization.py      search spaces, trials y ranking
python/studio_ml/provenance.py        digest, signature y model card
python/studio_ml/service.py           casos de uso de registry/score/deployments
python/studio_storage/ports.py        Protocols de persistencia
python/studio_storage/sqlite_*.py    adapters SQLite
python/studio_storage/postgres_*.py  adapters PostgreSQL
python/studio_server/                 composición, rutas y OpenAPI
python/studio_ml/plugin.py            manifest, contribuciones y permisos
web/js/features.js                    estado y render de Studio
web-tests/tests/                      journeys de navegador
docs/contracts/                       contratos versionados y ADRs
```

Regla de dependencia: `studio_core` no importa scikit-learn, SQL, HTTP ni UI;
`studio_ml` depende de ports, no de una implementación concreta; el servidor
inyecta stores y adapters; la UI solo consume HTTP/OpenAPI.

### 14.2 Contratos de dominio y campos obligatorios

#### `LabId`, `LabVersionId`, `RunId`, `TrialId`, `ModelId`, `DeploymentId`

- Tipo externo: string UTF-8, máximo 256 caracteres, sin controles ni espacios
  laterales.
- Creación: generar UUID/ULID estable; nunca aceptar que otro workspace lo reutilice.
- Comparación: exacta y case-sensitive.
- Serialización: JSON string, sin conversión implícita.

#### `DatasetRef`

Campos: `catalog_id`, `snapshot_id`, `digest`, `row_limit`, `column_limit` y
`visibility_scope`. El resolver debe exigir que el snapshot existe, pertenece al
workspace, tiene el digest indicado y cabe en los límites antes de abrirlo.

#### `Lab`

Campos mínimos:

| Campo | Regla de construcción |
|---|---|
| `id` | `LabId` inmutable. |
| `workspace_id` | obligatorio; se toma del actor y nunca del body confiado. |
| `name` | 1–256 caracteres, sin controles. |
| `description` | opcional, límite documentado. |
| `task` | enum `classification`, `regression` o `clustering`. |
| `dataset_ref` | `DatasetRef` validado y visible. |
| `target_column` | obligatorio salvo clustering; debe existir en el snapshot. |
| `feature_definitions` | lista única por nombre y versión. |
| `backend_id` | backend anunciado por `BackendRegistry`. |
| `runtime_profile` | perfil permitido por la política del workspace. |
| `seed` | entero finito y persistido. |
| `created_at`, `updated_at` | timestamps UTC generados por el servicio. |
| `version` | entero monotónico para optimistic concurrency. |

#### `LabVersion`

Contiene el manifest canónico completo, su `manifest_digest`, la referencia a
`Lab`, el autor, la revisión fuente y el estado `draft`, `validated`, `compiled` o
`archived`. No se modifica después de validarse; un cambio crea otra versión.

#### `PipelineIR`

Campos: `ir_version`, `pipeline_digest`, `lab_version_id`, `nodes`, `resource_policy`,
`runtime_profile`, `source_revision` y `created_at`. Cada nodo contiene:

```json
{
  "id": "train-001",
  "kind": "train",
  "plugin": "builtin",
  "depends_on": ["prepare-001"],
  "config": {},
  "input_refs": [],
  "output_names": [],
  "resource_policy": {}
}
```

Validar antes de calcular el digest: IDs únicos, `depends_on` existentes, DAG sin
ciclos, tipos de nodo permitidos, límites de nodos, listas y payloads. El digest se
calcula sobre canonical JSON sin campos temporales ni secretos.

#### `Run`, `NodeExecution` y `Checkpoint`

`Run` conserva `run_id`, `workspace_id`, `lab_version_id`, `pipeline_digest`, `state`,
`idempotency_key`, `seed`, timestamps, actor y `failure_code`. `NodeExecution` añade
`node_id`, `attempt`, `state`, `runtime_identity`, `input_digests`, `output_digests`,
`started_at`, `finished_at` y `evidence_ref`. `Checkpoint` incluye el digest del nodo,
runtime, dependencias upstream y artifacts necesarios para reanudar.

#### `Trial`, `QualityResult`, `ModelVersion` y `Deployment`

- `Trial`: `trial_id`, `run_id`, parámetros canónicos, seed derivada, métricas finitas,
  coste, estado y timestamps.
- `QualityResult`: suite/version, dataset digest, checks, severidades, summary,
  evidence ref y decisión `allow`, `warn` o `block`.
- `ModelVersion`: model ID/version, artifact digest/size, signature de entrada/salida,
  metrics, provenance, stage `candidate|champion|archived` y owner.
- `Deployment`: deployment ID, workspace, model version, artifact digest fijado,
  state `pending|ready|degraded|failed|rolled_back`, health, endpoint y revision.

### 14.3 Máquinas de estados

Implementar las transiciones como funciones puras que reciben estado, evento, actor y
tiempo. Rechazar cualquier transición no listada con un error estable.

| Entidad | Transiciones válidas |
|---|---|
| LabVersion | `draft → validated → compiled → archived`; `validated → archived`. |
| Run | `queued → running → cancelling → cancelled`; `running → succeeded|failed`; `failed → retrying`; `retrying → running`. |
| Node | `pending → running → succeeded|failed|cancelled`; `pending → skipped`; `failed → retrying`. |
| ModelVersion | `candidate → champion|archived`; `champion → archived`; nunca `archived → champion`. |
| Deployment | `pending → ready|failed`; `ready → degraded|rolled_back`; `degraded → ready|failed`; `rolled_back → pending`. |

Persistir primero la autoridad de cancelación/promoción y después ejecutar efectos
externos. Un reintento repetido con la misma idempotency key debe devolver el recurso
original; una key con body distinto debe producir `409`.

### 14.4 Diseño de almacenamiento y migraciones

Crear migraciones forward-only con estas tablas lógicas e índices:

| Tabla | Claves y datos | Índices/constraints |
|---|---|---|
| `ml_labs` | workspace, id, name, task, current_version, timestamps. | PK `(workspace_id,id)`, nombre no obligatorio único. |
| `ml_lab_versions` | lab, version, manifest JSON, digest, state, actor. | unique `(workspace_id,lab_id,version,digest)`. |
| `ml_runs` | run, lab version, pipeline digest, state, idempotency, seed. | unique `(workspace_id,idempotency_key)`. |
| `ml_node_executions` | run, node, attempt, state, runtime identity. | unique `(run_id,node_id,attempt)`. |
| `ml_checkpoints` | run/node, input/output digests, evidence, runtime. | índice por `(run_id,node_id)`. |
| `ml_trials` | run, trial ID, params JSON, metrics JSON, rank. | unique `(run_id,trial_id)`. |
| `ml_quality_suites` | suite, version, expectations JSON, owner. | unique `(workspace_id,suite_id,version)`. |
| `ml_quality_results` | run, suite, dataset digest, decision, evidence. | índice por workspace/run. |
| `ml_model_versions` | model/version, artifact, signature, stage, provenance. | unique `(workspace_id,model_id,version)`. |
| `ml_deployments` | deployment, model pin, artifact digest, state, health. | unique `(workspace_id,deployment_id)`. |
| `ml_idempotency` | workspace, key, request digest, resource response. | unique `(workspace_id,key)`. |

Cada mutación debe abrir transacción, verificar workspace/version, escribir el estado
durable y devolver el nuevo `version`. Las listas deben ordenar por `(created_at,id)`
y devolver cursor opaco; no usar `OFFSET` para paginación pública.

Implementar el adapter SQLite primero. Después implementar PostgreSQL con la misma
interfaz y pruebas de paridad. La barrera de artifacts debe cubrir desde la escritura
de bytes hasta el commit de la referencia; el recolector usa lease exclusivo y falla
cerrado si no puede adquirirlo.

### 14.5 Compiler y orquestación: algoritmo de implementación

Implementar `compile_lab(lab_version, actor, now)` en este orden:

1. Cargar la versión por `(workspace_id, lab_id, version)` y verificar que no está
   archivada.
2. Resolver `DatasetRef` y materializar un snapshot read-only; devolver error antes
   de crear un run si el digest o el scope no coinciden.
3. Consultar `BackendRegistry`; verificar task, algoritmo, preprocessor y runtime.
4. Normalizar defaults, seed, resource policy y opciones en canonical JSON.
5. Crear nodos base: `profile → quality → prepare → train → evaluate → select`.
6. Añadir `register` solo si el actor lo solicita y tiene permiso.
7. Añadir nodos plugin usando `plugin:<namespace>.<stage>` y validar sus ports.
8. Validar el DAG y topological sort estable por `(dependency_order,node_id)`.
9. Calcular `pipeline_digest` y persistir el IR antes del `Run`.
10. Devolver el IR y la lista de warnings; nunca iniciar training durante compile.

Implementar `create_run` como operación idempotente: primero buscar la key, luego
persistir `queued`, después encolar el dispatch. Si el dispatch falla, el run queda
reconciliable y no se crea una segunda intención.

Implementar el ciclo del orquestador:

```text
load run
→ acquire workspace/resource lease
→ select pending nodes whose dependencies succeeded
→ persist node=running and attempt
→ dispatch node
→ record outputs/evidence/checkpoint
→ release lease
→ repeat until terminal
```

En cada ciclo, comprobar cancelación, timeout, generación de lease y digest de
dependencias. Si un nodo cambia de identidad, invalidar sus dependientes. Al alcanzar
`register`, volver a verificar artifact, workspace, digest y autorización antes de
publicar el modelo.

### 14.6 Runner y protocolo de plugins

Definir una interfaz de ejecución con:

```python
prepare(context) -> PreparedInputs
run(context, inputs, progress) -> NodeOutput
cancel(context) -> None
close(context) -> None
```

`context` contiene run/node/attempt, workspace, runtime, resource policy, input
ArtifactRefs y cancellation token; nunca contiene secretos serializados en el IR.

Implementar estas reglas en `runner.py`:

- crear workdir aleatorio dentro de un directorio permitido;
- materializar inputs read-only y comprobar tamaño/digest;
- imponer timeout, pids, CPU, memoria y salida máxima;
- emitir heartbeat con frecuencia bounded y progress monotónico;
- escribir output bytes mediante `ArtifactStore.put_bytes`;
- comprobar digest después de escribir y antes de persistir la referencia;
- cerrar backend en éxito, error y cancelación;
- conservar evidence parcial sin convertirla en output válido;
- borrar workdir en `finally`, salvo una policy explícita de debug.

Los plugins deben anunciar manifest, capabilities, schemas de configuración, routes,
jobs y UI contributions. Un plugin inválido no puede registrarse parcialmente.

### 14.7 Backends y artifacts locales

Implementar `BackendCapabilities` con task, algorithms, preprocessors, prediction,
inspection, determinism y resource limits. El registry debe rechazar IDs duplicados,
capabilities contradictorias y adapters sin version.

Para cada algoritmo local:

1. Validar columnas y tipos antes de convertir datos.
2. Separar preprocessing del estimator.
3. Derivar seed de la seed del run y del trial.
4. Guardar parámetros efectivos, defaults y protocolo de evaluación.
5. Calcular métricas finitas; NaN/inf es fallo del nodo.
6. Serializar un artifact declarativo con versión y checksum.
7. Implementar `inspect` sin ejecutar código del artifact.
8. Implementar `predict` verificando signature, columnas, tipos y límites.

Implementar primero Logistic/Linear Regression, después árboles, Random Forest,
Gradient Boosting y K-Means. Cada estimator debe tener un fitter puro y un loader
seguro. No añadir una dependencia opcional al requirements base.

### 14.8 Profiling y quality gates: reglas exactas

El profiler devuelve solo agregados:

- `row_count`, `column_count`, null count/rate;
- distinct bounded y duplicate rate;
- min/max/mean cuando el tipo lo permite;
- cuantiles con método documentado;
- histogramas y top categories limitados;
- target distribution y class imbalance.

Las expectations se evalúan en orden estable y producen `check_id`, observed value,
threshold, severity, message y evidence ref. La decisión se calcula así:

```text
si algún check failure → block
si no hay failure y existe warning → warn
si todos pasan → allow
```

El servicio debe evaluar quality antes de `prepare`; score puede exigir una suite
posterior si la policy lo indica. Un resultado no se considera aprobatorio hasta
persistir su evidence con el mismo dataset digest.

### 14.9 Search, trials y ranking

Implementar `SearchSpec` con:

- `mode`, `space`, `max_trials`, `random_seed`, `primary_metric`;
- dirección `maximize| minimize`;
- tie-breakers ordenados con dirección propia;
- `patience`, `min_delta` y `pruning_policy`.

Validar el espacio completo antes de crear el primer trial. Rechazar nombres
duplicados, tipos no soportados, valores ilimitados, grids vacíos y más del máximo
de combinaciones. Los IDs se derivan de canonical JSON de parámetros y seed.

Para cada trial, persistir `queued` antes de ejecutarlo. Los resultados parciales no
entran en el ranking final. El ranking compara primero la métrica primaria, después
los tie-breakers, después coste y finalmente `trial_id` para resolver un empate total.

Bayesian debe usar un surrogate discreto bounded, propuestas reproducibles, memoria
limitada y parada por paciencia. El pruning es cooperativo: el callback puede pedir
cancelación, pero el runner debe guardar la razón y el último heartbeat.

### 14.10 Registry, provenance y publicación

Implementar `register_execution` como transacción lógica en cuatro pasos:

1. Leer run terminal y verificar `succeeded`.
2. Leer artifact y comprobar bytes, tamaño, digest, workspace y signature.
3. Escribir `Experiment`, `MLRun` y `ModelVersion candidate` con provenance completa.
4. Persistir evidence y devolver el model version; reintentos idénticos deben ser
   idempotentes.

Implementar `promote_model` con lock por workspace/model ID:

- exigir permiso y reason no vacío;
- comprobar que la evaluación quality requerida está aprobada;
- archivar el champion anterior en la misma transacción;
- escribir audit event con actor, reason, from/to stage y digests;
- nunca borrar el artifact del champion anterior.

El model card debe incluir intended use, limitations, dataset/snapshot digest,
features, metrics, quality, fairness si aplica, owner, source revision, runtime,
dependencies y artifact digest.

### 14.11 API y OpenAPI: endpoints y validaciones

Implementar estas familias, siempre bajo workspace y autorización:

| Ruta | Operaciones mínimas |
|---|---|
| `/v1/ml-studio/backends` | `GET` capabilities disponibles. |
| `/v1/ml-studio/labs` | `POST`, `GET` paginado. |
| `/v1/ml-studio/labs/{lab_id}` | `GET`, `PUT/replace`, `archive`. |
| `/v1/ml-studio/labs/{lab_id}/validate` | validar manifest y dataset. |
| `/v1/ml-studio/labs/{lab_id}/compile` | generar/persistir PipelineIR. |
| `/v1/ml-studio/executions` | crear run idempotente y listar. |
| `/v1/ml-studio/executions/{run_id}` | detalle, events, evidence, cancel, retry. |
| `/v1/ml-studio/executions/{run_id}/compare` | ranking filtrado y export. |
| `/v1/ml-studio/executions/{run_id}/register` | publicar candidate model. |
| `/v1/ml-studio/executions/{run_id}/quality` | suite, resultado y evidence. |
| `/v1/ml-studio/models` | listar modelos/versiones. |
| `/v1/ml-studio/models/{model_id}/{version}/card` | model card. |
| `/v1/ml-studio/models/{model_id}/{version}/artifact` | descarga chunked verificada. |
| `/v1/ml-studio/models/{model_id}/{version}/promote` | promoción con reason. |
| `/v1/ml-studio/models/{model_id}/{version}/score` | score batch. |
| `/v1/ml-studio/deployments` | crear/listar deployment fijado. |
| `/v1/ml-studio/deployments/{id}/health` | readiness/health. |
| `/v1/ml-studio/deployments/{id}/predict` | prediction contra digest fijado. |
| `/v1/ml-studio/deployments/{id}/rollback` | rollback seguro. |

Cada handler debe aplicar esta secuencia: parsear JSON estricto, validar límites,
hidratar actor, comprobar workspace/permisos, invocar servicio, mapear error estable,
auditar la mutación y serializar respuesta. OpenAPI debe declarar campos required,
additionalProperties, límites, enums, paginación y respuestas de error.

### 14.12 UI: construcción por pantalla

#### Shell y navegación

- Registrar `mlstudio` en el manifest y en la navegación solo cuando el plugin está
  habilitado.
- Mantener `workspace_id` en el estado de ruta y no en una variable global implícita.
- Añadir estados `loading`, `ready`, `empty`, `error` y `forbidden` a cada vista.
- Cancelar fetches obsoletos al cambiar de workspace o seleccionar otro recurso.

#### Labs

- `LabsList`: llamar `GET /labs`, paginar con cursor y mostrar owner, task, dataset y
  versión.
- `LabWizard`: validar campos localmente, enviar manifest exacto y mostrar errores del
  servidor por campo.
- `LabDetail`: cargar versión, schema, profile, quality y PipelineIR desde API; nunca
  inferirlos de fixtures.

#### Pipeline y ejecución

- `PipelineCanvas`: renderizar nodos y edges desde PipelineIR, layout topológico,
  selección accesible y estado por nodo.
- `TrainForm`: poblar task/algorithm/preprocessor desde capabilities; ocultar o marcar
  `planned` cualquier capacidad no anunciada.
- `RunTimeline`: consumir events/evidence, ordenar por timestamp + ID y soportar refresh.
- `RetryDialog`: permitir seleccionar una etapa válida, mostrar consecuencias downstream
  y enviar idempotency key.

#### Trials, registry y serving

- `CompareView`: filtros, ranking direccional, tie-breakers y exportación desde la API.
- `ModelCard`: provenance, digest, métricas y limitaciones con enlace a evidence.
- `PromoteDialog`: reason obligatorio, permiso visible y confirmación de stage.
- `ScoreView`: batch ID, columnas, límites y errores de signature.
- `DeploymentView`: pin de versión, health, predict, eventos y rollback.

Cada vista debe conservar el estado al recargar, anunciar errores al lector de pantalla,
evitar doble submit y bloquear acciones mientras una mutación está pendiente.

### 14.13 Adapters remotos y MLflow

Definir un port común para `discover`, `submit`, `poll`, `cancel` y `predict` con:

- timeout finito por operación;
- límite de bytes de respuesta;
- backoff exponencial con máximo y jitter determinista opcional;
- clasificación de errores transitorios/permanentes;
- correlation ID y provider request ID;
- redacción de headers/body sensibles;
- cancelación que no borra evidence local.

`remote.ronin` envía solo PipelineIR firmado y refs; los secretos se resuelven en el
provider adapter. `mlflow.adapter` intercambia metadata canónica y flavors seguros;
no ejecuta código recibido ni sustituye `Run`/`ModelVersion` nativos. Un provider
indisponible debe dejar el run en estado reconciliable y conservar el último error.

### 14.14 Feature definitions y snapshots

Implementar `FeatureDefinition` versionado e inmutable con nombre, tipo, source
expression, owner, tags, dataset snapshot digest y created/retired timestamps.

- Crear una nueva versión para cualquier cambio semántico.
- Validar que todas las columnas fuente pertenecen al snapshot visible.
- Incluir feature manifest digest en `LabVersion` y `ModelVersion`.
- Impedir retirar una versión usada por un run o deployment activo.
- Exponer create/list/get/archive con workspace scope e idempotencia.

### 14.15 Observabilidad y auditoría

Emitir métricas bounded para compile, queue latency, node duration, retries, bytes,
quality failures, model promotions, score latency y deployment health. Cada evento
debe incluir workspace, run/model/deployment ID y correlation ID, nunca dataset values,
tokens o credentials.

Registrar audit events append-only para crear/reemplazar/archivar Lab, cancelar/retry,
registrar/promover modelo, descargar artifact y cambiar deployment. La auditoría debe
guardar actor, permiso evaluado, motivo, resultado y digests relevantes.

### 14.16 Migración, rollout y rollback

1. Añadir migración forward-only y actualizar el número de schema.
2. Ejecutar migración en una copia y verificar conteos, constraints y checksums.
3. Activar rutas nuevas detrás de `plugin_routes_enabled` o feature flag.
4. Migrar datos en lotes idempotentes, registrando progreso y último cursor.
5. Activar lectura nueva antes de activar mutaciones nuevas.
6. Observar errores, latencias y audit events durante el canary.
7. Para rollback de aplicación, desactivar la ruta sin borrar columnas ni artifacts.
8. Para rollback de datos, ejecutar solo procedimientos forward documentados; no hacer
   `down migration` destructiva en producción.

### 14.17 Criterios de terminado por fase

Una fase solo se marca `[x]` cuando se cumplen todos sus puntos:

- implementación real en los módulos indicados;
- contrato/documentación actualizado;
- tests unitarios/contrato de errores y camino feliz;
- persistencia o API real cuando la fase lo requiere;
- autorización, límites y redacción cubiertos;
- evidencia del gate inmediato asociada al commit;
- ningún TODO que cambie el comportamiento prometido;
- revisión de impacto en OpenAPI, SDK, UI, ledgers y migraciones.

Si una capacidad depende de un proveedor externo, marcarla `implemented,
qualification_pending` y registrar exactamente qué prueba externa falta. Nunca
marcarla como release-ready solo porque el adapter fake funciona.

### 14.18 Tabla de riesgos y corrección obligatoria

| Síntoma | Causa probable | Corrección requerida |
|---|---|---|
| Dos runs para la misma petición | idempotencia comprobada después del dispatch. | Reservar key y recurso en una transacción antes de encolar. |
| Checkpoint reutilizado con otro runtime | identity incompleta. | Incluir fuente, Python, dependencias, backend, options y upstream digests. |
| Artifact visible entre workspaces | ref sin scope en query o cache. | Filtrar por workspace en cada port y invalidar caches. |
| Ranking distinto en repetición | seed o orden no canónico. | Derivar seed/ID de canonical JSON y ordenar empates por ID. |
| UI muestra métrica inexistente | fixture o estado local inventado. | Renderizar solo payload validado de API y mostrar `unknown`. |
| Promoción deja dos champions | lock o transacción insuficiente. | Lock por scope/model y transición atómica con audit event. |
| Cleanup borra artifact usado | live set incompleto. | Barrera compartida, inventario completo y fail-closed. |
| Docker pasa local y falla CI | dependencia implícita del host. | Fijar imagen, variables, healthchecks y resource limits. |
| OpenAPI y handler difieren | cambio manual no sincronizado. | Contract test y snapshot actualizado en el mismo commit. |
| Ledger apunta a otro SHA | actualización parcial de documentos. | Ejecutar generador/check y actualizar todas las superficies. |
