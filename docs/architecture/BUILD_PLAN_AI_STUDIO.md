# Ronin AI Studio — build plan completo v1

Este plan implementa `AI_STUDIO_PROPOSAL.md` sin reescritura big-bang. Cada
fase debe dejar Ronin arrancable, actualiza el inventario de plugins y tiene
tests de contrato, negativos y rollback.

## 0. Reglas de construcción

1. AI Studio no importa internals de otros plugins.
2. `studio_core` no importa HTTP, SQLite, proveedores ni runtime.
3. No hay I/O al importar módulos.
4. Red y procesos sólo detrás de ports sustituibles por fakes.
5. Process supervision está desactivado por defecto.
6. Toda API tiene schema, auth, error mapping y snapshot OpenAPI.
7. Toda migración es idempotente y forward-only; no se borran datos.
8. El fallo del plugin produce `degraded`, no caída del host.

## 1. P0 — baseline y scaffolding

Archivos: `python/studio_ai_studio/{domain,application,adapters,storage,api,workers}`.

- Confirmar paquete `studio_ai_studio`, entry point `ai_studio` y manifest.
- Convertir `LocalModelEndpoint` y `RoutingPolicy` en facade compatible.
- Añadir schema de configuración como package data.
- Añadir ADR de compatibilidad OpenAI y scope document.
- Registrar el paquete en el gate como optional plugin, fuera de la matriz core.
- Añadir inventory y lockfile entries.

Tests: discover, validate, duplicate capability/permission, safe mode, plugin
disabled, missing optional dependency y no network during import.

Salida: plugin instalable, descubrible y sin tráfico.

## 2. P1 — contratos de dominio

Archivos: `contracts.py`, `errors.py`, `policy.py`, tests de value objects.

Implementar frozen/slotted objects: `EndpointId`, `PublicModelName`,
`ProviderModelId`, `EndpointConfig`, `ModelSnapshot`, `RequestLimits`,
`RouteCandidate`, `RouteDecision`, `UsageRecord`.

Enums: adapter, desired/observed state, operation, capability y outcome.
Validar NUL/newline, tamaños, URL sin userinfo/query/fragment, timeouts
100..600000 ms, limits positivos y capabilities conocidas. Añadir
serialización canónica ordenada y digest sha256 de metadata no secreta.

Tests: unicode, alias collision, overflow, URL inválida, capabilities
contradictorias, JSON determinista y round-trip.

## 3. P2 — config, secrets y policies

Implementar schema estricto para endpoints, routing, limits, redaction y
process profiles. Merge defaults → host → workspace; el request sólo puede
seleccionar campos permitidos. SecretRef se resuelve en el borde de ejecución.

Añadir `Redactor` que sustituya `Authorization`, api keys, cookies, secret,
token, credential y paths sensibles. El manifest, lock, errores, audit y
diagnostics nunca deben contener secreto plano.

Tests con secret-like corpus, unknown fields, workspace intentando elevar
límites, config inválida y serialization redacted.

## 4. P3 — persistencia

Archivos: `storage.py`, `studio_storage/migrations/ai_studio_001.sql`.

Crear `EndpointStore` Protocol: create/get/list/update_versioned/disable,
replace_models y stats_window. Implementar SQLite con bind parameters,
transacciones y optimistic concurrency por `version`. Añadir tablas de
endpoints, models y route stats descritas en la propuesta.

Eliminación es soft-disable. Modelo ausente requiere dos probes fallidos. El
port debe admitir adapter Postgres sin cambiar el dominio.

Tests: base vacía/existente, restart de migración, concurrent update,
duplicate idempotency, ordering y no delete físico.

## 5. P4 — transport y adapters

Archivos: `adapters/base.py`, `http_transport.py`, `fake.py`,
`openai_compatible.py`, `ollama.py`, `llama_cpp.py`, `vllm.py`.

Contrato:

```python
probe(endpoint) -> CapabilitySnapshot
list_models(endpoint) -> tuple[ModelSnapshot, ...]
invoke(request, decision) -> ProviderResponse
stream(request, decision) -> Iterator[bytes]
```

