# RONIN — plan práctico de construcción, UX, compatibilidad y release

**Release objetivo:** 7 de enero de 2027 (Europe/Madrid)  
**Ventana principal de pruebas y pulido:** 21 de diciembre de 2026 – 3 de enero de 2027  
**Estado inicial del plan:** 12 de noviembre de 2026  
**Producto:** plataforma open source, local-first, para desarrollar y operar soluciones de datos e IA compatibles con los flujos habituales de Databricks, Microsoft Fabric, Palantir Foundry y Dataiku.  
**Licencia propuesta para el núcleo:** Apache-2.0, sujeta a revisión legal y a un inventario completo de dependencias.

> Este documento convierte en decisiones de producto las instrucciones del usuario y reconcilia los dos documentos de referencia: `C:\Users\angel.alvarez\Downloads\RONIN_PUBLIC_V1_100_PERCENT_BUILD_PLAN.md` y `C:\Users\angel.alvarez\Downloads\RONIN_RELEASE_2026-11-03_TEST_MASTER.md`. Esos documentos son la línea base de riesgos, contratos y pruebas; no son evidencia de que el producto actual esté completo. La fecha del 7 de enero es un objetivo, no una autorización para rebajar gates.

## 1. Decisión de producto

### 1.1 Qué vamos a construir

RONIN será una plataforma local-first que permita al usuario:

1. Conectar y descubrir datos.
2. Crear tablas y pipelines mediante UI guiada, SQL, Python y notebooks.
3. Ejecutar trabajos acotados, programarlos, observarlos, cancelarlos y recuperar su evidencia.
4. Aplicar calidad, catálogo, linaje, semántica y controles de acceso al mismo objeto de trabajo.
5. Entrenar, registrar, evaluar, promover y servir modelos con contratos portables.
6. Exportar e importar proyectos, notebooks, tablas, pipelines, modelos y metadatos hacia los formatos y APIs soportados.
7. Operar todo desde una UI sencilla, con un camino guiado para la mayoría y un modo experto para quien necesite SQL, JSON, Python o configuración avanzada.

### 1.2 Qué significa “100% compatible”

No es técnicamente honesto prometer que una plataforma open source local reproduce cada servicio propietario de cuatro productos comerciales. En este plan, **100% compatible** significa:

- **100% de las operaciones comunes declaradas** tienen contrato, implementación, import/export o adaptador, y una prueba de aceptación.
- Los formatos y protocolos abiertos se preservan sin pérdida dentro del alcance soportado.
- Un proyecto documentado puede moverse entre RONIN y el producto de origen sin reescritura manual de la lógica soportada.
- Cada limitación propietaria queda visible en la UI, la matriz de compatibilidad y el export, nunca escondida detrás de un “success” ambiguo.
- Las funciones exclusivas de un proveedor se clasifican como `native`, `translated`, `emulated`, `export-only` o `unsupported`, con explicación y criterio de salida.

La compatibilidad no se contará por número de endpoints ni por líneas de código. Se contará por **journeys de usuario completos**, con entradas, efectos, evidencia y round-trip.

### 1.3 Edición gratuita y edición comercial

**RONIN Community / OSS:**

- Núcleo local-first, API, CLI, SDK, UI, conectores y formatos definidos en la matriz OSS.
- Uso individual y de equipos pequeños en local.
- Documentación reproducible, fixtures, formatos abiertos y migración sin vendor lock-in.
- Sin prometer soporte empresarial, SLA, alta disponibilidad ni certificación de proveedores que no tengan evidence pack.

**RONIN Pro / Commercial:**

- Soporte, SLA, hardening empresarial, gestión centralizada de identidades, multiusuario avanzado, Kubernetes gestionado, observabilidad empresarial, conectores premium y controles de gobierno adicionales.
- Módulos comerciales separados del núcleo Apache-2.0; no se debe contaminar el core con una dependencia propietaria ni retirar funcionalidades básicas para forzar la compra.

La separación OSS/Pro se aprobará en un ADR antes del release candidate. No se usará la edición comercial para ocultar que una capacidad OSS está incompleta.

## 2. Resultado que debe existir el 7 de enero

La release sólo será `GO` si existe un candidato único, limpio y reproducible que cumpla todos estos resultados:

