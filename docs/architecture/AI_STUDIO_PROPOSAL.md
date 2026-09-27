# Ronin AI Studio — propuesta técnica v1

Estado: propuesta open-source para `studio_ai_studio`.

## 1. Objetivo

AI Studio es el plugin vertical de Ronin para llamar, descubrir y exponer
modelos locales. No implementa un motor de inferencia: Ollama, llama.cpp, vLLM
y servidores OpenAI-compatible permanecen reemplazables. Ronin aporta el
plano de control, gateway, seguridad, routing, auditoría y observabilidad.

Responsabilidades:

1. Registrar endpoints locales y perfiles de ejecución.
2. Descubrir modelos y capabilities con probes acotados.
3. Exponer `/v1/models`, `/v1/chat/completions`, `/v1/completions`,
   `/v1/embeddings` y `/v1/responses`.
4. Validar, normalizar y limitar cada request antes del upstream.
5. Seleccionar endpoint con una política explícita y auditable.
6. Gestionar SSE, cancelación, backpressure y timeouts.
7. Registrar uso, latencia y fallos sin persistir prompts por defecto.
8. Supervisar runtimes sólo mediante perfiles opt-in y allowlists.

## 2. Decisiones derivadas de la investigación

vLLM ofrece Chat/Completions compatible con el cliente OpenAI. llama.cpp ofrece
chat completions, responses y embeddings, además de endpoints propios. Ollama
mantiene una capa OpenAI-compatible. Esto exige una API canónica de Ronin y
adapters por familia: “compatible” no significa idéntico.

llama.cpp distingue `/health` de `/slots`: el primero expresa readiness y el
segundo capacidad/concurrencia. AI Studio mantiene ambas señales separadas.
Un servidor sano pero lleno queda `saturated`, no `failed`, y no se reinicia.

Los gateways maduros añaden auth, rate limits, retries, fallback, logging,
routing y usage tracking. AI Studio los implementa mediante ports, sin acoplar
el dominio a httpx, FastAPI, SQLite, Prometheus o cloud.

Referencias:

- [vLLM OpenAI-compatible server](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/)
- [llama.cpp server API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [LiteLLM gateway](https://docs.litellm.ai/)

## 3. Alcance

V1 incluye endpoints externos, Ollama/llama.cpp/vLLM/genérico, buffered y SSE,
model catalog, probes, priority/weighted/least-in-flight/latency routing,
limits, retries seguros, rate limits, usage, audit y métricas.

Queda fuera: descarga automática de modelos, ejecución arbitraria de
Modelfiles, exposición LAN por defecto, prompt logging por defecto,
fine-tuning, serving multi-node y smart routing por contenido sensible.

## 4. Arquitectura de paquetes

```text
ronin-contracts: IDs, capabilities, envelopes, errors y ports
ronin-plugin-sdk: manifest, lifecycle, contributions y config
studio_ai_studio/
  domain: value objects, estados y políticas puras
  application: register, discover, route, proxy y usage
  adapters: openai, ollama, llama_cpp, vllm, process
  storage: EndpointStore mediante port
  api: routes, auth y serializers
  workers: probes y reconciliación
```

No hay imports entre plugins. El plugin consume contratos públicos. La
supervisión de procesos requiere `ai-studio:process`, separado de `read`,
`write`, `invoke` y `admin`.

Manifest objetivo:

```python
PluginManifest(
    id="com.sauronshepherd.ronin.ai-studio",
    name="Ronin AI Studio", version="0.1.0", plugin_api="1.0",
    host_requires=">=1,<2", isolation="worker",
    capabilities=("ai-studio.discovery", "ai-studio.proxy",
                  "ai-studio.exposure", "ai-studio.streaming"),
    permissions=("ai-studio:read", "ai-studio:write",
                 "ai-studio:invoke", "ai-studio:admin",
                 "ai-studio:process"),
)
```

## 5. Modelo de dominio

### EndpointConfig

```text
id                 lower-case, estable, sin slash, 1..128
adapter            ollama | llama_cpp | vllm | openai_compatible
base_url           scheme/host/path, sin userinfo/query/fragment
auth_secret_ref    SecretRef nullable; nunca token plano
tls_profile        default | custom-ca-ref
scope              global | workspace
mode               external | managed
desired_state      enabled | disabled
observed_state     unknown | probing | ready | degraded | saturated | failed
priority           0..65535; menor es preferido
weight             1..10000
max_in_flight      positivo
timeouts           connect/read/write/pool, bounded
```

HTTP sólo para loopback/private CIDR explícito. Remoto exige HTTPS. `managed`
requiere process profile aprobado. `disabled` no recibe tráfico.

### ModelSnapshot

```text
endpoint_id + provider_model_id = key
public_name, capabilities, context_window, max_output_tokens
input/output modalities, loaded_state, metadata_digest, last_seen_at
```

Capabilities son declaradas/observadas y pueden ser `chat`, `completion`,
`embedding`, `response`, `streaming`, `tools`, `structured_output`, `vision`,
`audio` o `rerank`. El proxy rechaza una capability ausente antes del upstream.

### Request/Usage

```text
request_id, correlation_id, workspace, operation, mode, body_digest
route_decision, attempt, queue_ms, first_byte_ms, total_ms
prompt_tokens?, output_tokens?, outcome, provider_status
```

Body, headers secretos y response no forman parte del audit event.

## 6. HTTP público

Administrativo:

```text
GET/POST/PATCH /v1/ai-studio/endpoints[/id]
POST /v1/ai-studio/endpoints/{id}/probe|enable|disable
GET /v1/ai-studio/models[/name]
GET /v1/ai-studio/health
GET /v1/ai-studio/metrics
```

Compatible:

```text
GET  /v1/models
POST /v1/chat/completions
POST /v1/completions
POST /v1/embeddings
POST /v1/responses
```

`read` permite catalog; `write` muta endpoint; `invoke` llama modelos;
`admin` cambia policy; `process` arranca/paran procesos.

Error estable:

```json
{"error":{"message":"model does not support streaming",
"type":"capability_error","param":"stream",
"code":"capability_not_supported","request_id":"req_01"}}
```

Códigos mínimos: `invalid_request`, `unauthorized`, `forbidden`,
`model_not_found`, `capability_not_supported`, `endpoint_unavailable`,
`endpoint_saturated`, `upstream_timeout`, `upstream_bad_response`,
`rate_limited`, `body_too_large`, `stream_limit_exceeded` y
`proxy_misconfigured`.

## 7. Routing y retries

Pipeline: validate → resolve public model → filter state/capability/policy →
check rate/concurrency → score → reserve slot → forward → release → usage.

Strategies: priority, weighted round-robin, least-in-flight y latency-aware.
El score puede usar prioridad, EWMA p95, ratio in-flight y locality; nunca
prompt, PII o contenido semántico.

Retry sólo para connect reset, 502/503/504 y timeout antes de bytes. Nunca para
400/401/403/404, errores de capability, stream parcial u operación no
idempotente sin `Idempotency-Key`. Fallback a otro endpoint es explícito,
crea un nuevo attempt y conserva el request id.

## 8. Streaming

SSE bounded: parser por eventos, máximo de línea/evento/bytes/segundos,
`BoundedEventQueue(max_events=256)`, cancelación al desconectar el cliente y
`[DONE]` sólo tras cierre correcto. Si la cola se llena, se bloquea la lectura
upstream; tras `backpressure_timeout` se cancela con `client_backpressure`.
Nunca se bufferiza el stream completo.

## 9. Discovery

Probe común: health/readiness, `/v1/models`, capacity adapter-specific y
request sintética opcional desactivada. Tiene timeout, jitter, lease,
circuit-breaker y backoff 1/2/4/8 segundos hasta 5 minutos.

Ollama usa OpenAI API y native metadata sólo cuando haga falta. llama.cpp usa
`/health` para readiness, `/slots` para capacidad y `/metrics` opcional. vLLM
usa `/v1/models`; `extra_body` requiere schema. Generic nunca autodetecta ni
lanza procesos.

Estados: `unknown → probing → ready`; `ready → degraded/saturated/failed`;
`saturated → ready`; `failed → probing` tras cooldown; cualquiera → disabled
por desired state.

## 10. Persistencia

AI Studio posee sus tablas. Migración `ai_studio_001.sql` contiene:

```sql
ai_studio_endpoints(endpoint_id PK, workspace_id, adapter, base_url,
  auth_secret_ref, tls_profile, mode, desired_state, observed_state,
  priority, weight, max_in_flight, timeout columns, config_json,
  created_at, updated_at, version)
ai_studio_models(endpoint_id, provider_model_id, public_name,
  capabilities_json, metadata_json, metadata_digest, loaded_state,
  last_seen_at, PRIMARY KEY(endpoint_id, provider_model_id))
ai_studio_route_stats(endpoint_id, public_name, window_start, requests,
  failures, input_tokens, output_tokens, latency aggregates,
  PRIMARY KEY(endpoint_id, public_name, window_start))
```

Optimistic concurrency por `version`; soft-disable, no delete físico. Un
modelo desaparece tras dos probes consecutivos, no inmediatamente. Retención
de stats local configurable, 30 días por defecto.

## 11. Seguridad

SSRF guard con resolución DNS/IP final, bloqueo metadata/link-local,
redirects desactivados y revalidación de TLS. Auth entrante reutiliza grants
Ronin; auth upstream usa SecretRef. CORS desactivado por defecto.

Headers reenviados son una allowlist: no `Cookie`, `Authorization` del cliente,
`X-Forwarded-*` ni headers arbitrarios. Body, SSE y response son bounded.
Tools sólo pasan con ToolPolicy; jamás se interpretan como Python/comandos.

Process supervisor usa `Popen(argv, shell=False)`, executable digest, env/cwd/
model directory allowlists, grupo de proceso, stdout bounded y apagado
SIGTERM/grace/kill. No hereda secretos.

## 12. Observabilidad

Logs: request/correlation, workspace hash, endpoint, model, operation, attempt,
outcome, duración y status. Métricas:

```text
requests_total{operation,model,endpoint,outcome}
duration_seconds{operation,model,endpoint}
time_to_first_byte_seconds{model,endpoint}
in_flight{endpoint,model}, queue_depth{endpoint,model}
upstream_errors_total{endpoint,code}, tokens_total{direction,model,endpoint}
probe_status{endpoint}, model_load_seconds{endpoint,model}
```

Labels son IDs controlados; nunca prompt, URL completa o tenant sin límite.
Audit events cubren cambios administrativos y decisiones denegadas, no cada
invocation por defecto.

## 13. Hooks y aceptación

Hooks: `provider_adapter.v1`, `request_policy.v1`, `route_score.v1`,
`response_normalizer.v1`, `redaction.v1`, `health_probe.v1` y
`process_profile.v1`. Ninguno puede saltar validación de seguridad.

Aceptación: cliente OpenAI funciona; aislamiento workspace funciona; capability
incorrecta falla antes del upstream; desconexión cancela en <2 s; endpoint
caído entra cooldown; saturación no reinicia; retries no duplican; no hay
secretos/body en logs/audit; safe mode arranca aunque AI Studio falle.
