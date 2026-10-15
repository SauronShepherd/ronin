# Machine Learning Studio — operación local

## Activación

La composición local de Ronin inicializa automáticamente `SqliteMLLabStore` y `SqliteMLStore` sobre la base definida por `RONIN_DB`. El plugin se activa cuando `RONIN_PLUGIN_API=plugin`, que es el valor por defecto del perfil local.

El extra opcional de ML debe estar instalado:

```powershell
pip install -e ".[ml]"
```

Si scikit-learn no está disponible, el plugin puede descubrirse y mostrar sus capacidades, pero el backend `local.sklearn` devolverá un error de dependencia al ejecutar.

## Flujo operativo

1. Crear un Lab mediante `POST /v1/ml-studio/labs`.
2. Compilarlo con `POST /v1/ml-studio/labs/{lab_id}/compile`.
3. Enviar una ejecución asíncrona a `POST /v1/ml-studio/labs/{lab_id}/executions`.
4. Consultar `GET /v1/ml-studio/executions/{run_id}` hasta un estado terminal.
5. Consultar el provenance persistido con `GET /v1/ml-studio/runs/{run_id}` cuando el registry esté habilitado.
6. Cancelar una ejecución activa con `POST /v1/ml-studio/executions/{run_id}/cancel`.

Para ejecutar una búsqueda grid local, usar `POST /v1/ml-studio/labs/{lab_id}/search`
con `spec`, `rows` y parámetros definidos. Cada combinación se entrena realmente y se
devuelve rankeada. El parámetro `seed` está soportado explícitamente; otros parámetros
requieren que el backend los aplique antes de considerarse efectivos.

El scoring batch de una versión registrada está disponible en
`POST /v1/ml-studio/models/{model_id}/{version}/predict`. El contrato exige el artefacto
canónico en `artifact_base64` o, cuando el host inyecta un `ArtifactStore`, resuelve el
artefacto por `storage_ref`; en ambos casos el servicio comprueba digest y firma antes de
predecir. La forma inline es deliberadamente de desarrollo y debe evitarse con datasets
grandes.

Antes de ejecutar un dataset, puede usarse `POST /v1/ml-studio/labs/{lab_id}/quality` con
`{"rows": [...]}`. La respuesta incluye el perfil por columna (`dtype`, nulos,
cardinalidad y constantes), advertencias y fallos bloqueantes. Por defecto se exige un
mínimo de cuatro filas; en clasificación también se exigen dos clases y al menos dos
ejemplos por clase. Un `passed: false` debe detener el pipeline antes de entrenar.

La ejecución local mantiene el mismo contrato que el futuro worker broker: `queued`, `running`, `succeeded`, `failed` y `cancelled`. El coordinador se cierra durante el shutdown del plugin para no dejar threads vivos.

El estado de ejecución se persiste en `ml_studio_executions` dentro de la base SQLite
local. Si Ronin se reinicia, una consulta de un `run_id` terminal recupera su estado y
su error de auditoría sin volver a lanzar el entrenamiento. Los artefactos y métricas
completos siguen viviendo en el registry/provenance; la tabla de ejecuciones es el
registro durable del lifecycle y el punto de integración para un futuro worker broker.

## Seguridad

Los permisos requeridos son `ml-studio:read`, `ml-studio:write` y `ml-studio:execute`. El body de ejecución actual está pensado para datasets pequeños y de desarrollo; la siguiente integración sustituirá las filas inline por `AssetRef` y lectura mediante catálogo para producción.

## Diagnóstico

- `BackendNotFound`: el Lab pide un backend no instalado.
- `MLDependencyError`: instalar el extra `[ml]`.
- `ValueError` de split o target: revisar filas, target y tamaño mínimo.
- `failed`: consultar el estado de ejecución y conservar el error como evidencia.
- `plugins_unavailable`: revisar `RONIN_PLUGIN_API`, lockfile y diagnostics de `/v1/platform/plugins`.

## Verificación E2E

La prueba de integración `tests/integration/test_ml_studio_http.py` levanta el host de
plugins y el control plane HTTP, autentica con un bearer de pruebas y verifica el flujo:

1. `POST /v1/ml-studio/labs?workspace_id=...` crea el lab.
2. `POST /v1/ml-studio/labs/{lab_id}/quality?workspace_id=...` valida el dataset.
3. `POST /v1/ml-studio/labs/{lab_id}/executions?workspace_id=...` encola la ejecución.

Este escenario prueba también la autorización del permiso `ml-studio:write` y
`ml-studio:execute`, la resolución de `workspace_id` desde query string y el registro de
rutas del plugin dentro del control plane.
