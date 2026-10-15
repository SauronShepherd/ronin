# Ronin Public v1 — plan de construcción ejecutable

**Revisión:** 2026-10-15
**Checkout de trabajo:** `codex/final-main-audit` en `fe887a0fdae9`
**Propósito:** convertir los informes de análisis entregados en una secuencia implementable, con criterios de aceptación y evidencia por cambio. Este plan describe el checkout candidato; no afirma que sus cambios estén en `main` ni que Public v1 esté listo.

## 1. Alcance y fuentes

Se consolidaron los documentos entregados: `00-overview`, `01-architecture`, `02-features`, `03-plugins-extensions`, `04-quality-security-performance`, `05-improvement-backlog`, `06-analysis-state`, `07-blockers-build-plan`, `CONSTRUCTION_PLAN`, `machine-learning-studio` y `quality-ci-release`. Las declaraciones históricas de cada corte se conservan como evidencia del corte, pero las revisiones fechadas el 15/oct prevalecen para el estado actual. El código y sus pruebas en el checkout son la autoridad de implementación; los documentos expresan alcance y requisitos, no son órdenes operativas ni evidencia de que una función exista.

**Contrato de producto:** Ronin es una plataforma OSS, local-first y autohospedable para desarrollo, evaluación y operación reproducible. Una versión alpha, el éxito parcial de CI, un endpoint existente o una pantalla presente no prueban un journey completo. Public v1 se considera incompleto hasta que los journeys P1–P14 y los contratos publicados pasen gates sobre el mismo candidato.

## 2. Estado inicial y riesgos dominantes

La revisión adjunta identifica 30 bloqueos y 48 tareas con ID estable. Los más urgentes en este checkout son:

| Prioridad | Hallazgo | Efecto | Criterio de salida |
|---|---|---|---|
| P0 | `RON-CONN-001`: discovery/preview/plan/checkpoint sin autorización workspace/resource-scoped | Operaciones pueden resolver conexiones/secretos o leer checkpoints tras autenticación solamente | Pruebas HTTP deny-before-side-effect para cada ruta; permisos y workspace derivados de una identidad de conexión validada |
| P0 | `RON-CONN-003`: paginación HTTP podía reenviar Bearer a otro origen | Exposición de credenciales a un origen no confiable | Origen paginado restringido; HTTPS obligatorio para Bearer; fixture local confirma que el segundo origen nunca recibe una llamada |
| P0 | `RON-ML-001`: `cancel()` reentraba en un `Lock` no reentrante mediante `status()` | Deadlock determinista | Cancelación, carrera con finalización y timeout regresivo pasan |
| P0 | `RON-ARC-001`, `RON-VCS-001`: import de CLI hacia Connectors viola DEP001; rutas Windows/POSIX divergen | CI y ejecución multi-OS no fiables | Reglas de dependencia pasan y las rutas se canonicalizan con casos Windows y POSIX explícitos |
| P0 | `RON-WEB-003/004`, `RON-WEB-002`: DOM dinámico inseguro, handlers/formularios conflictivos y journey flaky | Riesgo de XSS y recorridos de usuario rotos | Construcción DOM sin `innerHTML` con datos no confiables; pruebas de payload hostil, errores y journey sin retries |
| P0 | `RON-API-001/002`: contrato de bootstrap de Workspace ambiguo y algunas mutaciones leen JSON antes de autorizar | Contrato API y orden de seguridad inconsistentes | Decisión de autoridad documentada; pruebas 401/403/503 que confirman que no hay lectura/efecto antes de autorización |
| P0 | `RON-CI-002/003/004/005/006/008`: formato/pin de action, Compose vacío, Playwright del wheel y pruebas dependientes del runner | PR no calificable y posible falso verde | Workflow exact-SHA sin fallos, skips justificados y Compose con aserciones reales |
| P1 | `RON-CONN-004`: no existe presupuesto total de bytes/tiempo en `http.json` | Respuesta paginada no confiable puede agotar memoria/CPU/tiempo | Cotas globales aplicadas durante streaming, digest incremental y pruebas de exceso |
| P0 | `RON-ML-003`: contrato Lab/v1 no coincide con clustering, campos extra y política de split | Compatibilidad pública ambigua | ADR, schema, parser y fixtures golden acuerdan una semántica versionada |
| P1 | `RON-ML-002/005/006`: aislamiento/recuperación de ejecución incompletos; experimento ficticio; publicación artefacto-run-model no atómica | Riesgo de duplicados, scope y éxito ficticio | Workspace+CAS/fencing y recovery; create/read/reopen real; reconciliación con fault injection |