httpx es dependencia opcional sólo del adapter. Configurar connect/read/write/
pool timeouts; redirects false; bounded response reader; content-type y JSON
shape checks; error body truncado/redactado.

Ollama usa API OpenAI más native metadata opcional. llama.cpp usa `/health`
para readiness, `/slots` para capacidad y `/metrics` opcional. vLLM usa
`/v1/models`; `extra_body` necesita schema. Generic exige capabilities
declaradas y no lanza procesos.

Contract matrix por adapter: success, 400/401/404/429/500, timeout, malformed
JSON, response grande, wrong content type, partial stream y cancellation.

## 6. P5 — discovery worker

Implementar `ProbeScheduler` con intervalos bounded, jitter, leases,
deduplicación y backoff 1/2/4/8 s hasta 5 min. Separar readiness y capacity.
Guardar snapshot y publicar `ai-studio.endpoint-observed.v1`.

Implementar state reducer puro:

```text
unknown -> probing -> ready
ready -> degraded | saturated | failed
saturated -> ready
failed -> probing después de cooldown
any -> disabled si desired_state=disabled
```

Circuit breaker: threshold 5/30 s, cooldown 15 s, half-open 1 (configurable y
bounded). Probar flapping, disabled, half-open, clock fake y crash del worker.

## 7. P6 — model catalog

Resolver `public_name` a bindings endpoint/provider model. Rechazar alias
collision por workspace. Añadir refresh manual idempotente, TTL y
invalidación post-probe. `/v1/models` sólo publica metadata segura y filtrada
por autorización.

Tests: stale metadata, modelo desaparecido, endpoint disabled, ordering
determinista y aislamiento de workspace.

## 8. P7 — request normalization

Crear parser por operación. Leer body bounded antes de parsear cuando el host
lo permita; validar roles/content blocks/rangos/unknown fields. `stream` sólo
si capability. Tools, response_format, vision y extra_body tienen schemas
separados. Asignar request/correlation/idempotency IDs y body digest.

Añadir golden JSON tests para todos los errores: invalid request, model not
found, capability not supported, body too large y misconfiguration.

## 9. P8 — router y capacity ledger

Pipeline: validate → resolve → filter → rate/concurrency → score → reserve →
forward → release → usage.

Implementar `CapacityLedger` bounded, reserve atómico y reconciliación desde
probes. Strategies puras: priority, weighted round-robin, least in-flight y
latency-aware. Tie-break por endpoint id. No score usa prompt.

Tests de 100 threads con max_in_flight=1, weighted fairness, stale capacity,
disabled durante reservation, deterministic ties y release en `finally`.

## 10. P9 — proxy buffered

Registrar routes `/v1/chat/completions`, `/completions`, `/embeddings` y
`/responses`. Flujo: normalize → route → reserve → invoke → normalize response
→ release → usage.

Retry sólo connect reset, 502/503/504 y timeout pre-bytes. Nunca 400/401/403/
404, capability, stream parcial u operation no idempotente. Fallback explicit
policy, nuevo attempt, mismo request id. No passthrough de headers inseguros.

Tests con cliente OpenAI, upstream malformed, errors, retry matrix, response
oversize, slot release y no duplicación.

## 11. P10 — streaming SSE

Implementar parser para eventos fragmentados, multiline data, comments y
blank terminator. Añadir `BoundedEventQueue(max_events=256)`, max line/event/
bytes/seconds y cancellation token conectado a disconnect.

Si queue llena, frenar lectura upstream; tras backpressure timeout cancelar.
`[DONE]` sólo en cierre correcto. `finally` cancela upstream, libera reserva y
publica usage parcial sin guardar chunks.

Tests: unicode partido, `[DONE]`, malformed SSE, upstream/client disconnect,
queue full, timeout, memory bound, task leak y cancellation <2s.

## 12. P11 — limits y fairness

Token bucket por `(workspace, subject, public_model)`; semaphore por endpoint /
model; límites separados buffered/stream; 429 con Retry-After. Counters vivos
pueden ser memoria; agregados persistidos según policy.

Tests de burst/refill con clock fake, fairness, simultaneous acquire/release y
restart behavior documentado.

## 13. P12 — seguridad de red

