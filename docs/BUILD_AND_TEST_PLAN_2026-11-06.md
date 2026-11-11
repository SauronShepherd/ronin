# RONIN — plan de construcción, pruebas y decisión de release

**Corte:** 2026-11-10 (Europe/Madrid)
**Fuente autoritativa actual:** candidato runtime/test exacto `16dbe56ee773f9aee698de63cb193ce8d3695109`; `main` actual `3bb4a09e` es un descendiente documental sin cambios de runtime. Las evidencias de esta ficha se refieren al candidato `16dbe56e`, salvo cuando se indique expresamente una ejecución anterior o un snapshot limpio distinto. La qualification técnica se separa de la decisión de release: las lanes técnicas del candidato están verdes, pero licencia, revisión humana, familias, claims, soporte, rollback y gobierno siguen abiertos.
**Documentos revisados:** `C:\Users\angel.alvarez\Downloads\RONIN_PUBLIC_V1_100_PERCENT_BUILD_PLAN.md` y `C:\Users\angel.alvarez\Downloads\RONIN_RELEASE_2026-11-03_TEST_MASTER.md`

## 0. Cualificación exacta actual — candidato `16dbe56e`

El candidato runtime/test exacto está verde en las lanes locales ejecutadas:
Chromium `147/147`, regresión Python web/release `27 passed`, auditoría web sin
fallos, budget `2,132,739` bytes, route consistency `196 operations`, capability
status y OpenAPI snapshot válidos. Docker/Helm y el snapshot limpio de
infraestructura están documentados por separado y permanecen ligados a sus
SHA/digests propios; no se mezclan con esta ficha. Resultado de release:
**NO-GO**. El ledger permanece en `0/13` familias y siguen abiertos los gates de
proveedores/credenciales, seguridad/VEX, legal/NOTICE/claims, licencias,
revisión visual manual, rollback/backup, soporte y gobierno de CI/branches.

## 0.1 Plan de cierre obligatorio para la siguiente iteración

Este resultado no se convierte en GO repitiendo las mismas pruebas técnicas. El
siguiente ciclo debe cerrar los bloqueos por separado sobre un nuevo candidato
congelado y conservar una relación unívoca `commit → artefactos → imagen →
recibos → decisión`:

1. **Congelar identidad y release bundle.** El release operator debe elegir
   versión pública, rama/tag, política de freeze, matriz de plataformas y
   manifest agregado; debe rehashear wheel, sdist, imagen, SBOM, provenance,
   VEX y cada archivo del bundle en una única receipt. La identidad técnica
   actual ya valida wheel/sdist, TAR runtime/probe, SBOM crudo, SBOM de
   aplicación, provenance y dos inventarios CycloneDX; falta convertirla en
   bundle de release aprobado y congelar branch/tag. PASS sólo si el
   verificador rechaza cualquier mezcla de SHA, digest, tag o perfil.
2. **Cerrar seguridad de imagen.** Revisar el inventario Trivy de las imágenes
   exactas, resolver o aceptar formalmente el `CVE-2026-4738` de zlib y explicar
   la diferencia entre el matching de VEX por digest y el escaneo de TAR; obtener
   aceptación explícita del security reviewer para las tres declaraciones VEX.
   PASS sólo con findings críticos/altos triageados, el hallazgo medio con una
   decisión documentada y `container_image_inventory` no vacío o una excepción
   formal firmada.
3. **Cualificar las 13 familias Public v1.** Para P1–P8 y P10–P14, completar
   journey de usuario, API/SDK, negativo, persistencia y evidencia del mismo
   candidato; probar cada proveedor que se vaya a anunciar con credenciales
   separadas, y mantener P9 fuera de scope. Un `implemented` o una ruta que
   carga no cuenta como familia cualificada.
4. **Cerrar recuperación operacional.** Ensayar upgrade, rollback y restore
   externo de PostgreSQL, datos locales y object store en el candidato final;
   registrar tiempos, checksums, pérdida aceptable, fallo intermedio y cleanup.
   PASS sólo si el runbook reproduce el resultado desde un entorno limpio.
5. **Cerrar claims, licencias y soporte.** El maintainer debe firmar versión,
   claims, NOTICE/licencias, OS/Python/Docker/Compose/Kubernetes soportados,
   límites de proveedores y política de soporte. No inferir aprobación legal o
   de soporte a partir de tests automáticos.
6. **Pasada manual de producto y UX.** Revisar desktop/tablet, teclado/foco,
   contraste, densidad, errores, carga vacía y estados de operación en todas
   las superficies. Para alcanzar la referencia Databricks/Dataiku/Palantir/
   Fabric, la siguiente construcción debe unificar navegación, objetos,
   author/connect/operate/govern, lineage/evidence y progressive disclosure:
   una acción principal por pantalla, contexto visible, guardrails antes de
   ejecutar y recuperación clara después de cada error. La aceptación debe
   conservar la identidad original charcoal/copper/gold de Ronin y registrar
   capturas, defectos, viewport y resolución.
7. **Recalificar y decidir.** Repetir Python/PostgreSQL, estático, auditoría,
   budget, artefactos, Docker, Helm, live, VEX y supply chain en el mismo SHA;
   actualizar ledger y plan; hacer una revisión inferior independiente; y
   marcar GO sólo si las 13 familias y todos los gates obligatorios están
   cerrados. Si queda un solo blocker, publicar NO-GO con su owner y evidencia,
   nunca compensarlo con una métrica técnica verde.

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

La iteración del 2026-11-07 hizo accionable ese shell: el context bar abre un diálogo accesible para cambiar workspace, proyecto, entorno y runtime; el contexto queda en la URL, se conserva al navegar y se sincroniza con los formularios de la superficie activa. La selección de workspace/proyecto desde las listas también actualiza el contexto canónico. La home incorpora actividad reciente real y acotada por proyecto, con estados loading/empty/error honestos y enlace directo al run. La command palette ya navega al hacer click en una opción y el shell compacto permanece usable a 320 px.

La iteración del 2026-11-08 convirtió Run detail en un espacio de decisión operativo: brief derivado del estado durable, identidad y failure code visibles, resumen de salud de evidencia, timeline con secuencia/intento/timestamp y tabla de referencias con disponibilidad, digest truncado, media type y celda. No se expone el locator privado de almacenamiento ni se infiere éxito por ausencia de evidencia. El journey Playwright usa ahora el contrato público real y cubre el cambio entre Summary, Evidence y Events.

La iteración del 2026-11-08 también convirtió Catálogo en un workbench gobernado: registro de activos con búsqueda por nombre/tag/clasificación, selección que prepara lineage, mapa source→target con versión/operación/mode/run, respuesta raw colapsable, glosario consultable y estados loading/error/empty honestos. La interacción conserva el alcance de workspace y evita inventar activos o términos.

La segunda pasada del 2026-11-08 convirtió Semantic Studio en un workbench de decisión: registro de modelos, dashboard con acciones explícitas, nota operativa, portabilidad Bundle separada y laboratorio de consultas/composición. Conserva los contratos API, la revisión digest-bound y el límite de 700 KiB, pero evita presentar cinco formularios planos como si fueran una experiencia de producto.

La tercera pasada del 2026-11-08 convirtió Scheduler Studio en un control plane de operaciones: contexto de workspace/schedule/workflow/run visible, acciones agrupadas en Observe/Change/Execute/Recover, resultado de operador separado y ruta de recuperación presentada como primera clase. Se conservan los endpoints, payloads, idempotencia, cancelaciones y backfills existentes.

La cuarta pasada del 2026-11-08 convirtió Quality Studio en un workbench de decisión: postura de gate visible, alcance de workspace/asset/version separado de la autoría del contrato, playbook de tres pasos, KPI de decisión/latest run/rule evidence, tabla de evidencia y timeline histórico inmutable. Se preservan los selectores y APIs existentes (`Load contract`, `Save contract`, `Dry-run rows`, enforcement blocking) y se añadió una regresión de estado simulado, guardado/carga, postura y responsive a 390 px. La hoja de estilo propia queda fuera de `components.css` para mantener el límite estructural de 400 líneas.

La quinta pasada del 2026-11-08 convirtió Data Engineering en un workbench de decisión: hero con límites explícitos, modos Query/Compose/Observe, SQL bounded con historial/exportación, pipeline versionado con validación/preview/run/inspect y observabilidad separada. Se conservaron los IDs, payloads y APIs existentes, incluido el editor visual de nodos/aristas, y se añadió una regresión específica de modos, alcance y responsive a 390 px. El objetivo es que el operador entienda el siguiente paso antes de encontrarse con el formulario completo.

La sexta pasada del 2026-11-08 convirtió Ingestion Studio en un workbench de decisión: hero con la frontera de escritura, navegación Discover/Preview/Sync/Observe, callouts de seguridad, definición JSON compartida, handoff explícito al worker y evidencia/lineage separados. Se conservaron todos los IDs, payloads, acciones y contratos live existentes; una regresión de journey comprueba la nueva jerarquía y la suite completa conserva accesibilidad y responsive.

