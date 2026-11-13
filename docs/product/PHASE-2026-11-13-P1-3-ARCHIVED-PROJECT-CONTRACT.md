# P1.3 — contrato de proyectos archivados

Fecha: 2026-11-13  
Estado: PASS (subfase acotada; no cierra P1 ni cualifica Public v1)

## Alcance

Se cerró la invariancia OSS local del contrato de proyecto archivado: el
listado continúa mostrando únicamente proyectos activos y las mutaciones
`replace`/`unregister` no pueden modificar ni eliminar un registro archivado.
La misma barrera queda aplicada en SQLite y PostgreSQL mediante el predicado
transaccional `archived_at IS NULL`. Un intento de mutación que pierde la
condición devuelve el error estable de proyecto no encontrado en la capa de
servicio; no existe reactivación implícita.

La lectura de un proyecto archivado permanece permitida para conservar
trazabilidad. La restauración explícita, la cualificación PostgreSQL real y
los journeys instalados API/SDK/Studio con restart siguen siendo trabajo
posterior y no se declaran cubiertos por este recibo.

## Evidencia

- `python -m pytest -q tests/test_workspace_project_services.py tests/integration/test_workspace_project_http_api.py tests/test_project_manifest.py`
  — **134 passed, 0 failed**.
- `ruff check` sobre los cuatro archivos modificados — **All checks passed**.
- `ruff format --check` sobre los cuatro archivos modificados — **4 files already formatted**.
- Regresión específica de archivo/mutación: **11 passed, 52 deselected**.

## Archivos modificados

- `python/studio_storage/workspaces.py`
- `python/studio_storage/postgres_core.py`
- `python/studio_execution/workspace_service.py`
- `tests/test_workspace_project_services.py`

## Límites de la afirmación

Este recibo acredita una subfase contractual y no una cualificación de P1
completa. No acredita proveedor Git remoto, PostgreSQL ejecutado en laboratorio,
multiusuario/OIDC, restart E2E ni ninguna familia Public v1. El denominador
oficial continúa en **0/13, 0%, NO-GO**.
