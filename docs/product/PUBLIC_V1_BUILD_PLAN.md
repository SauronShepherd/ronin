# Ronin Public v1 — Plan de construcción

**Estado del producto:** INCOMPLETE. Este plan no declara completada ninguna capacidad ni autoriza un release.
**Autoridad de alcance:** [`PUBLIC_V1_SCOPE.md`](PUBLIC_V1_SCOPE.md).
**Arquitectura y portabilidad:** [`../architecture/`](../architecture/) y [`PLATFORM_PORTABILITY_V1.md`](PLATFORM_PORTABILITY_V1.md).
**Base reconciliada:** `main@e3ca935055968460ba4a0cc3063617c42383b45f` (2026-10-17 14:20 UTC). Los estados de una tarea se reconfirman contra el SHA que se cualifica; este plan no reemplaza los ledgers de producto.

## Progreso verificable

**Progreso de release: 0% (0 de 14 familias P1–P14 release-qualified).** El porcentaje cuenta una familia sólo cuando su journey obligatorio Public v1, la evidencia de proveedor/seguridad aplicable y la evidencia exact-head están completas. Las 14 familias siguen `partial`; por eso la implementación existente y los slices ya integrados no se cuentan como familias terminadas. El porcentaje se recalcula desde la columna `Release-qualified` de la [matriz de capacidades](PUBLIC_V1_CAPABILITY_MATRIX.md), no desde commits, líneas de código ni pruebas aisladas. Estado del producto: **INCOMPLETE**.

## Propósito y límites

Construir una plataforma OSS self-hostable para desarrollo, aprendizaje, experimentación, simulación y evaluación reproducible. El recorrido de producto debe ser coherente desde contratos de dominio y services hasta APIs, ejecución durable, Studio, portabilidad y evidencia.

No se promete paridad con plataformas propietarias, SLA ni alta disponibilidad general. Las certificaciones de proveedores se limitan a los subconjuntos declarados y a los entornos realmente cualificados. Un adapter registrado, un endpoint, una pantalla o un test aislado no equivalen a una capacidad end-to-end.

## Reglas de ejecución y evidencia

1. Mantener estables los identificadores RPV1 y VER. La lista y las dependencias del plan reconciliado aportado son el índice de trazabilidad; esta secuencia agrupa su DAG, no lo sustituye.
2. Antes de cada ola, confirmar que los contratos fuente y ADRs siguen vigentes, identificar criterios de aceptación y dependencias, y fijar el SHA base.
3. Implementar por slice vertical: contrato → dominio/service → adapter persistente → API → cliente/Studio cuando aplique → pruebas positivas, negativas y de límites.
4. Probar primero sin credenciales ni servicios externos mediante doubles deterministas, fixtures locales y perfiles OSS. Los proveedores reales se cualifican después en jobs condicionales autorizados.
5. Registrar por SHA exacto qué se ejecutó, versiones, resultados, skips, artefactos y límites. Un test escrito no es un test ejecutado; un gate verde de otra rama no valida el candidato; skipped no es pass.
6. Cambiar el estado del ledger únicamente con evidencia de sus criterios. Mantener release INCOMPLETE hasta cerrar todo el alcance obligatorio y obtener la decisión humana prevista.

## Ruta de construcción

