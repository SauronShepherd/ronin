# RONIN — plan diario de construcción, pruebas y handoff

**Fecha de arranque:** 2026-11-14
**Ventana de candidato técnico:** 2026-11-14 a 2026-12-22
**Ventana de revisión humana:** 2026-12-23 a 2026-12-31
**Rama operativa única:** main
**Estado al arrancar:** NO-GO, 0/13 familias cualificadas, 0%

Este documento convierte los tres documentos de producto y pruebas en un
procedimiento diario ejecutable. Los documentos adjuntos son la fuente de
requisitos funcionales, contratos y criterios de prueba. Este documento es la
fuente de ejecución: ordena el trabajo, fija el alcance, define cuándo se
puede cerrar una fase y obliga a dejar un handoff verificable para el siguiente
agente.

## 1. Decisiones operativas que prevalecen

1. El objetivo ejecutable es Scope A: 13 familias Public v1, P1-P8 y P10-P14.
   P9 GenAI/RAG/agentes queda fuera del denominador y no se puede cerrar por
   inferencia. El objetivo ampliado 14/14 es una hipótesis aparcada, no una
   modificación automática del producto aprobado.
2. Solo se trabaja en main. No se crean ramas, worktrees ni PRs intermedias.
   Cada cierre válido se hace con commit y push directo a origin/main.
3. No se usan workflows hospedados ni automatización remota de CI. Todas las
   pruebas de este plan se ejecutan localmente con PowerShell, Python, npm,
   Docker/Compose, Helm/kind y los perfiles de proveedor que estén realmente
   disponibles. El push es una operación Git explícita y verificable.
4. No se borran ni se incorporan al commit los artefactos no rastreados que ya
   existen en la copia del usuario. Para reproducir un candidato limpio se
   genera un sandbox temporal desde git archive del SHA exacto. No es un
   worktree, no es una rama y no altera la copia de trabajo.
5. No hay intervención humana durante la construcción autónoma. Las decisiones
   que la documentación reserva a revisión humana —licencias, NOTICE, claims
   públicos, seguridad final y aprobación de release— se preparan y se dejan
   explícitamente pendientes para Navidad. No se usan como excusa para
   inflar el progreso técnico.

## 2. Situación real congelada al iniciar

| Hecho | Estado comprobable | Consecuencia |
| --- | --- | --- |
| HEAD local y remoto | main en e22819aeb3429bfe8cdd4d512b9c1a935970f426 | Es el punto de partida de D00 |
| Ledger público | public-v1-status.json conserva 0/13 y NO-GO; su observed_main_sha no coincide con el HEAD actual | No se reutiliza como evidencia exact-HEAD |
| Familias | 13 activas; P9 excluida | Denominador fijo: 13 |
| Implementación | Varias áreas aparecen partial o con evidencia histórica | Partial nunca equivale a familia cualificada |
| Suites históricas | Existen recibos de distintos SHAs, algunos de worktree sucio | Se conservan como historia; no cierran el candidato actual |
| Artefactos locales | Hay directorios, ZIP, resultados y ficheros coverage no rastreados | No se tocan; se aíslan con sandbox de candidato |
| Workflows remotos | No hay ficheros activos en .github/workflows en la copia observada | El proceso de este plan es local y Git directo |
| Release | No hay candidato 13/13 exact-SHA | NO-GO permanece |

La primera tarea no es declarar que el código está peor o mejor por el número de
recibos históricos. La primera tarea es hacer que el siguiente resultado sea
reproducible: un SHA, un entorno, un comando, un resultado y un artefacto que
pueda inspeccionarse.

## 3. Métricas que se muestran siempre

Se publican cuatro contadores independientes en cada cierre diario:

| Contador | Fórmula | Estado inicial | Qué permite afirmar |
| --- | --- | --- | --- |
| Familias cualificadas | familias con aceptación completa / 13 | 0/13 = 0% | Progreso real de Public v1 |
| Días cerrados | días PASS / 39 | 0/39 = 0% | Avance de ejecución de este plan |
| Gates de release | gates exact-SHA PASS / 10 | 0/10 = 0% | Preparación técnica del candidato |
| Tareas verificadas | tareas con criterio y evidencia / total inventariado | se baselina en D01 | Avance de implementación, separado del release |

El porcentaje de familias solo sube cuando existe un recibo de familia ligado al
SHA candidato y todos sus criterios pasan. Un test unitario, un recibo de Docker,
un navegador verde o una mejora visual no incrementan por sí solos una familia.
Si una prueba obligatoria está bloqueada, la familia permanece abierta.

