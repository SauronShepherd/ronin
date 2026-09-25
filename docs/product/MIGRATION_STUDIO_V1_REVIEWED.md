# Ronin Migration Studio v1 — propuesta revisada

**Documento de origen:** `RONIN_MIGRATION_STUDIO_BUILD_PLAN_ITERATION_1 (1).md`  
**Estado:** propuesta revisada para decisión de producto/arquitectura  
**Fecha de revisión:** 2026-09-19

## 1. Decisión principal

Migration Studio debe integrarse en Ronin Studio como una capacidad de importación y conversión orientada a proyectos PySpark. No debe crear una aplicación, shell, modelo de ejecución ni subsistema de migraciones paralelo.

La propuesta se divide en tres contratos relacionados pero independientes:

1. **Discovery:** qué contiene el origen y qué referencias no se han podido resolver.
2. **Conversion:** cómo se transforma un subconjunto seleccionado a un modelo semántico y después a PySpark.
3. **Qualification:** qué evidencia demuestra equivalencia semántica, calidad, ejecución y rendimiento.

El primer incremento sólo debe certificar el contrato de Discovery. No debe insinuar que la generación PySpark, la equivalencia funcional o la optimización están completas.

## 2. Relación con la portabilidad existente

Migration Studio reutiliza `studio_migration` y los estados canónicos existentes:

`exact`, `translated`, `partial`, `passthrough`, `unsupported`, `manual_decision`.

La diferencia es de propósito:

- `PLATFORM_PORTABILITY_V1.md` define portabilidad entre plataformas y Ronin Bundle.
- Migration Studio define un flujo de conversión de artefactos de integración/ETL hacia un proyecto PySpark verificable.
- IICS es el primer `SourceAdapter`; no debe contaminar el modelo canónico ni el generador.

Una misma unidad puede tener dos resultados: un estado de migración de portabilidad y un estado de conversión a PySpark. No conviene forzar ambos conceptos en un único campo.

## 3. Alcance v1 recomendado

### Incluido

- IICS como primer adaptador.
- Múltiples ZIP y artefactos locales.
- Descubrimiento determinista de paquetes, procesos, mappings, parámetros y dependencias.
- Resolución explícita de `MTT.mappingId` frente a `DTEMPLATE.assetFrsGuid`.
- Selección de alcance con cierre de dependencias.
- Evidencia de referencias no resueltas.
- Blueprint determinista de referencia.
- Modelo de sesión durable y API proyectada a workspace/proyecto.
- UI Ronin-native para `Source`, `Scope` y estado de la sesión.

### No incluido en el primer slice

- Generación PySpark final.
- Ejecución Spark o certificación de equivalencia.
- Optimización automática.
- Integración autenticada contra un control plane IICS.
- Copia automática de datos o credenciales.
- Certificación de cualquier plataforma distinta de IICS.

## 4. Modelo de dominio mínimo

Los modelos deben ser serializables mediante el contrato JSON canónico y tener identidad estable:

```text
SourceArtifact
SourceAdapterDescriptor
DetectionResult
SourceInventory
SourceObject
MigrationUnit
DependencyEdge
ScopeSelection
BlueprintContract
MigrationSession
MigrationResult
```

Requisitos:

- Los identificadores lógicos no pueden depender de rutas temporales, nombres de archivos subidos o claves de base de datos.
- Cada objeto descubierto conserva `source_type`, `source_id`, `source_path` y, cuando exista, el identificador nativo del proveedor.
- Los hashes de artefacto, inventario, selección, blueprint, reglas y versiones deben ser independientes y componibles.
- La selección debe congelarse antes de cualquier conversión.
- Una dependencia implícita o irresoluble se conserva como finding bloqueante o de revisión; nunca se completa por similitud de nombres.

## 5. Estado de sesión

```text
draft
→ artifacts_ready
→ discovering
→ scope_ready
→ converting
→ qualifying
→ completed

 cualquier estado → failed | cancelled
```

Reglas:

- `discovering` sólo lee artefactos inmutables y produce inventario.
- `scope_ready` requiere inventario válido, findings visibles y fingerprint de selección.
- `converting` requiere una selección congelada y un blueprint congelado si el perfil lo exige.
- `qualifying` sólo puede iniciarse si existe un proyecto generado y un plan de qualification explícito.
- `completed` no significa “equivalente”; significa que el resultado declarado y su evidencia están disponibles.

## 6. Adaptador IICS

El adaptador es responsable exclusivamente de detectar, descubrir y extraer el modelo canónico. Debe soportar:

- `DTEMPLATE`;
- `MTT`;
- `mappingTemplate.json`;
- `mtTask.json`;
- `bin/@*.bin`;
- `ParamFiles`;
- `mappingId` y `assetFrsGuid`.

La normalización recomendada es:

```text
Package
└── Process
    ├── Mapping
    ├── Parameters
    ├── Sources
    ├── Targets
    └── Dependencies
```

La fixture inicial de 43 mappings y 50 processes debe convertirse en una fixture versionada, con conteos, hashes, casos válidos, ambiguos, incompletos y maliciosos. El número de objetos no es por sí mismo evidencia de cobertura.

## 7. Ingesta segura

La carga binaria debe quedar fuera del JSON normal y usar un artefacto temporal con digest SHA-256. Antes de extraer:

- exigir `Content-Length` y límites de archivo, sesión, entradas y tamaño descomprimido;
- rechazar traversal, enlaces simbólicos y nombres inseguros;
- no ejecutar ni importar código durante discovery;
- escribir temporalmente y renombrar atómicamente;
- validar el archivo completo antes de hacerlo visible a la sesión;
- congelar los artefactos cuando comience un run;
- almacenar sólo referencias a secretos.

El límite de request de 1 MiB de los endpoints JSON no debe reutilizarse para ZIPs. La subida debe tener contrato y errores propios, con autorización antes de aceptar el artefacto.

## 8. Blueprint

El blueprint no debe ser un conjunto opaco de heurísticas. Debe producir reglas con evidencia:

```text
Rule
├── rule_id
├── classification: MANDATORY | DERIVED | ADVISORY
├── evidence
├── effect
└── conflict_policy
```

Debe congelarse mediante un hash que incluya el proyecto de referencia, versión del extractor y reglas inferidas. Si dos reglas del mismo nivel entran en conflicto, la conversión falla cerrada y exige revisión.

La conformance no debe expresarse como porcentaje salvo que exista un denominador contractual. En el primer slice se debe mostrar una lista de reglas satisfechas, incumplidas, ambiguas y no aplicables.

## 9. API y ejecución

La API propuesta es válida como dirección, pero debe integrarse con los contratos actuales de workspace/proyecto, autenticación, autorización, errores estables y runs de Ronin. El servicio de aplicación recomendado es:

```text
HTTP / CLI
→ MigrationService
→ studio_migration
→ artifact/storage ports
→ Ronin Run / Evidence
```

La UI no debe implementar descubrimiento, resolución de dependencias ni reglas. El CLI y la UI deben llamar al mismo servicio o a la misma capa de aplicación.

Los trabajos prolongados deben crear un Ronin Run y devolver su referencia. El endpoint de creación no debe bloquear esperando conversión, Spark o benchmark.

## 10. Generación y qualification

Cuando se implemente la conversión, separar claramente:

```text
CanonicalSourceModel
→ GeneratedProgram (tentativo)
→ RuleApplication
→ Static Findings
→ QualificationPlan
→ Runtime Evidence
→ MigrationResult
```

La equivalencia Delta debe comparar salidas independientes, no dos ejecuciones del mismo código generado. Las comparaciones mínimas son esquema, columnas y diferencias bidireccionales (`exceptAll`).

La optimización sólo puede promover un cambio cuando hay equivalencia semántica, ausencia de regresión bloqueante y evidencia compatible de rendimiento. Un hallazgo estático nunca debe presentarse como mejora medida.