| Resultado | Criterio mínimo de aceptación |
|---|---|
| Primera experiencia | Un usuario nuevo crea contexto, conecta un dataset de ejemplo y ejecuta una transformación sin leer documentación técnica. |
| Datos | Ingesta batch de CSV/JSON/JSONL/Parquet, SQL sobre Postgres/DuckDB, tablas Delta/Iceberg dentro del alcance publicado y export reproducible. |
| Pipelines | Flow visual y modo código; validación antes de ejecutar; preview; ejecución durable; reintento; cancelación; logs; evidencia; lineage. |
| Notebooks | Import/export `.ipynb`, SQL/Python, celdas editables, revisión de cambios, ejecución parcial/total, parámetros, cancelación y resultados. |
| Calidad | Reglas, profiling, resultados legibles, severidad, bloqueo opcional y vínculo al dataset/versión/run que produjo el hallazgo. |
| Catálogo y semántica | Assets, owners, tags, columnas, relaciones, métricas, objetos y links; búsqueda y navegación por contexto. |
| ML | Dataset → experimento → modelo → evaluación → registro → promoción → batch/online inference dentro de los contratos soportados; artefactos con digest. |
| Compatibilidad | Round-trip probado para los formatos/protocolos P0 y journeys de import/export para cada plataforma objetivo. |
| UX | Formularios progresivos, defaults seguros, no JSON obligatorio para el camino común, errores accionables, foco/teclado, responsive 320–1440 px y estados loading/empty/error/success. |
| Seguridad | Secrets fuera de logs, autorización por contexto, SSRF/IDOR/CSRF/XSS/SQLi cubiertos, SBOM, provenance, escaneo de secretos y política de dependencias. |
| Recuperación | Backup/restore probado, migraciones expand/contract, rollback de aplicación y artefactos, recuperación documentada y rehearsed. |
| Release | Wheel/sdist/imagen construidos una vez, instalados fuera del checkout, con hashes, SBOM, provenance, LICENSE/NOTICE y evidencia candidate-bound. |

Si falta un resultado obligatorio, el release se aplaza; no se reduce silenciosamente la definición de “completa”.

## 3. Estudio de mercado y decisiones de interoperabilidad

La selección no se basa en una cifra de cuota de mercado no verificable, sino en los patrones que los cuatro productos documentan y que se repiten en los equipos de datos: workspace/contexto, ingesta, flow/pipeline, notebooks/SQL, ejecución observable, catálogo/linaje, semántica, ML, gobierno y despliegue.

### 3.1 Patrones que RONIN debe adoptar

| Plataforma | Patrón observado | Decisión RONIN |
|---|---|---|
| Databricks | Lakehouse, notebooks, SQL, jobs, MLflow/registro y gobierno de datos/IA | Priorizar notebooks + SQL + jobs + Delta/Iceberg/Parquet + MLflow/ONNX + catálogo y lineage. El usuario debe poder importar un flujo de notebook/job y ver qué parte es portable. |
| Microsoft Fabric | Workspace, Lakehouse, Warehouse/SQL, notebooks, pipelines, OneLake y modelos semánticos | Adoptar workspace → lakehouse → notebook/pipeline → modelo semántico como journey. Usar Parquet/Delta/SQL y APIs de export, no copiar servicios cerrados. |
| Palantir Foundry | Data Connection, proyectos por etapas, lineage/versiones, Ontology de objetos/links/acciones y workflows operativos | Construir una capa de objetos/links/acciones encima del catálogo y conectar acciones con runs y auditoría. La UI debe mostrar “qué decisión/acción habilita este dato”, no sólo el esquema. |
| Dataiku | Proyecto, Flow visual, datasets/recipes, visual + code recipes, ML, escenarios, despliegue y gobierno | Hacer del Flow el centro de authoring: cada transformación debe tener inputs, outputs, preview, configuración simple, explicación y receta editable. |

### 3.2 Matriz de compatibilidad por prioridad

#### P0 — contrato común de la release

- Python 3.11/3.12, REST/OpenAPI, CLI y SDK Python.
- SQL parametrizado, Postgres, DuckDB y resultados paginados.
- CSV, JSON, JSONL, Parquet, Arrow y `.ipynb`.
- Delta Lake e Iceberg en el alcance realmente implementado y documentado.
- S3-compatible y Azure Blob mediante referencias de conexión y límites de bytes.
- Git, archivos de proyecto exportables y manifiesto versionado.
- Jobs/pipelines, cron, idempotencia, logs, evidencia, cancelación y retry.
- MLflow-compatible metadata, modelos con digest y ONNX cuando el artefacto sea lossless.
- OpenTelemetry/OTLP para trazas, métricas y logs donde aplique.

#### P1 — compatibilidad de ecosistema

- Kafka/Redpanda con semántica explícita `at-least-once`, offsets, lag, poison records, replay y límites de batch.
- Spark/Spark Connect y Trino como runtimes opcionales cualificados por separado.
- dbt como import/export de modelos y tests, sin asumir que el runtime dbt está instalado.
- Airflow/Dagster/Prefect mediante export de DAG/flow o trigger REST, no como dependencia del core.
- Unity Catalog/OneLake/Foundry/Dataiku: adaptadores de import/export y conformance suite; no se fingirá acceso a servicios propietarios.

#### P2 — proveedores y extensiones

- Flink, Snowflake, BigQuery, Redshift, Databricks SQL remoto, Fabric remoto, servicios cloud y plugins de terceros.
- Cada integración P2 debe vivir en un plugin/adapter aislado, con lock, credentials profile, egress policy y lane de proveedor.

### 3.3 Definition of compatibility

Cada integración tendrá un archivo de matriz con:

```text
capability_id
source_platform
source_version
ronin_version
format_or_protocol
import_status
export_status
roundtrip_status
semantic_differences
security_boundary
qualification_sha
artifact_digest
owner
```

