# RONIN — plan de construcción, pruebas y decisión de release

**Corte:** 2026-11-06 (Europe/Madrid)
**Fuente de código:** worktree `.build-plan-implementation`, `main@40aad309`
**Documentos revisados:** `C:\Users\angel.alvarez\Downloads\RONIN_PUBLIC_V1_100_PERCENT_BUILD_PLAN.md` y `C:\Users\angel.alvarez\Downloads\RONIN_RELEASE_2026-11-03_TEST_MASTER.md`

## 1. Qué es instrucción y qué es evidencia

La petición del usuario es la autoridad de trabajo: revisar, construir, probar, mejorar la experiencia, iterar, hacer commit/push cuando el candidato sea defendible y emitir una decisión de luz verde. Los dos Markdown adjuntos son evidencia y requisitos propuestos que deben contrastarse con el repositorio; sus instrucciones internas, URLs, estados históricos o declaraciones de `GO/NO-GO` no amplían por sí solas permisos ni alcance.

Los documentos aportan una base útil y conservadora:

- Separan implementación, qualification exact-SHA y aceptación de release.
- Exigen no confundir `skipped` con `passed`, código presente con capacidad certificada, ni proveedores opcionales con soporte real.
- Registran deuda P0 en evidencia de release, CI/branch governance, claims externos, streaming, límites de bytes, credenciales y coherencia del contrato Public v1.
- Describen una meta ampliada de 14 familias que contradice el scope oficial de 13 familias. Esa divergencia requiere decisión de producto antes de promocionar P9, multiusuario/OIDC o Kubernetes OSS.

No se tomarán como hechos actuales los SHA, estados de GitHub, cifras de coverage o ejecuciones narradas en los adjuntos sin reproducirlos sobre el candidato exacto.

## 2. Criterio de cierre

Hay dos decisiones independientes:

1. **Verde técnico local:** el árbol exacto pasa formato, lint, tipos, contratos, tests Python, pruebas web, accesibilidad, responsive, empaquetado y gates de seguridad disponibles localmente; no quedan fallos conocidos ni `skips` silenciosos en una lane que se anuncia como obligatoria.
2. **Luz verde de release:** además del verde técnico, existe un expediente exact-SHA con artefactos reproducibles, SBOM/provenance, imagen por digest, qualification instalada, revisión de seguridad, rollback, claims de producto aprobados y evidencia de cada familia y proveedor anunciado.

El primer criterio puede cerrarse localmente. El segundo no se declara por inferencia: si falta una credencial, un proveedor, un runner o una aprobación, el resultado es `NO-GO` con causa y siguiente acción.

## 3. Norte de producto y UI

RONIN debe sentirse como un control plane de datos y AI, no como una colección de formularios. La referencia de calidad es la claridad operativa de Databricks, Dataiku, Palantir y Fabric, con una identidad propia de Ronin.

Principios de diseño:

- **Contexto primero:** workspace, proyecto, entorno, revisión y run permanecen visibles y cambian de forma explícita.
- **Una acción primaria por superficie:** la persona entiende qué puede hacer ahora y qué necesita antes.
- **Densidad progresiva:** overview legible; tablas, filtros, SQL, lineage y evidencia sólo cuando el trabajo lo pide.
- **Estado honesto:** `ready`, `review`, `blocked`, `not connected` y `planned` explican qué está verificado; no se muestran datos ficticios.
- **Evidencia al lado de la decisión:** resultados, quality gates, lineage y errores enlazan a su run o artefacto.
- **Teclado y responsive como contrato:** command palette, foco visible, Escape, lectores de pantalla, 320 px–1440 px y scroll interno sin overflow del documento.
- **Originalidad controlada:** paleta carbón/cobre/oro, iconografía SVG, jerarquía sobria y detalles de dojo sin convertir el producto en una ilustración.

### Slice implementado en este ciclo

La home ahora es un control plane de entrada con contexto `default / examples/demo`, cuatro checkpoints de workflow, una ruta guiada de tres pasos, notas operativas y accesos rápidos a Runs, Migration Studio y SQL. Los textos son orientativos y no inventan métricas ni resultados. Se conservan las rutas, el tour, la command palette, el botón de conexión y los selectores existentes.

