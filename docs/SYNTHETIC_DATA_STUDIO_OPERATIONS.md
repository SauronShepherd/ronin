# Synthetic Data Studio: operación local

## Alcance

Synthetic Data Studio funciona en Ronin community sin conexión obligatoria con Databricks, Snowflake, Glue u otros catálogos externos. La ejecución local usa el runtime de Ronin, el catálogo SQLite configurado y los adapters de storage disponibles.

## Configuración mínima

```text
RONIN_DB=<ruta absoluta a ronin.sqlite3>
RONIN_WORKSPACE_ID=<workspace activo>
RONIN_PLUGIN_API=plugins
RONIN_PLUGIN_LOCK=<ruta opcional a plugin-lock.json>
```

La configuración de workspace se obtiene del contexto autenticado en despliegues HTTP. El valor de `RONIN_WORKSPACE_ID` sólo sirve para el composition root local y no sustituye la autorización server-side.

## Límites recomendados

```text
SDS_MAX_ROWS_PER_RUN=100000
SDS_MAX_TABLES_PER_PLAN=100
SDS_MAX_COLUMNS_PER_TABLE=2000
SDS_MAX_LINEAGE_DEPTH=50
SDS_MAX_CONCURRENT_RUNS=2
SDS_RUN_TIMEOUT_SECONDS=3600
SDS_TEMPORARY_OUTPUT_TTL_SECONDS=86400
```

Los límites deben aplicarse antes de reservar recursos y deben aparecer en el diagnóstico de un plan rechazado. Un cambio de límite no modifica la identidad de un asset, pero sí debe quedar en la evidencia de la ejecución.

## Arranque y health check

1. Crear o seleccionar un workspace activo.
2. Ejecutar las migraciones del storage SQLite.
3. Descubrir y validar `com.ronin.synthetic-data-studio`.
4. Comprobar que sus permisos, rutas y manifest no tienen colisiones.
5. Confirmar que el catálogo local responde.
6. Confirmar que el plugin está `ready`, no sólo `discovered`.

La readiness debe fallar si el plugin es crítico y no puede arrancar. Si el catálogo opcional no está configurado, Synthetic Data Studio puede generar en modo efímero, pero debe mostrar `catalog unavailable` y no afirmar que el output fue gobernado.

## Modo offline

La UI obtiene los formatos desde `GET /v1/synthetic-data-studio/formats` tras
una generación. Solo presenta formatos con estado `available` y ejecuta
`POST /v1/synthetic-data-studio/export` con el `run_id`, la tabla y el formato
seleccionados. Si no hay adaptadores instalados, el panel de exportación queda
oculto y la generación local sigue siendo válida.

En community offline:

- `GET /v1/synthetic-data-studio/catalog/providers` muestra los perfiles locales
  de Ronin, Unity Catalog y Polaris.
- Los perfiles Unity Catalog y Polaris son compatibilidad de namespace y
  capacidades del catálogo local; no crean conexiones salientes ni sincronizan
  credenciales. Esa última función pertenece a la extensión Pro.
- Los namespaces registrados se conservan en SQLite mediante
  `catalog_namespace_bindings` y se consultan con
  `GET /v1/synthetic-data-studio/catalog/namespaces`. El registro es idempotente
  por workspace, proveedor e identificador.
- La generación asíncrona local usa `POST /v1/synthetic-data-studio/generate/async`
  y consulta `GET /v1/synthetic-data-studio/jobs/{job_id}`. Su capacidad es
  bounded por proceso (`synthetic-data-studio.jobs.v1`): si el proceso termina,
  el job en memoria no se recupera. La reanudación lease-fenced queda pendiente
  de la integración con el worker durable de Ronin.
- La cancelación cooperativa está disponible en
  `POST /v1/synthetic-data-studio/jobs/{job_id}/cancel`; jobs terminales son
  idempotentes y conservan su estado.
- Para persistir el estado de jobs se puede configurar `SDS_JOBS_DB` con una ruta
  SQLite local. Los estados terminales sobreviven a la recreación del facade y
  los jobs `queued` se reencolan al arrancar; un job `running` requiere una
  expiración/heartbeat explícito antes de ser reclamado; la coordinación multi-
  proceso y fencing lease siguen siendo responsabilidad del worker de Ronin.
- Cuando varios facades comparten esa misma base SQLite, el claim de ejecución
  usa `lease_owner` y `lease_epoch` mediante una actualización atómica; solo el
  proceso que obtiene el claim puede pasar el job a `running`. Esto evita dos
  ejecuciones concurrentes del mismo job en el modo local SQLite.
- El claim tiene una expiración de 60 segundos (`lease_expires_at`) y el worker
  local la renueva cada 10 segundos mientras genera. Un facade nuevo puede
  recuperar jobs `running` cuyo lease haya vencido.

- no se permiten llamadas de red desde generators declarativos;
- no se cargan SDKs cloud;
- los adapters externos no se inicializan;
- la UI muestra únicamente assets locales;
- las operaciones de generación, validación y lineage local siguen disponibles;
- cualquier intento de sincronización debe responder `capability_unavailable`.

El modo offline se verifica con una policy de red bloqueada y un test que ejecuta el flujo completo sin resolver DNS ni hacer requests externos.

## Flujo operativo normal

```text
registrar asset
  -> publicar schema version
  -> crear profile
  -> compilar plan
  -> ejecutar run
  -> validar output
  -> publicar asset version
  -> registrar lineage
  -> exportar evidencia
```

Un input no se sobrescribe. Cada output debe tener un asset lógico, una versión, un content digest y una relación de lineage hacia su input.

## Backup y restore

Antes de actualizar el plugin o ejecutar migraciones:

1. detener nuevos submits;
2. esperar o cancelar runs activos según política;
3. realizar backup SQLite mediante la utilidad oficial;
4. verificar que el backup puede abrirse en una copia temporal;
5. guardar plugin lock, versión de Ronin y schema version;
6. aplicar migraciones;
7. ejecutar smoke test de catálogo, run y lineage.

El restore se realiza en una ruta distinta para validar el backup antes de reemplazar el database path activo. Nunca borrar el backup original durante la recuperación.

## Troubleshooting

### `plan_stale`

El schema, generator registry, policy o adapter capability cambió. Crear una nueva revisión del perfil y recompilar. No forzar la ejecución del plan anterior.

### `catalog unavailable`

Verificar `RONIN_DB`, permisos de filesystem, migraciones y workspace activo. La generación efímera no equivale a publicación gobernada.

### `quality_failed`

Consultar la evaluación y sus thresholds. El output no debe marcarse como publicado si la policy es blocking.

### `idempotency_key_conflict`

La misma clave fue usada con otro plan. Generar una clave nueva o repetir exactamente la request original.

### lineage vacío

Comprobar que el output se publicó mediante `SyntheticOutputPublisher` y que el input source revision existe en el mismo workspace.

## Verificación de release

```text
pytest -q tests/test_synthetic_data.py
pytest -q tests/test_govern_studio_application.py
pytest -q tests/test_synthetic_data_plugin.py
pytest -q tests/test_synthetic_data_publication.py
node --check web/js/synthetic-data-studio.js
```

El release no debe anunciarse como operativo si sólo pasan los tests del motor y no los de plugin, persistencia, catálogo y lineage.

## Frontera Ronin Pro

La sincronización con Databricks, Snowflake, Glue y otros proveedores no se activa cambiando una variable community. Debe existir un plugin Pro separado, con worker, secrets resolver, auditoría, health, retries, circuit breaker y una capability explícita. El modo local no depende de esos paquetes.