| Ola | Trabajo y trazabilidad | Dependencias / puerta de salida |
| --- | --- | --- |
| 0. Estado y cimientos | RPV1-000–004: reconciliar producto y ledgers, issues históricas, tamaño de cambios, runner neutral y contrato de plugins. | Alinear SHA, árbol, APIs y evidencia; corregir contradicciones antes de usarlas como premisa. Mantener capacidad y qualification como estados separados. |
| 1. Spines compartidos | RPV1-100–104, 200–205, 300–305 y 400–403: source control, environments, connections, identidad/roles/audit, ingestion, tablas/SQL y scheduler. | Contratos tipados, autorización y límites primero. Cerrar persistencia, ownership, errores, budgets, checkpoints y conformance por adapter antes de ampliar journeys de Studio. |
| 2. Authoring y conocimiento | RPV1-404–406 y 500–507: notebooks/pipelines con revisión durable, Data Engineering, catalog/lineage, ontology/KG/RQL y quality. | Depende de workspace, storage, scheduler y services de Ola 1. Verificar concurrencia, replay, aislamiento, historial y contratos API. |
| 3. Dominios Data + AI | RPV1-600–604, 610–613, 700–702, 710–712 y 800–804: feature/model/evaluation/serving ML; GenAI durable y evaluación; capa semántica; streaming; telemetría, alertas y FinOps. | Usar identidad y ejecución canónicas. Cerrar búsqueda, cancelación, replay, límites de recursos, autorización y adapters antes de exponer controles de Studio. Cualificación externa no se infiere de mocks. |
| 4. Seguridad y perfil compartido | RPV1-900–903 y 1000–1006: audit, secretos, autorización por clasificación, administración, PostgreSQL multi-dominio, Bundle atómico, Compose, Kubernetes y backup/restore. | Requiere los spines que consume cada perfil. Definir explícitamente consistencia, recuperación y límites de aislamiento; cualificar el perfil de referencia sin convertirlo en promesa de HA/SLA, que queda fuera del contrato Public v1. |
| 5. Portabilidad | RPV1-1100–1106: Bundle para quality, ontology, ML, GenAI, datos/semántica y streaming, más API/CLI/Studio. | Antes de certificar migraciones. Cada import debe tener preflight, límites, identidad, atomicidad/recovery, reporte de pérdida/remap y round-trip para el subset declarado. |
| 6. Migraciones | RPV1-1200–1205: framework común, perfiles Databricks, Microsoft Fabric, Dataiku DSS, Palantir Foundry/AIP y Migration Studio. | Depende de Bundle y contratos ejecutables. Cualificar import → inspección → ejecución/validación → export/round-trip con fixtures OSS; credenciales y proveedores reales sólo en qualification autorizada. |
| 7. Producto y compatibilidad | RPV1-1300–1303: superficies Data/Catalog/Environments, Graph/Quality/AI/Dashboard, Streaming/Monitoring/Cost/Admin, OpenAPI y compatibilidad de clientes. | Montarse sobre APIs backend-backed. Completar estados de carga/vacío/error, accesibilidad, permisos, versionado y paridad de contratos, con journeys reproducibles. |
| 8. Qualification y release | VER-001–009 más todos los gates de capacidad aplicables. | Ejecutar en candidato limpio e inmutable; resolver todos los fallos requeridos y explicar cada skip. Agregar evidencia consistente, revisión legal/seguridad y decisión humana. No hay release mientras una familia obligatoria siga parcial, bloqueada o sin evidencia. |

## Inventario trazable de capacidades

Los rangos siguientes preservan los IDs del plan fuente y forman el índice completo de sus **85 tareas de implementación**. Cada ficha de ese plan conserva objetivo y criterio propios; se cierra sólo la ficha dueña con su prueba/evidencia.

| Familia | IDs | Resultado verificable |
| --- | --- | --- |
| Verdad de estado y arquitectura | RPV1-000–004 | Estado reproducible por SHA; deuda histórica reconciliada; contratos y fronteras de plugins/runner explícitos. |
| Control plane y administración | RPV1-100–104 | Ciclos públicos de source control, environments y connections; roles/membership y cobertura de audit sobre recursos autorizados. |
| Ingestion y conectores | RPV1-200–205 | Ingestion como servicio; perfiles cualificados; incrementalidad y escritura con contratos; API/CLI/Studio gobernados. |
| Tablas y consultas | RPV1-300–305 | TableService neutral, perfiles Iceberg/Delta, binding gestionado/externo, SqlService y perfiles OSS distribuidos/interactivos declarados. |
| Scheduler y authoring | RPV1-400–406 | Estado durable de branching/skips, adapters y notificaciones; APIs de schedules/events/backfill; revisiones de notebooks/pipelines y Studio integrado. |
| Catalog, ontology y quality | RPV1-500–507 | CatalogService/ownership/classification, OpenLineage, ontology durable, RQL v1 y quality integrada con catálogo/alertas. |
| ML y GenAI | RPV1-600–604, 610–613 | Feature assets, backends e interoperabilidad, serving, Studio; evaluación, runs durables, qualification de proveedores y GenAI Studio. |
| Semántica y streaming | RPV1-700–702, 710–712 | Relaciones/métricas/drill-down y APIs/Studio; servicio streaming, fuentes/sinks y profile distribuido con estado. |
| Observabilidad y costes | RPV1-800–804 | Adopción de telemetry, adapter OpenTelemetry, alertas/notificaciones, allocation/budgets y anomalía/forecast con UI. |
| Seguridad | RPV1-900–903 | Audit completa, backend de secretos, autorización aware de clasificación y Security Administration Studio. |
| Operación y despliegue | RPV1-1000–1006 | PostgreSQL compartido, transacción Bundle, Compose multiusuario, Kubernetes, execution adapter, backup/restore y frontera HA cualificada. |
| Bundles | RPV1-1100–1106 | Import/export coherente para dominios requeridos y superficies públicas, con atomicidad y evidencia de round-trip. |
| Migraciones | RPV1-1200–1205 | Framework común y cuatro perfiles certificados para subsets explícitos; Migration Studio con reportes de cobertura/pérdida. |
| Superficies cliente | RPV1-1300–1303 | Studio por grupos de dominio y disciplina de compatibilidad OpenAPI/CLI/SDK/Studio. |