Los estados admitidos son `native`, `translated`, `emulated`, `export-only`, `unsupported`, `qualified`, `experimental`. Nunca se puede mostrar `compatible` sin un caso de aceptación ejecutado sobre una identidad exacta.

## 4. Objetivo UX/UI: Databricks + Fabric + Palantir + Dataiku, pero más simple

La prioridad no es añadir más pantallas. Es reducir decisiones visibles y poner el contexto y el siguiente paso delante del usuario.

### 4.1 Principios de diseño

1. **Una operating surface.** El usuario no debe saltar entre 20 mini-Studios para completar una tarea.
2. **Contexto visible y persistente.** Workspace, proyecto, entorno, asset y run aparecen siempre en la cabecera.
3. **Progressive disclosure.** El camino común muestra 3–7 decisiones; los campos avanzados aparecen bajo “Más opciones”.
4. **Defaults seguros.** Un botón primario debe hacer algo razonable sin rellenar JSON.
5. **Preview before commit.** Toda mutación durable ofrece preview/diff/impacto antes de escribir.
6. **Evidence by default.** Cada run muestra estado, entradas, outputs, logs, lineage, warnings y coste/limitaciones.
7. **Recoverability.** Un error mantiene el formulario, la selección y el contexto; nunca devuelve al usuario a una pantalla vacía.
8. **Consistencia verbal.** `Create`, `Preview`, `Run`, `Review`, `Publish`, `Promote`, `Rollback`, `Archive`, `Delete` deben significar lo mismo en toda la plataforma.
9. **No raw JSON en el camino feliz.** JSON, YAML y código son modos expertos, no la interfaz primaria.
10. **Agradable antes que espectacular.** Tipografía, whitespace, foco, densidad, estados y velocidad importan más que gradientes o dashboards decorativos.

### 4.2 Nueva arquitectura de navegación

La navegación objetivo se reduce a seis superficies principales:

1. **Home:** contexto, recientes, salud, tareas pendientes y quick actions.
2. **Build:** Flow visual, SQL, notebooks y transformaciones.
3. **Data:** conexiones, catálogo, tablas, perfiles, calidad y lineage.
4. **Run:** jobs, schedules, executions, logs, evidence, retry y recovery.
5. **ML:** labs, experiments, models, evaluations, deployments y monitoring.
6. **Govern:** owners, policies, permissions, semantic objects, audit, bundles y release readiness.

`Settings` queda como configuración de cuenta/instancia. Los nombres técnicos (`QueryFlux`, `Synthetic Data Studio`, etc.) se muestran como subtítulos o modo avanzado, no como la taxonomía principal.

### 4.3 Plantilla de cada pantalla

Cada pantalla debe responder en este orden:

1. **Qué puedo hacer aquí.** Título y una frase de objetivo.
2. **Sobre qué objeto.** Context bar y breadcrumbs.
3. **Qué estado tiene.** KPI o status legible, con timestamp.
4. **Cuál es el siguiente paso.** Un CTA primario y máximo dos secundarios.
5. **Qué evidencia existe.** Preview, diff, lineage, logs o resultado.
6. **Qué puedo hacer si falla.** Retry, edit, change context, copy error, export evidence.

### 4.4 Wizards prioritarios

Construir primero estos seis wizards:

1. **Connect data:** tipo → credencial referenciada → test connection → preview schema → save.
2. **Build pipeline:** source → transform → quality → destination → preview → schedule/run.
3. **Run notebook/SQL:** choose context → editor → parameters → limits → run → evidence.
4. **Train model:** dataset → target/features → candidate → quality gate → register → review/promote.
5. **Deploy:** artifact → environment → endpoint/batch → policy → preview impact → publish.
6. **Recover:** failed run/asset → diagnosis → available backup/checkpoint → dry-run restore → restore → verify.

Cada wizard debe tener un happy path de menos de diez minutos para un dataset de ejemplo y un expert path sin ocultar las capacidades avanzadas.

### 4.5 Criterios UX medibles

Antes del RC se medirán con usuarios internos y externos de prueba:

- 90% de usuarios nuevos completan `connect → preview → run` sin ayuda.
- Tiempo mediano a primer resultado: ≤10 minutos.
- No más de 7 controles visibles en el primer paso de un wizard.
- 0 campos JSON obligatorios en los seis happy paths.
- 0 bloqueos de teclado, foco perdido o acciones sólo accesibles por ratón.
- 0 errores sin causa, impacto y siguiente acción.
- 100% de operaciones destructivas con diálogo de impacto accesible.
- Responsive validado a 320, 390, 768, 1024, 1280 y 1440 px.

Los targets no son evidencia actual; se convierten en PASS sólo con sesiones y receipts guardados.

## 5. Arquitectura funcional objetivo

### 5.1 Núcleo mínimo

