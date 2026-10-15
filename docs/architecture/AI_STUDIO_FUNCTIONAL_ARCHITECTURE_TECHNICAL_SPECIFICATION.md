# Ronin AI Studio

## Functional, Architectural, and Technical Specification

**Status:** Implemented specification  
**Plugin name:** AI Studio  
**Plugin identifier:** `com.sauronshepherd.ronin.ai-studio`  
**Python package:** `studio_ai_studio`  
**Entry point:** `ai_studio = studio_ai_studio.plugin:factory`

## 1. Purpose and product definition

AI Studio is Ronin's open-source control plane and proxy for discovering,
calling, routing, observing, and safely exposing local or self-hosted AI model
servers. It is deliberately not an inference engine. Model execution remains
the responsibility of replaceable providers such as Ollama, llama.cpp, vLLM,
or any server implementing the supported OpenAI-compatible surface.

AI Studio provides the missing platform layer around those runtimes:

- endpoint registration and lifecycle;
- model and capability discovery;
- workspace-scoped model exposure;
- OpenAI-compatible buffered and streaming APIs;
- deterministic routing and capacity accounting;
- retries, fallback, rate limits, and body/stream bounds;
- SSRF protection and upstream secret isolation;
- optional, allowlisted process supervision;
- audit events, metrics, usage records, and redacted diagnostics;
- declarative UI metadata and operational runbooks.

The core design principle is **provider neutrality**. The domain and gateway
must not depend on Ollama, llama.cpp, vLLM, HTTPX, SQLite, FastAPI, a cloud
service, or a particular operating system.

## 2. Goals and non-goals

### 2.1 Goals

1. Make local model serving look like a governed Ronin capability.
2. Preserve workspace and permission isolation for every catalog and invocation.
3. Expose a stable canonical API while adapting provider differences explicitly.
4. Keep all network, storage, and process I/O behind replaceable ports.
5. Fail closed for invalid URLs, unsupported capabilities, oversized payloads,
   unsafe headers, unauthorized workspaces, and unsafe process profiles.
6. Make readiness, degradation, saturation, and failure distinguishable.
7. Make operational behavior testable without a model server or GPU.
8. Make a real runtime optional for development while retaining deterministic
   fake and contract test suites in CI.

### 2.2 Non-goals

- downloading arbitrary models automatically;
- executing arbitrary shell commands, Modelfiles, Python, or tool payloads;
- fine-tuning, training, or multi-node scheduling;
- GPU allocation or physical VRAM scheduling;
- semantic routing based on prompt contents;
- prompt or completion persistence by default;
- exposing a local endpoint to a LAN by default;
- pretending that OpenAI compatibility means identical provider behavior.

## 3. User-facing functional specification

### 3.1 Endpoint management

An administrator can register an external or managed endpoint with:

- stable endpoint ID;
- adapter family;
- base URL;
- workspace or global scope;
- desired enabled/disabled state;
- priority and routing weight;
- concurrency limit;
- connection, read, write, and pool timeouts;
- TLS profile and secret reference;
- optional managed process profile.

Endpoint mutations are permission-protected, versioned, auditable, and
optimistic-concurrency safe. Disable is a soft state transition; physical
deletion is not required for normal lifecycle operations.

### 3.2 Discovery and catalog

AI Studio periodically or manually probes configured endpoints. Discovery
records provider model IDs, public names, capabilities, context limits, model
metadata, readiness, and capacity observations.

The catalog must:

- hide models outside the caller's workspace scope;
- reject ambiguous public aliases;
- expose only safe metadata;
- tolerate stale snapshots;
- require consecutive absence observations before removing a model;
- distinguish an endpoint that is healthy but saturated from one that failed.

### 3.3 Invocation

Supported public operations are:

| Operation | HTTP endpoint | Required capability |
|---|---|---|
| Model catalog | `GET /v1/models` | `read` |
| Chat | `POST /v1/chat/completions` | `chat` |
| Legacy completion | `POST /v1/completions` | `completion` |
| Embeddings | `POST /v1/embeddings` | `embedding` |
| Responses | `POST /v1/responses` | `response` |

