# QueryFlux: plan de ejecución cancelable y recuperable

Estado: `planned`, no cualifica ninguna familia Public v1 por sí solo.

## Objetivo

Convertir la ejecución QueryFlux actual, que mantiene `submit → poll` dentro de
una petición HTTP, en una operación durable que pueda observarse, cancelarse y
recuperarse sin perder el vínculo entre workspace, proyecto, ejecución,
intento, proveedor y evidencia.

## Contrato propuesto

### Crear ejecución

`POST /v1/workspaces/{workspace_id}/projects/{project_id}/data-engineering/queryflux/executions`

El cuerpo reutiliza `QueryFluxExecuteRequest` y exige `run_id`, `attempt_id`,
`engine`, `max_rows`, `page_size`, `max_result_bytes` y `translation_policy`.
La respuesta es `202 Accepted` con `{id, workspace_id, project_id, run_id,
attempt_id, state: "queued", provider, selected_engine}`. La combinación
`workspace_id/project_id/run_id/attempt_id` es idempotente y una repetición
devuelve la misma ejecución, nunca crea una segunda operación.

### Estado

`GET /v1/workspaces/{workspace_id}/projects/{project_id}/data-engineering/queryflux/executions/{run_id}/{attempt_id}`

Devuelve sólo metadatos seguros: estado, timestamps, proveedor/version,
`failure_code`, `cancel_requested`, `row_count`, cursores y referencia de
evidencia. Nunca expone credenciales, URI privadas ni SQL no autorizado.

Estados permitidos: `queued`, `running`, `cancelling`, `succeeded`, `failed`,
`cancelled`. Las transiciones terminales son irreversibles; `cancelling` sólo
puede avanzar a `cancelled` o `failed`.

### Cancelar

`POST /v1/workspaces/{workspace_id}/projects/{project_id}/data-engineering/queryflux/executions/{run_id}/{attempt_id}/cancel`

Es idempotente. Para `queued/running` registra la intención, cambia a
`cancelling` y delega `transport.cancel(handle)` en el worker. Para un estado
terminal devuelve el estado existente sin mutarlo. El worker debe comprobar la
intención antes de cada poll y persistir el resultado de cancelación junto con
la evidencia.

### Resultados

La ruta paginada existente permanece, pero sólo sirve resultados cuando el
estado es `succeeded`; en cualquier otro estado responde un estado seguro y no
simula una tabla final.

## Persistencia e invariantes

1. El registro se crea antes de encolar el trabajo y está ligado al proyecto.
2. El lease de ejecución y el lease de evidencia cubren el commit del estado
   terminal y de la referencia de artefacto.
3. Reiniciar el worker no duplica la ejecución: el claim se recupera mediante
   `run_id/attempt_id` e idempotency key.
4. Un proveedor cuya negociación no anuncia `cancel` no puede aceptar esta
   operación; la UI muestra `cancellation unavailable` y no presenta un botón
   accionable.
5. Timeout, límite de filas/bytes y cancelación manual producen estados y
   códigos distintos, aunque todos preservan la evidencia.
6. Toda respuesta mantiene el scope autorizado y no filtra configuración del
   proveedor.

## Construcción por capas

1. Añadir el modelo/store durable y las transiciones atómicas.
2. Separar el adaptador QueryFlux del handler HTTP síncrono y ejecutar el
   lifecycle en el worker existente.
3. Añadir las tres rutas y actualizar OpenAPI, inventario de plugins y
   compatibilidad v1.
4. Migrar la UI Data Engineering para mostrar estado, polling bounded,
   cancelación confirmada y recuperación tras error/reload.
5. Mantener la ruta `.../execute` durante la compatibilidad v1, delegándola al
   nuevo servicio sólo si el cliente exige respuesta síncrona y el proveedor
   termina dentro del límite documentado.

## Matriz de pruebas de aceptación

### Unitarias y contrato

- transiciones válidas e inválidas;
- idempotencia de creación y cancelación;
- autorización por workspace/proyecto;
- proveedor sin `cancel` fail-closed;
- timeout, límite de filas, límite de bytes y error de proveedor;
- evidencia para éxito, fallo, cancelación y reinicio;
- OpenAPI, permisos, inventario y compatibilidad sin divergencias.

### Integración

- worker que completa una consulta y pagina resultados;
- cancelación entre polls y cancelación durante `queued`;
- reinicio después de `cancelling` sin duplicación;
- PostgreSQL y SQLite con el mismo contrato;
- proveedor real QueryFlux/Trino cuando exista configuración del operador.

### Chromium

- submit devuelve una tarjeta `queued` con scope visible;
- polling muestra `running` y deshabilita acciones incompatibles;
- cancelación exige confirmación y muestra `cancelling`/`cancelled`;
- recarga conserva `run_id`, estado y evidencia;
- error, timeout y proveedor no disponible son accionables;
- viewport 320/390/520/768/900/1440, teclado, foco, Axe y ausencia de
  overflow;
- ningún secreto, URI privada o SQL sensible aparece en el panel de estado.

## Criterio de cierre

No se marca implementado hasta que todas las pruebas anteriores pasen en el
mismo SHA, el proveedor real aplicable esté cualificado y el receipt incluya
JUnit, OpenAPI, logs estructurados, capturas/manual checklist, cleanup y
rollback. Hasta entonces QueryFlux y Public v1 permanecen sin cualificar y el
release continúa `NO-GO`.