| Capa | Responsabilidad | Regla KISS |
|---|---|---|
| Context | workspace, project, environment, identity, permissions | Un objeto `Context` compartido en UI/API/SDK. |
| Assets | dataset, table, notebook, pipeline, model, deployment, semantic object | IDs estables, versiones y digest; no IDs implícitos en localStorage. |
| Execution | job, run, task, logs, evidence, cancellation, retry | Un contrato de run común; cada plugin sólo aporta executor. |
| Storage | SQLite/Postgres, object store local/S3-compatible, bundle | SQLite local-first; Postgres/objects como perfiles explícitos. |
| Catalog | schema, owner, tags, lineage, quality, semantic links | El catálogo es la vista humana del asset, no una segunda fuente de verdad. |
| Policy | grants, secrets refs, egress, byte/time/resource limits | Deny by default y explicación visible. |
| Adapters | Databricks/Fabric/Foundry/Dataiku/engine/provider | Adaptadores versionados, aislados y con matriz de compatibilidad. |

### 5.2 Contratos que no se deben romper

- OpenAPI es la fuente pública de rutas y schemas.
- SDK y CLI deben derivarse del mismo contrato o tener tests de paridad.
- Un run siempre incluye `context`, `input_refs`, `output_refs`, `state`, `timestamps`, `evidence_ref` y `failure_code`.
- Un asset mutable requiere `revision`/ETag y control `If-Match` o equivalente.
- Una operación repetible requiere `Idempotency-Key` y semántica documentada.
- Un conector no puede aceptar un endpoint o path fuera de su egress policy.
- Un secreto nunca aparece en logs, exports, bundles, screenshots o errores.
- Ningún adapter puede convertir `at-least-once` en `exactly-once` por copywriting.

## 6. Plan de construcción por etapas

Cada etapa termina con: cambios, tests focalizados, gate completo equivalente, commit, push, CI exacta y receipt. Si la etapa falla, se corrige en otro commit; no se avanza con rojo.

### Etapa 0 — alcance, baseline y gobierno (12–18 noviembre)

**Entregables**

- Este plan aprobado y un ADR de alcance OSS/Pro.
- Matriz `capability × platform × format × evidence` para las seis superficies.
- Product glossary y nombres finales de navegación.
- Lista de claims permitidos/prohibidos.
- Restablecimiento/confirmación de CI obligatoria para PR/push, branch protection y release refs.

**Aceptación**

- No existen dos definiciones de Public v1.
- Cada capacidad tiene owner, prioridad, dependencia, test y criterio GO/NO-GO.
- Los claims no cualificados aparecen como `experimental` o `unsupported`.

### Etapa 1 — design system y shell (19–25 noviembre)

**Entregables**

- Shell único con Home/Build/Data/Run/ML/Govern.
- Context bar, command palette, breadcrumbs, notifications, global search y quick create.
- Componentes accesibles: button, input, select, combobox, table, tabs, wizard, dialog, toast, status, empty/error/loading.
- Tokens de color/espaciado/tipografía, light/dark, focus-visible y responsive.
- Migración de las rutas existentes al shell sin perder deep links.

**Aceptación**

- 100% de rutas canónicas usan shell/contexto común.
- 0 confirmaciones nativas; 0 formularios con JSON como único camino.
- Axe sin serious/critical, teclado completo, 320–1440 responsive.
- `studio_budget` no crece sin una justificación y un nuevo baseline.

### Etapa 2 — primer valor y Data/Build (26 noviembre–6 diciembre)

**Entregables**

- Wizard Connect data.
- Catalog/data preview/schema/profile/quality.
- Flow visual con source, select, filter, join, aggregate, derive y sink.
- SQL editor con parámetros, límites visibles, preview y save as asset.
- Import/export de notebook `.ipynb` y editor de celdas.

**Aceptación**

- Un dataset fixture recorre conexión → preview → transformación → tabla → query.
- El mismo flow se exporta y vuelve a importar sin perder IDs, versiones o configuración.
- Error de schema, credencial, timeout y límite conserva inputs y ofrece recuperación.

### Etapa 3 — Run, scheduler y evidencia (7–13 diciembre)

**Entregables**

- Run detail unificado para pipeline, SQL, notebook, ML y adapter.
- Scheduler con cron/timezone, pause/resume, retry policy y backfill.
- Logs, metrics, evidence, lineage y artifacts desde una vista común.
- Cancelación segura y accesible, idempotencia y deduplicación.

**Aceptación**

- 15/15 journeys P0 sin skips sobre un candidato exacto.
- Un run se puede inspeccionar, reintentar, cancelar y exportar con evidencia.
- Un fallo de proveedor no produce estado `success` ni checkpoint falso.

### Etapa 4 — ML y operaciones (14–20 diciembre)

**Entregables**

- ML Lab simplificado: dataset, features, candidate, quality, train, register, review, promote.
- Model card, digest, provenance, batch prediction y deployment health.
- Operaciones con rollback/disable/restore, siempre con impact dialog y audit.
- Monitoring de drift/quality y alerta accionable.

**Aceptación**

- Model lifecycle completo en local con artefacto reproducible.
- Promoción exige motivo/review y no usa prompts nativos.
- Rollback no pierde evidencia ni modifica la versión anterior.