## Tracks de evidencia independientes

| Track | Cierre requerido |
| --- | --- |
| VER-001 — Mutation gate (retired) | Campaña final histórica 86.88% vs 90% y decisión permanente de no repetirla en [`MUTATION_CAMPAIGN_FINAL.md`](../quality/MUTATION_CAMPAIGN_FINAL.md). Track superseded; no es un blocker ni un pass de calidad. Sólo reabrir con una decisión de producto y un plan nuevos; mantener suites ordinarias de regresión, contrato e integración. |
| VER-002 — Qualification exact-head | Gates aplicables ejecutados en SHA limpio e inmutable; matriz de estados y skips completa. |
| VER-003 — Contracts | Conformance de cada contrato/adapter y casos negativos en stores y versiones soportadas. |
| VER-004 — E2E | Journeys por capacidad desde API hasta resultado persistido/observable, incluyendo fallo, permisos y recuperación. |
| VER-005 — Migraciones | Evidencia campo-a-campo, mappings, pérdidas/remaps y round-trip del subset certificado. |
| VER-006 — Kubernetes/reference server | Despliegue reproducible y controles de seguridad/operación de los perfiles publicados. |
| VER-007 — Performance/resource | Budgets calibrados en runner fijado, límites medidos y artefactos vinculados al SHA. |
| VER-008 — Supply chain/legal/release | SBOM, dependencias, instalación, licencias y controles de publicación; aprobación explícita de release. |
| VER-009 — Evidencia del candidato | Matriz trazable que concilia gates y capacidades; no derivar una afirmación de release de workflows aislados. |

## Criterios transversales de aceptación

- Aislamiento por workspace/tenant en lecturas, escrituras, jobs, checkpoints, artifacts y permisos; pruebas de denegación sin side effects.
- Operaciones durables idempotentes, recuperables y observables; evitar afirmar éxito terminal cuando un worker conserva efectos pendientes.
- Límites de tiempo, bytes, páginas, concurrencia y reintentos finitos y probados; ningún input inválido alcanza DNS, secretos o sockets.
- Ninguna expansión de trust por redirects, paginación off-origin, plugin, provider o configuración implícita. El opt-in local no habilita credential forwarding.
- Persistencia y migración con schema versionado, rollback/recovery definido, integridad de identity y ausencia de estado parcial no reportado.
- Tests focalizados por cambio; suites completas y qualification en Docker/CI donde corresponda; evidencia conservada fuera de los artefactos fuente.
- Accesibilidad y UX no sustituyen autorización de backend; ningún control de Studio simulado se presenta como una operación ejecutada.

## Riesgos y decisiones que bloquean avance

| Riesgo | Respuesta / condición de avance |
| --- | --- |
| Diferencia entre docs, código y main | Revalidar fuente y SHA; no traer estado de un branch o de una fecha anterior como verdad actual. |
| Cambios amplios con señales mezcladas | Slices pequeños, gates por superficie y matriz exact-SHA; no fusionar por volumen ni por un workflow verde. |
| Proveedores externos o credenciales ausentes | Harness determinista sin secretos; marcar qualification externa `blocked` hasta tener entorno autorizado. |
| Persistencia distribuida/HA no demostrada | Publicar sólo semánticas probadas; separar referencia local de garantías de producción. |
| Certificación vendor por import superficial | Exigir ejecución y round-trip por subset, recibos y reporte explícito de pérdida/remap. |
| Presión para declarar release por cobertura parcial | Mantener `INCOMPLETE` y pedir evidencia/decisión humana sólo en el gate de release final. |

