# Cloud Studio — Build Plan

**Estado:** MVP técnico iniciado  
**Objetivo:** plugin open-source de Ronin para diseñar, emular y validar topologías cloud localmente, con compatibilidad Terraform/OpenTofu.

## Decisiones base

- Cloud Studio será un plugin vertical, no una modificación del núcleo Ronin.
- `CloudTopology` será el contrato común entre UI, emuladores y exportadores.
- `EmulatorBackend` aislará el núcleo de Floci, LocalStack y futuros backends.
- El backend por defecto será `in-memory`; Floci será el backend externo recomendado.
- LocalStack será opcional y siempre configurable por entorno.
- Terraform se integrará inicialmente mediante HCL + endpoints AWS compatibles; un provider RPC propio queda para una fase posterior.
- La UI será declarativa y podrá evolucionar hacia React Flow sin hacer obligatorio React en el runtime base.

## Fases

### Fase 0 — Fundaciones (completada)

- [x] Manifest y entry point `com.sauronshepherd.ronin.cloud-studio`.
- [x] Catálogo inicial: S3, Lambda, SQS y DynamoDB.
- [x] Modelo `CloudResource` / `CloudTopology`.
- [x] Validación determinista.
- [x] Emulador en memoria.
- [x] Exportación HCL básica.
- [x] UI drag & drop standalone.

### Fase 1 — Backend abstraction (completada)

- [x] Contrato `EmulatorBackend`.
- [x] Backends `in-memory`, `floci` y `localstack`.
- [x] Configuración por `RONIN_CLOUD_STUDIO_BACKEND` y `RONIN_CLOUD_STUDIO_ENDPOINT`.
- [x] Compose reproducible para Floci y LocalStack.
- [x] Configuración Terraform con endpoints locales.

### Fase 2 — Runtime de emulación (en progreso)

- [ ] Sustituir la delegación externa por un cliente HTTP real con timeouts, health checks y errores RFC 9457.
- [x] Crear ciclo `plan → apply → refresh → destroy` para el backend in-memory.
- [x] Persistir snapshots JSON atómicos por workspace.
- [ ] Añadir aislamiento por proyecto/tenant y límites de recursos.
- [x] Health/readiness real con timeout y errores para backends HTTP.
- [x] Smoke test manual contra Floci en Docker (contenedor healthy, endpoint HTTP 200).
- [x] Terraform `init`, `validate`, `apply` y `destroy` verificados contra Floci con AWS provider 6.65.0.
- [x] Backend externo ejecuta `plan/apply/refresh/destroy` mediante Terraform CLI con workspace aislado.
- [x] Timeout, captura de stdout/stderr y `TF_PLUGIN_CACHE_DIR`.
- [x] Selección Terraform/OpenTofu mediante `RONIN_CLOUD_STUDIO_IAC`.
- [x] Rechazo de traversal y aislamiento por workspace de snapshots/state.
- [x] Crear matriz de compatibilidad por servicio y backend.

### Fase 3 — Terraform/OpenTofu

- [ ] Generar `provider.tf`, recursos y variables a partir del grafo.
- [x] Importar el subconjunto HCL escalar generado por Cloud Studio mediante parser controlado.
- [ ] Probar `init`, `validate`, `plan` y `apply` contra Floci en CI.
- [ ] Añadir state local aislado por workspace.
- [ ] Evaluar un `terraform-provider-cloud-studio` RPC separado sólo si el export/endpoints no cubre los casos de uso.

### Fase 4 — Diseñador visual (MVP operativo)

- [x] Canvas con nodos, edges SVG y auto-layout por dependencias.
- [x] Canvas con nodos, edges y selección.
- [x] Inspector de propiedades básico.
- [x] Validación visual y navegación de errores básica.
- [x] Undo/redo e import/export JSON.
- [x] Zoom 50–200%, auto-layout inicial y navegación básica por teclado.
- [x] Auditoría web verifica render de edges SVG y cálculo de layout.
- [x] Auditoría automatizada de superficie web, controles accesibles, handlers y sintaxis.
- [x] Browser end-to-end headless sobre la superficie visual standalone.
- [x] Import/export JSON de topologías.
- [x] Layout automático y vistas por proveedor/servicio (catálogo/backend metadata).
- [ ] Tests de accesibilidad y rendimiento.

### Fase 5 — Calidad y distribución

- [x] Contract tests contra Terraform y AWS-wire-compatible Floci.
- [ ] Tests de compatibilidad Floci/LocalStack por servicio.
- [x] Security review de credenciales, endpoints y ejecución de contenedores.
- [x] Documentación de contribución de nuevos recursos y backends.
- [x] Publicación como paquete plugin independiente del wheel Ronin.

## Criterios de aceptación del MVP

1. Ronin arranca con Cloud Studio sin Floci, LocalStack ni credenciales externas.
2. Una topología visual se puede validar y exportar a HCL.
3. La misma topología puede apuntar a Floci o LocalStack sólo cambiando configuración.
4. Terraform/OpenTofu puede usar endpoints localhost y credenciales mock.
5. Ningún token o secreto aparece en código, fixtures, logs o artefactos generados.
6. El plugin puede desactivarse sin romper el host.

## Riesgos

- La compatibilidad de un emulador no implica paridad con el proveedor real.
- La configuración de endpoints AWS varía por versión del provider.
- Importar HCL arbitrario requiere límites claros; no se debe ejecutar código durante parsing.
- LocalStack puede cambiar disponibilidad, licencia o requisitos de autenticación; por eso no es dependencia obligatoria.

## Próximo hito recomendado

Implementar el cliente HTTP real de `EmulatorBackend`, health/readiness y el ciclo `plan/apply/refresh/destroy`, empezando por Floci y cubriendo S3, SQS y DynamoDB con Terraform en CI.