### Etapa 5 — portabilidad y adapters (21 diciembre–2 enero)

Esta etapa coincide con Navidad; se trabaja en carriles paralelos con fixtures pequeños y proveedores reales sólo cuando exista autorización y un entorno aislado.

**Databricks adapter**

- Notebook/jobs/SQL/Delta/MLflow/Unity-Catalog-like metadata.
- Import/export de proyecto y bundle.
- Tabla de diferencias frente a Spark/Photon/Unity Catalog/Model Serving.

**Fabric adapter**

- Workspace/lakehouse/notebook/pipeline/SQL/semantic model.
- Parquet/Delta/OneLake-compatible paths donde el entorno lo permita.
- Import/export y pruebas de notebook/SQL/pipeline.

**Foundry adapter**

- Data Connection → raw dataset → transform → ontology object/link → action/workflow.
- Lineage de versiones, políticas y evidencia de writeback.
- No se afirma compatibilidad con una Ontology propietaria sin un contrato de adapter verificable.

**Dataiku adapter**

- Project/Flow/datasets/recipes/scenarios/model bundle.
- Visual recipe para prepare, join, aggregate y train.
- Import/export de Flow y evidencia de rebuild.

**Aceptación común**

- Cada adapter tiene 10 journeys P0, 5 negativos y 1 round-trip.
- La UI explica qué se traduce y qué no.
- Un export no contiene secretos ni dependencia oculta del checkout.

### Etapa 6 — seguridad, supply chain y recovery (21 diciembre–3 enero)

**Entregables**

- Threat model actualizado por superficie.
- SBOM SPDX/CycloneDX por wheel, sdist e imagen.
- Provenance/attestation de builds; hashes del candidato.
- Secret scan, dependency review, SAST/lint/type checks, container scan, SSRF/IDOR/CSRF/XSS/SQLi/command injection.
- Backup SQLite/Postgres + árbol de artefactos; restore con integridad, digest y destino limpio.
- Rollback aplicación/imagen/Helm y runbook ejecutado.

**Aceptación**

- Cero HIGH/CRITICAL sin decisión explícita y evidence de excepción.
- Licencias y NOTICE cerrados por versión exacta del artefacto.
- Restore y rollback probados después de corrupción, interrupción y restart.
- La evidencia puede reconstruir el candidato sin conexión al árbol de trabajo.

### Etapa 7 — RC, hardening y release (4–7 enero)

**4 enero:** congelar SHA, versión `0.1.0`, manifests, artefactos y matriz.  
**5 enero:** ejecutar qualification completa, tres roles de usuario y todos los lanes P0.  
**6 enero:** revisión Product/QA/Security/Legal/Release; corregir sólo P0/P1 que no cambien alcance.  
**7 enero:** publicar únicamente si el acta dice `GO`; si no, mover la fecha sin reescribir el criterio.

## 7. Plan de pruebas exhaustivo

### 7.1 Pirámide

1. **Unitarias:** dominio, validación, permisos, transforms, parsers, retries, checksums.
2. **Contract:** OpenAPI, SDK/CLI, package data, schemas, error envelopes, idempotency, pagination.
3. **Integration:** SQLite/Postgres, object store, DuckDB, Spark/Trino, Kafka/Redpanda, OTLP, Azurite/Floci.
4. **E2E browser:** journeys reales del producto, no sólo presencia de botones.
5. **Compatibility:** import/export/round-trip por formato y plataforma.
6. **Security:** authz, tenancy, SSRF, secrets, injection, resource exhaustion, tampering.
7. **Resilience:** timeout, retry, cancellation, restart, corrupt artifact, stale revision, partial output.
8. **Performance:** p50/p95, RSS, bytes, concurrency, cold start, large schema, 100/1k/10k fixture rows.
9. **Manual UX:** tareas con usuario, observación, tasa de éxito, tiempo, errores y satisfacción.
10. **Packaging:** wheel/sdist/container/Helm limpio, instalado fuera del checkout.

### 7.2 Matriz mínima de journeys

| Journey | Happy path | Negativos obligatorios |
|---|---|---|
| Onboarding | crear contexto, fixture, primer run | contexto inválido, ausencia de token, API caída |
| Connection | create/test/schema/preview | secret faltante, endpoint fuera de egress, 401/403/timeout |
| Flow | source/filter/join/sink/preview/run | schema drift, input vacío, límites, duplicate idempotency |
| SQL | parameterized query/result paging/save | SQL injection, timeout, row/byte cap, cursor foreign |
| Notebook | import/edit/run/revision/export | dirty changes, invalid cell, runtime missing, cancel |
| Scheduler | create/preview/run/pause/backfill | timezone, overlap, duplicate run, failed retry |
| Quality | profile/rule/fail/waiver | malformed rule, PII leakage, unbounded scan |
| Catalog/ontology | asset/tag/lineage/object/link/action | cross-project, stale version, unauthorized write |
| ML | train/register/evaluate/promote/predict | bad artifact, digest mismatch, model rollback, drift |
| Deploy | bind/health/operate/rollback | wrong env, unavailable provider, policy deny, partial publish |
| Bundle | export/plan/import/verify | tamper, wrong workspace, duplicate, oversize, secret leak |
| Recovery | backup/restore/verify | corrupt backup, incomplete copy, restart, rollback failure |

