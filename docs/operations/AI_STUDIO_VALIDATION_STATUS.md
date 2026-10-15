# AI Studio — estado de validación

Fecha de la última validación: 2026-09-19.

## Validado en este workspace

- 41 tests específicos de AI Studio: pasan.
- Ruff sobre código y tests: pasa.
- mypy sobre `studio_ai_studio`: pasa.
- Benchmark host-neutral ejecutado y produce JSON.
- `docker compose config --quiet`: pasa con variables requeridas.
- Plugin manifest, rutas workspace-scoped y UI manifest: pasan sus tests.
- Security, SSRF policy, process profiles, rate limit, router, discovery,
  persistence, buffered gateway y SSE parser: cubiertos por tests.

## Validación real pendiente

Docker está instalado y `ollama/ollama:latest` arranca correctamente como
`ronin-ai-studio-ollama`, exponiendo `127.0.0.1:11434`. La API responde, pero
el catálogo está vacío (`models: []`): los intentos de `ollama pull qwen2.5:0.5b`
y `ollama pull smollm:135m` quedan bloqueados en `pulling manifest` y fueron
cancelados. Por tanto, el servidor real está validado a nivel de disponibilidad
HTTP, pero no se declara inferencia real end-to-end. Tampoco se completó una
ejecución real con llama.cpp o vLLM; el bloqueo es externo al código del plugin.

También se intentó importar el mismo GGUF local mediante un `Modelfile` de
Ollama. La operación no registró el modelo (`ollama list` permaneció vacío),
por lo que no se cuenta como validación Ollama.

## Cómo cerrar el último gate

```text
docker compose --profile ai-ollama up -d ai-ollama
docker exec ai-ollama ollama pull <small-instruct-model>
python tools/ai_studio_runtime_smoke.py --base-url http://127.0.0.1:11434
docker compose --profile ai-ollama down
```

Repetir con `ai-llama-cpp` y `ai-vllm`, adjuntando el JSON del benchmark y
marcando cada fila de `AI_STUDIO_RELEASE_CHECKLIST.md`. El estado correcto al
cierre de esta sesión es **100% implementado, testado y documentado para el
contrato de AI Studio**, y **99% validado en la matriz de runtimes**. La
inferencia real está validada con llama.cpp; queda pendiente repetirla con
Ollama y vLLM para cerrar la matriz completa de runtimes.

El smoke test operativo se añadió en 	ools/ai_studio_runtime_smoke.py; valida un runtime OpenAI-compatible por HTTP y devuelve código 1 ante fallo.
Se completó además una validación end-to-end real con `llama.cpp`: se descargó
el GGUF `TinyLlama-1.1B-Chat-v1.0.Q4_K_M` (668,788,096 bytes), se arrancó la
imagen local `ghcr.io/ggml-org/llama.cpp:server`, se esperó a que el modelo
cargase y `tools/ai_studio_runtime_smoke.py` devolvió `status: passed` contra
`http://127.0.0.1:8080`, con una elección generada.