La séptima pasada del 2026-11-08 convirtió ML Studio en un workbench de decisión: el flujo se organiza en Lab/Qualify/Govern/Serve, con contexto de workspace, acciones de refresco, preparación de calidad, comparación, registro, promoción, revisión y despliegue. Se conservaron los IDs, formularios, contratos, handlers de runtime e inyecciones dinámicas existentes; la regresión focalizada verifica la jerarquía, las rutas de decisión y la accesibilidad. La interfaz ahora comunica el siguiente paso operativo sin ocultar los controles avanzados.

La octava pasada del 2026-11-08 convirtió Workspaces en un workbench de decisión: la entrada de la plataforma se organiza en Observe/Create/Govern, con contexto de workspace, inventario honesto, creación idempotente y handoff explícito a Projects. Se conservaron los IDs, endpoints, botones de selección/archivo, formularios de creación y journey de Bundle/permisos/operación; la regresión añade accesibilidad Axe, scroll de modos y responsive a 390 px. El control plane ahora explica la frontera operativa antes de mostrar las acciones avanzadas.

La novena pasada del 2026-11-09 convirtió Projects en un workbench de decisión: Author/Connect/Operate/Govern hace visible la autoría del manifiesto, la conexión de entorno, la ejecución gobernada y los permisos/Bundle. Se conservaron los formularios, IDs, endpoints y contratos live existentes; el journey completo mantiene contexto, binding, operación, permisos, exportación y archive, con regresión responsive a 390 px. Además, el diálogo de conexión obtiene un listener síncrono antes de los módulos pesados para evitar que una navegación rápida deje el botón activo sin panel visible.

La undécima pasada del 2026-11-10 convirtió Environments en un workbench Observe/Author/Govern: el contexto de workspace es explícito, el inventario distingue estados activos y pausados, la autoría conserva campos guiados más definición avanzada, Preview diff usa el contrato real y Govern expone pause/restore. La duodécima pasada convirtió Deployments en Observe/Bind/Operate: los bindings se leen y reemplazan como array validado, el proyecto/entorno quedan visibles y el siguiente paso enlaza con Projects y Runs. Ambas superficies tienen regresión focalizada de jerarquía, responsive a 390 px y Axe sin defectos serious/critical.

La décima pasada del 2026-11-09 añadió al workbench de Projects un brief operativo antes de los formularios: métricas de proyectos visibles, postura de fuente (`Unconfigured`, `Declared` o `Mixed`), siguiente gate (`Author` o `Use context`) y columna Source derivada sólo de adapter/default_ref, sin exponer URI ni secretos. El estado vacío/error se mantiene honesto (`Unknown`/`Review error`) y el journey móvil verifica la jerarquía a 390 px.

El control de presupuesto se recalibró después de medir los cambios aprobados: `asset_bytes` queda en `2,088,109`, con `67` requests, `36` módulos, `12` hojas de estilo y `5,299` bytes HTML. La regresión de Playwright, la barrida responsive, la auditoría estática y el journey de Projects cubren el cambio; el baseline no autoriza crecimiento ilimitado.

### Verificación histórica del corte UI 2026-11-09

Sobre el árbol UI del candidato `4157181`, la suite web estática completa pasa `132/132` con Chromium; la auditoría web exacta reporta `68` archivos, `38` módulos, `180` invocaciones de ruta y cero fallos, con presupuesto `2,088,109` bytes, `67` requests, `36` módulos, `12` hojas de estilo y `5,299` bytes HTML. Las pruebas responsive de Workspaces/Projects/Data Engineering/Ingestion/ML Studio y las regresiones previas confirman igualdad entre ancho visible y scrollable en 390 px. La qualification live exacta del candidato pasa `33/33`.

### Qualification exact-SHA histórica del candidato runtime `4157181`

El checkout limpio `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-release-4157181` queda ligado al runtime/test `4157181843d47893e77d62bed62fdafeb31d6f0b`; la delta desde `4a6c546` es UI/presupuesto y no contiene Python ni runtime backend.

- Web estática: Chromium `132/132`; auditoría `68` archivos, `38` módulos, `180` invocaciones, `0` fallos; presupuesto `2,088,109` bytes, `67` requests, `36` módulos, `12` hojas de estilo y `5,299` bytes HTML. Recibo reproducible mediante `node web-tests/node_modules/@playwright/test/cli.js test --config web-tests/playwright.config.mjs --grep-invert [Ll]ive --workers=2`.
- Artefactos instalados: `90/90`; wheel `5cf92538ee70f1631bd13c5dcc79cf8a2321cbbbdf2adaea9c4c693b6df9ce8c`, sdist `6873d4d3748e7d1d9a4fbf7cf59a9bdccb0d459ae73bb396dba6c0382a110b24`; identidad exacta `%TEMP%\\ronin-artifact-identity-4157181-release.json`.
- Docker: `27/27`, strict v0.1 `15/15`, cleanup correcto; imagen local `sha256:af76b755b4bf64ef17f1a670d7b35e1e099f8cd8b26b808194446fb30be6755e`.
- Helm/kind: lint, frontera de Secret, cluster aislado, carga de imagen, instalación, readiness, health, Studio/API, job persistente, restart y cleanup pasaron; `%TEMP%\\ronin-helm-4157181-20261109b`.
- Live: `33/33`, `25` rutas activas, `24` API-backed, `247` eventos correlacionados (`232` OK, `15` WARN esperados), `0` errores server/network y `0` gaps inesperados de autorización; `%TEMP%\\ronin-live-4157181-20261109c` (la primera corrida tuvo un timeout de fixture Kafka y fue descartada, con cleanup correcto).
- Seguridad: VEX Docker Scout `1.27.0`: `3` raw, `0` tras OpenVEX exacto para la imagen; `%TEMP%\\ronin-vex-4157181-20261109b`. Trivy no está disponible y no se afirma SBOM de contenedor; el reviewer debe aceptar formalmente las justificaciones.
- Supply chain SDK: SBOM CycloneDX, provenance y resumen de digests verificados para `4157181`; identidad `%TEMP%\\ronin-artifact-identity-4157181-release.json`, SBOM `%TEMP%\\ronin-release-sbom-4157181.json`, provenance `%TEMP%\\ronin-release-provenance-4157181.json` y resumen `%TEMP%\\ronin-supply-chain-4157181.json`. El inventario de contenedor queda vacío por falta de Trivy.
- Python/PostgreSQL: `4562 passed`, `27 skipped`, `0 failed` de `4589` en `%TEMP%\\ronin-python-full-8a85586-20261108`; el diff desde `8a85586` hasta este candidato no toca Python/backend, por lo que este recibo se conserva como evidencia del código ejecutable sin cambios. Los skips son explícitos y están justificados por Docker/servicios opcionales, POSIX/symlinks o proveedores no configurados.

El candidato es técnicamente defendible en las lanes completadas, pero la decisión sigue `NO-GO`: ledger de familias `0/13`, proveedores/credenciales, revisión humana de seguridad/VEX, legal/NOTICE/claims, review visual manual, Trivy/SBOM de contenedor, rollback, Terraform/toolchain y gobierno de CI/branches siguen abiertos.

### Qualification exact-SHA histórica del candidato runtime `1a9fd01`

El checkout limpio `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-release-1a9fd01` queda ligado al runtime/test `1a9fd01ad50f39189389883e7804c6e78c9ac779`; la delta desde `6279ef7` es UI/tests/presupuesto y no contiene Python ni runtime backend.

- Web estática: Chromium `130/130`; auditoría `65` archivos, `37` módulos, `180` invocaciones, `0` fallos; presupuesto `2,069,139` bytes, `64` requests, `35` módulos, `10` hojas de estilo y `5,111` bytes HTML. Recibo reproducible mediante `node web-tests/node_modules/@playwright/test/cli.js test --config web-tests/playwright.config.mjs --grep-invert [Ll]ive --workers=2`.
- Artefactos instalados: `90/90`; wheel `d30de6d1a9b3c2f4ea5f7d505eaf1e4b88c92b8284dcf988f7ea530d69dc362c`, sdist `0c1032f9d0a4bbf9530a1e3b689945e016d360bd99f5c6e3bb28e29f5dcbd50e`; identidad exacta `%TEMP%\\ronin-artifact-identity-1a9fd01.json`.
- Docker: `27/27`, strict v0.1 `15/15`, cleanup correcto; imagen local `sha256:e28c696201dda415668524c3c3cd21b55c3c28979b4574693953bfe65453abcb`.
- Helm/kind: lint, frontera de Secret, cluster aislado, carga de imagen, instalación, readiness, health, Studio/API, job persistente, restart y cleanup pasaron; `%TEMP%\\ronin-helm-1a9fd01-20261108`.
- Live: `33/33`, `25` rutas activas, `24` API-backed, `248` eventos correlacionados (`233` OK, `15` WARN esperados), `0` errores server/network y `0` gaps inesperados de autorización; `%TEMP%\\ronin-live-1a9fd01-20261108`.
- Seguridad: VEX Docker Scout `1.27.0`: `3` raw, `0` tras OpenVEX exacto para la imagen; `%TEMP%\\ronin-vex-1a9fd01-20261108`. Trivy no está disponible y no se afirma SBOM de contenedor; el reviewer debe aceptar formalmente las justificaciones.
- Supply chain SDK: SBOM CycloneDX, provenance y resumen de digests verificados para `1a9fd01`; identidad `%TEMP%\\ronin-artifact-identity-1a9fd01.json`, SBOM `%TEMP%\\ronin-release-sbom-1a9fd01.json`, provenance `%TEMP%\\ronin-release-provenance-1a9fd01.json` y resumen `%TEMP%\\ronin-supply-chain-1a9fd01.json`. El inventario de contenedor queda vacío por falta de Trivy.
- Python/PostgreSQL: `4562 passed`, `27 skipped`, `0 failed` de `4589` en `%TEMP%\\ronin-python-full-8a85586-20261108`; el diff desde `8a85586` hasta este candidato no toca Python/backend, por lo que este recibo se conserva como evidencia del código ejecutable sin cambios. Los skips son explícitos y están justificados por Docker/servicios opcionales, POSIX/symlinks o proveedores no configurados.