### 7.3 Manual Christmas test programme

**Roles**

- Analista: conectar, explorar, filtrar, crear métrica, compartir resultado.
- Data engineer: ingestar, crear Flow, ejecutar, programar, depurar y recuperar.
- ML engineer: entrenar, comparar, registrar, promover y observar modelo.
- Operator/reviewer: revisar permisos, evidencia, seguridad, backup y release.

**Sesiones**

- 21–23 diciembre: onboarding y Data/Build.
- 24–27 diciembre: Run/notebooks/scheduler y recuperación de errores.
- 28–30 diciembre: ML, deployments, governance y bundles.
- 31 diciembre–1 enero: compatibilidad/import-export y reinstalación limpia.
- 2–3 enero: smoke completo, regresión visual, accesibilidad y cierre de defectos.

**Registro por sesión**

```text
user_role
environment
candidate_sha
task_id
start/end UTC
success/failure
help_needed
unexpected_field_or_error
screenshot_or_trace
severity
suggested_fix
retest_result
```

Un test manual no es “lo he mirado”: debe indicar tarea, resultado y defecto o confirmación.

## 8. Licencias, NOTICE y modelo open source

### 8.1 Recomendación

Mantener el core bajo Apache-2.0 porque el repositorio ya declara `Apache-2.0` y existe `LICENSE`. Es una buena base para uso local, integración empresarial, modificación y una futura oferta comercial, pero no elimina las obligaciones de conservar avisos, attribution y condiciones de dependencias.

No se debe llamar “100% open source” a una distribución que incluya un componente con restricciones incompatibles, una dependencia de sólo evaluación o un servicio propietario obligatorio.

### 8.2 Política propuesta

- SPDX ID para cada componente propio y cada licencia de dependencia.
- `LICENSE` para el core y `NOTICE` generado/revisado para atribuciones.
- Inventario exacto por lockfile, wheel, sdist, container y frontend assets.
- SBOM SPDX + CycloneDX por artefacto y digest.
- Allowlist inicial: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, MPL-2.0 y otras aprobadas caso por caso.
- Bloqueo automático de GPL/AGPL/SSPL/Commons Clause/BSL o licencias desconocidas en el core distribuido, salvo decisión legal y aislamiento explícito.
- Los cambios de dependencia abren una revisión de licencia/NOTICE y seguridad.
- DCO para contribuciones comunitarias en la primera fase; CLA sólo si el abogado y la estrategia de relicensing lo justifican.
- Marca RONIN y logos con política de trademark separada; Apache-2.0 no concede derechos de marca.

### 8.3 Cierre requerido

El gate legal lo firma una persona responsable. El tooling puede identificar hechos y diferencias, pero no puede decidir por sí solo si una licencia es admisible en todas las jurisdicciones o si un aviso satisface una obligación.

## 9. Seguridad y supply chain

### 9.1 Controles de merge

- PR obligatoria, branch protection efectiva y checks required.
- Actions fijadas por SHA, dependencias con hashes y lockfiles revisados.
- Ruff, mypy, pytest, OpenAPI/architecture/negative gates, web audit/budget y Playwright.
- Dependency review para cambios de dependencias.
- Secret scanning en working tree e historia.
- SBOM, provenance y artifact identity en cada RC.

### 9.2 Controles de runtime

- Auth y grants fail-closed.
- Contexto workspace/project en cada lectura/escritura.
- Egress allowlist y bloqueo SSRF de loopback/link-local/metadata endpoints.
- Secrets referenciados, nunca incluidos en bundles ni logs.
- Límites de bytes, filas, tiempo, memoria, concurrencia y número de tareas.
- Revisión de resultados antes de aplicar acciones externas.
- Audit event para mutaciones, promoción, restore, rollback y export.

### 9.3 Respuesta

`SECURITY.md` debe publicar sólo un canal que exista y haya sido verificado. Cada finding debe tener severidad, exploitability, affected artifact, fixed version, disclosure date y evidencia de retest.

## 10. Backup, restore y rollback

### 10.1 Diseño

- Backup atómico de DB y artefactos con manifest versionado.
- SHA-256 por archivo, digest de árbol y candidate SHA.
- Destino de restore nuevo y limpio; nunca sobrescribir origen por defecto.
- SQLite `integrity_check`; PostgreSQL dump/restore y validación de esquema.
- Migraciones `expand → migrate/backfill → contract`; nunca downgrade destructivo.
- Object store versioning o snapshot equivalente donde aplique.
- Imagen, wheel, sdist, Helm chart y configuración immutable por versión.

### 10.2 Rehearsal obligatorio