El CI anotado en los documentos no es un resultado de este checkout local: los runs remotos citados apuntan a refs/SHAs específicos. Mutation testing está congelado por política en `docs/quality/MUTATION_CAMPAIGN_FINAL.md`; no es parte de este plan ni se debe ejecutar como atajo de release.

## 3. Reglas de implementación y evidencia

1. **OSS primero:** desarrollar con fixtures, fake servers y servicios locales; providers reales solo después de conformance y con acceso autorizado.
2. **Fall closed:** fallo de autenticación, autorización, audit, contrato, digest o límite detiene la operación antes de efectos externos.
3. **Exact ref:** cada resultado de CI, Docker, wheel, SBOM y benchmark queda unido al SHA de source, dependencias, imagen, perfil y skips.
4. **No confundir estados:** `skipped`, `not_run`, `blocked` y `not_published` nunca cuentan como `passed`.
5. **Sin doble implementación:** extender servicios y contratos existentes; reutilizar `Job/Run/Attempt`, `ArtifactRef`, stores y puertos cuando aplique.
6. **Seguridad por límites:** workspace/resource, origin/scheme/DNS peer, secretos, filesystem y presupuesto total se prueban por separado.
7. **Definition of Done por tarea:** contrato actualizado, implementación, pruebas positivas y negativas, docs/API/OpenAPI y gate de la superficie tocada.

## 4. Plan por waves y dependencias

### Wave 0 — Recuperar un candidato reproducible

**Tareas:** `RON-CI-006`, `RON-DOC-001/002`, `RON-CI-007`, `RON-REL-001`. Inventariar diff frente a `main`, confirmar changed-surface por dueño, validar action pins, dependencias y rutas de evidencia; normalizar ledgers para enlazar SHA en tiempo de ejecución. Mantener separados los resultados de `main`, PR branch y merge ref. Documentar la política de mutation y decidir un gate alternativo aceptado sin repetir campañas.

**Aceptación:** manifest del candidato registra ref/SHA, changed paths, matrices aplicables, artifacts y conclusión; cualquier required gate omitido produce `blocked`, no `success`. Un review por arquitectura, seguridad, CLI/SDK, Web, storage y release firma sus superficies.

**Dependencias:** ninguna. Bloquea merge/release de cambios grandes.

### Wave 1 — Cerrar límites críticos de seguridad y recursos

**Tareas:** `RON-CONN-001/002/003/004`, `RON-API-002`, `RON-WEB-003`, `RON-ARC-001`, `RON-VCS-001`, `RON-CLI-001`.

- Autorizar rutas de connectors con workspace y permiso de lectura/ejecución adecuados antes de resolver secretos, tocar checkpoints o efectuar requests. No aceptar un workspace suministrado que no se vincule a la conexión.
- En HTTP JSON: bloquear credenciales sobre HTTP; mantener paginación en el mismo origin por defecto; validar cada URL y destino DNS; no seguir redirects; limitar bytes por página y por operación, páginas, retries y duración total; actualizar SHA-256 incrementalmente; registrar solo métricas redacted.
- Evitar importar Connectors desde el composition root CLI: introducir factory/puerto en runtime o infraestructura y mantener la dirección de dependencia permitida.
- Normalizar checkout/path y quoting en un solo adaptador; cubrir separadores, drive letters, UNC, symlinks y escapes en Windows/POSIX.
- Separar token de API de jobs y token de control-plane, con permisos mínimos locales y perfiles explícitos.
- Eliminar sinks DOM de contenido no confiable y unificar IDs/handlers del Connections Studio.

