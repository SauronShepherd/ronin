# AI Studio — runbook operativo

## Arranque mínimo

1. Instalar Ronin con el extra `data-plane` para HTTP.
2. Activar el plugin `ai_studio` en el lockfile.
3. Configurar un endpoint local, preferiblemente loopback:

```json
{
  "id": "ollama",
  "adapter": "ollama",
  "base_url": "http://127.0.0.1:11434",
  "allow_http": true,
  "models": ["qwen"],
  "max_in_flight": 1
}
```

4. Ejecutar un probe y comprobar `ready` y el catálogo de modelos.
5. Invocar mediante `/v1/workspaces/{workspace_id}/ai-studio/invoke`.

HTTP en loopback requiere `allow_http=true`; un endpoint remoto requiere HTTPS,
TLS verificado y `SecretRef`. Nunca pongas API keys en URLs, manifests o logs.

## Diagnóstico

| Estado | Significado | Acción |
|---|---|---|
| `unknown` | aún no probado | ejecutar probe |
| `probing` | probe en curso | esperar o revisar worker |
| `ready` | listo para tráfico | comprobar modelo/capability |
| `degraded` | metadata/capacity parcial | revisar adapter |
| `saturated` | sin slots disponibles | reducir concurrencia o esperar |
| `failed` | readiness fallido | revisar proceso, URL y TLS |
| `disabled` | desactivado administrativamente | habilitar con permiso admin |

Readiness no equivale a capacidad. En llama.cpp `/health` puede estar sano
mientras `/slots` no tenga capacidad; no reinicies por `saturated`.

## Síntomas comunes

- `model_not_found`: el alias público no aparece en el snapshot.
- `capability_not_supported`: el adapter no declaró streaming/tools/embedding.
- `endpoint_saturated`: `max_in_flight` está ocupado; es retryable.
- `upstream_timeout`: revisar timeout, carga y context window.
- `upstream_bad_response`: revisar versión/chat template.
- `client_backpressure`: consumidor SSE demasiado lento.

## Seguridad y privacidad

Se bloquean credenciales embebidas, redirects, hosts no allowlisted y
direcciones reservadas. Los perfiles managed sólo se activan con
`ai-studio:process`, usan `shell=False` y ejecutables allowlisted. Prompts y
respuestas no se guardan por defecto; workspace se etiqueta con hash.

## Rollback

1. Deshabilitar endpoint o capability del plugin.
2. No borrar tablas ni snapshots.
3. Mantener audit y métricas.
4. Volver al lockfile anterior sólo si el plugin API es compatible.
5. Rehabilitar tras probe y smoke test.

## Validación antes de release

```text
python -m ruff check python/studio_ai_studio tests
python -m mypy python/studio_ai_studio
python -m pytest -q tests/test_ai_studio_*.py
```

La matriz real debe repetir el smoke test contra Ollama, llama.cpp y vLLM en
buffered y SSE, con HTTP loopback y HTTPS custom CA. CI sin GPU usa fake
transport y no declara serving real validado.