Every invocation is normalized, authorized, model-resolved, capability-checked,
rate-limited, routed, capacity-reserved, forwarded, normalized, and released
through a `finally` path.

### 3.4 Streaming

Streaming uses bounded Server-Sent Events. The implementation supports
fragmented events, multiline data, comments, blank event terminators, provider
errors, client disconnect, upstream cancellation, and the `[DONE]` convention.
The complete stream is never buffered in memory.

### 3.5 Runtime supervision

Process supervision is opt-in and separately permissioned. A process profile
must define the executable, argument template, executable digest, environment
allowlist, working directory, model directories, port constraints, and
resource bounds. AI Studio starts processes with `shell=False`, bounded output,
process-group cleanup, graceful termination, and restart backoff.

Generic endpoints never start processes automatically.

## 4. Plugin manifest and host integration

```text
id:           com.sauronshepherd.ronin.ai-studio
name:         Ronin AI Studio
entry point:  studio_ai_studio.plugin:factory
isolation:    worker
capabilities: ai-studio.discovery
              ai-studio.proxy
              ai-studio.exposure
              ai-studio.streaming
permissions:  ai-studio:read
              ai-studio:write
              ai-studio:invoke
              ai-studio:admin
              ai-studio:process
```

The plugin is discovered through the existing Ronin plugin registry and
contributes workspace-scoped routes and a declarative UI manifest. Importing
the package performs no network access, process launch, model loading, or
database mutation. Failure of AI Studio must degrade the plugin rather than
bring down the host or unrelated plugins.

## 5. Logical architecture

```text
Client / OpenAI SDK
        |
Ronin HTTP host, auth, workspace context
        |
AI Studio HTTP API
        |
normalization -> policy -> catalog -> limits -> router
        |                                      |
        |                              capacity ledger
        v                                      |
Buffered gateway / SSE gateway ----------------+
        |
Provider adapter port
        |
HTTP transport port
        |
Ollama | llama.cpp | vLLM | generic OpenAI-compatible server

Discovery worker -> adapter probes -> state reducer -> endpoint/model store
Process supervisor (optional, allowlisted) -> managed runtime
Audit / metrics / usage -> Ronin observability ports
```

### 5.1 Package responsibilities

| Package/module | Responsibility |
|---|---|
| `contracts.py` | IDs, enums, endpoint/model/request value objects |
| `errors.py` | Stable domain and provider-facing error taxonomy |
| `adapters.py` | Provider adapter protocol and concrete adapters |
| `discovery.py` | Probing, snapshots, state transitions, persistence |
| `router.py` | Candidate filtering, strategies, capacity ledger |
| `gateway.py` | Invocation orchestration and slot release |
| `http_api.py` | Host-neutral canonical HTTP operation mapping |
| `streaming.py` | SSE parsing, queue bounds, stream limits |
| `limits.py` | Token buckets and bounded request fairness |
| `security.py` | URL validation, DNS/IP SSRF policy, network scope |
| `processes.py` | Explicit managed runtime supervision |
| `storage.py` | SQLite persistence port and optimistic concurrency |
| `observability.py` | Redaction, bounded labels, audit/metrics records |
| `plugin.py` | Manifest, permissions, route and UI contribution |
| `ui_manifest.py` | Endpoints, models, health, policy navigation metadata |

No plugin imports another plugin's internals. Core domain code does not import
HTTP clients, databases, subprocess APIs, or provider SDKs.

## 6. Domain model

### 6.1 Endpoint configuration