**Aceptación:** pruebas deny-before-side-effect por ruta y workspace cruzado; dos servidores locales demuestran que un Bearer no sale del origin; límites de bytes/tiempo prueban la terminación; payload XSS queda como texto; DEP001 y matriz de paths pasan.

**Dependencias:** Wave 0 para cambios que impactan gates; `RON-API-001` resuelve la autoridad de Workspace.

### Wave 2 — Hacer fiables contratos y lifecycle de ML

**Tareas:** `RON-ML-001/002/003/004/005/006`, `RON-EXT-001/002`, `RON-PORT-001`.

- Reconciliar `MACHINE_LEARNING_STUDIO_FULL_SPECIFICATION` con `ronin.ml-lab/v1`, Pipeline IR, backend y remote adapter. Acordar clustering, `target`, campos desconocidos y rango/política de `test_fraction`; cualquier cambio incompatible requiere versión nueva, no reinterpretar v1 en silencio.
- Corregir cancelación; después introducir identidad `(workspace_id, run_id, lab_version)`, request digest/idempotency, compare-and-set, ownership y fencing. Reconcile `queued/running` tras restart con policy explícita y sin reejecución ciega.
- Limitar transport remoto por origin/allowlist, redirects, bytes, deadline, backoff y clasificación de errores. No enviar credenciales hasta tener policy y testkit OSS.
- Persistir experimentos realmente o devolver unsupported; validar el recorrido POST→GET→reopen. Reconciliar artefacto/run/model con fault injection y GC conservador.
- Integrar ML Bundle tras contratos/registry estables, incluyendo manifest, digest y referencias externas explícitas.

**Aceptación:** golden tests de contrato, carrera cancel/finalización, dos workspaces con run_id homónimo, reinicio/store reopen, requests maliciosas/oversize/NaN-Inf, y round-trip Bundle sin secretos portables.

**Dependencias:** contrato Lab antes de aislamiento/migraciones; `ML-001/003` antes de `ML-002`; `ML-003/006` antes de Bundle.

### Wave 3 — Alinear API, SDK y journeys de Studio

**Tareas:** `RON-API-001/002/003`, `RON-SDK-001`, `RON-WEB-002/003/004`, `RON-ACCESS-001`, `RON-QUAL-001`.

- Definir si Workspace creation pertenece al contrato HTTP v1, quién puede bootstrapearlo y cómo se concede el primer grant. Alinear OpenAPI, documentación, SDK y pruebas.
- Aplicar autenticación/autorización antes de parsear cuerpos de mutaciones; distinguish 401/403/503 y comprobar ausencia de escritura/audit incompleto.
- Añadir paging de Connections al SDK con cursor opaco y límite explícito; probar contrato HTTP–SDK–Studio con server real local.
- Corregir formularios/estados de Access, Workspace/Project, Connections y Quality; validar loading/empty/error/retry y accesibilidad por teclado.
- Eliminar timers globales en Quality Studio y proteger envío/idempotencia del run.
- Cubrir rotación de service identities con evidencia verificable y sin exponer secretos.

**Aceptación:** contract suite API/SDK y Playwright sin retries sobre Chromium; journey crea/lee/actualiza y deniega correctamente; audit falla cerrado.

**Dependencias:** Waves 1 y 2 donde se consumen conexiones/ML.

### Wave 4 — Corregir CI, packaging y Docker qualification

**Tareas:** `RON-CI-001/002/003/004/005/006/008`, `RON-WEB-002`, `RON-DOC-002`.

- Corregir pin SHA no resoluble, imports Ruff/format y declarar Playwright Python en el intérprete que hace smoke de wheel.
- Hacer tests de Govern independientes de si `deltalake` está instalado; cubrir perfiles optional-present y optional-absent.
- Corregir Migration tests para comparar versiones inequívocas, normalizar `python.exe`/rutas del host y no depender del Python que corre pytest.
- Capturar stderr sanitizado al fallar tutorial wheel; aislar build dependencies e instalar con Python 3.11 y 3.12.
- Reemplazar el paso Compose vacío por up/health/down real, único proyecto, secretos efímeros y cleanup aun ante fallo.
- Calificar Python 3.11/3.12, quality, security, negative gates, wheel/sdist, Web, Docker y release por exact SHA; skips reportados con razón.

