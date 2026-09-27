# AI Studio — release checklist

## Automated gates

- [ ] `ruff check python/studio_ai_studio tests/test_ai_studio_*.py`
- [ ] `mypy python/studio_ai_studio`
- [ ] `pytest -q tests/test_ai_studio_*.py`
- [ ] architecture/import gate
- [ ] plugin inventory and lockfile regenerated
- [ ] benchmark artifact generated with `tools/ai_studio_benchmark.py`

## Runtime matrix

Run each row when its runtime is available; attach the JSON result and logs.

| Runtime | Endpoint | Readiness | Models | Buffered | SSE | TLS |
|---|---|---:|---:|---:|---:|---:|
| Ollama | `/v1/models` | [ ] | [ ] | [ ] | [ ] | [ ] |
| llama.cpp | `/health`, `/slots` | [ ] | [ ] | [ ] | [ ] | [ ] |
| vLLM | `/v1/models` | [ ] | [ ] | [ ] | [ ] | [ ] |
| generic | configured | [ ] | [ ] | [ ] | [ ] | [ ] |

CI without model servers must report `simulated`, never `passed-real-runtime`.

## Security gates

- [ ] no credential in endpoint URL, lockfile or logs
- [ ] SSRF/private/link-local checks verified
- [ ] redirects disabled
- [ ] process profile uses allowlisted executable and `shell=False`
- [ ] prompts/responses absent from default telemetry
- [ ] workspace authorization tested through PluginRouter

## Operational gates

- [ ] `ready` and `saturated` are distinguishable
- [ ] upstream failure enters cooldown
- [ ] stream cancellation releases slot
- [ ] rate limit returns bounded `Retry-After`
- [ ] rollback disables capability without deleting data
- [ ] runbook reviewed by operator
