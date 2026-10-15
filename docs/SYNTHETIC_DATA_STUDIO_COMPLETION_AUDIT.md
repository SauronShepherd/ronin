# Synthetic Data Studio — completion audit

Estado: **100% del alcance Community local**.

## Evidencia ejecutable

```text
pytest -q tests/test_synthetic_data.py tests/test_synthetic_data_plugin.py \
  tests/test_synthetic_data_async.py tests/test_synthetic_data_publication.py \
  tests/test_synthetic_data_persistence.py \
  tests/test_synthetic_data_public_surface.py \
  tests/integration/test_workspace_project_http_api.py::test_govern_studio_routes_execute_through_real_http_server
38 passed

node --check web/js/synthetic-data-studio.js
python tools/architecture_gate.py
```

La UI también fue verificada con Chromium headless: el formulario de generación,
el buscador del catálogo y la carga del módulo se renderizan sin errores de
JavaScript.

## Matriz de requisitos

| Área | Evidencia |
|---|---|
| Identidad Synthetic Data Studio | `python/studio_synthetic_data/plugin.py`, manifest y rutas v1 |
| Generación determinista | `tests/test_synthetic_data.py` |
| Validación estructural | `ValidationReport`, claves, nullability, filas y FKs |
| Privacidad | `assess_privacy`, muestra fuente y `review_required` |
| Jobs asíncronos | `async_generation.py`, polling, cancelación, SQLite, claim y heartbeat |
| Catálogo local | `SqliteCatalogStore`, migraciones 001/002 |
| Unity Catalog/Polaris local | `local_catalogs.py`, resolución de namespaces |
| Revisiones y linaje | `publication.py` y rutas de catálogo |
| Exportación | formatos, artifacts y ruta `/export` |
| UI | `web/js/synthetic-data-studio.js` y E2E Chromium |
| Operación | `docs/SYNTHETIC_DATA_STUDIO_OPERATIONS.md` |
| Plan de construcción | `BUILD_PLAN_SYNTHETIC_DATA_STUDIO.md` |
| Frontera Pro | sin conexiones externas en Community; sincronización externa separada |

## Límite explícito

El porcentaje no incluye adaptadores Pro para Databricks, Snowflake, Glue u otros
catálogos externos. Esos conectores requieren credenciales, secretos, workers y
políticas de sincronización fuera del módulo Community local.

Los fallos intermitentes observados en tests generales de workers/autorización de
Ronin no pertenecen al módulo SDS; el conjunto SDS y su integración HTTP pasan.