El estado global solo puede ser GO cuando las 13 familias, los diez gates, el
candidato exacto y los requisitos humanos de release estén cerrados. Durante la
ventana autónoma el estado esperado, aunque el candidato técnico quede listo,
es CANDIDATE-READY / NO-GO-HUMAN-REVIEW.

## 4. Definición de cierre de fase y de familia

Cada día tiene un entregable pequeño y un criterio de salida. El agente no
marca PASS porque el comando termine sin excepción si faltan pruebas del
contrato.

### 4.1 Cierre diario obligatorio

1. Leer este plan, el ledger JSON, el handoff anterior y el estado de Git.
2. Ejecutar primero el comando de reproducción del handoff anterior.
3. Implementar solo el alcance del día; cada cambio debe tener un test o una
   razón documentada de por qué la prueba se ejecuta en el cierre de familia.
4. Ejecutar las pruebas unitarias, contrato/API, integración, E2E, seguridad,
   recuperación y UI que correspondan al alcance.
5. Guardar recibos en docs/qualification/daily y hashes de los artefactos.
6. Actualizar el ledger únicamente con estados respaldados por esos recibos.
7. Comprobar diff, secretos, licencias mecánicas, rutas no deseadas y que no se
   hayan añadido artefactos del usuario.
8. Crear el handoff del día con contexto, resultado, fallos, comandos y próxima
   acción.
9. Si el día está PASS, hacer commit y push a main, y verificar que
   git ls-remote origin refs/heads/main devuelve exactamente el SHA publicado.
10. Si falla cualquier gate, el día queda FAIL o BLOCKED: se conserva el
    porcentaje anterior, se registra la causa y el siguiente agente reintenta
    primero el mismo comando.

### 4.2 Cierre de una familia

Una familia solo pasa de in_progress a qualified si su recibo incluye:

- contrato versionado y rutas reales que aplican;
- backend real con persistencia, límites y migraciones comprobadas;
- API, SDK, CLI y Studio cuando formen parte del alcance;
- camino positivo, entradas inválidas, autorización negativa, reintento,
  cancelación cuando aplique, reinicio y recuperación;
- aislamiento por workspace/proyecto, secretos y redacción;
- telemetría, evidencia de ejecución y budgets relevantes;
- proveedor o emulador certificado para cada claim que se publica;
- ejecución sobre el mismo SHA candidato, sin worktree sucio;
- JUnit/JSON/logs saneados, hash de resultados, exit code y limpieza;
- ausencia de P0/P1 abierto que afecte al contrato de esa familia.

Si falta una celda, el estado correcto es partial, in_progress o blocked; no se
crea una excepción textual para convertirla en PASS.

## 5. Calendario diario hasta el candidato técnico

Los estados de esta tabla se actualizan al cerrar cada día. Las fechas futuras
son objetivos de trabajo, no evidencia de que ya se haya ejecutado nada.

