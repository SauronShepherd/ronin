# P1.6 — autorización exacta de proyecto

Fecha: 2026-11-13  
Estado: PASS (subfase HTTP/plugin; no cierra P1 ni cualifica Public v1)

## Alcance

El despacho de rutas de workspace/proyecto delegadas a plugins propaga ahora el
`project_id` capturado como `resource_ref` a la autorización tipada. Antes se
autorizaba únicamente el workspace para la ruta base de lectura de proyecto,
lo que permitía que un actor con permiso sobre otro proyecto del mismo servidor
superara la comprobación de recurso. El handler sigue sin ejecutarse cuando el
grant exacto falta.

## Evidencia

- Regresión de autorización exacta y compatibilidad de la ruta:
  `python -m pytest -q tests/integration/test_workspace_project_http_api.py -k 'project_routes_require_exact_workspace_grant or plugin_project_read_replace_delete_routes_use_project_port or authentication_and_denial'`
  — **3 passed, 53 deselected, 0 failed**.
- El negativo verifica actor con `project.read` únicamente en workspace B,
  acceso a proyecto de workspace A, respuesta `403` y `resource_ref` igual al
  proyecto solicitado.
- Ruff check — **All checks passed**.
- Ruff format check — **2 files already formatted**.

## Límites

Este recibo cubre el dispatcher HTTP in-process y el plugin de workspaces. No
acredita multiusuario/OIDC, instalación empaquetada, PostgreSQL/Compose,
browser/SDK parity ni una familia Public v1 completa. El estado oficial sigue
en **0/13, 0%, NO-GO**.
