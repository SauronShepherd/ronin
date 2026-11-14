# RONIN — Master unificado de construcción, pruebas y release

**Revisión:** 2026-11-14
**Fuente de implementación:** este repositorio
**Rama única:** main
**Último SHA de implementación verificado:** c563d7682687f327f11d6a144d8a3b086979ab0b
**Estado:** NO-GO
**Familias Public v1 cualificadas:** 0/13 (0%)
**Días del plan diario cerrados:** 1/39 (2,56%)
**Gates de release cerrados:** 0/10 (0%)

Este es el único documento maestro de la carpeta de proyecto. El código, los
tests y los artefactos de trabajo viven en este repositorio. Los
documentos históricos no son autoridad y no pueden convertir evidencia de otro
SHA en progreso actual.

## 1. Reglas operativas no negociables

1. El objetivo actual es Scope A: 13 familias, P1-P8 y P10-P14.
2. P9 GenAI/RAG/agentes queda fuera del producto Public v1 y del denominador.
3. OIDC multiusuario, administración multiusuario, multi-worker y Kubernetes
   productivo pertenecen a Ronin Pro salvo decisión normativa posterior.
4. Solo se trabaja en main. No se crean ramas, worktrees ni PRs intermedias.
5. No se utilizan workflows hospedados ni GitHub Actions. Las pruebas y las
   subidas se ejecutan localmente y se publican con Git directo.
6. No se usa un mock para certificar un proveedor real.
7. No se incrementa ningún porcentaje por inferencia, documentación, test
   focalizado o recibo histórico.
8. La revisión humana de Navidad se mantiene pendiente y separada: licencias,
   NOTICE, claims públicos, revisión visual, seguridad final y aprobación GO.

## 2. Jerarquía de autoridad

Cuando dos documentos discrepan, se aplica este orden:

1. decisiones explícitas del usuario;
2. este master;
3. contrato vigente del repositorio;
4. plan diario y ledger de progreso;
5. recibos exact-SHA del candidato;
6. documentos históricos, análisis y snapshots.

Canon técnico actual:

- [Scope Public v1](PUBLIC_V1_SCOPE.md)
- [Matriz de capacidades](PUBLIC_V1_CAPABILITY_MATRIX.md)
- [Estado público](public-v1-status.json)
- [Plan diario operativo](RONIN_DAILY_BUILD_TEST_PLAN.md)
- [Ledger diario](ronin-daily-progress.json)
- [Checklist de decisión](RELEASE_DECISION_CHECKLIST_2026-11-03.md)
- [Plan final de release](PLAN_FINAL_RONIN_RELEASE_2026-11-03.md)
- [Inventario de casos](RELEASE_CASE_INVENTORY_2026-10-29.md)
- [Runbook manual de release/subidas](../operations/MANUAL_RELEASE_AND_UPLOAD_RUNBOOK.md)

Los documentos eliminados durante la limpieza eran copias, snapshots o recibos
de fases sin referencias externas. Los ficheros rastreados siguen recuperables
desde el historial Git del repo; los artefactos locales se enviaron a la
papelera o se eliminaron si Windows no pudo mover sus rutas generadas.

## 3. Situación real congelada

| Dimensión | Estado |
| --- | --- |
| Repositorio | este repositorio en main |
| Último cierre operativo | c563d768: handoff D00 actualizado tras la limpieza |
| Árbol Git | limpio; local y origin/main sincronizados |
| Alcance | 13 familias; P9 excluida |
| Qualification | 0/13; NO-GO |
| Implementación | varias áreas partial; no equivale a qualification |
| Release gates | 0/10 |
| Automatización remota | no usada |
| Siguiente fase | D01: sandbox de candidato desde git archive |

El repositorio es autónomo: `.git` contiene su propia historia y `main` ya no
depende de un worktree ni de un `.git` externo.

La limpieza ha dejado un fallo conocido que no se ha ocultado: el test
tests/test_public_capability_matrix.py detecta que
PUBLIC_V1_CAPABILITY_MATRIX.md y public-v1-status.json observan SHAs distintos.
Es una deuda de reconciliación del ledger, no una consecuencia de borrar
documentación y no se considera PASS hasta corregirse y repetirse.

## 4. Familias y criterio de cierre

Las familias activas son:

| ID | Familia |
| --- | --- |
| P1 | Workspace, proyecto y source control |
| P2 | Conexiones de datos e ingestión |
| P3 | Lakehouse y SQL |
| P4 | Data Engineering Studio |
| P5 | Planner y scheduler |
| P6 | Catálogo, lineage, ontología y knowledge graph |
| P7 | Data quality y contratos |
| P8 | AI/ML clásico y MLOps |
| P10 | Modelos semánticos, métricas y dashboards |
| P11 | Tiempo real y streaming |
| P12 | Observabilidad, alertas y FinOps |
| P13 | Seguridad y gobierno single-operator |
| P14 | Despliegue y operaciones |

Una familia cuenta como cualificada solamente cuando el mismo candidato
contiene:

- contrato y backend real con persistencia;
- API, SDK, CLI y Studio cuando apliquen;
- camino positivo, errores, autorización, límites, retry, cancelación,
  restart y recuperación;
- aislamiento de workspace/proyecto, secretos, redacción y auditoría;
- telemetría, evidencia y budgets correspondientes;
- proveedor real o emulador expresamente permitido para cada claim;
- recibo JSON/JUnit/logs ligado al SHA exacto;
- limpieza reproducida y ningún P0/P1 abierto que afecte al camino.

Un test verde aislado nunca cierra una familia.