| ID | Fecha | Foco de construcción y pruebas | Entregable y criterio de cierre |
| --- | --- | --- | --- |
| D00 | 14 nov | Verdad, alcance, ledger, validador y protocolo de handoff | Plan y ledger válidos; 13 familias y 10 gates definidos; sin incremento de familia |
| D01 | 15 nov | Frontera de candidato: git archive, manifest, digest y sandbox limpio | Candidato reproducible desde SHA, sin leer artefactos no rastreados; tests del selector |
| D02 | 16 nov | Baseline técnica: formato, lint, tipos, contratos, suite Python y Web | Baseline actual exacta; primer grupo rojo corregido o bloqueo reproducible |
| D03 | 17 nov | P1: workspace/project, identidad de proyecto y rutas CRUD | Contratos y persistencia P1 cubiertos; evidencia de creación/lectura/errores |
| D04 | 18 nov | P1: autorización, aislamiento, Git/source control y restart | Tests W-A/W-B, actor viewer/editor, reinicio y redacción pasan |
| D05 | 19 nov | P1: Studio, SDK/CLI, Bundle y jornada completa | Recibo P1 exact-SHA; cerrar P1 solo si todas las celdas pasan |
| D06 | 20 nov | P13: bearer/auth, secrets, clasificación y policy fail-closed | Inventario de seguridad ejecutable y pruebas positivas/negativas |
| D07 | 21 nov | P13: audit, redaction, aislamiento, scans y recuperación | Recibo P13 exact-SHA; cerrar P13 solo con seguridad y auditoría completas |
| D08 | 22 nov | P2: HTTP/REST, validación, allowlist, timeouts y paginación | Contrato de conector y errores deterministas con datos sintéticos |
| D09 | 23 nov | P2: JDBC/PostgreSQL, transacciones, schemas y límites | Perfil PostgreSQL real local y persistencia/reopen verificados |
| D10 | 24 nov | P2: S3/Azure/Ozone o emuladores certificados, digest y cleanup | Cada proveedor reclamado tiene perfil ejecutado; los no disponibles quedan bloqueados |
| D11 | 25 nov | P2: retry, idempotencia, backoff, fallos y Studio/SDK/CLI | Recibo P2; cierre solo de los claims realmente certificados |
| D12 | 26 nov | P3: lakehouse metadata, SQL compiler y conexión al motor | Contrato SQL y límites de consulta con persistencia |
| D13 | 27 nov | P3: ejecución, cancelación, permisos, resultados y restart | E2E API/SDK/Studio con fallo y recuperación |
| D14 | 28 nov | P3: integración de proveedor, Bundle y regresión completa | Recibo P3; sin cierre si el motor real o el round-trip faltan |
| D15 | 29 nov | P4: notebooks, editor SQL, pipelines y transforms | Autoría persistente y validación de payloads |
| D16 | 30 nov | P4: worker, DAG, retry/cancel, artefactos y lineage | Ejecución durable, errores saneados y evidencias correlacionadas |
| D17 | 01 dic | P4: PostgreSQL/Spark/SDP según claim, UI y SDK/CLI | Perfiles reales disponibles ejecutados; gaps separados de mocks |
| D18 | 02 dic | P4: jornada completa y regresión | Recibo P4 exact-SHA; cerrar únicamente con backend y Studio |
| D19 | 03 dic | P5: planner, cron, dependencias y estado durable | Scheduler determinista y persistencia después de reopen |
| D20 | 04 dic | P5: restart, misfire, cancelación, notificaciones y límites | Fault injection y recovery pasan sin doble ejecución |
| D21 | 05 dic | P5: jornada API/Studio/worker y regresión | Recibo P5; cierre solo con evidencia PostgreSQL/operador aplicable |
| D22 | 06 dic | P6: catálogo, assets, revisiones, búsqueda y permisos | Persistencia de metadatos y aislamiento por proyecto |
| D23 | 07 dic | P6: lineage, ontology y knowledge graph, RQL | Subgrafo, tipos, relaciones, autorización y round-trip |
| D24 | 08 dic | P6: jornada completa, UI, SDK/CLI y recuperación | Recibo P6 exact-SHA; cerrar con graph/catalog integrado |
| D25 | 09 dic | P7: quality contracts, checks, thresholds y datos inválidos | Contratos versionados, ejecución y resultados reproducibles |
| D26 | 10 dic | P7: lineage/evidence, alertas, retry y reportes | Recibo P7; cierre si falla cerrado, recovery y gobernanza pasan |
| D27 | 11 dic | P8: ML clásico, datasets, training, registry y artefactos | Digest, límites, persistencia y reproducibilidad |
| D28 | 12 dic | P8: promotion, serving, rollback, drift y Studio | Recibo P8; sin GenAI; cerrar solo con journey completo |
| D29 | 13 dic | P10: semantic models, metrics, joins y compiler | Persistencia, parámetros, autorización y ejecución |
| D30 | 14 dic | P10: dashboards, tiles, Bundle e import/export | Recibo P10; round-trip sin pérdida y UI/API coherentes |
| D31 | 15 dic | P11: Kafka, offsets, checkpoints, microbatches y sink | Consumo bounded, idempotencia y checkpoint durable |
| D32 | 16 dic | P11: broker real, poison, replay, reset/resume y UI | Recibo P11 exact-SHA; cerrar con fallos y recuperación |
| D33 | 17 dic | P12: métricas, eventos, instrumentación y alert state machine | Telemetría persistente y transiciones pending/firing/resolved |
| D34 | 18 dic | P12: budgets, coste real/estimado, tags, anomaly y policy | W-A/W-B, deny-new-work y redacción de costes |
| D35 | 19 dic | P12: Monitoring Studio, SDK/CLI, notificaciones y regresión | Recibo P12; cerrar con operación observable de extremo a extremo |
| D36 | 20 dic | P14: Compose, health, migraciones, instalación y clean install | Instalación desde artefactos y migración reversible |
| D37 | 21 dic | P14: backup/restore, upgrade/rollback, restart y Helm si aplica | Recibo P14; cerrar solo con recuperación exacta y cleanup |
| D38 | 22 dic | Candidato final: todas las familias, diez gates, supply chain, regresión | Paquete técnico final; 13/13 solo si los 13 recibos pasan; GO sigue sujeto a revisión humana |