## Decisiones resueltas y bloqueos humanos vigentes

Las decisiones sobre namespace de capacidades de plugins (**#50**) y protocolo runner neutral (**#62**) están aceptadas y sus issues están cerradas; el trabajo de conformance técnica permanece separado en RPV1-003/004. La política de reporte de vulnerabilidades (**#45**) también está cerrada. La campaña de mutation está congelada y retirada, no se ejecutará de nuevo ni cuenta como puerta de release.

La API de GitHub confirma que `main` requiere ocho status checks, aplica reglas también a administradores y prohíbe force-push y borrado; además, el ruleset activo protege tags de release `v*`. Esto cubre las protecciones configuradas que se pueden observar; la revisión legal de licencias/NOTICE/atribución y la aprobación de release siguen siendo humanas. La evidencia exact-head no equivale a journeys completos ni a certificación de proveedores.

## Incremento ejecutado en esta actualización

Como cambio acotado de hardening, se añadió validación de timeout finito y acotado en OIDC/JWKS y HTTP JSON, con preflight HTTP antes de DNS, lectura de secretos y transporte. Las pruebas focalizadas de ambos módulos se ejecutaron en Docker: **47 passed**; Ruff: **All checks passed**. No se ejecutaron proveedores externos ni se cerró ningún ID RPV1/VER por este incremento.

La iteración siguiente elevó a **90% mínimo** la cobertura por línea de 11 módulos que deciden identidad, aceptación, licencias y evidencia de release; la ejecución focalizada combinada pasó **214 tests** con **96% agregado**. Se reforzó además el binding de sujetos de procedencia a los digests de artefactos y la validación de metadatos SBOM. En el perfil Compose/PostgreSQL, el store implementa actualmente importación de workflow/schedule, no la interfaz durable completa del scheduler; se dejó de conectar el adaptador HTTP SQLite a ese store incompleto para que las rutas devuelvan `scheduler_unavailable` en vez de fallar al ejecutarse. El adaptador Postgres completo para runs, events, backfills, branches, leases y task evidence sigue en el critical path; no se reclama soporte de HA de producción.

## Reconciliación de candidato y evidencia exacta

Las bases anteriores `main@58876c2`, `main@106ec8e`, `main@db9c81d`, `main@41a2024`, `main@fa8cc73` y `main@46f9805` pasaron sus workflows exact-head. La base previa `main@2a7d0c9ef697d3de131f04d0973b49bfb2e1c780` también pasó [CI](https://github.com/SauronShepherd/ronin/actions/runs/39036976451), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39036976461), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39036976408), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39036976428), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39036976444) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39036976413). La base actual `main@e3ca935055968460ba4a0cc3063617c42383b45f` pasó [CI](https://github.com/SauronShepherd/ronin/actions/runs/39039830705), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39039830679), [Web](https://github.com/SauronShepherd/ronin/actions/runs/39039830690), [Security](https://github.com/SauronShepherd/ronin/actions/runs/39039830694), [Release](https://github.com/SauronShepherd/ronin/actions/runs/39039830715) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39039830750). Los PR #397, #398 y #399 se integraron tras pasar CI 3.11/3.12, Docker con gate PostgreSQL y aceptación estricta, Web, Security, Release, Status consistency, calidad, dependencias y gates negativos; `mutation` quedó **skipped** y no se cuenta como aprobada. No se declaran completos los journeys P1–P14; `release_status` permanece `incomplete` y `qualification_status` permanece `blocked`.

El PR [#389](https://github.com/SauronShepherd/ronin/pull/389) conectó el gate estricto al job Docker y al job de aceptación de tags: cada uno construye y fija la identidad de la imagen Ronin y falla ante cualquier skip, fallo, error o paso ausente. En el workflow de progreso de CI, `--progress-only` sigue siendo informativo y no sustituye esta puerta. Los PR #390 y #391 reconciliaron ledgers y cobertura; el PR [#392](https://github.com/SauronShepherd/ronin/pull/392) amplió la cobertura de las decisiones de release y endureció el binding de SBOM/procedencia. `main@58876c2` pasó sus workflows exact-head.

El ledger anterior citaba `5d598b903541f1c8aeaf2040896f2a4e6ae7ba45`; se reconcilió primero contra `4daf8a1`, `58876c2`, `106ec8e`, `db9c81d`, `41a2024`, `fa8cc73`, `46f9805`, `2a7d0c9` y ahora contra el HEAD real `e3ca935` de `main`. También se reconciliaron las campañas de mutation con el único registro final congelado, sin volver a ejecutar la campaña retirada. El plan detallado aportado sigue siendo un índice de alcance histórico: sus conteos y estados no se promueven automáticamente; cada elemento RPV1 y VER debe revisarse contra este código y evidencia vigente antes de cerrarse.

El ejecutor local `tools/run_docker_qualification.ps1` también aplica el gate estricto. En `main@25d0c44`, Docker construyó la imagen de runtime y ejecutó **21 passed en 112,16 s**; el gate confirmó **15/15 pasos**, cero skips, fallos o errores. Docker CI confirmó el mismo gate en el candidato exacto. Se retiró una warning de JUnit y se reemplazó el cómputo de progreso por una comprobación de igualdad entre los tests declarados y el manifiesto de aceptación. Esto verifica el journey congelado v0.1; no cierra VER-004 para todos los journeys de Public v1.

El PR [#393](https://github.com/SauronShepherd/ronin/pull/393) hizo que las rutas del scheduler fallen de forma cerrada en PostgreSQL hasta disponer del store completo. El PR [#394](https://github.com/SauronShepherd/ronin/pull/394) añadió una prueba de reapertura del store SQLite del scheduler y comprobó que el outbox conserva intent, no duplica una tarea con lease expirado, despacha y reconcilia un resultado terminal. Sus checks exact-head pasaron: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39031409654), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/39031409536) y [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39031409451), junto con calidad, dependencias, seguridad y gates negativos; `mutation` quedó retirado/skipped.

La base reconciliada `main@41a2024` pasó **CI, Docker, Web, Security, Release y Status consistency** exact-head. El PR [#395](https://github.com/SauronShepherd/ronin/pull/395) añadió replay idempotente con reapertura del store durable de jobs además del outbox SQLite. El PR [#396](https://github.com/SauronShepherd/ronin/pull/396) añadió una prueba que termina forzadamente un dispatcher independiente tras el submit durable; reabre los stores, comprueba el no-reclaim de la tarea y reproduce el mismo Job. La suite scheduler/API pasó **151 tests**, Ruff pasó, y la cualificación Docker local confirmó **21 passed**, con **15/15 pasos** estrictos. Esto cualifica el proceso aislado y la durabilidad de SQLite; no cualifica la caída del daemon real, PostgreSQL scheduler ni HA. P5 y VER-004 siguen parciales.

El PR [#397](https://github.com/SauronShepherd/ronin/pull/397) integró `PostgresSchedulerSnapshotStore` en `main@46f9805`: snapshots workflow/task con atomicidad, idempotencia de triggers, aislamiento por workspace y migraciones versionadas. El PR [#398](https://github.com/SauronShepherd/ronin/pull/398) añadió decisiones de branching replay-safe y estados `pending`/`blocked`. Ambos PR pasaron CI 3.11/3.12, Docker, Web, Security, Release, Status consistency, calidad, dependencias y gates negativos; `mutation` quedó skipped. Docker tardó **7m32s** y **7m17s**, respectivamente, e incluyó cobertura PostgreSQL, qualification de contenedor y aceptación estricta. El store PostgreSQL de liderazgo pasó **4 tests** con cobertura de **87%**; la suite scheduler/workflow local pasó **115 tests**. Ruff, formato, arquitectura y mypy focalizado pasan; mypy global aún reporta tres `unused-ignore` en archivos ajenos al slice. `main@2a7d0c9` pasó los seis workflows exact-head.

El PR [#399](https://github.com/SauronShepherd/ronin/pull/399) integró persistencia PostgreSQL de liderazgo con fencing por generación y corrigió la prueba para tolerar ejecuciones repetidas sobre la misma base Docker. Los checks exact-head pasaron CI 3.11/3.12, Docker (**7m12s**), Web, Security, Release, Status consistency, calidad, dependencias y gates negativos; `mutation` quedó skipped. En Docker pasaron el gate PostgreSQL/cobertura, qualification real de contenedor y aceptación estricta. El siguiente slice pendiente es persistir leases de intentos de tareas en PostgreSQL; outbox, events, backfills y task evidence también siguen incompletos.
