# P1.5 — persistencia de proyecto tras reinicio

Fecha: 2026-11-13  
Estado: PASS (subfase SQLite OSS; no cierra P1 ni cualifica Public v1)

## Alcance

Se añadió una regresión de reinicio en la frontera durable de workspace/proyecto.
La prueba crea el proyecto con una instancia de `SqliteWorkspaceStore`, lo lee
con una nueva instancia sin cache compartida, archiva el proyecto, vuelve a
crear el store y verifica que el registro sigue siendo legible para trazabilidad,
no aparece en el inventario activo y no puede ser reemplazado implícitamente.

## Evidencia

- `python -m pytest -q tests/test_storage_ports.py::test_sqlite_project_lifecycle_survives_new_store_instance_after_restart tests/test_storage_ports.py tests/test_workspace_project_services.py`
  — **16 passed, 0 failed**.
- `ruff check tests/test_storage_ports.py` — **All checks passed**.
- `ruff format --check tests/test_storage_ports.py` — **1 file already formatted**.

## Límites

La evidencia es SQLite local y no sustituye una corrida PostgreSQL/Compose,
restart del servidor HTTP instalado, SDK/Studio real, concurrencia entre
clientes ni autorización multiusuario/OIDC. Es una subfase de persistencia, no
una cualificación completa de P1 ni de Public v1. El estado oficial sigue en
**0/13, 0%, NO-GO**.
