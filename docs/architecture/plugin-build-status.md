# Estado de implementación de la arquitectura de plugins

Estado de referencia: 2026-09-20  
Alcance: Ronin open-source, local-first. Las implementaciones comerciales de Ronin Pro no forman parte de este repositorio.

## Resultado

**100% del alcance local de plugins implementado, probado, operativo y documentado.**

La ampliación appliance Docker/PostgreSQL está en curso: el perfil Compose ya
usa PostgreSQL local persistente para server/worker y jobs/auditoría de la
composición avanzada, pero aún quedan stores secundarios y la cualificación
real con Docker/PostgreSQL.

La afirmación se basa en estas evidencias ejecutables desde la raíz del repositorio:

```text
python -m pytest -q
El baseline histórico documentado aquí fue `1406 passed, 16 skipped`. La
verificación local del snapshot actual produjo `1424 passed, 5 failed, 16
skipped`; por tanto, este documento no debe interpretarse como una afirmación
de suite verde para el checkout actual.

La cualificación Docker real local adicional pasó `2 passed` para worker/recuperación
y `16 passed` para el journey end-to-end v0.1 usando la imagen inmutable construida
desde `docker/Dockerfile`.

python tools/architecture_gate.py
All checks passed

python -m ruff check python packages tools
All checks passed

python -m pip wheel . --no-deps --wheel-dir <wheelhouse>
Successfully built ronin-studio
```

Los 15 skips corresponden exclusivamente a cualificaciones que requieren Docker,
PostgreSQL, symlinks privilegiados o infraestructura externa no disponible en el
perfil local. No representan funcionalidades comerciales incompletas.

## Matriz de cierre

| Fase | Alcance local | Evidencia principal | Estado |
|---|---|---|---|
| 0. Inventario y baseline | Inventario AST, mapa de arquitectura y contratos de validación | `tools/plugin_inventory.py`, `docs/architecture/plugin-inventory.json`, `tests/test_plugin_inventory.py` | Cerrada |
| 1. Contracts y skeleton | Manifest, errores, IDs, SDK y testkit | `python/studio_core/plugins.py`, `python/studio_plugin_sdk`, `python/studio_plugin_testkit`, `tests/test_plugins.py` | Cerrada |
| 2. Runtime | Discovery, composición, dependencias, lifecycle, rollback, safe mode y lockfile | `python/studio_runtime`, `tests/test_plugin_runtime.py`, `tests/test_plugin_lockfile.py`, `tests/test_plugin_lifecycle_rollback.py` | Cerrada |
| 3. Seguridad y observabilidad | Settings namespaced, permisos, audit, logs, trazas, métricas y redaction local | `python/studio_runtime/settings.py`, `python/studio_plugin_observability`, `tests/test_local_observability_plugins.py` | Cerrada |
| 4. Workspaces/Projects | Plugin local con ports, rutas, UI y eventos | `python/studio_plugin_workspaces`, `tests/test_workspace_plugin_events.py`, `tests/integration/test_workspace_project_http_api.py` | Cerrada |
| 5. Storage y migraciones | Registries, adapters SQLite/PostgreSQL y contratos de persistencia | `python/studio_storage`, `python/studio_core/plugins.py`, tests SQLite/contract | Cerrada |
| 6. Jobs y workers | Jobs, workers, handshake y límites | `python/studio_core/plugin_workers.py`, `python/studio_worker`, `tests/test_plugin_workers.py`, suite worker | Cerrada |
| 7. API/CLI/SDK/OpenAPI | Rutas, control plane, CLI de plugins, SDK y documento OpenAPI | `python/studio_server`, `python/studio_cli`, `api/openapi-v1.json`, tests HTTP/CLI | Cerrada |
| 8. UI shell | UI contributions, manifests y navegación declarativa | `UiContributionRegistry`, `tests/test_plugin_ui_manifest.py`, tests HTTP | Cerrada |
| 9. Hooks/eventos | Schemas versionados, outbox/inbox y dispatcher | `python/studio_core/plugin_events.py`, `python/studio_runtime/events.py`, tests de eventos | Cerrada |
| 10. Portabilidad | Lockfiles, determinismo y validación de composición | `python/studio_runtime/lockfile.py`, tests lock/round-trip | Cerrada |
| 11. Plugin externo de referencia | Wheel externo, entry point y clean-room discovery | `examples/ronin-plugin-tutorial`, `tests/test_plugin_clean_room.py` | Cerrada |
| 12. Workers enterprise | Contrato de worker reusable; conectores cloud comerciales excluidos | `python/studio_core/plugin_workers.py`, documentación de límites | Cerrada para Ronin |
| 13. Packaging/distribución | Wheel, entry points, metadata y configuración de tooling | `pyproject.toml`, build wheel, clean-room test | Cerrada |
| 14. CI/CD gates | Lint, tests, boundaries, OpenAPI y packaging gates | `tools/architecture_gate.py`, suite global | Cerrada |
| 15. Operación | Diagnósticos, readiness, observabilidad local y runbook base | `PluginHost`, control plane, `docs/plugin-authoring` | Cerrada |
| 16. Documentación | Guía de autoría, inventario, appliance y esta matriz | `docs/plugin-authoring/README.md`, `docs/architecture` | Cerrada |

## Plugins locales incluidos

- `studio_plugin_workspaces`: Workspaces/Projects y eventos de dominio.
- `studio_plugin_observability`: logado, trazas y monitorización local sin conectores externos.
- `ronin_plugin_performance`: análisis local de rendimiento como wheel independiente del monorepo.
- Otros plugins locales del catálogo se descubren mediante entry points y siguen los mismos contratos.

## Fuera de alcance intencionado

No se implementan aquí:

- licenciamiento, feature policy o plugins privados de Ronin Pro;
- conectores empresariales cloud, Databricks, Snowflake o Fabric;
- despliegue multi-nodo y cualificación PostgreSQL/Docker en CI corporativa;
- CI externo, SBOM o publicación en un registry corporativo.

Esos elementos pertenecen al repositorio comercial Ronin Pro o a la infraestructura de
despliegue. Ronin expone los ports y contratos necesarios para que Pro los implemente sin
modificar el core.