## 11. UI revisada

La ubicación propuesta es compatible con la IA de Ronin:

- `+ Create → Import / Migrate` para iniciar;
- `Project → Migration` para continuar;
- navegación de sesión por `Source → Scope → Blueprint → Convert → Verify → Review`.

En Iteration 1 sólo se implementan `Source` y `Scope`:

- adapter detectado y evidencia de detección;
- archivos y hashes;
- árbol de paquetes/procesos/mappings;
- estado y razón de cada objeto;
- dependencias incluidas automáticamente;
- referencias no resueltas;
- fingerprint de la selección;
- acción clara para congelar el alcance.

La UI debe conservar la regla del Studio: es un cliente de API, no una segunda implementación semántica.

## 12. Plan de ejecución corregido

### Slice A — Discovery seguro

1. Contrato de producto `MIGRATION_STUDIO_V1.md`.
2. Modelos genéricos y JSON canónico.
3. Digest/fingerprint y errores estables.
4. Adaptador IICS y fixtures versionadas.
5. Subida ZIP segura y puertos de artefactos.
6. Servicio de discovery y rutas mínimas.
7. UI Source/Scope y CLI equivalente.

### Slice B — Blueprint y generación tentativa

1. Extractor de blueprint.
2. Reglas con evidencia y conflictos fail-closed.
3. Modelo semántico IICS normalizado.
4. Generador PySpark determinista de proyecto candidato, con manifiesto y provenance.
5. Manifest de ownership y protección de archivos existentes.

### Slice C — Verificación

1. Analyzer estático.
2. Fixtures semánticas independientes.
3. Delta, calidad, idempotencia y plan de ejecución.
4. Runtime metrics y fingerprints de entorno.
5. Resultados y evidencias en Ronin Run.

### Slice D — Optimización y certificación

1. Shadow rewrites.
2. Benchmarks compatibles.
3. Promoción/rechazo con evidencia.
4. Rehearsal de fallo, cancelación y reanudación.
5. Certificación IICS del subconjunto explícitamente soportado.

## 13. Criterios de aceptación del Slice A

1. Las APIs existentes de `studio_migration` siguen funcionando.
2. IICS no aparece en modelos ni lógica del core.
3. ZIPs múltiples se almacenan y extraen con límites y validación segura.
4. El mismo conjunto de artefactos produce el mismo inventario y digest.
5. Todos los objetos descubiertos aparecen en el inventario.
6. `mappingId` sin correspondencia queda explícitamente en revisión.
7. La selección es reproducible y sus dependencias tienen una razón.
8. Los artefactos quedan inmutables al iniciar un run.
9. API, CLI y UI no divergen en la semántica.
10. La autorización se comprueba por workspace/proyecto en cada ruta.
11. El resultado se puede consultar mediante Run/Evidence.
12. No se afirma que exista generación PySpark completa ni equivalencia certificada.

## 14. Riesgos que deben resolverse antes de prometer conversión

- Semántica real de IICS no representable sólo con archivos exportados.
- Dependencias entre mappings, parámetros, conexiones y runtime.
- Diferencia entre código PySpark generado y comportamiento operacional del origen.
- Ausencia de un runtime Spark reproducible para qualification.
- Propiedad de archivos en proyectos existentes.
- Coste y límites de extracción de ZIPs grandes.
- Integración de workflow/pipeline en Ronin Bundle, que actualmente no cubre todos los dominios.
- Certificación de datos, Delta, calidad y rendimiento sin fabricar evidencia.

## 15. Conclusión

La propuesta original debe aprobarse como dirección arquitectónica, con un alcance incremental: la entrega actual cubre discovery/scoping seguro y generación de un proyecto PySpark candidato, pero no certifica todavía equivalencia funcional completa IICS→PySpark.