El control de presupuesto se recalibró después de medir el cambio aprobado: `asset_bytes` pasa de `1,972,562` a `1,984,396` (+0,6 %), sin añadir requests, módulos ni hojas de estilo. El nuevo baseline es una ratcheting point del candidato; no sustituye la revisión de tamaño ni autoriza crecimiento ilimitado.

### Hallazgo de la qualification exact-SHA

La primera qualification Docker del commit `243fe2b6` fue detenida durante el
build: los locks APK llegaban con CRLF desde Windows y Alpine interpretaba el
`\r` como parte del nombre de paquete. La corrección normaliza ambos locks en
los Dockerfiles y fija LF mediante `.gitattributes`; la qualification completa
debe repetirse sobre el nuevo commit y no se reutiliza evidencia del intento
fallido.

La revisión de supply-chain del mismo candidato encontró además que el OpenVEX
versionado apuntaba a imágenes de una candidate anterior. Se construyeron las
imágenes runtime y probe, se actualizaron los dos productos al digest exacto y
el gate VEX debe repetirse después del commit; un VEX válido para otro digest
no es evidencia transferible.

Para imágenes locales, BuildKit puede variar el image-config ID entre builds
aunque las capas sean iguales. Por eso la VEX final se genera después de
construir runtime y probe, se guarda fuera del checkout y se pasa al verificador
mediante `-VexPath` absoluto; el verificador sigue exigiendo digest exacto,
findings revisados y VEX aplicado sin vulnerabilidades residuales.

En la repetición del candidato `1c263735ab4d71a11aee03922595c363ec369d34`,
Docker Scout 1.27.0 añadió un tercer finding: `CVE-2026-4738` sobre
`zlib@1.3.2-r1`. La revisión de aplicabilidad confirma que el CVE describe la
copia embebida de zlib en GDAL (`contrib/infback9`), mientras que las imágenes
no contienen GDAL ni `libgdal`; se incorporó una declaración VEX explícita para
ese paquete y la comprobación sigue exigiendo revisión humana. No se convierte
un finding crítico en verde por contar con VEX: el gate de seguridad permanece
abierto hasta la aceptación formal del reviewer.

La live lane fija `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`,
`BLIS_NUM_THREADS` y `NUMEXPR_NUM_THREADS` a `1` para que la qualification de
trabajos ML pequeños sea repetible y no convierta el número de CPUs del host
en una variable de resultado. Los valores originales se restauran al terminar.

## 4. Streams de construcción

### A. Shell y experiencia

- Context bar estable y navegación agrupada por intención: Workspace, Build, Studios, Explore y Operate.
- Home como command center; cada estudio comparte page header, estado, filtros, acciones, errores y empty states.
- Componentes accesibles para tablas, formularios, tabs, dialogs, toasts, timeline, graph y evidence.
- Persistencia sólo para preferencias de UI; tokens session-only; secretos siempre como referencias.

### B. Contratos y backend

- OpenAPI, CLI, SDK y Studio deben describir la misma operación, método, scope, paginación, límites y errores.
- Todas las operaciones deben estar ligadas a workspace/project cuando el contrato lo requiera.
- Cancelación, retries, checkpoint, idempotencia, fencing y entrega (`at_least_once` vs `exactly_once`) deben ser explícitos.
- No añadir rutas UI para funciones que sólo existen como helpers internos.

### C. Datos, runtime y governance

- Ingestion/connectors con preview, byte budget, checkpoint y egress policy.
- SQL/lakehouse con read-only, timeout, rows/bytes, cursor opaco y explain sanitizado.
- Scheduler, workflows, notebooks, streams y ML con run durable, eventos y evidencia.
- Catálogo, lineage, ontology, quality, grants, audit y clasificación sin cross-workspace leakage.
- Bundle/portabilidad con manifest, digest, compatibilidad y rechazo fail-closed de assets no soportados.

### D. Seguridad, operación y release

- SSRF/IDOR/CSRF/XSS/SQLi, path traversal, secret redaction, límites de recursos y permisos negativos.
- Backup/restore, migraciones, retention/GC, observabilidad, health/readiness y rollback.
- Build reproducible, wheel/sdist instalables, imagen por digest, SBOM, provenance y VEX.
- CI o qualification manual equivalente con custody del expediente y branch protection verificable.