1. Crear datos A/B y un run con evidencia.
2. Tomar backup, registrar hashes y manifest.
3. Corromper un artefacto y alterar una fila en el destino de prueba.
4. Restaurar en entorno limpio.
5. Verificar bytes, digests, IDs, revisiones, lineage, permisos y ausencia de secretos.
6. Reiniciar servicios durante un run y comprobar checkpoint/idem­potency.
7. Hacer rollback de imagen/Helm y confirmar compatibilidad de esquema.
8. Documentar tiempos RTO/RPO observados, no estimados.

**Criterio:** cualquier pérdida silenciosa, mezcla de tenants, restore parcial no visible o rollback que requiera editar manualmente la DB es `NO-GO`.

## 11. Cualificación de capacidades

La matriz de 13 familias se mantiene como el contrato técnico inicial. Cada familia debe pasar:

1. Journey happy path.
2. Negativos de seguridad y recuperación.
3. API/SDK/CLI/UI parity.
4. Artifact/package qualification.
5. Proveedor aplicable.
6. UX/accessibility.
7. Evidencia exact-SHA.
8. Owner y aprobación.

### Estados

- `implemented`: código existe.
- `tested`: tests automatizados verdes.
- `qualified`: journey completo sobre artefacto exacto.
- `release-qualified`: todos los gates aplicables y aprobación cerrados.
- `experimental`: existe pero no se promete.
- `out-of-scope`: explícitamente no incluido.
- `blocked`: falta una condición externa o técnica.

Sólo `release-qualified` cuenta para el porcentaje de release. La meta de enero es 100% de las familias declaradas dentro del alcance de la release, no 100% de todas las funciones comerciales de cuatro vendors.

## 12. Gobernanza y responsabilidades

| Decisión | Responsable primario | Evidencia | Veto |
|---|---|---|---|
| Scope/claims | Product owner | ADR + compatibility matrix | Product/Security |
| UX/UI | Product + UX | task sessions, screenshots, axe | Product |
| Code quality | Engineering | CI + receipts | Engineering |
| Licenses/NOTICE | Legal/OSS compliance | inventory + signed review | Legal |
| Security | Security owner | threat model, scans, VEX | Security |
| Providers | Platform/QA | provider receipts | Platform |
| Recovery | SRE/Platform | restore/rollback rehearsal | SRE |
| Release | Release manager | candidate report + decision record | Product/Legal/Security |

### Release checkpoint

El 6 de enero se debe publicar un `RELEASE_DECISION_2027-01-07.md` con:

- SHA candidato y tag propuesto.
- Artefactos y hashes.
- Tabla de todos los gates `PASS/FAIL/WAIVED`.
- Lista de skips, si existe alguno.
- SBOM/provenance/license/NOTICE.
- Compatibility matrix.
- UX manual report.
- Security report.
- Recovery report.
- Known limitations.
- Firmas/aprobaciones y decisión `GO` o `NO-GO`.

Un `WAIVED` requiere owner, motivo, riesgo, fecha de expiración y aprobación; nunca se convierte en `PASS`.

## 13. Calendario y hitos

| Fecha | Hito | Salida obligatoria |
|---|---|---|
| 12 nov | Inicio | Este plan, alcance y decisión de compatibilidad. |
| 18 nov | Scope freeze | ADR OSS/Pro, claims y matriz P0/P1/P2. |
| 25 nov | UX shell | Design system, shell, context, wizard primitives y baseline visual. |
| 6 dic | First value | Connect → preview → transform → run funcionando. |
| 13 dic | Run platform | Run/evidence/scheduler/retry/cancel/recovery básica. |
| 20 dic | Product complete | Data, Build, Run, ML, Govern y P0 journeys integrados. |
| 21 dic | Holiday freeze | Feature freeze; sólo P0/P1 y polish UX. |
| 21–30 dic | Test wave 1 | Usuarios, compatibilidad, seguridad y recovery en paralelo. |
| 31 dic–3 ene | Test wave 2 | Regresión completa, defect triage y reinstalación limpia. |
| 4 ene | RC freeze | SHA, tag, wheel/sdist/image/Helm, SBOM/provenance. |
| 5 ene | Qualification | Journeys completos y receipts candidate-bound. |
| 6 ene | Decision | Acta GO/NO-GO y release notes definitivas. |
| 7 ene | Release | Publicación sólo si todos los gates obligatorios son PASS. |

Si el 4 de enero queda cualquier P0 abierto, se activa automáticamente una extensión de la fecha; la presión del calendario nunca convierte un `blocked` en `qualified`.

## 14. Definition of Done de la release

### Producto

- [ ] Los seis wizards principales funcionan sin JSON obligatorio.
- [ ] Las operaciones comunes de Databricks/Fabric/Foundry/Dataiku están en la matriz y tienen journey.
- [ ] Los modos experto no rompen el camino simple.
- [ ] Import/export no pierde contexto, versiones ni evidencia.

### UX

- [ ] First-success ≤10 min en sesión manual.
- [ ] 0 serious/critical axe.
- [ ] Teclado/foco responsive y screen-reader smoke pass.
- [ ] 0 confirmaciones/prompt nativos.
- [ ] Todos los errores tienen causa, impacto y siguiente acción.

### Técnica