```text
EndpointId       lower-case stable identifier, 1..128 chars, no slash
adapter          ollama | llama_cpp | vllm | openai_compatible
base_url         http/https URL without userinfo, query, or fragment
auth_secret_ref  opaque SecretRef; never a plaintext token
tls_profile      default or named custom-CA reference
scope            global or workspace
mode             external or managed
desired_state    enabled or disabled
observed_state   unknown | probing | ready | degraded | saturated | failed
priority         0..65535; lower is preferred
weight           1..10000
max_in_flight    positive bounded integer
timeouts         bounded connect/read/write/pool durations
```

### 6.2 Model snapshot

```text
endpoint_id + provider_model_id  composite identity
public_name                      Ronin-visible alias
capabilities                     observed/declarative capability set
context_window                   optional provider limit
max_output_tokens                optional provider limit
modalities                       text, image, audio, or provider values
loaded_state                     unknown, loading, loaded, unavailable
metadata_digest                  deterministic SHA-256 of safe metadata
last_seen_at                     observation timestamp
```

Capabilities include `chat`, `completion`, `embedding`, `response`,
`streaming`, `tools`, `structured_output`, `vision`, `audio`, and `rerank`.
The gateway rejects an operation before forwarding it when the selected model
does not advertise the required capability.

### 6.3 Lifecycle state machine

```text
unknown -> probing -> ready
ready -> degraded | saturated | failed
saturated -> ready | degraded | failed
failed -> probing after cooldown
any state -> disabled when desired_state=disabled
```

Readiness and capacity are separate observations. A healthy endpoint with all
slots occupied is `saturated`, not `failed`, and is not restarted.

## 7. Provider adapter specification

Every adapter implements the conceptual contract:

```python
probe(endpoint) -> CapabilitySnapshot
list_models(endpoint) -> tuple[ModelSnapshot, ...]
invoke(request, decision) -> ProviderResponse
stream(request, decision) -> Iterator[bytes]
```

### 7.1 Generic OpenAI-compatible adapter

The generic adapter requires explicit configuration where provider behavior is
ambiguous. It probes `/v1/models`, validates JSON shape, bounds response size,
disables redirects, and never starts a process.

### 7.2 Ollama adapter

The Ollama adapter uses its OpenAI-compatible API for common invocation and may
use native metadata endpoints for provider-specific discovery. Model names are
not inferred from local files. Availability, model loading, and provider errors
are represented explicitly.

### 7.3 llama.cpp adapter

The llama.cpp adapter uses `/health` for readiness, `/v1/models` for model
identity, and optional `/slots` or `/metrics` information for capacity. It
supports the OpenAI-compatible completion/chat surface and the provider's
streaming behavior through the canonical adapter contract.

### 7.4 vLLM adapter

The vLLM adapter uses `/v1/models` and OpenAI-compatible operations. Provider
extensions such as `extra_body` require explicit schema and policy approval;
unknown extensions are not blindly passed through.

## 8. Public API and permissions

### 8.1 Workspace routes

The plugin contributes workspace-scoped routes for model listing and invoke:

```text
GET  /v1/workspaces/{workspace_id}/ai-studio/models
POST /v1/workspaces/{workspace_id}/ai-studio/invoke
```

The canonical compatibility routes are exposed by the host integration and are
subject to the same workspace context and permission checks.

### 8.2 Permission model

| Permission | Meaning |
|---|---|
| `ai-studio:read` | Read endpoints, health, models, and safe metadata |
| `ai-studio:write` | Create/update/disable endpoint configuration |
| `ai-studio:invoke` | Invoke a permitted model |
| `ai-studio:admin` | Change routing, limits, policies, or recovery state |
| `ai-studio:process` | Start/stop an approved managed runtime |

### 8.3 Error envelope

```json
{
  "error": {
    "message": "model does not support streaming",
    "type": "capability_error",
    "param": "stream",
    "code": "capability_not_supported",
    "request_id": "req_01"
  }
}
```

Stable codes include `invalid_request`, `unauthorized`, `forbidden`,
`model_not_found`, `capability_not_supported`, `endpoint_unavailable`,
`endpoint_saturated`, `upstream_timeout`, `upstream_bad_response`,
`rate_limited`, `body_too_large`, `stream_limit_exceeded`, and
`proxy_misconfigured`.