## 5. Orden de construcción

El trabajo se ejecuta en esta secuencia:

| Fase | Resultado |
| --- | --- |
| D00 | alcance, ledger, validador, handoff y política de repositorio |
| D01 | sandbox reproducible desde git archive, manifest y digest |
| D02 | baseline exact-HEAD de formato, tipos, contratos y suites |
| P1/P13 | control plane, source control, permisos, secrets y auditoría |
| P2/P3 | conectores, ingestión, lakehouse, SQL y recuperación |
| P4/P5 | authoring, workers, pipelines y scheduler durable |
| P6/P7 | catálogo, graph, lineage, quality y contratos |
| P8 | ML clásico, artefactos, promoción, serving y rollback |
| P10 | semantic models, métricas, dashboards y Bundle |
| P11 | Kafka, checkpoints, sink, poison, replay y resume |
| P12 | métricas, alertas, budgets, costes y Monitoring Studio |
| P14 | instalación, migración, backup/restore, upgrade y rollback |
| Final | candidato exacto, diez gates y expediente para revisión humana |

El calendario diario completo, con objetivos D00-D38, está en el [plan diario
operativo](RONIN_DAILY_BUILD_TEST_PLAN.md).

## 6. Modelo de pruebas

Cada fase ejecuta las capas que correspondan:

1. unitarias y propiedades;
2. contratos API/OpenAPI/SDK/CLI;
3. integración SQLite/PostgreSQL y servicios reales;
4. E2E de API, worker y Studio;
5. seguridad negativa, aislamiento, secretos y redacción;
6. restart, cancelación, retry, replay, backup y rollback;
7. UI, accesibilidad automatizada y revisión visual cuando corresponda;
8. rendimiento, límites, budgets y observabilidad;
9. proveedor certificado, sin sustituirlo silenciosamente por mock;
10. regresión completa del mismo candidato.

Cada evidencia registra comando, entorno, SHA, resultado, duración, artefactos,
hashes y cleanup. Un skip obligatorio o un proveedor no disponible produce
BLOCKED, nunca PASS.

## 7. Diez gates de release

| ID | Gate | Condición |
| --- | --- | --- |
| G01 | Identidad del candidato | SHA, archive, manifests y artefactos coinciden |
| G02 | Calidad | formato, lint, tipos, contratos y suites pasan |
| G03 | Jornadas E2E | cada familia tiene jornada candidate-bound |
| G04 | Seguridad | auth, secrets, audit, redaction y scans pasan |
| G05 | Instalación/plataformas | instalación limpia sin source leakage |
| G06 | Persistencia/recuperación | restore, restart, upgrade y rollback pasan |
| G07 | Proveedores | todos los claims tienen perfil verificable |
| G08 | Supply chain | SBOM, provenance, digest y licencia mecánica |
| G09 | UI/operación | Studio, accesibilidad, observabilidad y budgets |
| G10 | Expediente | JSON/JUnit/logs, versión, handoff y límites completos |

El estado global solo puede ser GO con 13/13 familias, 10/10 gates, candidato
exacto y revisión humana completada.

## 8. Progreso reproducible

El ledger oficial de ejecución es:

    docs/product/ronin-daily-progress.json

Comandos de consulta:

    cd .
    python -m tools.ronin_daily_progress --check --report
    git status --short --branch
    git rev-parse HEAD
    git ls-remote origin refs/heads/main

Los contadores se muestran siempre separados:

- familias: qualification de producto;
- días: avance del plan diario;
- gates: preparación técnica del release;
- tareas: implementación verificada, una vez baselinado el inventario.

## 9. Handoff diario

Cada cierre deja un handoff en:

    docs/qualification/handoffs/YYYY-MM-DD.md

Debe incluir SHA local/remoto, estado Git, métricas, comandos, resultados,
artefactos, fallos, bloqueos, primera orden del siguiente agente y criterio de
cierre. El agente siguiente empieza reproduciendo el comando del handoff.

## 10. Commit y subida manual

Una fase solo se cierra si sus pruebas pasan y el commit se publica directamente
en main:

    git add <rutas exactas de la fase>
    git diff --cached --check
    git commit -m "phase: <id> <resultado>"
    git push origin main
    git rev-parse HEAD
    git ls-remote origin refs/heads/main

Si los dos últimos SHA no coinciden, la fase queda BLOCKED. No se usan Actions,
worktrees, ramas auxiliares ni evidencias de una ejecución anterior.

## 11. Higiene del proyecto

La carpeta externa contiene solo este repositorio. Los históricos, análisis,
sandboxes, entornos, logs, coverage, ZIPs, reports y copias completas de repo
no son fuente del producto y no se conservan aquí.

El repositorio interno mantiene su propia higiene y su .gitignore evita que
vuelvan a entrar candidate sandboxes, coverage shards, resultados, builds y
artefactos de instalación.

## 12. Próximo trabajo

D01 debe implementar el sandbox limpio desde el SHA actual. Debe demostrar que:

1. se genera desde el commit exacto;
2. excluye todo fichero no rastreado;
3. el digest y el manifest son reproducibles;
4. los comandos pueden recibir el SHA aunque el sandbox no tenga .git;
5. cualquier cambio del archive o manifest falla cerrado.

D01 no incrementa familias. Después se ejecuta D02 y se corrige el primer grupo
rojo de la baseline antes de iniciar cierres P1/P13.

**Estado final de este master:** 0/13 familias, NO-GO, revisión humana pendiente
para Navidad y ejecución autónoma obligada por el plan diario.