- [ ] Unit, contract, integration, E2E, compatibility, performance y recovery gates verdes.
- [ ] CI exact-SHA verde en Python 3.11/3.12 y Chromium.
- [ ] Artefactos instalados fuera del checkout y verificados.
- [ ] OpenAPI/SDK/CLI/UI parity.

### Legal/seguridad

- [ ] Licenses/NOTICE revisados para el artefacto exacto.
- [ ] SBOM/provenance/secret scan/dependency review completos.
- [ ] VEX/exceptions aprobados por Security.
- [ ] Canal de reporte de seguridad real y probado.

### Operaciones

- [ ] Backup/restore y rollback rehearsed.
- [ ] RTO/RPO observados y documentados.
- [ ] Runbook de upgrade, incidentes y revocación publicado.
- [ ] Version/tag protegido e inmutable.

### Release

- [ ] 100% de familias dentro del alcance declaradas `release-qualified`.
- [ ] No quedan P0 abiertos.
- [ ] Product, QA, Security, Legal y Release firman el acta.
- [ ] `GO` se decide sobre un candidato único, no sobre una mezcla de históricos.

## 15. Recomendación ejecutiva

1. Mantener el 7 de enero como objetivo, pero convertir el 4 de enero en el verdadero punto de decisión.
2. No intentar clonar todas las funciones propietarias; construir una experiencia común, simple y portable sobre estándares abiertos.
3. Concentrar el 80% del esfuerzo en: first-success, Flow, notebooks/SQL, runs/evidence, catálogo/lineage, ML lifecycle, import/export y recovery.
4. Reducir la complejidad visible; la potencia debe estar disponible bajo “Advanced”, no delante del usuario nuevo.
5. Mantener Apache-2.0 para el core y preparar desde el primer RC un programa de compliance tipo SPDX/OpenChain, con revisión legal real.
6. Mantener proveedores externos en carriles separados y no prometer compatibilidad certificada sin pruebas instaladas.
7. Usar Navidad para probar y pulir, no para añadir features grandes: feature freeze el 21 de diciembre.
8. Dar `GO` el 7 de enero sólo si el producto común está completo, cualificado y agradable de usar; si no, publicar una release candidate interna y retrasar la pública.

**Recomendación actual:** aprobar este plan y seguir construyendo; todavía no aprobar la release. El objetivo correcto es una plataforma local open source con una experiencia de nivel comercial, pero la fecha sólo se conserva si la evidencia del candidato llega a verde de verdad.

## 16. Fuentes y referencias

### Documentos de RONIN

- `C:\Users\angel.alvarez\Downloads\RONIN_PUBLIC_V1_100_PERCENT_BUILD_PLAN.md`
- `C:\Users\angel.alvarez\Downloads\RONIN_RELEASE_2026-11-03_TEST_MASTER.md`
- `docs/product/PUBLIC_V1_SCOPE.md`
- `docs/product/PUBLIC_V1_BUILD_PLAN.md`
- `docs/product/PUBLIC_V1_CAPABILITY_MATRIX.md`
- `docs/RELEASE_RUNBOOK.md`
- `docs/ui/RONIN_UI_DESIGN.md`
- `docs/ui/PRODUCT_UI_MATURITY_SCORECARD.md`

### Referencias de producto y ecosistema

- [Databricks — Lakeflow Jobs](https://learn.microsoft.com/en-us/azure/databricks/jobs/jobs-quickstart)
- [Databricks — MLflow, Unity Catalog, Jobs y Model Serving](https://developers.databricks.com/perspectives/databricks-connects-notebook-experiments-to-production-model-deployment)
- [Microsoft Fabric — Data Engineering](https://learn.microsoft.com/en-us/fabric/data-engineering/)
- [Microsoft Fabric — notebooks, APIs, parámetros y ejecución](https://learn.microsoft.com/en-us/fabric/data-engineering/how-to-use-notebook)
- [Microsoft Fabric — OneLake y formatos abiertos](https://learn.microsoft.com/en-us/fabric/onelake/onelake-overview)
- [Palantir Foundry — Data Connection](https://www.palantir.com/docs/foundry/data-connection/overview)
- [Palantir Foundry — project structure y pipelines](https://www.palantir.com/docs/foundry/building-pipelines/recommended-project-structure)
- [Palantir Foundry — Ontology](https://www.palantir.com/docs/foundry/architecture-center/ontology-system)
- [Dataiku — Flow](https://doc.dataiku.com/dss/latest/flow/index.html)
- [Dataiku — visual recipes](https://knowledge.dataiku.com/latest/data-preparation/index.html?opals=true)
- [Apache Iceberg — REST Catalog](https://iceberg.apache.org/rest-catalog-spec/)
- [Apache Iceberg — REST protocol](https://iceberg.apache.org/docs/latest/rest-protocol/)

### Licencia y supply chain

- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.html)
- [SPDX License List](https://spdx.org/licenses/)
- [OpenChain ISO/IEC 5230](https://openchainproject.org/license-compliance)
- [GitHub Dependency Review](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/configure-dependency-review-action)