## 9. Request pipeline and routing

```text
authenticate
  -> resolve workspace and permissions
  -> bounded body read
  -> normalize operation
  -> resolve public model
  -> filter state, capability, scope, and policy
  -> apply rate and concurrency limits
  -> score candidates
  -> reserve capacity atomically
  -> forward through adapter
  -> normalize provider response
  -> release capacity in finally
  -> record usage, metrics, and outcome
```

Routing strategies are priority, weighted round-robin, least-in-flight, and
latency-aware. Tie-breaking is deterministic by endpoint ID. Scores may use
priority, EWMA latency, in-flight ratio, and locality; they never use prompt
contents, PII, or semantic classification.

Retries are limited to connection reset, HTTP 502/503/504, and timeouts before
provider bytes have been received. The gateway never retries validation,
authentication, authorization, capability, 400/404 errors, partial streams,
or non-idempotent operations without an idempotency key. Fallback creates a
new attempt while retaining the original request ID.

## 10. Limits and streaming safety

The implementation bounds request body size, provider response size, stream
line length, event size, total stream bytes, stream duration, queue depth, and
concurrency. Token buckets are keyed by workspace, subject, and public model.

Streaming uses a bounded event queue, normally `max_events=256`. If the queue
fills, upstream reading is backpressured. A `backpressure_timeout` cancels the
upstream with a stable `client_backpressure` outcome. Client disconnect always
propagates cancellation and releases the capacity reservation.

## 11. Persistence and consistency

AI Studio owns its persistence tables and migration namespace. The SQLite
implementation uses parameterized statements, transactions, and optimistic
concurrency through a version column. The storage port is replaceable by a
Postgres implementation.

Logical tables are:

- `ai_studio_endpoints`;
- `ai_studio_models`;
- `ai_studio_route_stats`.

Model disappearance requires two consecutive failed observations. Statistics
are aggregate-only and have bounded retention. Secrets, prompts, completion
content, and raw provider bodies are not stored by default.

## 12. Security model

### 12.1 Network security

The SSRF policy validates scheme, host, port, DNS resolution, final IP class,
redirect behavior, and TLS. Loopback/private targets are allowed only under an
explicit local network scope. Metadata, link-local, multicast, ambiguous, and
unsafe addresses are rejected. Redirects are disabled and DNS/IP policy is
rechecked after resolution.

### 12.2 Header and secret security

Only an allowlisted set of headers is forwarded. Client `Authorization`,
`Cookie`, `X-Forwarded-*`, arbitrary credential headers, and internal tracing
headers are not forwarded blindly. Upstream credentials are resolved from
opaque secret references at the execution boundary and are redacted from
errors, logs, metrics, and audit records.

### 12.3 Process security

Managed processes use `Popen(argv, shell=False)`, executable digests, explicit
working directories, model-directory allowlists, environment allowlists,
bounded stdout/stderr, process groups, graceful shutdown, and bounded restart
backoff. No shell interpolation or inherited secret environment is allowed.

## 13. Observability and audit

Logs contain request/correlation ID, workspace hash, endpoint ID, model alias,
operation, attempt, outcome, latency, and provider status. They do not contain
prompts, completions, raw bodies, full URLs with credentials, or secret values.

Recommended bounded metrics include:

```text
requests_total{operation,model,endpoint,outcome}
duration_seconds{operation,model,endpoint}
time_to_first_byte_seconds{model,endpoint}
in_flight{endpoint,model}
queue_depth{endpoint,model}
upstream_errors_total{endpoint,code}
tokens_total{direction,model,endpoint}
probe_status{endpoint}
model_load_seconds{endpoint,model}
```

Audit events cover endpoint creation/update/enable/disable, process lifecycle,
policy changes, probes, and denied routing decisions. Individual invocation
content is not an audit event by default.

## 14. Configuration and deployment