**Aceptación:** todos los jobs obligatorios pasan en exact ref; Docker comprueba server/PostgreSQL/broker healthy en ≤60 s y elimina recursos propios; no hay paquete publicado en este wave.

**Dependencias:** Waves 1–3 estabilizan los tests y contratos.

### Wave 5 — Cerrar el spine de datos y scheduler

**Tareas:** bloques `RPV1-100..105`, `200..205`, `300..305`, `400..406`, `500..507`, `700..702`, además de `RON-EXT-003` y `RON-PORT-001`.

Completar source-control lifecycle, environment/connection APIs y audit; ingestion application service, perfiles JDBC/object-store, incremental ingestion y connector write; TableService, binding managed/external, SQL neutral y perfiles OSS; scheduler durable (branch/skipped, adapters, notifications, backfill); Notebook/Pipeline authoring integrado; Catalog, glossary, ownership, classification, OpenLineage y APIs de Quality; Ontology/KG/RQL contracts y semantic/dashboard. Migración vendor se desarrolla con corpus sintético y harness neutral antes de credenciales.

**Aceptación:** cada capability tiene contrato versionado, API/CLI/SDK/UI coherentes, store reopen/rollback, tenant-scoping, journey e2e y bundle/migration cuando aplique. Discovery o traducción por fixtures no se etiqueta certificación vendor.

**Dependencias:** Waves 1–4.

### Wave 6 — Completar AI/ML, GenAI y streaming

**Tareas:** `RPV1-600..613`, `RPV1-710..712`.

Ampliar Feature Assets y backends; qualify MLflow; definir serving/deployment; integrar AI/ML Lab sobre lifecycle durable; evaluación GenAI y agent runs durables; providers locales primero y remotos con qualification separada; streaming service/APIs, source/sink/schema y perfil stateful distribuido.

**Aceptación:** conformance suite por backend/provider, datos/outputs con digest y workspace, límites de red/recursos, cancelación/recovery, y evidencia browser/HTTP exact ref. Los adapters simulados no se presentan como providers certificados.

**Dependencias:** Waves 2, 3 y 5.

### Wave 7 — Operaciones, seguridad, bundles y deployment

**Tareas:** `RPV1-800..804`, `900..903`, `1000..1006`, `1100..1106`, `1200..1205`, `1300..1303`; `RON-OPS-003`, `RON-PERF-001`, `RON-PERF-002`, `RON-EXTQUAL-001/002`, `RON-OPS-001/002`, `RON-SEC-001`.

Adoptar telemetría por dominios, OpenTelemetry, alertas y FinOps; completar audit, secret backend refs y clasificación-aware auth; calificar PostgreSQL server/migrations/backup/restore y deployment Compose/Kubernetes; definir límites HA antes de hacer claims. Cerrar bundles por familia con commits atómicos y API/CLI/Studio. Crear migration framework común y perfiles Databricks, Fabric, Dataiku y Foundry con fixtures, luego credenciales/artefactos autorizados para certificación. Ejecutar benchmarks fijados por SHA y registrar p50/p95, memoria, CPU, dataset, hardware, warmup y límites.

**Aceptación:** perfiles reproducibles, restauración probada, bundle round-trip y migración verificable; test de HA en runner PostgreSQL multi-node; decisión admin/legal documentada. No llamar producción-ready a un profile local.

**Dependencias:** Waves 1–6; providers, runners HA, reporting privado y sign-offs pueden bloquear su cierre.

### Wave 8 — Release Public v1

**Tareas:** `RON-PROD-001`, `RON-REL-001/002`, `VER-001..009`, matriz P1–P14.

El agregador acepta solo evidence del candidato exacto y perfil declarado. Todo journey debe tener fixture reproducible, asserts observables y artifacts vinculados al source SHA. Revalidar supply chain, licencias, SBOM, pins, documentación, compatibilidad API y política de rama/tag. Un aprobador autorizado decide publicación cuando todos los gates están en verde.

