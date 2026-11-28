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

## AWS Emulator: segundo backend de referencia (decision 13-11-2026)

**Aprobado como referencia secundaria, no como implementacion runtime.**
[aws/aws-emulator](https://github.com/aws/aws-emulator) se incorporara como
segundo backend de referencia. **Floci permanece como backend externo actual
para todas las pruebas Docker/S3/Terraform** y conserva sus fixtures sin
modificacion. El backend por defecto continua siendo in-memory; LocalStack
continua opcional. No anunciar AWS Emulator como soporte operativo todavia.

**Criterio de sustitucion:** NO reemplazar Floci ni cambiar la preferencia
hasta demostrar, en el mismo SHA, que AWS Emulator pasa el **100 % de los
escenarios obligatorios ya aprobados en Floci**, sin skips ni fallos, con
comportamiento equivalente o superior de errores, retries, aislamiento,
limpieza, recuperacion y Terraform/OpenTofu; consumos en presupuesto,
rollback probado y ADR/PR aprobada. Si falla cualquier gate, Floci sigue.
Ningun emulador acredita por si mismo compatibilidad con AWS real ni sirve
para certificar seguridad/produccion.

| Fase | Objetivo / contratos | Dependencias | Aceptacion | Estado |
| --- | --- | --- | --- | --- |
| AWS-0 | Documentar seleccion y preservacion Floci | ninguna | Decision y restricciones registradas | documentada |
| AWS-1 | Compose oficial/version fijada, TLS, telemetria off | AWS-0 | Arranque local, endpoint fiable y cleanup; sin AWS real | missing |
| AWS-2 | Adaptador opcional en backends.py; sin cambiar defaults | AWS-1 | Seleccion aws-emulator, credenciales mock, contratos UI/API | missing |
| AWS-3 | S3/ML/SQS/DynamoDB/Lambda, IaC por operacion | AWS-2 | Matriz con pruebas reales, fallos y limites reportados | missing |
| AWS-4 | Comparador Floci vs AWS y decision de preferencia | AWS-3 y VER | 100 % casos Floci, cero skips obligatorios, rollback | blocked |
| AWS-VER | Tests, CI, supply chain, licencias, recibos exact-SHA | AWS-1..4 | Gates remotos verdes, separados de implementacion | missing |

La telemetria de AWS Emulator esta activa por defecto: en tests usar
EMULATOR_TELEMETRY=off; verificar certificados TLS sin desactivar su
validacion globalmente. Revisar CC0-1.0 y Apache-2.0 (vendor/) antes de
redistribucion; fijar releases/digests. La adaptacion sera opcional: solo
se anunciara capacidad por servicio/operacion despues de su conformance.

**Proceso por fase:** implementar -> probar -> si falla corregir y repetir ->
solo tras PASS hacer commit/push autorizado y validar CI remota -> informar
porcentaje global RPV1 y cualificacion release separada. Esta decision no
cierra ninguna de las 91 RPV1 ni modifica 0/13 familias NO-GO.

Especificacion: [AWS Emulator reference](docs/architecture/CLOUD_STUDIO_AWS_EMULATOR_ADOPTION.md).

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

- [x] Sustituir la delegación externa por un cliente HTTP real con timeouts, health checks y errores RFC 9457.
- [x] Crear ciclo `plan → apply → refresh → destroy` para el backend in-memory.
- [x] Persistir snapshots JSON atómicos por workspace.
- [x] Añadir aislamiento de estado por workspace y límites deterministas de recursos.
- [ ] Añadir aislamiento multiusuario/tenant de producción (fuera del alcance local actual).
- [x] Health/readiness real con timeout y errores para backends HTTP.
- [x] Smoke test manual contra Floci en Docker (contenedor healthy, endpoint HTTP 200).
- [x] Terraform `init`, `validate`, `apply` y `destroy` verificados contra Floci con AWS provider 6.65.0.
- [x] Backend externo ejecuta `plan/apply/refresh/destroy` mediante Terraform CLI con workspace aislado.
- [x] Timeout, captura de stdout/stderr y `TF_PLUGIN_CACHE_DIR`.
- [x] Selección Terraform/OpenTofu mediante `RONIN_CLOUD_STUDIO_IAC`.
- [x] Rechazo de traversal y aislamiento por workspace de snapshots/state.
- [x] Crear matriz de compatibilidad por servicio y backend.

### Fase 3 — Terraform/OpenTofu

- [x] Generar `provider.tf`, recursos y variables a partir del grafo.
- [x] Importar el subconjunto HCL escalar generado por Cloud Studio mediante parser controlado.
- [x] Probar `init`, `validate`, `plan` y `apply` contra Floci en CI.
- [x] Añadir state local aislado por workspace.
- [x] Evaluar un `terraform-provider-cloud-studio` RPC separado sólo si el export/endpoints no cubre los casos de uso.

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
- [x] Tests de accesibilidad y rendimiento.

### Fase 5 — Calidad y distribución

- [x] Contract tests contra Terraform y AWS-wire-compatible Floci.
- [x] Tests reales de compatibilidad Floci y LocalStack para el subconjunto S3/SQS
  habilitado por los perfiles fijados; la matriz completa de servicios permanece pendiente.
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