El candidato es técnicamente defendible en las lanes completadas, pero la decisión sigue `NO-GO`: ledger de familias `0/13`, proveedores/credenciales, revisión humana de seguridad/VEX, legal/NOTICE/claims, review visual manual, Trivy/SBOM de contenedor, rollback, Terraform/toolchain y gobierno de CI/branches siguen abiertos.

### Qualification exact-SHA histórica del candidato runtime `6279ef7`

El checkout limpio `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-release-6279ef7` queda ligado al runtime/test `6279ef792d41a78a6e022f8193ed70bcf5ff7fc3`; el commit de VEX/documentación posterior actualiza el binding digest-bound sin cambiar la delta de UI. El diff desde `8a85586` no contiene Python ni runtime backend.

- Web estática: Chromium `130/130`; auditoría `64` archivos, `37` módulos, `180` invocaciones, `0` fallos; presupuesto `2,059,874` bytes, `63` requests, `35` módulos, `9` hojas de estilo y `5,050` bytes HTML. Recibo reproducible mediante `node web-tests/node_modules/@playwright/test/cli.js test --config web-tests/playwright.config.mjs --grep-invert [Ll]ive --workers=2`.
- Artefactos instalados: `90/90`; wheel `aa8db3bc80c8356b2a05821655a58a14e8b86a46f9b1d15eab2a1311e70cbdda`, sdist `4ba0f8c5c92a29fcd87b9d18ba838412f080324bb0a718bb5ea30a85596ecc6d`; identidad exacta `%TEMP%\\ronin-artifact-identity-6279ef7.json`.
- Docker: `27/27`, strict v0.1 `15/15`, cleanup correcto; imagen local `sha256:a6771cf1fa7dee4566f6fc298ea89d23ddf31c61233d5e25c3daac985c3e1aca`.
- Helm/kind: lint, frontera de Secret, cluster aislado, carga de imagen, instalación, readiness, health, Studio/API, job persistente, restart y cleanup pasaron; `%TEMP%\\ronin-helm-6279ef7-20261108`.
- Live: `33/33`, `25` rutas activas, `24` API-backed, `252` eventos correlacionados (`237` OK, `15` WARN esperados), `0` errores server/network y `0` gaps inesperados de autorización; `%TEMP%\\ronin-live-6279ef7-20261108`.
- Seguridad: VEX Docker Scout `1.27.0`: `3` raw, `0` tras OpenVEX exacto para la imagen nueva; el reviewer debe aceptar formalmente las justificaciones. Trivy no está disponible y no se afirma SBOM de contenedor. Los recibos Gitleaks/pip-audit del backend sin cambios permanecen ligados al candidato previo `8a85586`.
- Supply chain SDK: SBOM CycloneDX, provenance y resumen de digests verificados para `6279ef7`; el inventario de contenedor sigue vacío y no se confunde con revisión humana.
- Python/PostgreSQL: `4562 passed`, `27 skipped`, `0 failed` de `4589` en `%TEMP%\\ronin-python-full-8a85586-20261108`; el diff `8a85586..6279ef7` no toca Python/backend, por lo que este recibo se conserva como evidencia del código ejecutable sin cambios. Los skips son explícitos y están justificados por Docker/servicios opcionales, POSIX/symlinks o proveedores no configurados.

El candidato es técnicamente defendible en las lanes completadas, pero la decisión sigue `NO-GO`: ledger de familias `0/13`, proveedores/credenciales, revisión humana de seguridad/VEX, legal/NOTICE/claims, review visual manual, Trivy/SBOM de contenedor, rollback, Terraform/toolchain y gobierno de CI/branches siguen abiertos.

### Qualification exact-SHA final del candidato runtime `6012ed52`

El checkout limpio `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-release-6012ed5`,
detached en `6012ed52deb5b5a449abc73944cd21293ac06d33`, queda técnicamente verde
en las lanes locales disponibles:

- Python/PostgreSQL: `4562 passed`, `27 skipped`, `0 failed` de `4589`; recibo
  `%TEMP%\\ronin-python-full-6012ed5-20261108`.
- Artefacto instalado: wheel `pyronin-0.0.1a0-py3-none-any.whl` y sdist
  `pyronin-0.0.1a0.tar.gz` construidos desde el checkout limpio; instalación
  aislada y `90 passed` de los contratos SDK. Digests: wheel
  `8d0b7392c9ec9d2dabe827d1081b23ff00eaaf9662e2406278bffed8e04c6057`, sdist
  `47b997a6dfc2cf58602a219e0bc47f2370e227e7a931110a8cbe3cdabb292d49`.
- Docker: `27/27` casos reales, `0` skips/fallos; aceptación v0.1 estricta
  `15/15`; imagen `sha256:89b122401876ff1b82f06b9e1f20dab3fa077981fb9bf51e264d3bd00d5b6be0`;
  cleanup correcto. Recibo: `%TEMP%\\ronin-docker-6012ed5-20261108`.
- Helm/kind: lint, frontera de Secret, cluster aislado, carga de imagen,
  instalación, readiness, health, Studio/API, job persistente, supervivencia
  tras restart y cleanup; recibo `%TEMP%\\ronin-helm-6012ed5-20261108`.
- Live: `33/33` Playwright, `25` rutas activas, `24` API-backed, `247`
  eventos/calls reales, `0` errores de servidor/red y `0` gaps inesperados de
  autorización; `15` WARN esperados. Recibo:
  `%TEMP%\\ronin-live-6012ed5-20261108`.
- UI estática: Chromium `128/128`; audit web `61` archivos, `37` módulos,
  `180` invocaciones `/v1/`, `0` fallos; presupuesto `2,034,189` bytes,
  `60` requests, `35` módulos, `6` hojas de estilo y `4,871` bytes HTML.
- Seguridad automatizada: Gitleaks `8.30.1` sin leaks en árbol ni historial;
  pip-audit `2.10.1` sin vulnerabilidades conocidas en test, runtime y
  bootstrap. El VEX de release `9b1d16ef` se verificó contra el digest exacto:
  Docker Scout `1.27.0`, `3` findings raw y `0` tras OpenVEX. Trivy no está
  disponible y, por ello, no se afirma inventario SBOM de contenedor.
- Supply-chain SDK: SBOM CycloneDX y provenance generados/verificados para el
  mismo commit y artifact identity; la evidencia de artefactos/SBOM/provenance
  del SDK pasa. Esto no sustituye la revisión de contenedor ni aprobación
  humana de seguridad.

Esta repetición corrige la única discrepancia encontrada en el corte: el VEX
apuntaba al digest anterior. El VEX se actualizó y publicó en `9b1d16ef`, y la
verificación posterior quedó en `%TEMP%\\ronin-vex-6012ed5-20261108-rerun`.
El bloque técnico local queda verde para este runtime, pero el release no:
ledger de familias `0/13`, proveedores/credenciales, revisión humana de
seguridad/VEX, legal/NOTICE/claims, review visual manual, Trivy/SBOM de
contenedor, rollback, Terraform/toolchain y gobierno de CI/branches siguen
abiertos.

### Qualification exact-SHA anterior del candidato `7026cd7c`

El checkout limpio del candidato `7026cd7c65e6581c38a3136bae4336bcc3dd40fc`
queda técnicamente verde en las lanes disponibles localmente:

- Python/PostgreSQL: `4562 passed`, `27 skipped`, `0 failed` de `4589`; los
  skips están razonados por Docker/servicios externos opt-in o limitaciones
  POSIX/Windows y no se cuentan como soporte anunciado. Recibo:
  `%TEMP%\\ronin-python-full-7026cd7-20261108`.
- Docker: `27/27` casos reales, `0` skips/fallos; aceptación v0.1 estricta
  `15/15`; imagen runtime local `sha256:e4d6a39d040e5af9e337328f8521d1e4faf71cf53bf954e79c95e26c28953f52`;
  cleanup correcto. Recibo: `%TEMP%\\ronin-docker-7026cd7-20261108`.
- Helm/kind: lint, frontera de Secret, cluster aislado, carga de imagen,
  instalación, readiness, health, Studio/API, job persistente y supervivencia
  tras restart; cleanup correcto. Recibo: `%TEMP%\\ronin-helm-7026cd7-20261108`.