**Aceptación:** ningún P1–P14 aparece como completo sin test de journey; gate fallido/skipped/ausente bloquea; review de cambios por superficies; evidencia de branch/tag policy y signoffs admin/legal; release artifacts verifican digest.

**Dependencias:** cierre de waves anteriores y approvals/infra externa.

## 5. Ruta crítica

```text
Wave 0 (candidate/evidence)
  → Wave 1 (auth, egress, budgets, filesystem)
  → Wave 2 (ML contracts/lifecycle)
  → Wave 3 (API/SDK/UI journeys)
  → Wave 4 (CI + Docker exact-SHA)
  → Waves 5–7 (capability families, portability, ops)
  → Wave 8 (P1–P14 + release authorization)
```

Las Waves 5 y 6 pueden avanzar en paralelo por dominio una vez que sus contratos del spine estén estables. La integración y qualification vuelven a ser secuenciales antes del release.

## 6. Backlog de riesgos que no se cierra con código local

- `RON-OPS-001`: ver policy completa de branch protection y required checks; el acceso citado solo confirma `protected=true` y protección de tags, mientras el detalle devuelve 403.
- `RON-OPS-002` y `RON-PERF-002`: requieren runner multi-node/medición fijada, no inferibles desde Docker Desktop.
- `RON-EXTQUAL-001/002`: providers/vendedores reales requieren tenants, credenciales y artefactos autorizados; primero completar harness OSS.
- `RON-SEC-001`: necesita decisión de reporting privado/legal.
- `RON-REL-002`: la publicación requiere autorización explícita del responsable después de evidence completa.
- `RON-CI-007`: no repetir mutation campaign; autoridad decide gate alternativo y documenta la política.
- `RON-ML-003`, `RON-API-001` y política de bootstrap requieren decisión de contrato/versionado antes de cambiar semántica.

## 7. Trabajo aplicado en este checkout

Esta revisión implementa autorización previa y resolución de conexiones/checkpoints por workspace en las rutas de Connectors, propaga el scope por CLI y SDK, corrige `studio_ml.cancel`, añade límites globales y same-origin/HTTPS Bearer en `http.json`, actualiza OpenAPI y su digest, sustituye el paso Compose vacío por health assertions y cleanup aislado, corrige el pin inválido de `upload-artifact` y hace deterministas los casos de optional-dependency/Spark runner. La suite completa en Windows/Python 3.13 detectó dos pruebas con límites temporales frágiles y un ledger de matriz desincronizado; se ajustaron y sus siete regresiones dirigidas pasan. La cualificación Docker real pasó 21/21 en el checkout fijo. Se amplió el lock dev para el browser tooling y el build backend exacto, limitado a resoluciones de Python 3.11, y se regeneraron el inventario y la política de licencias desde ruedas Linux. CI descubrió imports Ruff no ordenados que el ignore global del equipo ocultaba localmente; quedaron corregidos en 911 archivos Python rastreados. El workflow web instala Chromium para Playwright Python y Node. La matriz de capabilities vuelve a coincidir con el ledger de estado.

## 8. Auditoría e integración de ramas

Se actualizaron las referencias remotas y se revisaron las ramas locales y remotas. El único PR abierto es `#385` (`codex/final-main-audit`), que contiene el estado completo de esta revisión. Las ramas de CLI, HTTP, evidencia, JobStore, Docker, rendimiento, OIDC y scheduler corresponden a PRs fusionados posteriormente, PRs cerrados/sustituidos o implementaciones anteriores; no se reaplicaron sus commits históricos. Las ramas locales de budget/UI y las ramas de documentación están obsoletas frente al estado actual. `codex/ronin-studio-build` cambiaría 16 archivos que evolucionaron desde esa rama; no se integró para evitar revertir el estado actual. `fix/exact-logo-upload-2` contiene únicamente bloques de transferencia `.b64`, no una fuente del producto.

La rama remota `public-v1/graph-rql-runtime` era la única feature aislada sin PR ni implementación equivalente. Se integró como merge revisado, se añadieron pruebas de parser, materialización, persistencia SQLite y consultas/traversal, y se registró `studio_graph` en el gate de arquitectura. El conflicto de merge quedó limitado a la lista de paquetes de `pyproject.toml`.
