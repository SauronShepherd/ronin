# P1.4 — scope explícito en GET de plugins

Fecha: 2026-11-13  
Estado: PASS (subfase acotada; no cierra P1 ni cualifica Public v1)

## Alcance

El despacho HTTP de rutas GET de plugins `data-engineering:*` y `ml-studio:*`
ahora falla cerrado cuando no existe `workspace_id` en la ruta ni en la query.
El handler del plugin no se invoca y se devuelve `403` con el código estable
`plugin_workspace_scope_required`. Los scopes explícitos existentes continúan
pasando por la autorización tipada y las rutas Cloud Studio conservan su
política separada de workspace por defecto.

## Evidencia

- `python -m pytest -q tests/integration/test_data_engineering_http.py tests/integration/test_ml_studio_http.py tests/integration/test_workspace_project_http_api.py -k 'plugin or data_engineering or queryflux or ml_studio'`
  — **16 passed, 46 deselected, 0 failed**.
- Regresión nueva: `test_data_engineering_get_without_workspace_scope_fails_closed`
  — **passed**.
- Ruff check sobre `control_plane.py` y el test nuevo — **All checks passed**.
- Ruff format check — **2 files already formatted**.

## Límites

Este recibo cubre el guard de despacho GET en un fixture HTTP in-process. No
acredita la instalación empaquetada de plugins, multiusuario/OIDC, proveedor
externo, navegador ni una familia Public v1 completa. El estado oficial sigue
en **0/13, 0%, NO-GO**.