Si un día termina antes de cerrar su objetivo, el siguiente día no salta al
tema posterior: reproduce el fallo, corrige la causa y vuelve a ejecutar los
gates afectados. La fecha es una guía de capacidad, no permiso para declarar
PASS incompleto.

## 6. Matriz de aceptación por familia

| Familia | Camino obligatorio | Fallos y recuperación | Evidencia de cierre |
| --- | --- | --- | --- |
| P1 | workspace -> project -> source -> Studio/API/SDK/CLI | tenant cruzado, viewer, restart, Bundle | family-P1.json + JUnit + manifest |
| P2 | connector -> ingest -> metadata/data -> provider profile | timeout, retry, digest, duplicate, provider unavailable | family-P2.json + provider receipts |
| P3 | lakehouse/table -> SQL plan -> execute -> result | invalid SQL, cancellation, permission, reopen | family-P3.json + query/log evidence |
| P4 | author -> DAG/notebook -> worker -> artifact/lineage | retry, cancel, worker restart, bad input | family-P4.json + execution evidence |
| P5 | schedule -> dispatch -> run -> notify | misfire, duplicate, restart, durable status | family-P5.json + scheduler evidence |
| P6 | asset/catalog -> revision -> lineage/graph/RQL | forbidden edge, stale revision, reopen | family-P6.json + graph/bundle evidence |
| P7 | contract -> check -> result -> report/lineage | threshold fail, retry, malformed data | family-P7.json + quality evidence |
| P8 | dataset -> train -> registry -> promote/serve/rollback | digest mismatch, drift, deadline, restart | family-P8.json + artifact/model evidence |
| P10 | model -> metric -> query -> tile/dashboard -> bundle | bad parameter, scope leak, import rollback | family-P10.json + semantic evidence |
| P11 | stream -> checkpoint -> batch/sink -> lag/replay | poison, oversized, reset/resume, duplicate | family-P11.json + broker evidence |
| P12 | metric/event -> alert -> notification -> budget policy | cooldown, ack, W-A/W-B collision, delivery error | family-P12.json + observability evidence |
| P13 | auth -> policy -> secret -> audit/redaction | missing token, wrong scope, secret leak, fail closed | family-P13.json + security evidence |
| P14 | install -> migrate -> run -> backup/restore -> upgrade | crash/restart, rollback, corrupted backup, cleanup | family-P14.json + operations evidence |

## 7. Diez gates de release

Estos gates son contadores de preparación, no sustituyen los recibos de las
familias:

| ID | Gate | Condición PASS |
| --- | --- | --- |
| G01 | Identidad del candidato | SHA, archive, artefactos instalados y manifests coinciden |
| G02 | Suite de calidad | formato, lint, tipos, contratos y suite Python/Web del SHA pasan |
| G03 | Jornadas end-to-end | cada familia tiene jornada candidate-bound |
| G04 | Seguridad | auth, secrets, redaction, audit, scans y negative paths pasan |
| G05 | Instalación y plataformas | clean install y matriz soportada ejecutadas sin source leakage |
| G06 | Persistencia y recuperación | backup/restore, restart, upgrade/rollback y cleanup pasan |
| G07 | Proveedores | cada claim publicado tiene proveedor real o emulador permitido y recibo |
| G08 | Supply chain | SBOM, provenance, digest, licencia mecánica y agregación íntegra |
| G09 | UI y operación | rutas, accesibilidad automatizada, budgets, observabilidad y journeys |
| G10 | Expediente de release | JSON/JUnit/logs, versionado, changelog y handoff completos |

Los asuntos exclusivamente humanos se registran dentro de G08/G10 como
pending-human-review; nunca se convierten en PASS automático.

## 8. Estructura de evidencia y handoff

Cada cierre usa estas rutas:

- docs/qualification/daily/YYYY-MM-DD-Dxx.json: recibo diario estructurado;
- docs/qualification/handoffs/YYYY-MM-DD.md: handoff completo al siguiente agente;
- docs/qualification/families/family-Px-SHA7.json: recibo de familia;
- docs/qualification/candidates/candidate-SHA7.json: identidad y artefactos;
- docs/product/ronin-daily-progress.json: ledger visible y único de progreso;
- docs/product/RONIN_DAILY_BUILD_TEST_PLAN.md: calendario y criterios.

El handoff debe contener exactamente:

1. SHA local y SHA remoto confirmado;
2. estado de Git y lista de rutas modificadas;
3. estado de las cuatro métricas;
4. comandos ejecutados, duración, passed/failed/skipped y artefactos;
5. cambios de producto y contratos;
6. fallos reproducibles, bloqueos reales y lo que no se pudo ejecutar;
7. la primera orden que debe ejecutar el siguiente agente;
8. objetivo, criterios y comandos de cierre de la siguiente fecha;
9. prohibiciones vigentes: no Actions, no ramas/worktrees, no borrar artefactos
   del usuario, no subir secretos y no reutilizar evidencia de otro SHA.

El siguiente agente no necesita preguntar qué hacer: si el handoff dice FAIL o
BLOCKED, empieza reproduciendo el comando indicado; si dice PASS, ejecuta el
smoke de recepción y continúa con la fecha siguiente.

## 9. Higiene y retención del repositorio

El repositorio conserva únicamente documentación que tiene una función actual:

- contratos, alcance, arquitectura, runbooks, inventario de casos, checklist de
  release y el plan diario;
- recibos nuevos bajo daily, families, candidates y handoffs;
- assets usados por README, Studio o el diseño vigente.

Los recibos fechados PHASE de las pasadas anteriores, prototipos sin consumidor
y duplicados de assets se eliminan de main cuando dejan de ser la fuente de
 trabajo. Siguen recuperables en el historial Git si una auditoría los
 necesita; no se usan como evidencia de un candidato nuevo.

Los sandboxes, cachés, entornos instalados, coverage shards, reports, ZIPs y
directorios de resultados viven fuera del árbol versionado y están ignorados
explícitamente. Un candidato se construye desde git archive y no necesita
 conservar copias de ejecuciones anteriores dentro del repo.

## 10. Comandos del ciclo diario

    python -m tools.ronin_daily_progress --check
    python -m tools.ronin_daily_progress --report
    git status --short --branch
    git rev-parse HEAD

Para cerrar un día PASS, el agente añade solo las rutas del día:

    git add docs/product/RONIN_DAILY_BUILD_TEST_PLAN.md docs/product/ronin-daily-progress.json
    git add docs/qualification/daily docs/qualification/handoffs tools tests
    git commit -m "phase: Dxx <resultado>"
    git push origin main
    git ls-remote origin refs/heads/main

El SHA de ls-remote debe coincidir con git rev-parse HEAD. Si no coincide, el
handoff es BLOCKED y no se anuncia cierre remoto.

## 11. Regla de fracaso y replanificación

- Un fallo reproducible de código se corrige en la misma fase; el test se
  ejecuta de nuevo y se conserva el primer fallo en el recibo.
- Un fallo de infraestructura se aísla con un comando mínimo y se marca
  BLOCKED solo si el perfil no puede existir en el entorno autorizado.
- Un proveedor externo sin credenciales o servicio real no se simula para
  cerrar una certificación. Se cierra el perfil local si el claim lo permite y
  se deja el perfil externo pendiente.
- Un cambio de alcance modifica el denominador solo con una decisión normativa
  explícita y una nueva versión del ledger. P9 no entra por accidente.
- Si D02 no consigue una suite base verde, los días de familia se convierten en
  análisis/fixes de calidad hasta recuperar el baseline. No se cuentan días
  nominales como avance funcional.

## 12. Handoff inicial y estado de hoy

El cierre verificable de D00 queda registrado en el commit
a31132183f977fb3834ed5e86e6c619942cc8dc0 y en origin/main. El contador de
ejecución pasa a 1/39 días (2.56%); el contador de release no cambia:
0/13 familias y 0/10 gates. El siguiente corte operativo es D01.

El handoff de D00 vive en:

    docs/qualification/handoffs/2026-11-14.md

El siguiente trabajo, D01, comienza por construir el sandbox de candidato y
demostrar que un archivo generado desde e22819aeb3429bfe8cdd4d512b9c1a935970f426
no incluye ninguno de los artefactos no rastreados de la copia local. Hasta que
esa prueba pase, cualquier resultado de integración se considera diagnóstico y
no puede cerrar una familia.