Docker profiles are intentionally opt-in:

```text
docker compose --profile ai-ollama up -d ai-ollama
docker compose --profile ai-llama-cpp up -d ai-llama-cpp
docker compose --profile ai-vllm up -d ai-vllm
```

Model directories and vLLM model identifiers are explicit environment inputs.
Services do not mount the Docker socket. Health checks are separate from
capacity checks. CI uses fakes and contract tests when no model server or GPU
is available; real-runtime jobs must report their model, image digest, host,
and smoke-test artifact.

## 15. Testing and quality requirements

The implemented AI Studio suite covers:

- plugin manifest, permissions, route contributions, and UI metadata;
- value object validation and stable error mapping;
- SQLite migration, persistence, and optimistic concurrency;
- adapter probes and malformed provider responses;
- discovery state transitions and snapshots;
- priority, weighted, least-in-flight routing and capacity release;
- buffered gateway retry and fallback rules;
- SSE parsing, bounds, and cancellation;
- token buckets and rate limits;
- SSRF/network policy and URL validation;
- process profiles and safe subprocess arguments;
- redaction, bounded metrics, and audit records;
- runtime smoke behavior against an actual local HTTP server.

Required gates are:

```text
pytest tests/test_ai_studio_*.py
ruff check python/studio_ai_studio tools/ai_studio_runtime_smoke.py tests/
mypy python/studio_ai_studio
python tools/architecture_gate.py
git diff --check
docker compose config --quiet
```

The real-runtime smoke tool checks `/v1/models`, verifies the requested model,
then sends a minimal `/v1/chat/completions` request and returns non-zero on
any transport, model, JSON, or response failure.

## 16. Performance and reliability targets

For a local buffered request without TLS, AI Studio should add less than 20 ms
of p95 proxy overhead under the benchmark harness. Additional streaming time to
first byte should remain below 30 ms excluding provider generation. All queues,
buffers, retries, and labels are bounded. Capacity reservations are released
on success, error, timeout, cancellation, and malformed provider response.

The host remains usable in safe mode when AI Studio is disabled, misconfigured,
or unable to reach a provider. Circuit breakers use bounded failure thresholds,
cooldowns, and half-open probes; endpoint failure must not cause an infinite
restart loop.

## 17. Extension points

Future extensions are versioned ports, not imports into internal modules:

- `provider_adapter.v1`;
- `request_policy.v1`;
- `route_score.v1`;
- `response_normalizer.v1`;
- `redaction.v1`;
- `health_probe.v1`;
- `process_profile.v1`.

An extension may add behavior but may not bypass authentication, workspace
scope, capability validation, body/stream limits, SSRF policy, or audit rules.

## 18. Acceptance criteria

AI Studio is accepted when:

1. An OpenAI-compatible client can list and invoke an allowed local model.
2. Workspace isolation prevents cross-workspace model visibility and calls.
3. Unsupported capabilities fail before an upstream request.
4. Endpoint readiness and capacity are independently observable.
5. Retry logic cannot duplicate unsafe non-idempotent operations.
6. Client disconnect cancels a stream and releases capacity promptly.
7. No secret, prompt, completion, or raw body appears in default telemetry.
8. SSRF, unsafe headers, oversized payloads, and unsafe process profiles fail
   closed.
9. Safe mode continues to run the host when AI Studio is unavailable.
10. Documentation includes deployment, troubleshooting, rollback, security,
    compatibility, and real-runtime validation procedures.

## 19. Operational references

- [AI Studio proposal](./AI_STUDIO_PROPOSAL.md)
- [AI Studio build plan](./BUILD_PLAN_AI_STUDIO.md)
- [AI Studio runbook](../operations/AI_STUDIO_RUNBOOK.md)
- [AI Studio release checklist](../operations/AI_STUDIO_RELEASE_CHECKLIST.md)
- [AI Studio validation status](../operations/AI_STUDIO_VALIDATION_STATUS.md)