- Live: `33/33` Playwright, `25` rutas activas, `24` API-backed, `246`
  llamadas/eventos reales, `0` errores de servidor/red y `0` gaps inesperados
  de autorización; `15` WARN esperados registrados. Recibo:
  `%TEMP%\\ronin-live-7026cd7-20261108`.
- VEX: Docker Scout `1.27.0`, `3` findings raw y `0` tras OpenVEX ligado al
  digest exacto; recibo `%TEMP%\\ronin-vex-7026cd7-20261108-rerun`. El VEX
  sigue requiriendo aceptación formal del security reviewer.
- UI estática: Chromium `128/128` sobre el checkout final; presupuesto y
  auditoría deben permanecer como recibos separados del mismo corte de UI.

Estos resultados cierran el bloque técnico local de este candidato, pero no
cierran el release: el ledger de familias sigue en `0/13` y continúan abiertos
la matriz de proveedores/credenciales, revisión humana de seguridad y VEX,
legal/NOTICE/claims, review visual manual, artefactos/SBOM/provenance,
rollback, Terraform/toolchain y gobierno de CI/branches.

En el checkout exacto de producto `91d37fe90b9e5413adf257cf6c326b1ff6dc2daf`
la suite estática Chromium pasa `125/125`; el journey focalizado de Studio pasa
`17/17`, la revisión visual automatizada en desktop/móvil no detecta overflow
horizontal y la suite de presupuesto (`asset_bytes=2,010,715`), auditoría web,
consistencia de rutas y ledgers queda verde. La suite Python/PostgreSQL completa
queda en `4562 passed`, `27 skipped`, `0 failed` de `4589`. Los skips son
explícitos y corresponden a Docker/servicios externos opt-in o limitaciones
POSIX/Windows; no se convierten en soporte anunciado.

La iteración encontró y corrigió un race real de UI: Ingestion Studio podía
escribir la respuesta de capacidades sobre un nodo desaparecido después de
navegar. El guard de destino evita esa actualización tardía. También se hizo
explorable la lista de Runs con alcance por proyecto, contadores de salud, reset
explícito, estados honestos y scroll de tabla confinado en móvil. El candidato
Docker exacto queda verde: `27/27` y acceptance v0.1 estricta `15/15`.

### Qualification exact-SHA del candidato y baseline histórico

La qualification completa anterior de `1daa6c5` queda conservada sólo como
baseline histórico. El candidato de producto `91d37fe` tiene la siguiente
recepción; el test harness live final se ejecutó desde `56e1668d` sin cambiar el
artefacto runtime:

- Docker: `27/27`, strict v0.1 `15/15`, runtime
  `sha256:5324b8f6d3e0a57ef5dcd9047ba988936761cdb7bce9a95d42b5cf6444cc2e85`.
- Helm/kind: lint, boundary de Secret, instalación, rollout, health,
  Studio/API autorizado, job persistente tras restart y cleanup, todo verde.
- Live: `33/33`, `25` rutas activas, `24` contratos API, `244` eventos
  correlacionados, `0` gaps de autorización inesperados y `0` errores de
  servidor/red.
- Python/PostgreSQL: `4562/4589` passed, `27` skips explícitos y `0` fallos en
  `%TEMP%\\ronin-python-full-91d37fe-20261108`.
- Web: estática Chromium `125/125`; Studio focalizado `17/17`; live final
  `33/33`, `25` rutas, `244` eventos (`229` OK, `15` WARN esperados), todo
  correlacionado y sin errores server/network. Evidencia live:
  `%TEMP%\\ronin-live-56e1668-final2-20261108`.
- VEX exacto: Docker Scout `1.27.0`, `3` findings raw y `0` aplicados para el
  runtime `sha256:5324b8f6d3e0a57ef5dcd9047ba988936761cdb7bce9a95d42b5cf6444cc2e85`
  y el probe exacto `sha256:9dd91be3e3316186fda38f397a50abe36cba7d86123f4d8d317249904b9c8527`.
- Seguridad automatizada: Gitleaks fijado encontró `0` leaks en 41,22 MB y
  pip-audit hash-locked encontró `0` vulnerabilidades conocidas en dev/test.

Evidencia: `%TEMP%\\ronin-python-full-91d37fe-20261108`,
`%TEMP%\\ronin-docker-91d37fe-20261108`,
`%TEMP%\\ronin-helm-91d37fe-20261108`,
`%TEMP%\\ronin-live-56e1668-final2-20261108`,
`%TEMP%\\ronin-vex-b4928d2-20261108`,
`%TEMP%\\ronin-gitleaks-56e1668-20261108` y
`%TEMP%\\ronin-pip-audit-56e1668-20261108`. El VEX sigue requiriendo
aceptación del security reviewer; Trivy no está instalado en el host y permanece
abierto.

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
una qualification real de PostgreSQL. El nuevo target `make test-postgres`
ejecuta la suite completa con el DSN/servicio configurado y aplica también el
ratchet de esos adaptadores; `make test` sigue siendo la comprobación rápida sin
servicios. En este entorno Windows sin DSN esa lane queda explícitamente
pendiente; no se cuenta como cobertura certificada ni como motivo para marcar la
release en verde.

Los probes de qualification que lanzan procesos Python auxiliares mantienen
10 s por celda en Linux y usan 45 s por celda sólo en Windows, además de 120 s
para observar el arranque frío de Docker Desktop. Los tests de timeout,
cancelación, aislamiento y finalización siguen siendo independientes y no se
relajan; estos márgenes sólo evitan falsos negativos de infraestructura del
host.

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

El runtime candidato `6012ed52` queda **verde en las lanes técnicas locales
disponibles**: Python/PostgreSQL `4562/4589`, artefacto instalado `90/90`, web
Chromium `128/128`, Docker `27/27` + strict `15/15`, Helm, live `33/33` sobre
25 rutas y 247 eventos, VEX aplicado `0`, Gitleaks/pip-audit limpios y SDK
SBOM/provenance verificados. Eso no equivale a release-qualified: la UI avanzó
en Run/Evidence, Runs explorer, Catalog, Semantic y Scheduler, pero aún no
alcanza la profundidad operativa completa de Databricks/Dataiku/Palantir/Fabric;
el ledger Public v1 mantiene `0/13` familias cualificadas; faltan revisión
visual/manual formal, revisión legal/NOTICE/claims, aceptación humana de
seguridad/VEX, Trivy/SBOM de contenedor, Terraform `1.13.5`, qualification de
proveedores, rollback y gobernanza CI/branch/release. Los skips externos y la
ausencia de Trivy no se presentan como verde.

## 9. Plan de iteración 2 hacia GO

Esta iteración no se considera cerrada por pasar el código local. Para convertir el
NO-GO en GO deben cerrarse, en este orden, los siguientes gates:

1. **Custodia exacta del release:** tratar `6012ed52` como el runtime candidato y
   `9b1d16ef` como el commit VEX/documental posterior; exportar un source bundle y
   un artifact-identity manifest reproducibles; regenerar wheel, sdist, runtime,
   probe, SBOM y provenance contra esos bytes; verificar que los commits
   documentales no cambien el SHA de código ni desacoplen los receipts.
2. **Seguridad reproducible:** ejecutar Trivy fijado en el toolchain sobre runtime
   y probe, repetir Gitleaks de árbol e historial desde un repositorio bare
   montable, revisar los 3 hallazgos VEX con un Security owner y registrar la
   decisión (aceptar, corregir o retirar la excepción). Un `0` automatizado sin
   esa firma no cierra el gate.
3. **Toolchain y operación:** usar exactamente Terraform `1.13.5`, completar la
   matriz Windows/Linux y Python soportada, verificar rollback y migraciones, y
   probar CI, protección de `main`, artifacts retenidos, expiración y acceso al
   expediente. Si no existe runner o credencial de laboratorio, el claim se
   mantiene `qualification_pending`.
4. **Familias y proveedores:** convertir cada familia activa en una journey
   candidate-bound con API/CLI/SDK/Studio, límites, errores, recuperación,
   evidencia y cleanup. Completar las lanes reales de Databricks, Dataiku,
   Foundry, Fabric, Kafka/streaming y cualquier driver anunciado; fixtures locales
   sólo pueden certificar el contrato que ejercitan.
5. **Producto/UI:** hacer una revisión manual firmada en 320 px, tablet y desktop
   de cada ruta; después iterar authoring, lineage, run/evidence, quality,
   migration y operations con progressive disclosure, búsqueda/command palette,
   estados honestos y una acción primaria clara. El objetivo es alcanzar la
   sencillez y potencia de Databricks/Dataiku/Palantir/Fabric sin perder la
   identidad Ronin, no añadir formularios por volumen.
6. **Decisión:** actualizar el ledger sólo cuando las 13 familias, el proveedor
   aplicable, el security/legal/product sign-off y el expediente exact-SHA tengan
   receipts consistentes. En caso contrario, mantener `0/13` y publicar el
   siguiente bloqueo concreto.