La métrica de éxito inicial es la reproducibilidad y trazabilidad del inventario seleccionado. `generate_project` produce un fichero por unidad seleccionada y un manifiesto `ronin.migration.generated-project/v1`; aplica el cierre transitivo de dependencias y falla cerrado ante unidades `unsupported`. `qualify_generated_project` verifica sintaxis y hallazgos estáticos, y marca explícitamente la necesidad de revisión cuando corresponde. La equivalencia de datos y optimización siguen dependiendo de un runtime Spark reproducible.

## 16. Validación de resultados

Migration Studio debe permitir definir qué significa que el resultado generado cuadra con el esperado. No se debe llamar “igualdad” a una única comprobación.

Los modos son:

- `schema`: columnas y estructura;
- `counts`: número de filas;
- `multiset`: comparación duplicate-aware equivalente conceptualmente a `exceptAll` en ambas direcciones;
- `keyed`: full outer join lógico por claves, con diferencias por columna y tolerancias.

La validación por claves debe comprobar primero la unicidad. Si una clave aparece varias veces, el sistema no debe inventar una correspondencia fila a fila: debe emitir un detalle `__PAYLOAD__` basado en conteos/grupos.

Las tolerancias son explícitas por columna para números y timestamps. `null` frente a `null` es igual; `null` frente a un valor es diferente. La igualdad de plan (`sameSemantics`/`semanticHash`) puede ser evidencia adicional de generación, pero nunca sustituye la comparación de datos.

Cada resultado puede producir:

- informe `simple`: estado global, checks, conteos, digest y resumen de diferencias;
- informe `full`: además, filas extra/faltantes, claves afectadas, columnas modificadas, valores esperado/actual y evidencia de claves duplicadas.

El CLI `ronin migrate validate` permite descargar el mismo resultado en `json` (contrato máquina), `markdown` (revisión operativa) o `html` autocontenido (compartible). Los tres formatos conservan el digest del informe; el formato `full` incluye los detalles forenses dentro del informe, sin cambiar la semántica del gate.

El endpoint HTTP aplica límites defensivos: 100.000 filas por lado y 1.000 columnas por fila o claves, exige filas objeto y rechaza tolerancias duplicadas, negativas, booleanas o no finitas. Estos límites protegen el proceso de comparación frente a payloads malformados o de consumo excesivo y no sustituyen los límites del almacenamiento o del runtime Spark.

La ingestión de `source-artifacts` aplica el mismo límite de 512 MiB por archivo que discovery IICS, un máximo de 256 artefactos y 2 GiB acumulados por sesión. Exige nombres tokenizados sin separadores de ruta ni espacios laterales. El endpoint acepta bytes binarios directamente (o base64 sólo para clientes JSON pequeños), conserva el contenido con digest y nunca lo ejecuta durante la ingestión.

La implementación inicial está en `studio_migration.validation` y es independiente de PySpark para poder validar contratos y fixtures sin runtime Spark. El adaptador Spark debe compilar estos mismos modos a `assertSchemaEqual`, `exceptAll`, agregaciones y full outer joins, conservando los mismos estados y fingerprints.

El compilador inicial está en `studio_migration.spark_validation.SparkValidationPlan`. Genera un snippet ejecutable que recibe dos DataFrames (`expected` y `actual`) y devuelve checks serializables para Evidence. El snippet evita `collect()` y no trata igualdad de plan como igualdad de datos. La comparación keyed comprueba salud de clave, compara claves únicas con tolerancias y genera diffs de celdas; las claves duplicadas se representan mediante `__PAYLOAD__`.

## 17. Benchmarks y promoción segura

`studio_migration.benchmark` define el benchmark mínimo reproducible: un warmup configurable, cinco ejecuciones medidas por defecto, mediana en milisegundos y fingerprint del entorno/configuración/dataset. Sólo se comparan resultados con fingerprints compatibles.

La promoción de una optimización requiere simultáneamente:

1. equivalencia semántica aprobada;
2. quality gates aprobados;
3. fingerprint compatible;
4. ausencia de regresión superior al umbral configurado, 5% por defecto.

