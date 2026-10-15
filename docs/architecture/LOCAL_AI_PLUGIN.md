# Ronin AI Studio plugin

## Decision

`studio_ai_studio` is the community plugin for discovering and exposing local
inference servers through one policy-aware OpenAI-compatible surface. It does
not embed Ollama, llama.cpp or vLLM. Those runtimes remain replaceable workers;
Ronin owns endpoint metadata, model routing, request bounds, permissions and
audit/telemetry integration.

The first supported wire contract is `/v1/chat/completions`, `/v1/completions`,
`/v1/embeddings` and `/v1/responses`. Streaming is intentionally a follow-up:
it needs an explicit bounded SSE contract and cancellation propagation instead
of silently buffering responses.

## Why this shape

- Ollama, llama.cpp and vLLM all expose OpenAI-compatible HTTP surfaces, so a
  provider adapter should be shared rather than duplicated.
- LiteLLM demonstrates that a proxy becomes valuable around the model call:
  routing, retries/fallback, authentication, rate limits and usage tracking.
- Local endpoints are commonly plain HTTP on loopback. HTTP is accepted only
  for explicitly configured local endpoints; remote endpoints must use HTTPS.
- The plugin is declared as a worker-isolated capability. A future trusted
  in-process adapter can reuse the same contracts without changing callers.

## Configuration and safety invariants

Endpoint URLs cannot contain credentials, query strings or fragments. Model
names are allowlisted per endpoint. Requests are bounded by bytes and route
allowlist. Routing is deterministic (`priority` by default, optional
round-robin), and retries do not fan out implicitly to another model.

The HTTP API should be mounted by the host with `ai-studio:read` and
`ai-studio:write` scopes. Secrets must be resolved at execution time and
never be stored in the manifest, endpoint URL, logs or events.

## References

- [vLLM OpenAI-compatible server](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/)
- [llama.cpp server API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [LiteLLM gateway overview](https://docs.litellm.ai/)

## Next implementation slices

1. Persist endpoint registrations in the GenAI bounded context and add model
   discovery health checks (`/v1/models`).
2. Add a host adapter for streaming SSE with maximum event/byte limits.
3. Add rate-limit, usage and audit ports; keep cost calculation optional for
   local models.
4. Add optional process supervision for llama-server/Ollama profiles, behind a
   capability and explicit user consent.