7. **Estabilidad de qualification:** la repetición exacta en `6012ed52` ya pasó
   `4562/4589`; conservar el orden, el seed y los receipts. Repetirla en un host
   estable o segundo sistema operativo antes de convertir el resultado local en
   claim de plataforma.
   Los timeouts observados en composición PostgreSQL y en tres contratos de
   subprocesos no se convierten en `pass` por haber pasado en aislamiento; si
   reaparecen, aislar la fuga de recursos o la presión de procesos antes de
   promocionar el candidato.

**Criterio de salida de la iteración 2:** todos los gates anteriores en `pass`,
ningún `skip` usado como soporte anunciado, `progress.complete = 13`, revisión
humana registrada y rollback ensayado. Hasta entonces, la plataforma queda en
`NO-GO` aunque las suites locales sean verdes.

## 10. Iteración 2026-11-10 — shell de interacción y candidato actual

La revisión del candidato actual añadió una mejora de producto al command
palette del Studio (`b3829bbe`): relación accesible explícita entre búsqueda,
lista y opción activa, cierre al pulsar fuera del diálogo y restitución del foco
al control que abrió la paleta. Es una mejora deliberadamente pequeña pero
representativa del objetivo UX: navegación rápida, reversible y usable por
teclado sin añadir complejidad visual ni inventar capacidades de backend.

Evidencia ejecutada sobre el `HEAD` actual:

- suite Chromium estática y de journeys: `147 passed`;
- suite Python completa: `4511 passed, 77 skipped, 0 failed`;
- checks de status/capability: `16 passed`;
- `python tools/generate_public_v1_status.py --check`: correcto;
- `main` y `origin/main` sincronizados en `b3829bbe`.

Los skips siguen siendo dependencias opt-in, credenciales, proveedores reales o
limitaciones del host; no se convierten en evidencia de release. La decisión
permanece `NO-GO`, porque el ledger de familias continúa en `0/13` y siguen
abiertos los gates humanos, legales, de proveedores, supply chain, rollback,
gobernanza y revisión visual formal descritos arriba.

## 11. Reconciliación del ratchet web

La pasada estática del `HEAD` `e4ce9afd` detectó que el baseline histórico de
`docs/ui/web-budget.json` (`2,123,786` bytes) ya no representaba el árbol actual:
varios workbenches incorporados después de aquel baseline habían aumentado el
paquete sin actualizar su receipt. Se corrigió además el límite de longitud de
`components.css`, que quedó en `400` líneas. El baseline se regeneró de forma
explícita sobre el árbol candidato actual: `2,132,739` bytes, 70 requests, 36
módulos y 15 hojas de estilo; `studio_web_audit`, `studio_budget --check`, Ruff,
route consistency, Studio surface, OpenAPI snapshot y capability status pasan.
Las futuras regresiones se medirán contra este baseline candidate-bound, no se
usará esta reconciliación para convertir skips externos en evidencia de release.

## 12. Regresión de contratos web y release ledger

Sobre el mismo `HEAD` `16dbe56e`, la regresión Python específica de las
superficies web, configuración de proyectos y ledger de release pasó `27 tests`
en `7.22s`. Incluye `test_studio_static.py`, `test_project_configuration.py`,
el status fail-closed, el generador de status, capability status y la matriz
Public v1. El resultado confirma que el ajuste de command palette/CSS y la
reconciliación del presupuesto no rompieron los contratos estáticos ni la
coherencia del expediente.

## 13. Suite Python completa del candidato actual

La ejecución completa sobre el `HEAD` documental `d977edcd` (sin cambios de
runtime respecto de `16dbe56e`) terminó en `4511 passed, 77 skipped, 0 failed`
en `353.24s`. Una primera ejecución había mostrado una única interrupción
`WinError 10053` durante la segunda petición del caso
`test_queryflux_execution_is_bound_to_an_existing_project_in_workspace`; el
caso pasó `11/11` veces aislado y la repetición completa posterior pasó sin
fallos. Se conserva como señal de contención/flakiness del host Windows, no se
cuenta como pass de una lane externa y debe vigilarse en futuras qualification.

## 14. Command palette: foco al abrir con atajo

La revisión de accesibilidad reprodujo un defecto real: al abrir la command
palette con `Ctrl/⌘K`, el foco inicial de Chromium podía ser `main`, y el cierre
intentaba restaurarlo como si fuera el disparador. El shell ahora conserva como
disparador sólo un elemento que sea realmente `[data-action="open-command"]` y
usa el botón visible como fallback. Se añadió una regresión específica de
apertura por atajo y restitución de foco.

La suite Chromium del candidato actualizado pasó `148/148` en `3.4m`; las tres
pruebas de command palette pasan juntas y la suite completa mantiene
accesibilidad, responsive, navegación y journeys en verde. La suite Python
posterior al mismo fix pasó `4511 passed, 77 skipped, 0 failed` en `251.10s`.

## 15. Ratchet final tras la limpieza de command palette

La limpieza posterior centralizó la restauración de foco y retiró estado y
atributos redundantes sin relajar la accesibilidad comprobada. El tamaño final
medido del Studio es `2,132,538` bytes, por debajo del baseline candidate-bound
de `2,132,739`; `studio_budget --check` y `studio_web_audit` pasan. La suite
Chromium completa posterior a esta limpieza permanece en `148/148`.

## 16. Command palette: saltos Home/End

La paleta admite ahora `Home` y `End` para saltar al primer y último resultado,
manteniendo actualizado `aria-activedescendant`. La regresión confirma ambos
saltos y la suite Chromium completa posterior pasa `148/148`; el paquete queda
en `2,132,718` bytes, dentro del ratchet vigente.

## 17. Rúbrica de producto y decisión candidate-bound

La calidad técnica del shell no se interpreta como equivalencia automática con
Databricks, Dataiku, Palantir o Fabric. Para que la comparación sea útil, cada
familia de producto debe demostrar simultáneamente los siguientes cinco
contratos en el mismo candidato limpio:

1. **Orientación:** la persona entiende dónde está, qué contexto (`workspace`,
   `project`, `environment`, `runtime`) está activo y cuál es el siguiente paso
   seguro sin leer documentación externa.
2. **Flujo completo:** puede descubrir, configurar, ejecutar, observar,
   corregir y volver a ejecutar la capacidad; los estados `loading`, `empty`,
   `error`, `blocked`, `running` y `success` son distinguibles y honestos.
3. **Control y reversibilidad:** las operaciones destructivas explican su
   alcance, requieren confirmación proporcional, producen un receipt y ofrecen
   cancelación, rollback o una recuperación documentada cuando el dominio lo
   permite.
4. **Densidad sin complejidad:** búsqueda/command palette, navegación por
   teclado, foco visible, responsive de 320–1440 px y progressive disclosure
   permiten trabajar con potencia sin convertir la pantalla en un panel de
   controles indistinguibles.
5. **Evidencia:** API/OpenAPI, persistencia, autorización, auditoría, métricas y
   documentación describen el mismo contrato que muestra la UI; ningún texto
   de demo se usa como resultado operativo.

La aceptación visual requiere además una revisión humana con capturas de cada
journey en viewport ancho y estrecho, más una revisión de lector de pantalla y
teclado. Los tests automatizados prueban regresión, no sustituyen esta firma.
La hoja de decisión de Public v1 debe marcar una familia como `qualified` sólo
cuando los cinco contratos, el journey end-to-end, el proveedor declarado, la
licencia/NOTICE y el rollback tengan evidencia candidate-bound. Una suite verde
con `0/13` familias no puede producir `GO`.

**Observación actual:** el `HEAD` documental/runtime `1b124cb0` está publicado y limpio;
la regresión web completa es `148/148`, el subconjunto Python/ledger candidate-bound es `17/17`,
la auditoría web y el presupuesto pasan, y el candidato runtime/test base
`772e381d` conserva la suite Python `4511 passed, 77 skipped, 0 failed`.
La rúbrica no cierra por inferencia los journeys, proveedores, licencias,
revisión visual, supply chain, rollback ni gobierno de release: el ledger
continúa en `0/13` y la decisión verificable continúa **NO-GO**.

**Siguiente ciclo obligatorio:** seleccionar una familia con owner y proveedor,
congelar un SHA limpio, ejecutar el journey de los cinco contratos, adjuntar
capturas/receipts y sólo entonces cambiar su estado del ledger. Repetir hasta
`13/13`; si una evidencia falta, conservar `NO-GO` y registrar el blocker
concreto en lugar de rebajar el estándar.

## 18. Metadata explícita del command palette

El disparador visible de la command palette declara ahora `aria-haspopup="dialog"`
 y `aria-keyshortcuts="Control+K Meta+K"`. Esto hace que el modo de apertura y
 sus atajos sean descubribles para tecnología asistiva, manteniendo el mismo
 comportamiento visual y de teclado. El contrato Playwright focalizado pasa
 `3/3` y el contrato estático pasa `10/10`.

El incremento medido es deliberado y pequeño: `asset_bytes=2,132,778` y
`html_bytes=5,838`. Se actualiza el baseline candidate-bound para que el ratchet
 siga detectando cualquier incremento posterior; no se usa como evidencia de
 release ni cambia el ledger `0/13` o la decisión **NO-GO**.

## 19. Revisión visual manual del shell