Si cualquiera falla, el candidato se rechaza y se conserva la razón. La API `decide_promotion` no modifica código: devuelve una decisión auditable para que el servicio aplique el resultado sólo después de una revisión/promoción explícita.

La ruta project-scoped `POST .../migration/sessions/{session_id}/promote` expone este gate por API: valida la forma de ambos benchmarks, compara fingerprints, exige los gates semántico y de calidad y devuelve la decisión junto con `promotion_evidence`. La ruta no modifica código ni promueve automáticamente; deja la decisión explícita y auditable para el siguiente paso de aprobación.

El CLI equivalente es `ronin migrate promote <candidate_id> baseline.json candidate.json --semantic-passed --quality-passed --output promotion.json`. Consume mediciones ya capturadas, devuelve código distinto de cero cuando el candidato se rechaza y escribe el mismo contrato `ronin.migration.optimization-evidence/v1`.

La exportación portable se realiza con `ronin migrate export <generated-project> --output ronin_migration.py` o mediante `GET .../migration/sessions/{session}/export`. El script generado es autónomo respecto a Ronin, usa PySpark estándar, acepta `--source`, `--output` y `--app-name`, y embebe el manifest y `project_digest` para conservar provenance fuera del producto. La UI ofrece la misma descarga como `ronin_migration.py`; el script sigue requiriendo revisión y qualification antes de ejecutarse.

`ronin migrate adapters` devuelve el catálogo determinista de adapters con sus versiones y capacidades; actualmente el adapter IICS expone `discover`, `scope` y `generate`, igual que la ruta HTTP project-scoped.

`ronin migrate artifact <name> <file> --media-type application/zip` genera un descriptor seguro con digest SHA-256, tamaño y `execution=not_run`. El comando no ejecuta, descomprime ni interpreta el fichero; el descriptor se puede usar como entrada de ingestión de la API.

Los resultados de discovery, validation, qualification y benchmark se pueden publicar mediante `studio_migration.evidence.MigrationEvidence` y `publish_migration_evidence`. `validation_evidence` convierte un `ValidationReport` en una celda con `report_digest`, digests de expected/actual y checks serializables; `publish_validation_evidence` combina ambas operaciones para el caller del worker. `publish_promotion_evidence` hace lo mismo para una decisión de optimización. `publish_evidence_bundle` compone varias celdas bajo el mismo contexto fenced y deriva referencias de almacenamiento por `cell_id`, que es el punto de entrada recomendado para el worker. El bundle exige ids únicos y tokens path-safe, rechazando traversal o colisiones antes de tocar el store. El adaptador calcula el digest SHA-256 del JSON canónico y escribe la referencia mediante el `put_evidence` fenced de Ronin; no crea un almacén paralelo ni permite asociar evidencia a otro Run/attempt.

`promotion_evidence` añade al payload el baseline y el candidato completos, sus fingerprints, los gates semánticos/calidad y la decisión de promoción o rechazo. Por tanto, un rechazo por fingerprint incompatible, equivalencia fallida, quality gate fallido o regresión de rendimiento también queda disponible como evidencia durable.

La prueba de aceptación `tests/integration/test_migration_studio_acceptance.py` ejecuta el recorrido completo con un ZIP IICS sintético: discovery, cierre de dependencias, blueprint, generación, qualification estática, benchmark, promoción y publicación fenced en un Run. Es la evidencia automatizada de que las piezas no sólo pasan aisladas, sino que comparten provenance y terminan en Evidence durable.

