# Informe de pruebas funcionales en vivo — 2026-10-23

## Alcance

Las comprobaciones se ejecutaron contra Ronin en Docker con servidor, worker, runner-broker y PostgreSQL reales. La UI se sirvió desde la misma instancia que respondió al API (`127.0.0.1:18080`); no se usó el servidor estático de Playwright. El stack y su volumen PostgreSQL eran aislados y se retiraron al terminar. El contenedor PostgreSQL preexistente `ronin-postgres-1` quedó intacto.

Se comprobaron operaciones HTTP, trabajos completos, estados/eventos/evidencias durables, logs del worker, navegación autenticada de Runs y la matriz de rutas y tamaños de pantalla.

## Resultados del API

| Caso | Resultado observado |
| --- | --- |
| Health check | `200` |
| Lista autorizada, proyecto `examples/demo` | `200` |
| Sin credenciales | `401 unauthorized` |
| Lista sin filtro de proyecto o fuera del grant | `403 forbidden` |
| Límite inválido (`limit=0`) | `400 invalid_request` |
| Job inexistente | `404 job_not_found` |
| Crear job | `201` |
| Repetir idempotency key con la misma solicitud | `200`, mismo job |
| Reutilizar idempotency key con otra solicitud | `409 idempotency_conflict` |

## Ejecuciones reales

- **Éxito:** el worker ejecutó las cinco celdas del notebook demo; el job acabó `succeeded`, registró `worker.attempt.succeeded` y expuso 15 referencias de evidencia.
- **Error de preparación:** un target inexistente acabó `failed` con `worker.preparation.error` y el evento `worker.preparation.failed`. El worker siguió disponible para el siguiente trabajo.
- **Error de ejecución:** un notebook inline de prueba lanzó una excepción controlada. El job acabó `failed` con `kernel.container.nonzero_exit`; quedaron eventos de celdas y 12 referencias de evidencia.
- **Logs del worker:** `docker logs` mostró registros `INFO` para éxito, `WARNING` para fallo de preparación y `ERROR` para fallo de ejecución. Incluyen job/run/attempt, estado, duración y código; no incluyen bearer tokens.

Los eventos y las referencias se leyeron de nuevo por el API autenticado. El fallo de ejecución también se abrió en Runs y se contrastó con el timeline y la vista de evidencia.

## UI y navegación

- **39/39** pruebas de traversal de rutas y matriz responsive pasaron contra el servidor Docker real.
- **1/1** regresión autenticada de Runs/Connect pasó contra el API real: el filtro `examples/demo` se conserva al refrescar, la petición filtrada devuelve `200`, Connect no llama por error a `/connections` y no aparecen errores JavaScript.
- La vista Runs mostró en su timeline los estados de fallo de preparación, fallo de celda y éxito; la ejecución correcta mostró sus 15 referencias de evidencia.
- `/studio/routes.json` respondió `200` como JSON; no reapareció el `404` observado anteriormente.

## Correcciones aplicadas

- El worker configura logging a `stderr` para Docker. `RONIN_LOG_LEVEL` permite ajustar el nivel y por defecto usa `INFO`.
- Los resultados del worker emiten logs `INFO`, `WARNING` o `ERROR` según el estado. Los fallos de preparación quedan en el job y no detienen el worker.
- Runs conserva el filtro de proyecto/estado cuando vuelve a renderizarse, por lo que la petición ya no pierde el scope y falla con `403`.
- El formulario editor de Connections tiene ahora un ID propio; Connect ya no es interpretado como un alta de conexión con workspace vacío.
- El servidor incluye `.json` en sus recursos estáticos y no cachea HTML/JSON, para que la UI cargue el manifiesto de rutas actualizado.
- La imagen Docker incluye los recursos `agent-skills`; el drop de privilegios preserva el grupo suplementario necesario para el socket del broker.

## Comprobaciones de código

- `pytest` dirigido a worker, topología Compose y recursos estáticos: **26 passed**.
- Test live de Runs/Connect: **1 passed**.
- Traversal/responsive live: **39 passed**.
- Ruff, `node --check` y `git diff --check`: sin errores. `git diff --check` solo informó avisos de conversión LF/CRLF en archivos preexistentes.

## Límites

La prueba cualifica el ciclo HTTP, autorización, jobs, worker Docker, Postgres, eventos/evidencias y la UI de Runs en este stack local. No cualifica conectores de proveedores, S3, modelos remotos/LLM ni estudios que dependan de servicios externos que no estaban configurados.

El servidor HTTP suprime deliberadamente los access logs normales; el contrato de transporte lo hace para no exponer credenciales. Se verificaron los logs operativos del worker y los eventos durables de cada job.