Se inspeccionó el `HEAD` en Chromium con capturas de `1440×900` y `390×844`,
servidor estático local y navegación real. La jerarquía del rail, la entrada
action-first y el contraste de las superficies son consistentes; no apareció
un desbordamiento horizontal ni una interacción inaccesible en esta pasada.

Quedan dos hallazgos de producto que impiden firmar la revisión visual como
completa: en móvil los chips de `workspace/project/runtime` se comprimen hasta
truncarse y pierden parte de su legibilidad; además, el control plane queda
parcialmente próximo a la barra de navegación fija y necesita una comprobación
de espacio inferior al recorrer contenido largo. La captura `fullPage` tampoco
es evidencia suficiente para este shell porque `main` mantiene scroll interno.
El próximo ciclo debe capturar el viewport visible y recorrer el scroll en cada
breakpoint, y debe resolver la compresión del contexto móvil antes de pedir la
firma humana. El estado de release no cambia: `0/13`, **NO-GO**.

## 20. Contexto móvil y navegación fija

Se implementó el primer fix del hallazgo visual: bajo `700px` el shell muestra
un resumen único y truncable de `workspace / project` en lugar de tres chips
comprimidos, y `main` reserva espacio inferior adicional para la barra de
navegación fija. El diálogo conserva los cinco campos completos para editar el
contexto sin perder información.

La matriz responsive y de contexto pasa `16/16`; la suite Chromium candidate-bound
pasa `148/148` con un worker; la auditoría web queda en 71 archivos y 0 fallos.
El tamaño candidate-bound sube a `2,133,306` bytes por la
metadata visual y la reserva de scroll; el baseline se actualiza de forma
explícita y cualquier incremento posterior seguirá fallando cerrado. La suite
Chromium completa sigue siendo obligatoria antes de aceptar este cambio.
El expediente reproducible de esta revisión queda en
`docs/ui/MANUAL_VISUAL_REVIEW_2026-11-11.md`; sus hallazgos abiertos mantienen
la firma visual humana en `qualification_pending`.

## 23. Regresión Python completa del candidato P1

La suite `python -m pytest --ignore=tests/perf -q` sobre el mismo código de
runtime del candidato `8d5f8c0f` terminó `4511 passed, 77 skipped, 0 failed`
en `502.30s`. Los skips corresponden a Docker/worker, PostgreSQL, S3/Azure,
OTLP, Trino/SDP/Spark, symlinks y otros proveedores o límites del host; quedan
enumerados por pytest y no se convierten en passes ni en qualification externa.
El resultado confirma que la UI de revisión/comparación no rompe los contratos
Python del candidato. No altera el ledger `0/13` ni cierra los gates de
proveedores, legal, visual, supply chain, rollback o gobierno.

## 21. P1 — evidencia de revisiones en Project Studio

Project Studio ahora ofrece una superficie de sólo lectura para consultar las
revisiones inmutables de un pipeline antes de seleccionar `revision_key` para
una operación. La UI mantiene explícitos `workspace`, `project` y `pipeline`,
renderiza digest y clave de revisión, y muestra un estado vacío o un error
scoped sin inventar revisiones. Reutiliza el endpoint existente
`GET /v1/workspaces/{workspace}/projects/{project}/pipelines/{pipeline}/revisions`;
no introduce un backend paralelo ni mutación implícita.

El journey `workspace-workbench.spec.mjs` verifica la lectura de una revisión
con digest y clave (`2/2` casos del archivo), y la auditoría web queda en 181
invocaciones sin fallos. El coste medido es `asset_bytes=2,135,236`, nuevo
baseline candidate-bound explícito. Esto fortalece P1 y la ergonomía de
source-control/evidence, pero no convierte la familia en `qualified`: faltan
journeys completos, provider/source-control real y gates humanos.

## 22. P1 — comparación explícita de revisiones

La superficie de evidencia de Project Studio añade ahora comparación de dos
revisiones mediante el endpoint existente
`GET .../revisions/compare?left_revision=&right_revision=`. El resultado se
renderiza como evidencia secundaria de sólo lectura; la UI conserva el scope
de workspace/proyecto/pipeline y muestra los cambios recibidos sin aplicar
ninguna mutación.

El journey de workspace verifica historial y comparación con `2/2` casos del
archivo; la auditoría registra 182 invocaciones y 0 fallos. El baseline
candidate-bound queda en `asset_bytes=2,136,819`, actualizado explícitamente
por este incremento funcional. P1 continúa parcial y el release permanece
`0/13`, **NO-GO**.

## 25. Regresión Chromium completa del HEAD actual

La suite Chromium no-live se ejecutó en un solo worker sobre el HEAD actual
`9ae80e80dac0a55700e7835e80a4b9c5e9ff6cf0` y terminó con **152 passed, 0
failed** en 10m36s. Incluye accesibilidad por Studio, navegación por teclado,
matriz responsive, traversal de rutas, journeys de Catalog/Lineage,
Data Engineering/QueryFlux, Quality y Workspace/Project. Esta evidencia
automatizada mejora la confianza del candidato, pero no sustituye la revisión
visual humana ni cualifica por sí sola las familias Public v1.

## 24. Scorecard de madurez de UI

La aspiración de una UI comparable a Databricks, Dataiku, Palantir y Fabric
queda convertida en criterios verificables en
`docs/ui/PRODUCT_UI_MATURITY_SCORECARD.md`. El scorecard separa evidencia
automatizada de decisión visual humana y exige revisar orientación,
divulgación progresiva, contexto, evidencia, recuperación, densidad responsive,
accesibilidad, presupuesto, límites destructivos y estado honesto por Studio.
No cambia el NO-GO actual: el candidato todavía no tiene todos los Studios en
verde ni las aprobaciones humanas, de proveedores, seguridad, rollback y
gobernanza requeridas.

## 26. Regresión Python exact-head y reconciliación del ledger

La regresión `python -m pytest --ignore=tests/perf -q` se ejecutó sobre el
HEAD de implementación antes de esta reconciliación. Detectó un único fallo
de consistencia documental: `PUBLIC_V1_CAPABILITY_MATRIX.md` conservaba el
SHA anterior aunque el ledger ya había avanzado. El fallo no era funcional;
la referencia se corrigió y la selección de validadores del ledger pasó
`16/16`. La primera ejecución quedó registrada como `4510 passed, 77
skipped, 1 failed`; tras corregir la referencia, la repetición completa sobre
el mismo contenido terminó **4511 passed, 77 skipped, 0 failed** en 705.38s.
El resultado verde confirma también que la inconsistencia era documental y no
una regresión funcional.

## 27. Regresión Chromium posterior al arreglo de Synthetic Studio

La ejecución global sobre `96b4b2ab` encontró inicialmente dos fallos de
superficie; uno era una flake de navegación y el otro reveló una regresión
real: `synthetic-journey.js` no estaba importado por el shell, por lo que los
controles de validación y generación asíncrona no aparecían. El módulo se
conectó en `app.js`; los tres journeys Synthetic pasaron y la repetición
completa terminó **154 passed, 0 failed** en 8m18s.

## 28. Recalibración del presupuesto tras conectar Synthetic Journey

La importación del módulo que faltaba añade `2,214` bytes al shell. El
presupuesto candidate-bound se actualiza de `2,136,819` a `2,139,033` bytes,
manteniendo requests, módulos, hojas de estilo y HTML sin cambios. La
recalibración es explícita y `python -m tools.studio_budget --check` vuelve a
pasar; no se permite crecimiento implícito.

## 29. Identidad larga y accesible en Catalog

Las filas de Catalog conservan ahora el identificador completo mediante
`title` y `aria-label`, mientras la presentación puede truncarse dentro de la
tabla responsive. El journey de Catalog verifica un identificador largo y
ausencia de overflow en móvil (`5/5` casos del archivo). El coste medido sube
explícitamente de `2,139,033` a `2,139,167` bytes; el budget check y la
auditoría web pasan.

## 30. Recuperación del glosario en Catalog

La búsqueda del glosario ofrece ahora `Retry glossary search` tras un fallo,
conservando workspace y consulta. El journey de Catalog alcanza `6/6` casos,
incluye el error `503` y la recuperación, y mantiene el layout responsive. El
budget candidate-bound se actualiza explícitamente de `2,139,167` a
`2,139,459` bytes; auditoría y budget check pasan.

## 31. P3 — plan de construcción para cancelación QueryFlux

La cancelación de QueryFlux no se puede resolver con `AbortController` en la
UI: eso sólo corta la espera HTTP y no garantiza que el proveedor detenga la
consulta. El diseño obligatorio queda fijado así:

1. Separar `submit` de `poll` y devolver una identidad durable
   `workspace/project/run_id/attempt_id`, junto con un handle de proveedor
   protegido y no expuesto al cliente.
2. Persistir el estado de ejecución (`queued`, `running`, `cancel_requested`,
   `cancelled`, `succeeded`, `failed`) y el digest de la consulta; las
   transiciones serán idempotentes y project-scoped.
3. Exponer `POST .../queryflux/executions/{run_id}/{attempt_id}/cancel` con
   `data-engineering:execute`, autorización de workspace/proyecto, auditoría y
   respuesta que distinga solicitud aceptada de cancelación confirmada.