El gate `studio_migration.runtime.qualify_spark_runtime` y los comandos `ronin migrate spark-preflight` y `ronin migrate spark-smoke` producen evidencia `ronin.migration.spark-qualification/v1`. Los estados distinguen `passed`, `review_required` y `blocked_by_runtime`; un PySpark instalado no se considera suficiente. En Windows se exige además un worker Python ejecutable y compatible con el driver. En el entorno Windows el smoke test queda bloqueado si no hay worker configurado y, cuando se fuerza una combinación incompatible, se evita presentar un resultado falso como válido. La misma validación se ejecutó después en WSL2 con Python 3.12.3, PySpark 4.2.0 y Java 21: `spark-smoke` completó el plan `schema + counts + key_health + keyed`, con tolerancia `metric=0.01`, y devolvió `schema=pass`, `row_count=pass`, `key_health=pass` y `keyed_cells=pass`. Durante esa ejecución se corrigió el compilador para usar expresiones Spark reales y joins null-safe; la prueba quedó cubierta por regresión de sintaxis. El smoke es deliberadamente pequeño y sirve como gate operativo del runtime, no como sustituto de la qualification contra los datasets reales del asset.

## 18. Sesiones de Migration Studio

`MigrationSessionService` centraliza el ciclo de vida que deben compartir HTTP, CLI y UI:

```text
draft → scope_ready → converting → qualifying → completed
```

Una sesión conserva los digests de inventario, scope, blueprint, resultado, validación (`validation_digest`/`validation_status`) y promoción (`promotion_digest`/`promotion_status`). La validación y la decisión de promoción se ejecutan a través del servicio, quedan persistidas en el snapshot y la API devuelve la sesión actualizada; no son operaciones stateless. La decisión conserva un digest del `promotion_evidence` completo, pero no implica promoción automática de código. La conversión no puede comenzar sin inventario y scope congelado. El servicio es independiente del transporte; el adaptador de persistencia debe guardar estos snapshots junto con los Runs/Evidence de Ronin y recuperar sesiones tras reinicio.

La primera persistencia está implementada en `studio_migration.session_store.SQLiteMigrationSessionStore`. Guarda snapshots canónicos en una tabla dedicada, actualiza dentro de transacción SQLite y aplica comprobación de workspace/proyecto al leer. El snapshot es deliberadamente independiente de objetos Python para que una futura implementación PostgreSQL pueda conservar el mismo contrato.

El router `studio_migration.api.MigrationAPIRouter` define la primera superficie project-scoped:

```text
POST /v1/workspaces/{workspace}/projects/{project}/migration/sessions
GET  /v1/workspaces/{workspace}/projects/{project}/migration/sessions
GET  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}
GET  /v1/workspaces/{workspace}/projects/{project}/migration/adapters
PUT  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/source-artifacts/{name}
POST /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/discover
PUT  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/scope
PUT  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/blueprint
PUT  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/blueprint/{name}
POST /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/generate
POST /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/convert
GET  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/export
POST /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/qualify
POST /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/validate
POST /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/promote
GET  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/inventory
GET  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/blueprint-contract
GET  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/result
GET  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/findings
GET  /v1/workspaces/{workspace}/projects/{project}/migration/sessions/{session}/qualification
```

Las mutaciones requieren la acción de proyecto `submit`; las lecturas requieren `read`. `discover` recibe archivos IICS como base64 dentro de un payload acotado y aplica las mismas restricciones de ZIP que la API Python. `source-artifacts/{name}` admite además `PUT` binario con `Content-Length` y límite independiente de 512 MiB, sin pasar por el límite JSON de 1 MiB. Devuelve errores estables para autorización, rutas inexistentes y métodos no permitidos, oculta sesiones de otros proyectos y delega la semántica en `MigrationSessionService`. El adaptador HTTP concreto inyecta autenticación/autorización del control plane y reutiliza estos códigos, sin mover la lógica de migración al handler.

La vista `Migration Studio` de Ronin Studio adopta un cockpit operativo inspirado en el prototipo de runtime intelligence: KPIs de sesión y provenance, capas de evidencia, grafo Source→Scope→Blueprint→PySpark→Validate, findings accionables, timeline y consola de captura/optimización. Los controles de creación de sesión y discovery IICS siguen dentro de la misma vista y llaman a las rutas project-scoped. La acción de promoción exige pegar benchmarks medidos y gates explícitos; la UI no fabrica mediciones sintéticas ni presenta una decisión demostrativa como evidencia real.