Implementar DNS/IP SSRF guard: bloqueo metadata/link-local, private sólo con
network_scope local, revalidación post-DNS, redirects false y TLS verification.
Allowlist de headers; quitar Cookie, Authorization client y X-Forwarded.

Security tests: DNS rebinding, IPv4/IPv6, URL parser confusion, userinfo,
redirect, secret leakage, body overflow y auth bypass por ruta.

## 14. P13 — process profiles opt-in

Profile: executable digest, argv template, env allowlist, cwd, model dirs,
ports y limits. Ejecutar `Popen(argv, shell=False)`, sin shell string ni env
secrets. Crear process group, stdout/stderr bounded, SIGTERM/grace/kill y
restart backoff. Readiness exige health + model list.

Tests: metacharacters, path traversal, digest mismatch, inherited env, port
collision, child crash, zombie prevention y clean shutdown. Sólo
`ai-studio:process` puede activar esta superficie.

## 15. P14 — audit, metrics y UI

Eventos versionados: endpoint created/updated/enabled/disabled/probed,
process started/stopped, route denied y policy changed. Invocation telemetry
no es audit individual por defecto.

Métricas con labels bounded: requests, duration, TTFT, in-flight, queue,
upstream errors, tokens, probes y model load. Añadir redaction property tests,
cardinality budget y no body capture.

UI declarativa: Endpoints, Models, Health, Policies, Logs. Nunca mostrar
secret, filesystem path o capability no autorizada. Añadir readiness contributor
por endpoint y fallback si API no disponible.

## 16. P15 — Docker y perfiles locales

Documentar perfiles no activos por defecto:

```text
compose --profile ai-ollama up
compose --profile ai-llama-cpp up
compose --profile ai-vllm up
```

Servicios en red interna, healthcheck separado de capacity check, volúmenes de
modelos explícitos y sin socket Docker montado. AI Studio apunta al nombre del
servicio. Añadir smoke tests buffered y stream con fakes si no hay GPU.

## 17. P16 — benchmark y compatibilidad

Matrix: Python 3.11/3.12/3.13, Windows/Linux, SQLite/Postgres, cuatro adapters,
buffered/stream y HTTP/HTTPS custom CA.

Harness fake: concurrencia 1/4/16/64, p50/p95/p99, TTFT, throughput, memory,
queue y errors. Presupuesto: overhead p95 buffered <20 ms local sin TLS y TTFT
extra <30 ms. Guardar artefactos JSON reproducibles.

## 18. P17 — documentación y release

Crear quickstarts Ollama/llama.cpp/vLLM, curl buffered/SSE, cliente Python
OpenAI, generic HTTPS, troubleshooting readiness vs saturated, threat model,
operator runbook y upgrade guide.

Actualizar changelog, OpenAPI, schemas, plugin inventory, plugin-lock,
licenses, package data y release notes.

## 19. Orden de rollout

1. `AI_STUDIO_ENABLED=false`, sólo catalog/probes.
2. Endpoint fake de staging.
3. Buffered en workspace piloto.
4. Streaming tras soak y límites.
5. Adapters nativos uno por uno.
6. Process profiles sólo con aprobación explícita.

Rollback: deshabilitar capability y endpoints; conservar tablas, audit y stats;
no borrar migraciones. El host sigue operando el resto de plugins.

## 20. Definition of Done

- Tipos estrictos y gate de imports sin violaciones.
- Unit, property, contract, integration, negative y benchmark suites.
- OpenAPI/schema snapshots estables.
- SSRF, secret leak, auth bypass, overflow y process injection cubiertos.
- health/capacity separados y estados explicables.
- cancellation, graceful shutdown y no task leaks comprobados.
- logs/audit/metrics sin secretos ni contenido por defecto.
- safe mode funciona con plugin fallido.
- documentación de operación y rollback publicada.

## 21. Riesgos y mitigaciones

La compatibilidad OpenAI varía por versión y chat template: fixtures por
runtime y capability matrix. La VRAM queda fuera del control del proxy: no
prometer scheduling físico sin métricas fiables. Process supervision es
plataforma-dependiente: external-only primero. Streaming exige cancellation y
bounded queues antes de declararse estable. Tokens ausentes se representan
como null, nunca se inventa coste.