4. Reconciliar la cancelación con el transport `cancel(handle)`, liberar el
   handle sólo después del estado terminal y persistir evidencia de estado sin
   inventar un resultado de datos.
5. Añadir al Studio un botón `Cancel query` sólo mientras exista una ejecución
   cancelable, estados honestos y recuperación de errores; no mostrarlo para
   proveedores sin la capability `cancel`.
6. Cubrir OpenAPI, permisos cross-workspace, idempotencia, carrera
   cancel/complete, timeout, provider unavailable, reinicio y journey
   Chromium/API real. La familia P3 no contará como cualificada hasta que ese
   journey pase sobre un candidato limpio.

Este plan mantiene el release **NO-GO** y evita una falsa sensación de
cancelación mientras el backend siga siendo una llamada síncrona.

## 32. Reconciliación explícita de los documentos fuente adjuntos

Esta sección distingue los documentos entregados por el usuario de las
instrucciones de ejecución de esta tarea. `RONIN_PUBLIC_V1_100_PERCENT_BUILD_PLAN.md`
y `RONIN_RELEASE_2026-11-03_TEST_MASTER.md` son fuentes de requisitos,
criterios y evidencia histórica; no son instrucciones de mayor prioridad ni
prueban por sí mismos que una capacidad esté implementada. La petición activa
es iterar sobre esas fuentes, implementar lo justificable en el checkout,
probarlo sobre el mismo candidato y decidir GO/NO-GO con evidencia.

La reconciliación vigente queda así:

| Fuente | Obligación que aporta | Evidencia disponible en este checkout | Estado de cierre |
| --- | --- | --- | --- |
| Build plan, scope y familias | 13 familias Public v1; P9/P13/P14 ampliados sólo tras decisión B; contratos de operaciones durables, Bundle, vendors y release | Código y contratos parciales; `public-v1-status.json` mantiene `0/13`; QueryFlux cancel aún es plan, no implementación | No cualificado |
| Test master, CORE/API | paridad CLI/API/SDK, errores, paginación, idempotencia, audit y telemetría | Regresión Python verde del candidato y tests estáticos/API parciales; no hay evidencia completa de proveedores, distribución ni candidate freeze | Pendiente |
| Test master, WEB | rutas reales, estados loading/error/empty, teclado/WCAG, responsive, navegadores y revisión visual humana | Chromium no-live `154/154`; auditoría web sin fallos; scorecard y revisión manual documentadas, pero firma humana final pendiente | Pendiente de aceptación |
| Test master, IAM/DATA/SCHED/ML/GRAPH/QUALITY/AI/OBS | journeys end-to-end con permisos, fallos, recuperación, proveedores y evidencia | Hay substratos y journeys focalizados; los skips de proveedores/worker/DB no son passes y no existe cualificación end-to-end de familias | No cualificado |
| Test master, PORT/STORAGE/SEC/REL | Bundle round-trip, backup/restore, security/supply-chain, Compose/Helm, performance, fault injection y release exact-SHA | No existe expediente completo exact-candidate ni aceptación humana de esos gates; el branch/CI governance sigue abierto | Bloqueado |

Los números de pruebas ejecutadas se mantienen separados de los estados de
producto: `4511 passed, 77 skipped, 0 failed` en Python, `154 passed` en
Chromium no-live y los checks focalizados verdes demuestran regresión técnica
del candidato observado, pero no certifican proveedores externos, seguridad,
portabilidad, operación distribuida, legalidad, rollback ni aceptación de
release. Antes de cualquier GO deben existir, como mínimo, un candidato
congelado con expediente reproducible, la matriz completa de gates sin skips
obligatorios, revisión visual humana, decisiones de alcance B si se pretende
14/14, y aprobación explícita de seguridad, supply chain, legal y operación.

Consecuencia: esta reconciliación no cierra ningún RPV1 ni VER, no modifica el
ledger oficial y conserva la decisión **NO-GO / 0 de 13 familias cualificadas**.

## 33. Recuperación del inventario en Workspace Studio

Workspace Studio incorpora ahora `Retry workspace inventory` tanto en el
renderizado principal como en la mejora del Workbench. El retry sólo repite la
lectura `GET /v1/workspaces`: no reenvía formularios ni crea recursos, y deja
la frontera workspace/project intacta. Esto cubre el requisito de recuperación
del scorecard para un fallo transitorio del control plane.

La regresión existente del Workbench continúa verde (`2/2`): contexto,
orientación, responsive móvil y flujo de creación siguen funcionando. La
prueba de fallo transitorio queda pendiente de una fixture estable para la
doble fase de renderizado del shell; no se cuenta como pass hasta que esa
fixture pueda demostrar 503 → retry → inventario sobre el mismo candidato.
Este cambio mejora la UX, pero no cualifica P1 ni altera `0/13`.

## 34. Ratchet del presupuesto tras el retry de Workspace

La auditoría estática del shell sigue en `71` archivos, `38` módulos, `182`
invocaciones de ruta y `0` fallos. El mensaje y control de recuperación de
Workspace incrementan el asset budget de `2,139,459` a `2,139,801` bytes;
`python -m tools.studio_budget --check` pasa después de actualizar el baseline
candidate-bound. El incremento queda registrado deliberadamente y cualquier
crecimiento posterior volverá a fallar cerrado. El journey Workbench pasa
`2/2` en Chromium con un worker; esto no cambia la cualificación de release.

## 35. Consolidación pendiente del doble render de Workspace

La ruta activa también conserva un loader histórico en `features.js`, mientras
el Workbench moderno se mejora desde `workspace-journey.js`. Ambos pueden
observar la misma navegación y solicitar `/v1/workspaces`; por ello una fixture
que falle sólo la primera petición no demuestra de forma fiable el estado que
ve el operador. La implementación añade el retry a la ruta activa y mantiene
la prueba existente del Workbench (`2/2`), pero el caso 503 → retry se mantiene
pendiente hasta consolidar ambos loaders en una única autoridad de renderizado.

La auditoría estática sigue en `0` fallos; el presupuesto candidate-bound se
actualiza a `2,139,950` bytes. Esta deuda de consolidación es de producto y no
se interpreta como pass de recuperación ni como cierre de P1.

## 38. Hallazgo de routing para Scheduler/Workflows

La auditoría de recuperación de Workflows mostró que `#workflows` no usa el
loader histórico de `features.js` como superficie principal: el DOM y los
journeys activos pertenecen al Scheduler Studio moderno. Se retiró el cambio
experimental del loader histórico y no se contabilizó su prueba fallida.

La suite Scheduler vigente queda verde (`2/2`), incluyendo operaciones
durables, backfill y retry de observación. El siguiente trabajo de recuperación
de inventario debe implementarse en `scheduler-studio.js`, con el contrato y
selectores de esa superficie, no duplicando lógica en `features.js`.

## 39. Recuperación de entregas en Scheduler Studio

La observación `Inspect event deliveries` ahora comparte el contrato de
recuperación de las demás lecturas del Scheduler: ante un fallo conserva el
workspace y muestra `Retry this observation`; el retry vuelve a ejecutar sólo
el `GET` de entregas y no modifica estados durables.

La suite Scheduler pasa `3/3`, incluyendo la regresión existente y el caso
503 → retry de entregas. La auditoría web mantiene `0` fallos y el budget
candidate-bound queda en `2,140,294` bytes. Esto fortalece la observabilidad
operativa, pero no cualifica P5 ni cambia `0/13`.

## 37. Recuperación de Environment Studio

Environment Studio incorpora `Retry environment inventory` para errores de la
lectura workspace-scoped. La acción conserva el workspace activo y sólo repite
`GET /v1/workspaces/{workspace}/environments`; no reenvía creación, pausa ni
restauración. La suite del Studio pasa `5/5`, incluyendo el caso reproducible
503 → retry, autoría, gobernanza reversible y accesibilidad seria/critical en
cero.

La auditoría web continúa en `0` fallos y el presupuesto candidate-bound queda
en `2,140,105` bytes. Esto mejora la recuperación y la claridad operativa del
control plane, pero no cualifica P1 ni modifica el estado `0/13`.

## 36. Evidencia reproducible del retry Workspace

La fixture estable se obtuvo separando la carga inicial del refresh: el
inventario se carga correctamente, el siguiente `Refresh workspaces` se fuerza
a responder `503 service_unavailable`, y la acción `Retry workspace inventory`
debe recuperar el mismo inventario. El archivo
`workspace-workbench.spec.mjs` pasa ahora `3/3` con un worker, incluyendo el
caso 503 → retry y los journeys responsive de Workspace y Project.

La consolidación de los dos loaders sigue siendo una deuda técnica para evitar
solicitudes redundantes durante la navegación inicial, pero ya no invalida la
evidencia del comportamiento de recuperación del operador. No se cierra P1 ni
se modifica el estado de release `0/13`.

## 40. Regresión Chromium global con resultado terminal fiable

Tras cerrar un servidor estático residual que ocupaba el puerto `8099`, la
suite completa no-live se ejecutó con un proceso persistente sobre el candidato
actual: **`158 passed, 0 failed` en 6,3 minutos**, con un worker. El resultado
incluye accesibilidad de rutas, responsive, traversal, Catalog, QueryFlux,
Environment, Scheduler, Synthetic, Workspace/Project, Streaming, Semantic,
ML y journeys de plataforma.