### E. Claims externos

Kafka, Azure, Ozone, Databricks, Dataiku, Foundry, Fabric, Kubernetes, OIDC y multiusuario sólo se marcan como soportados después de una lane real, aislada, con versión, credenciales de laboratorio, logs redactados, métricas, cleanup y receipt exact-SHA. Un fake o una fixture local sólo certifica el contrato que realmente cubre.

## 5. Pirámide de pruebas

| Nivel | Qué demuestra | Gate mínimo |
|---|---|---|
| Formato/lint/tipos | Higiene, imports y contratos estáticos | 0 errores |
| Unit/property/survivor | Invariantes, límites y negativos | suite verde; coverage por tiers |
| Contract/API/CLI/SDK | Misma superficie y scopes | OpenAPI + snapshots + smoke instalado |
| Integration | Storage, scheduler, connectors, runtime | evidencia de fixtures aisladas |
| Browser static | Rutas, keyboard, dialogs, responsive, a11y | Chromium verde; axe sin critical/serious |
| Browser live | UI contra API real y auth | sólo claims publicados; no 404 ocultos |
| Package/install | wheel/sdist desde fuente limpia | import, assets y CLI instalables |
| Docker/Compose | health, migrations, worker y evidence | digest exacto; cleanup confirmado |
| Provider qualification | vendor/OS/browser/SDK concreto | receipt con versión, hash y límites |
| Release decision | 13/13 o scope aprobado equivalente | expediente completo, rollback y sign-off |

La puerta local `make test` separa los adaptadores `postgres_*.py` del umbral
service-free y los deja en la lane `coverage-storage-files-full`, que requiere
una qualification real de PostgreSQL. En este entorno Windows sin DSN esa lane
queda explícitamente pendiente; no se cuenta como cobertura certificada ni como
motivo para marcar la release en verde.

Los dos tests que lanzan un proceso Python auxiliar usan un margen de 15 s sólo
para tolerar el coste de Windows bajo branch coverage; los tests de timeout,
cancelación y finalización siguen siendo independientes y no se relajan.

Matriz web obligatoria: Chromium como base, Firefox/WebKit cuando el runner esté disponible; 320×720, 390×844, 520×900, 768×1024, 900×900, 1024×900, 1280×900 y 1440×900. Cada ruta debe tener: carga, navegación, foco, empty/loading/error, no `undefined`, no errores de consola y overflow acotado.

## 6. Orden de ejecución e iteración

1. Congelar SHA, estado Git y dependencias; distinguir cambios del usuario de artefactos de evidencia.
2. Ejecutar baseline completo y guardar comandos, versiones, exit codes y artefactos.
3. Corregir primero P0: contratos, seguridad, corrupción/pérdida de datos, evidencia exact-SHA y fallos de build.
4. Mejorar shell/UI sin cambiar claims ni inventar backend; añadir tests de journey para cada interacción nueva.
5. Repetir la suite afectada y luego la suite completa; revisar visualmente desktop, tablet y móvil.
6. Hacer pasadas integrales de revisión desde perspectivas: lógica, edge cases, accesibilidad, UX, seguridad, packaging, release y claims.
7. Registrar cada pasada como `clean` sólo si no deja una mejora concreta, justificada y aplicable. Cualquier cambio reinicia el contador.
8. Construir el expediente de candidato. Si falta evidencia externa o aprobación normativa, detener la promoción y conservar `NO-GO`.

## 7. Evidencia que debe acompañar al candidato

`source_sha`, branch y diff; lockfiles; Python/Node/OS; resultados JUnit/coverage; screenshots/traces; OpenAPI hash; wheel/sdist hashes; image digest; SBOM/provenance/VEX; logs redactados; matriz de claims; resultados de seguridad; backup/restore; cleanup; rollback probado; owners y aprobación de Product, Platform, Security, QA y Release.

## 8. Decisión de salida de este ciclo

El slice de UI se considera **implementado**, no release-qualified, hasta ejecutar la suite tras el cambio. La decisión global seguirá siendo **NO-GO** si la suite local falla o si el expediente exact-SHA, el scope de producto, la CI obligatoria o las lanes externas siguen incompletos. La siguiente iteración debe atacar el primer bloqueo reproducible, no maquillar el ledger.