Este resultado sí es evidencia exact-candidate de regresión web, pero no es
una cualificación de release: no sustituye proveedores live, seguridad,
supply-chain, Bundle/restore, Helm/Compose, revisión visual humana, legal,
rollback ni gobernanza de CI. El estado permanece **NO-GO / 0 de 13**.

## 41. Siguiente incremento: recuperación de Migration Studio

La revisión de Migration Studio identifica una deuda de recuperación en la
lectura de sesiones: el cockpit activo usa `loadMigrationCockpit()` dentro del
shell de `app.js`, mientras la vista histórica usa `loadMigrationSessions()`.
Ambas deben converger antes de añadir un retry, para que `Refresh` y
`Retry session inventory` apunten al mismo endpoint y no creen dos estados de
selección.

El incremento queda definido como lectura segura únicamente: `GET
/v1/workspaces/{workspace}/projects/{project}/migration/sessions`, conservar
workspace, project y session seleccionada, mostrar error tipado y retry tras
4xx/5xx, y no repetir create, discover, scope, blueprint ni promote. El cierre
requiere 503 → retry, ausencia de sesiones, selección y responsive en el
cockpit activo sobre un candidato exacto. No se implementa mediante un
listener paralelo mientras existan los dos loaders.

## 42. Regresión Python completa del candidato reconciliado

La ejecución `python -m pytest --ignore=tests/perf -q` sobre el candidato
reconciliado terminó **`4511 passed, 77 skipped, 0 failed` en 5m54s**. Los
skips están enumerados por pytest y corresponden a cualificaciones opt-in de
Docker/worker/Compose, PostgreSQL, S3/Azure, OTLP, Trino/SDP/Spark, symlinks,
credenciales y proveedores externos. No se convierten en passes ni cierran
los gates live, de portabilidad, seguridad o despliegue.

La evidencia confirma que la sincronización del ledger y los cambios de UI no
rompen el runtime Python del candidato. Junto con Chromium `158/158`, mejora
la confianza de regresión, pero no cambia `0/13` ni la decisión **NO-GO**.

## 44. Recuperación de Cloud Studio

Cloud Studio conserva el target JSON y ofrece `Retry validation` después de
un error del validador. El retry repite únicamente la validación del target;
no aplica infraestructura ni convierte el plan en una operación ejecutada.
La prueba focalizada pasa `2/2`, incluyendo 503 → retry y el journey de plan
reviewable.

La auditoría web permanece en `0` fallos y el budget candidate-bound queda en
`2,141,117` bytes. Esto mejora la recuperación de una superficie de
deployment planning, pero no cualifica P14 ni cambia `0/13`.

## 46. Recuperación de Debugger Studio

Debugger Studio conserva la sesión y las celdas introducidas cuando falla la
creación de una sesión, mostrando `Retry session creation`. El retry repite
únicamente el `POST` de creación; no reenvía breakpoints ni ejecución de
celdas. La prueba focalizada pasa `2/2`, incluyendo 503 → retry y el flujo de
breakpoint.

La auditoría web sigue en `0` fallos y el budget candidate-bound queda en
`2,141,636` bytes. Esto mejora la recuperación de una superficie de debugging
interactivo, pero no cualifica P4 ni cambia `0/13`.

## 47. Regresión Chromium global posterior a Debugger

La suite no-live completa del candidato actual terminó **`161 passed, 0
failed` en 8,1 minutos**, con un worker. Incluye el retry de creación de
sesión de Debugger, los retries de Performance y Cloud, accesibilidad,
responsive, traversal y el conjunto completo de journeys web.

Esta evidencia confirma regresión web exact-candidate, pero no cualifica
release. Proveedores live, seguridad, supply chain, Bundle/restore,
Helm/Compose, revisión visual humana, legal, rollback y CI governance siguen
abiertos; el ledger permanece **NO-GO / 0 de 13**.

## 45. Regresión Chromium global posterior a Performance y Cloud

La suite no-live completa del candidato actual terminó **`160 passed, 0
failed` en 5,9 minutos**, con un worker. La ampliación respecto a `158/158`
incluye los journeys de retry de Performance Studio y Cloud Studio, además de
accesibilidad, responsive, traversal y todas las superficies existentes.

La evidencia es una regresión web exact-candidate, no una aprobación de
release: proveedores live, seguridad, supply chain, Bundle/restore,
Helm/Compose, revisión visual humana, legal, rollback y gobernanza siguen
abiertos. El ledger permanece **NO-GO / 0 de 13**.

## 43. Recuperación de Performance Studio

Performance Studio conserva ahora el run JSON y el baseline introducidos
cuando el análisis falla, mostrando `Retry analysis` sólo después de un error
del `POST /api/v1/performance/analyze`. El retry reenvía la misma intención
visible y no crea ni modifica una operación durable.

La prueba focalizada pasa `2/2`, incluyendo 503 → retry y resultado válido. La
auditoría web sigue en `0` fallos y el budget candidate-bound queda en
`2,140,702` bytes. Esto mejora la recuperación de una superficie de
inteligencia operativa, pero no cualifica P12 ni cambia `0/13`.

## 48. Recuperación de discovery paginado en Ingestion Studio

Ingestion Studio ahora conserva la intención y el cursor de la página fallida
cuando la lectura read-only de discovery responde con error. La acción cambia
a `Retry discovery page` y repite únicamente esa lectura; si el fallo ocurre
en una página posterior, el cursor ya aceptado se conserva. Las operaciones
durables de preview, plan, checkpoint y sync no se reintentan automáticamente.

La prueba focalizada de Ingestion termina `5 passed, 3 skipped` (los skips son
los journeys live opt-in), incluyendo 503 → retry → página 1 → página 2,
cancelación, validación de página malformada y sync gobernado. `studio_web_audit`
queda en `0` fallos. El budget se recalibra explícitamente a
`asset_bytes=2,141,918` (`70` assets, `36` módulos, `15` hojas de estilo,
`5,838` bytes HTML), un incremento de `282` bytes para la etiqueta y estado
de retry. Esto refuerza la recuperación operativa de P2/P3, pero no cualifica
ninguna familia Public v1 ni cambia el estado **NO-GO / 0 de 13**.

## 49. Recuperación del inventario de Migration Studio

La ruta activa de Migration Studio (`renderMigrationCockpit()` y
`loadMigrationCockpit()`) ahora expone `Retry session inventory` cuando la
lectura de sesiones falla. El retry repite únicamente el `GET` read-only y no
recrea sesiones ni repite discovery, generación, validación o promoción.
También se conserva la indicación visual de que la cualificación sigue en
`REVIEW` hasta que exista evidencia runtime.

La prueba focalizada de Migration termina `2/2`, incluyendo 503 → retry del
inventario y la comprobación de que la UI permanece visualmente no cualificada.
`studio_web_audit` queda en `0` fallos. El budget se recalibra explícitamente a
`asset_bytes=2,142,258` (`70` assets, `36` módulos, `15` hojas de estilo,
`5,838` bytes HTML), un incremento de `340` bytes. Esto cierra una deuda de
recuperabilidad de la ruta activa, pero no cualifica P14 ni cambia el estado
**NO-GO / 0 de 13**.

## 51. Regresión exacta posterior al contexto de Migration

La regresión Chromium global del candidato `2e2b3940` ejecutó `197` casos con
un worker y terminó `163 passed, 33 skipped, 1 failed` en `22m06s`. El único
fallo fue `guided-tutorial.spec.mjs:32`, timeout de `60s` durante el setup de
`page`, sin aserción funcional fallida. La misma prueba aislada se reprodujo
inmediatamente con `1/1 passed` en `8.8s`, por lo que queda clasificada como
inestabilidad/contención del runner global, no como evidencia de release verde.

La regresión Python exacta del mismo candidato terminó `4511 passed, 77
skipped, 0 failed` en `530.87s`. Los skips corresponden a opt-ins explícitos
de Docker, PostgreSQL, proveedores externos, SDP/Spark, OTLP y capacidades
POSIX no disponibles en Windows. El budget y `studio_web_audit` permanecen
verdes. El gate web global sigue abierto hasta obtener una corrida completa
sin timeout y el ledger conserva **NO-GO / 0 de 13**.

## 50. Contexto de proyecto en Migration Studio

La revisión de la ruta activa encontró que el cockpit aceptaba workspace y
proyecto en sus controles, pero el inventario de sesiones seguía consultando
siempre `default/examples/demo`. `loadMigrationCockpit()` ahora construye el
endpoint con los valores visibles y mantiene el fallback sólo cuando aún no
existen los controles. Esto alinea la UI con el aislamiento por proyecto que
declara la API y evita presentar sesiones de otro contexto.

La regresión focalizada de Migration queda en `3/3`, incluyendo 503 → retry,
estado visual `REVIEW` y cambio explícito a `team-a/project-z`. La auditoría
web permanece en `0` fallos y el budget queda en `asset_bytes=2,142,571`.
Este arreglo corrige una inconsistencia de contexto, pero no cualifica P14 ni
modifica el **NO-GO / 0 de 13**.

