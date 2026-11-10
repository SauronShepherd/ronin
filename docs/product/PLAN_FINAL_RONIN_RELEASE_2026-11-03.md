# Ronin — plan de construcción, pruebas y decisión de lanzamiento

**Corte inicial:** 29 de octubre de 2026; ejecución actualizada el 30 de octubre de 2026
**Hora objetivo de lanzamiento:** 3 de noviembre de 2026, 09:00 (Europe/Madrid)
**Rama de este documento:** `20261029`
**Candidato revisado:** `f9a0456ab7df3e2bb77247d54b4336fca64903b0` (`main`, idéntico a `origin/main` al revisar)

**Nota de ejecución:** la evidencia de las secciones 1–2 es la fotografía base tomada sobre ese SHA. El trabajo actual se realiza en el worktree `20261029`; su SHA de código cambia y requiere ejecutar de nuevo todos los gates de candidato antes de emitir GO.

## 1. Objetivo y reglas de alcance

La hoja de decisión breve y el ledger accionable de gates están en
[`RELEASE_DECISION_CHECKLIST_2026-11-03.md`](RELEASE_DECISION_CHECKLIST_2026-11-03.md).
Es una vista conservadora del mismo plan; no sustituye los requisitos
detallados ni la evidencia candidate-bound.

Este documento convierte en trabajo calendarizado los dos adjuntos —`ronin_master_entrega_20261029.md` y `RONIN_PUBLIC_V1_100_PERCENT_BUILD_PLAN.md`— y la situación observada en el repositorio y GitHub. Los adjuntos son material de análisis; las decisiones directas del usuario y el contrato de producto vigente determinan el alcance.

El producto que se evalúa para publicar es una plataforma gratuita, open-source y local para aprender, experimentar y emular flujos representativos de plataformas comerciales. La emulación no equivale a compatibilidad completa ni a soporte de producción.

Decisiones de alcance que deben respetarse en todas las fases:

- **Ronin no incluye GenAI, RAG, agentes integrados ni invocación de modelos generativos, en ninguna edición.** Las skills para coding agents son instrucciones portables que se usan desde agentes externos; Ronin no aloja ni invoca esos agentes.
- **Public v1 y el posible MVP son de operador único y no incluyen funciones multiusuario.** Ronin Pro y cualquier alcance multiusuario quedan fuera de este plan; no se construirán ni anunciarán aquí flujos OIDC, membresías, invitaciones o administración de usuarios.
- Sí se prueba ML clásico y reproducible, sin runtime GenAI.
- Se prueba infraestructura local: Docker Compose, emulador cloud local y el perfil Helm single-node de Kubernetes. Esto no promete nube real, Kubernetes de producción, HA ni garantías operativas de producción.
- La política actual del usuario es **sin CI**. Todas las comprobaciones de lanzamiento se ejecutan manualmente, se registran contra un SHA exacto y requieren revisión humana. El publicador manual de alias de Docker Hub no es un gate de calidad.
- Para el alcance vigente, Public v1 tiene **13 familias**: P1–P8 y P10–P14. P9 no forma parte del denominador ni del backlog.

El adjunto de construcción, revisado el 25 de octubre en `4686571…`, plantea 14/14 e incluye GenAI y multiusuario. GenAI no forma parte de Ronin; multiusuario corresponde al alcance Pro y se excluye de esta release pública. Esos requisitos no entran en el denominador de Public v1. El adjunto también trata CI como activa; esa descripción es histórica. El plan maestro, cuya sección 106 está fechada el 29 de octubre, es más reciente y confirma la retirada de CI.

## 2. Situación verificable de partida

| Tema | Evidencia observada | Consecuencia para el plan |
|---|---|---|
| Git | `main`, `origin/main` y rama local `20261029` apuntan a `f9a0456a`; árbol limpio antes de crear este documento. GitHub muestra solo `main`, 0 PR abiertas y 14 issues abiertas. | El documento se trabaja en `20261029`; cualquier cambio posterior invalida resultados del SHA anterior. |
| GitHub Actions | Solo existe `.github/workflows/publish-dockerhub.yml`, disparado manualmente. No es CI ni qualification. El plan maestro registra cero runs en `f9a0456a`. | No atribuir ningún check verde al candidato. La ruta de release es manual. |
| Estado Public v1 | `docs/product/public-v1-status.json` declara `incomplete`, `blocked`, `0/13` y `release_ready=false`, pero observa `cca60214…`, anterior al candidato. Varios resúmenes todavía afirman que hay workflows de CI activos. | Actualizar SHA y texto descriptivo; conservar `0/13` hasta que cada journey esté cualificado. |
| Matriz de capacidades | `PUBLIC_V1_CAPABILITY_MATRIX.md` aún muestra el corte `4542002c` y resultados de otra pasada. | Reconciliar métricas y evidencias con `f9a0456a`; no reutilizar PASS de otro SHA. |
| Build plan adjunto | Revisado el 25/10 sobre `4686571…`; exige GenAI/multiusuario y presenta 14 familias. | Usar sus tareas comunes solo después de filtrarlas por el alcance vigente. |
| Plan maestro adjunto | 305 IDs de caso únicos + 25 rutas activas = 330 entradas planificadas; 28 rutas históricas (333 IDs caso/ruta); 171 bloqueos y 198 tareas según §106. Son conteos documentales, no resultados. | Usar inventario completo, conservar IDs, filtrar por alcance y no presentar el catálogo como ejecución. |
| Suite Python | Último resultado anotado para este SHA: **4104 passed, 74 skipped, 1 failed** en 1133 s. Falló `tests/test_quality_runtime.py::test_custom_python_expression_uses_bounded_sandbox`; la ejecución aislada posterior pasó 1/1. | La flakiness sigue sin resolver. La pasada aislada no sustituye al full suite verde. |
| Escaneo de seguridad | `make check` no ejecuta un detector de secretos, auditor de vulnerabilidades Python ni escáner de la imagen Docker. Hay `.gitleaks.toml`, pero no un carril de release local que consolide esos resultados. | Definir versiones y comandos manuales; no afirmar que `make check` cubre seguridad. |
| Empaquetado | `pyproject.toml` declara `version = "0.0.0"`; README y runbook hablan de alpha/v0.1; Helm declara `0.1.0`. GitHub no tiene una release de Public v1 según el maestro. | Resolver versión, nombre del producto, artefactos y tipo de lanzamiento antes de crear candidato. |
| Release evidence | Los perfiles ya usan gates locales y el emisor acepta intervalos reales de ejecución; los productores/validadores CycloneDX y provenance se implementaron con pruebas positivas/negativas. | Falta construir artefactos del candidato final y generar/validar los diez recibos contra el mismo SHA y digests. |
| Mutation testing | `docs/quality/MUTATION_CAMPAIGN_FINAL.md` registra una campaña cerrada y prohíbe repetir `make mutation` o equivalente sin decisión explícita y un nuevo plan de campaña. | No ejecutar mutation testing ni tratar #47 como gate automático de release; reconciliarlo como decisión diferida y continuar con regresión normal. |
| SBOM/provenance | El productor nuevo genera CycloneDX y provenance separados; el validador coteja subjects/digests con identidad de artefactos y las pruebas positivas/negativas están implementadas. | No se afirma PASS hasta construir wheel, sdist e imagen del candidato final y verificar los bytes exactos. |
| Interfaz | La navegación habitual de Playwright usa servidor estático/mocks; además existe `product-live`, que levanta Ronin, PostgreSQL y Redpanda y prueba las 25 rutas activas contra APIs reales. La fotografía inicial de este análisis pasó 28/28; la reejecución ampliada del §11 pasó 29/29. | Mantener separada la evidencia mock; revisar visualmente el candidato final y completar journeys P1–P14, no solo las rutas de lectura. |
| Kubernetes | Existe Helm chart con `single-node` como default y configuración multiusuario descrita para Ronin Pro. | Cualificar solo el perfil single-node de operador único en Public v1; el perfil Pro no se construye ni anuncia en esta release. |
| Cloud Studio / Floci | Se corrigió el falso `status=passed`: el gate valida código/estado final de plan/apply/refresh/destroy y los tests cubren fallos/recursos residuales. Terraform local es 1.16.2, distinto de 1.13.5 requerido. | Sin la versión fijada y el emulador no hay qualification live; instalar/usar toolchain exacto y ejecutar con fixtures aislados. |

No se ejecutaron comandos de prueba al preparar este plan. Los resultados citados son antecedentes anotados para el SHA y no constituyen una nueva qualification.

### Triaje de las 14 issues abiertas consultadas el 29/10

No se cambió ni cerró ninguna issue. Se aplican las decisiones directas del mantenedor: sin CI, sin GenAI y sin multiusuario en Public v1.

| Issue | Prioridad / asunto | Decisión para el plan |
|---|---|---|
| #22 | P0 · límites de ejecución, publicación y contratos de Job/Run | Mantener como bloqueo P0 hasta revisar tags inmutables, dependencia de publicación y contrato estable. |
| #43 | P1 · provenance y reproducibilidad exactos | Ejecutar productores/validadores sobre los artefactos finales; historial de otro SHA no acredita el actual. |
| #47 | P1 · mutation testing | Diferir; campaña congelada. No ejecutar mutmut ni reabrir la campaña sin decisión/plan explícitos. |
| #57 | P1 · journey v0.1 end-to-end | El código existe, pero requiere acceptance Docker 15/15 y evidencia del mismo candidato limpio. |
| #58 | P1 · licencias, dependencias y NOTICE | Requiere inventario real más revisión humana; mantener bloqueada la aprobación legal. |
| #59 | P2 · journey open-table | Roadmap posterior a v0.1; no ampliar el alcance actual. |
| #63 | P1 · protección de main/tags | Verificar antes de crear el tag; configuración remota y sus responsables siguen pendientes. |
| #69 | P2 · regresiones de rendimiento | Añadir/ejecutar mediciones según budgets y conservar resultados; no declarar cubierto por solo tres guards agregados. |
| #96 | P1 · gate estricto de acceptance | Ejecutar localmente `tools/run_docker_qualification.ps1`; no reactivar workflows por esta issue. |
| #102 | P1 · coverage de herramientas de release | Mantener coverage-tools y negativos del gate; ejecutar contra el estado final. |
| #115 | P2 · CPU/memoria observados por celda | Diferir la calificación de workload Docker/coste de medición hasta ejecución real documentada. |
| #199 | P1 · restaurar CI | Diferido por conflicto directo con la política vigente del usuario: no hay CI. No implementar ni anunciar CI. |
| #201 | P2 · presupuestos operacionales | Medir contra el candidato final; no reutilizar benchmarks históricos. |
| #202 | P1 · activar pasos Compose/evidence de acceptance | Revisar skips/casos del journey y conservar el gate estricto; el resultado local de esta pasada no permite cerrar la issue por sí solo. |

## 3. Criterios de cierre y decisión GO/NO-GO

Un check solo cuenta como **PASS** si se ejecutó contra el candidato indicado, produjo la evidencia exigida y no tuvo skips, xfails, tests ausentes ni resultados inesperados en el ámbito obligatorio. `implemented`, presencia de tests, screenshot de una maqueta o respuesta simulada no significan `PASS`.

### Gates técnicos

1. `make check` termina correctamente, incluidos formato, Ruff, OpenAPI, mypy, arquitectura, rutas, superficie Studio, presupuestos web, contratos, suite Python, coberturas declaradas y pruebas de rendimiento.
2. La repetición completa resuelve la prueba flaky de sandbox; no basta con repetir únicamente el test que falló.
3. La acceptance v0.1 ejecuta **15/15** pasos en Docker con cero skip/xfail/fallo/error/ausente, mediante `tools/run_docker_qualification.ps1` y `tools/v01_acceptance_gate.py`.
4. Las pruebas PostgreSQL usan PostgreSQL real efímero; las pruebas de API/UI funcional usan la app Ronin levantada. Las suites con mocks se reportan aparte.
5. Todas las 25 rutas del Studio instalado funcionan en el perfil soportado; las rutas y mutaciones de producto muestran estados correctos y se verifican con API real.
6. `helm lint`, render y smoke en cluster local temporal validan únicamente el chart single-node; el artefacto/values públicos no exponen `server.multiUser` (separar el perfil Pro si comparte chart).
7. Floci ejecuta el recorrido cloud local con recursos sintéticos, límites y limpieza confirmados.
8. Los diez gates del perfil de release tienen recibos completos contra el mismo commit y artefactos; el agregador devuelve un veredicto `passed`.
9. **13/13 familias** P1–P8 y P10–P14 tienen journey end-to-end completo y evidencia del candidato. No se calcula porcentaje de implementación global a partir del 0/13 de qualification.
10. Revisión de seguridad, dependencias/licencias, secretos, SBOM/provenance, documentación, instalación limpia y rollback no dejan bloqueos P0/P1 abiertos.

### Trazabilidad de las 13 familias activas

La numeración sigue `docs/product/PUBLIC_V1_SCOPE.md`. Un test aislado o una pantalla existente no cualifica una familia: cada fila requiere el journey integrado y sus evidencias contra el mismo SHA.

| Familia | Recorrido/evidencia mínima | Fases principales |
|---|---|---|
| P1 Workspaces, projects y source control | Crear/importar/exportar proyecto y manifiestos; revisar secretos por referencia, identidad de revisión y audit events. | 4, 11, 12 |
| P2 Connections e ingestion | Conectar PostgreSQL y archivos; discover, preview, validar, sync/incremental, fallos y reintentos. | 5, 12 |
| P3 Lakehouse y SQL | Tablas/formats soportados, evolución declarada, SQL acotado, paginación y evidencia. | 5 |
| P4 Data Engineering Studio | Editar y ejecutar notebook/pipeline por UI/API, confirmar revisión ejecutada, outputs/lineage. | 6, 12 |
| P5 Planner y scheduler | DAG, trigger manual/cron/event según claim, retry/backfill/cancelación y recuperación durable. | 6, 10 |
| P6 Catalog, lineage, ontology y graph | Inventario persistente, lineage, tipos/null/límites, query/import/replay/rollback. | 7 |
| P7 Data quality y contracts | Contratos/checks built-in/custom, límites de sandbox, severidad y evidencia integrada en assets/run. | 8, 9 |
| P8 ML Lab clásico | Dataset/snapshot, train/evaluate/register/infer/drift y artefactos reproducibles; sin GenAI. | 8 |
| P10 Semantic models, metrics y dashboards | Definiciones, joins/métricas, filtros, dashboard, export/import y fixture independiente. | 9, 12 |
| P11 Streaming y real time | Ingesta, offsets/checkpoints, backpressure/replay/sink y health/lag en broker local. | 9, 10 |
| P12 Observability, alerts y FinOps | Logs/métricas/alertas/presupuestos muestran resultado operativo; redacción y transiciones OK/WARN/ERROR. | 9, 12 |
| P13 Security y governance, single-operator | Auth/scope/secret handling/audit y pruebas negativas de autorización; sin multiusuario Pro. | 4, 10, 13 |
| P14 Deployment y operations | Compose, instalación, upgrade/backup/restore/runbooks y Helm single-node según claims. | 3, 10, 13 |

### Reconciliación del perfil de diez gates sin CI

El perfil `release_required` enumera diez gates: `local-quality`, `security`, `status-consistency`, `docker-qualification`, `browser`, `a11y`, `installed-artifact`, `sbom-provenance`, `license` y `artifact-identity`. Antes de emitir un veredicto se debe:

1. Documentar que el usuario mantiene la política sin CI y reconciliarla con la issue abierta #199 y el runbook.
2. **Implementado en el código de este corte:** los perfiles locales sustituyen `ci` por `local-quality`; no hay un gate de merge que requiera CI.
3. **Implementado en el emisor/agregador existentes:** reciben timestamps reales, perfil explícito, hashes de reportes incluso en fallos, validan commit/perfil y verifican frescura, existencia e integridad de los artefactos. Las pruebas negativas cubren esos rechazos; el recibo de estos cambios aún depende de ejecutar el suite final sobre el SHA resultante.
4. Mantener pruebas negativas para gate faltante/duplicado, SHA distinto, fechas inválidas/futuras o evidencia de más de 24 h, recibo `skipped/blocked/failed`, evidencia ausente o alterada, digest incorrecto y artefacto de release distinto; todas deben impedir GO.
5. Emitir los recibos con el emisor local solo después de ejecutar los comandos, validar el bundle con `release_evidence.py`, agregarlo con `aggregate_release_evidence.py` y revisar/firmar el expediente manualmente.

Mapeo de los diez recibos para **Public v1**: `local-quality` → `make check`, dependency surfaces y validación/empaquetado de skills externas; `security` → informes Gitleaks, pip-audit y Trivy; `status-consistency` → ledger, matriz y `capability-status-check` del mismo SHA; `docker-qualification` → JUnit y JSON estricto 15/15; `browser` → JUnit/logs live y evidencia de las 25 rutas; `a11y` → informe UI accessibility; `installed-artifact` → smoke de wheel/sdist instalados; `sbom-provenance` → SBOM, provenance y validación de digests; `license` → inventario, policy, NOTICE y revisión humana; `artifact-identity` → manifiesto y digests de wheel, sdist e imagen.

Si se decide lanzar el MVP, implementar un perfil separado `local_mvp_required` con las mismas diez categorías de evidencia y límites explícitos de scope: `status-consistency` cualifica 7/7 journeys y 12 rutas MVP; `docker-qualification` ejecuta una acceptance dedicada de los 7 journeys MVP, no presupone 15/15 pasos v0.1; `browser` requiere al menos 14 casos live y las 12 rutas MVP sin mocks/skips; `a11y` cubre esas 12 rutas. Seguridad, artefacto instalado, SBOM/provenance, licencia y artifact identity siguen siendo gates obligatorios y candidate-bound. No reutilizar recibos `release_required` si su alcance o suite no coincide con el MVP, y nunca presentar el resultado MVP como 13/13 Public v1.

Si no se reconcilia el contrato #199 / el agregador, o la versión y alcance de release siguen ambiguos, **NO-GO**. Un lanzamiento alpha con alcance reducido es una decisión distinta; no se rebautiza automáticamente como Public v1.

### Alternativa propuesta: Ronin Local MVP

La fecha del 3/11 es un objetivo, no un criterio de aceptación. La actualización del 30/10 amplió la evidencia local: la suite Python/PostgreSQL pasó 4.322/4.322 ejecutados sin avisos de recursos; Docker pasó 23/23 y su gate estricto 15/15; UI/API live pasó 30/30 casos y ejecutó un notebook mediante un worker Docker real. Aun así, el ledger sigue en 0/13: estos chequeos no equivalen a journeys completos de las 13 familias ni a qualification de candidato limpio. Mantener Public v1 como vía principal y trabajar el núcleo común. Si el corte de calidad no se alcanza, retrasar es la opción predeterminada; considerar este MVP únicamente si su producto reducido se ve y funciona como una unidad completa.

**Identidad y alcance del MVP:** publicar un “Ronin Local MVP” con claims propios, nunca etiquetarlo como Public v1 ni como paridad con Databricks, Fabric, Dataiku o Palantir.

| Incluido en el MVP operativo | Fuera del MVP y sin claims visibles |
|---|---|
| Docker Compose limpio y persistente: API, worker/broker y PostgreSQL local; un operador local con token acotado. | GenAI/RAG/agentes integrados en Ronin; funciones multiusuario de Ronin Pro, fuera de este MVP. |
| Workspaces y proyectos de un operador; conexiones y secretos locales. | Floci/emulación cloud, Helm/Kubernetes, HA y operación de producción. |
| Ingesta real desde archivos CSV/Parquet y PostgreSQL; descubrimiento, preview y sync a un destino local soportado. | Certificación de migración o paridad con proveedores comerciales. |
| SQL read-only con parámetros y límites, más ejecución manual de pipeline/workflow. | Streaming, semantic studio, graph/RQL, FinOps, ML Studio, synthetic data y notebooks avanzados. |
| Runs, cancelación, reintento seguro, logs/eventos/evidencia y estados OK/WARN/ERROR; controles básicos de calidad y persistencia tras reinicio. | Programación avanzada, conectores no cualificados y sistemas operativos no probados. |
| Backup/restore del workspace/proyecto incluido en el alcance; tour, tutoriales y UI marrón coherente para las rutas incluidas: `home`, `workspaces`, `projects`, `data`, `ingestion`, `sql`, `workflows`, `runs`, `quality`, `alerts`, `catalog` y `settings`. | Las rutas fuera de alcance ocultas del menú MVP; ninguna tarjeta o tutorial promete una función excluida. |

**Aceptación de MVP:** 7/7 journeys completos: (1) instalación/health/auth; (2) workspace/proyecto; (3) conexión y descubrimiento de PostgreSQL/archivos; (4) ingesta y consulta SQL; (5) workflow/run/cancelación/evidencia; (6) quality/alertas OK-WARN-ERROR; (7) reinicio y backup/restore. Exigir además al menos 14 casos live sin skip (12 rutas listadas más ingestión PostgreSQL y autorización) contra API Ronin y PostgreSQL reales, sin respuestas API simuladas; logs coinciden con resultados persistidos y no filtran secretos; las 12 rutas MVP funcionan con teclado/responsive; no hay fallo obligatorio, bloqueo P0/P1, finding crítico/alto no aceptado, ni gate de release ausente. Cualificar el perfil candidate-bound `local_mvp_required` de diez gates descrito arriba y revisar licencias, SBOM/provenance y artefactos por separado. No elegir el MVP para conservar la fecha si el alcance reducido todavía se ve incompleto, inconsistente o poco pulido: también se retrasa en ese caso.

**Corte de decisión:** como tarde al cierre de Fase 10 (31/10, 23:00), Public v1 sigue solo si ya hay evidencia verde de las 13 familias, suite completa estable, Docker/PostgreSQL/live UI y no quedan P0/P1 sin dueño/mitigación. Si no, solo cambiar al MVP si el recorrido y todos sus gates ya están implementados o pueden terminarse y repetirse antes de Fase 13; el MVP debe quedar cualificado antes de cerrar el 1/11 para reservar el 2/11 a regresión y QA manual. Si tampoco llega a ese corte, retrasar. No convertir un futuro workstream, un test omitido ni una maqueta en PASS.

| Fase | Si se adopta el MVP, el trabajo se concentra en |
|---|---|
| 1 | Declarar identidad/claims MVP, excluir GenAI y multiusuario de la release pública, decidir rutas publicadas y registrar sistemas operativos admitidos. |
| 2 | Convertir el ledger a P0/P1 del journey MVP; dejar vendor, K8s/cloud y studios avanzados como diferidos con IDs y razones. |
| 3 | Compose reproducible, README de instalación limpia, paquete/imagen versionados, licencia e instalación/diagnóstico. |
| 4 | CRUD de workspace/proyecto y autorización de un solo operador. |
| 5 | Ingesta CSV/Parquet y PostgreSQL real, preview, sync y SQL read-only acotado. |
| 6 | Pipeline/workflow manual, worker real, runs, cancelación, logs y evidencia durable. |
| 7 | Catálogo/lineage mínimo necesario para explicar una tabla derivada; diferir graph/RQL/ontology. |
| 8 | Quality checks útiles y resultados legibles; diferir ML Studio, sin runtime GenAI. |
| 9 | Logs, métricas y alertas operativas OK/WARN/ERROR; diferir streaming, semantic y FinOps. |
| 10 | Compose, persistencia, backup/restore y reinicio; diferir Helm/kind/Floci. |
| 11 | Bundle/restore y validación de las skills externas; diferir certificaciones vendor y migración avanzada. |
| 12 | QA live/visual de cada ruta que permanezca en el MVP; menú y tutoriales no muestran capacidades excluidas. |
| 13 | Repetir suite MVP y los diez gates contra un SHA/artefactos únicos; no marcar 13/13. |
| 14 | Pruebas manuales, revisión de release notes y GO/NO-GO; retraso si algún criterio falla. |

## 4. Calendario de 14 fases

Las fases detallan el alcance Public v1. Si se adopta el MVP, aplicar la matriz de reducción de §3: completar lo común y las tareas explícitas para sus 7 journeys/12 rutas, registrar las funciones restantes como diferidas y no ejecutar suites de proveedores, Cloud/Kubernetes, ML, streaming o studios fuera del alcance. Esto tampoco permite anunciar esas funciones como cualificadas.

Las horas son locales de `Europe/Madrid`. La distribución respeta 14 fases: dos hoy (tarde y noche), cuatro el 30, cuatro el 31, dos bloques de jornada el 1 y dos el 2. Los bloques del 1 y del 2 incluyen subtareas con entrega de madrugada, por la mañana, por la tarde y por la noche. El 2 de noviembre queda reservado a cierre de flecos y pruebas manuales.

### Fase 1 — Jueves 29/10, tarde: alcance, fuente de verdad y corte de release

**Tareas**

- Congelar el contrato de esta release: un operador, sin GenAI integrada y sin multiusuario en Public v1, ML clásico permitido, servicios cloud simulados y Kubernetes únicamente local. Ronin Pro queda fuera de alcance. Las skills solo contienen instrucciones para coding agents externos.
- Resolver si el objetivo de publicación es Public v1 o, si no supera el corte, el “Ronin Local MVP” de §3; no crear una alpha como atajo de fecha. Confirmar versión de paquete/tag: ahora mismo `0.0.0`, README alpha/v0.1 y Helm `0.1.0` no forman una identidad de release coherente.
- Crear tabla de claims públicos: función, perfil local probado, limitaciones, dependencias opcionales, sistema operativo/Python admitidos y evidencia requerida. **Borrador creado:** [`PUBLIC_V1_RELEASE_CLAIMS_DRAFT.md`](PUBLIC_V1_RELEASE_CLAIMS_DRAFT.md); cada familia sigue bloqueada y el borrador no autoriza claims de soporte.
- Actualizar `public-v1-status.json`, `PUBLIC_V1_CAPABILITY_MATRIX.md`, build plan, README, changelog y release runbook al SHA actual; corregir afirmaciones de CI activa y retirar claims públicos de GenAI/multiusuario.
- Inventariar y quitar de las superficies publicadas de UI/API/CLI/configuración/Helm las funciones, toggles, variables `RONIN_AI_*` y referencias que expongan GenAI o multiusuario; no basta con dejarlas desactivadas. Mantener las skills externas como archivos descargables/documentación, sin runtime de agente en Ronin. No tocar código/perfiles exclusivos de Pro salvo que se hayan mezclado accidentalmente en el paquete público.
- Acordar el perfil local-only de los diez gates, la aprobación humana y la reconciliación de #199. Mantener #63 y protección de tag como decisiones operativas abiertas hasta verificarlas.
- Si el producto candidato cambia a MVP, definir el perfil independiente `local_mvp_required`, sus diez gates y la acceptance Docker/live de 7 journeys/12 rutas/14 casos; mantener `release_required` con los criterios de Public v1 y no relajar sus umbrales.
- Resolver el desacople entre el JSON propio de `generate_sbom.py` y el formato SPDX/CycloneDX más el statement separado que exige `supply_chain_evidence.py`; incorporar un caso positivo y negativos de digest, nombre de subject, commit y archivo alterado.
- Reespecificar el contrato supply-chain: hoy el validador solo comprueba que los nombres de artefacto aparezcan en `packages`/`components` y que provenance tenga sus hashes; no valida un digest por artefacto dentro del SBOM. Acordar cómo representar los subjects del wheel, sdist e imagen en SBOM estándar y actualizar productor/validador antes de emitir PASS.
- Fijar y registrar el toolchain de qualification: Python por matriz, Node/npm, Docker Engine/Compose, PostgreSQL (hoy `16.4-alpine`), Playwright/Chromium según lock, Helm/kind/kubectl, Floci/provider/Terraform, Gitleaks, `pip-audit` y Trivy. Fijar digests de imágenes base/emulador y la fecha/base de advisories; no usar `latest`. Los scanners se ejecutan manualmente, fuera de cualquier CI.
- Cambiar en `tools/emit_release_evidence.py` la terminología `workflow gate` por gate local/manual y completar la reconciliación de perfiles/tiempos descrita en §3.
- Crear un seeder idempotente para `web-tests/tests/ingestion-live.spec.mjs`: el test requiere las tablas `ui_page_accounts` y `ui_page_orders`, pero el repo no contiene un fixture que las cree. El test live no puede quedar omitido por variables o fixture ausentes.
- Añadir una suite `product-live` que recorra y ejercite las 25 rutas contra Ronin levantado y API real. El repo solo tiene hoy dos pruebas live de ingestión; Playwright habitual usa servidor estático y mocks. La nueva suite no debe devolver respuestas simuladas: las llamadas deben llegar al backend/API y registrar método, ruta, status y resultado visible.
- Configurar Playwright para aceptar `PLAYWRIGHT_OUTPUT_DIR`, `PLAYWRIGHT_HTML_OUTPUT_DIR` y `PLAYWRIGHT_JUNIT_OUTPUT_FILE`, de modo que reportes, screenshots, traces y JUnit queden fuera del checkout y en el expediente de la ejecución.
- Cambiar `Makefile` para que `agent-skills-package` acepte `AGENT_SKILLS_OUTPUT`, de modo que los ZIP externos se creen en el expediente `$EvidenceDir` y no ensucien ni sobrescriban archivos del checkout.
- Cambiar los targets `ui-installed` y `ui-a11y` para aceptar `RONIN_QUALIFICATION_OUTPUT`; escribir sus wheels fuera del checkout y usar carpetas separadas por gate para preservar artifacts y logs candidate-bound.
- Añadir a `tools/run_docker_qualification.ps1` un parámetro obligatorio de directorio de evidencia para la qualification release; conservar JUnit, salida y JSON estricto bajo un path exclusivo por candidato/ejecución, incluidos los resultados cuando la suite falla.
- Fijar Floci `2.1.0`, AWS provider `6.65.0`, la versión de Terraform y sus digests/lock; corregir `examples/cloud-studio/compose.floci.yaml` para publicar el puerto solo en `127.0.0.1`; no usar la etiqueta mutable `latest` en el expediente release.
- Cambiar `tools/cloud_studio_floci_qualification.py` para declarar `passed` solo tras validar plan/apply/refresh/destroy, código de salida y estado final vacío (`terraform state list` y refresh del emulador); añadir pruebas positivas/negativas de recurso residual y fallo de destroy.

**Cierre de fase:** alcance y tipo/versionado de release aprobados por el responsable; ninguna afirmación pública contradice el contrato. Si no hay acuerdo, registrar NO-GO y continuar solo con análisis/fixes seguros.

### Fase 2 — Jueves 29/10, noche: triaje de defectos y congelación del backlog

**Tareas**

- Repetir primero `test_custom_python_expression_uses_bounded_sandbox` aislado para recoger diagnóstico y después dentro del full suite; revisar timeout, spawn, consumo y logs antes de tocar el código.
- Reproducir la suite completa del candidato y conservar JUnit, stdout/stderr saneados, entorno y duración. La ejecución aislada previa no cierra el fallo.
- Clasificar los 305 IDs de caso y las 25 rutas activas (330 entradas planificadas; 28 rutas históricas) por prioridad, familia, disposición de alcance, entorno y criterio; enlazar IDs existentes. El inventario registra campos fuente sólo cuando están etiquetados y deja `N/D` sin inferir PASS.
- Reconciliar 14 issues abiertas; priorizar #199 (política no-CI), #96/#202/#57 (acceptance estricta), #43 (provenance), #58 (licencias), #63 (refs), #22 (arquitectura), #69/#201/#115 (presupuestos) y #102 (cobertura de herramientas). Revisar #47 con la política de `MUTATION_CAMPAIGN_FINAL.md`: dejarlo diferido y no ejecutar mutation testing sin decisión explícita y un plan nuevo. No cerrar issues por inferencia.
- Acordar responsables y definición de “P0/P1 resuelto”; registrar dependencias de Docker, PostgreSQL, Floci, kind, Helm, navegadores y credenciales de proveedores.

**Cierre de fase:** matriz de alcance/pruebas/owners disponible; falla flaky reproducida o marcada BLOCKED con causa clara; se acepta formalmente que cualquier P0 pendiente bloquea lanzamiento.

### Fase 3 — Viernes 30/10, madrugada: instalación limpia, CLI y artefactos

**Tareas**

- Construir wheel y sdist exploratorios en entorno aislado; registrar toolchain, lockfile, nombres, versiones y digests. Estos no son los artefactos finales: todos los cambios de código, lock, licencia, versión y evidence tooling se cierran antes de congelar el SHA final en Fase 13.
- Instalar ambos fuera del checkout en un virtualenv limpio; probar `ronin --help`, `ronin doctor`, `ronin validate`, `ronin plan`, `ronin skills list|validate` y `ronin skills package --output (Join-Path $EvidenceDir 'installed-agent-skills')` para evitar escribir en el checkout, además de las rutas del quickstart.
- Confirmar que los recursos web, SQL, archivos de skills externas y entrypoints se incluyen en el wheel; verificar import desde site-packages, no desde el checkout.
- Revisar instalación en CPython 3.11, 3.12 y 3.13 si forman parte de los claims; probar Windows y al menos un entorno Linux limpio. Si faltan hosts/SO, dejarlo `blocked`, no asumir compatibilidad por `requires-python`.
- Instalar `requirements-test.lock` para la suite completa: `requirements-dev.lock` es deliberadamente ligero y omite extras opcionales como PyArrow/psycopg/scikit-learn, que las pruebas integrales requieren.
- En un entorno de qualification con `requirements-test.lock`, ejecutar `python tools/license_qualification.py --write-inventory third_party/licenses-v1.json`, revisar cada paquete y completar las decisiones/rationale de `third_party/license-policy-v1.json` y NOTICE. Guardar esos cambios antes del commit candidato; no regenerar inventory ni policy después.
- Fijar `SOURCE_DATE_EPOCH` al timestamp del commit candidato, construir wheel/sdist y normalizar el sdist con `python -m tools.normalize_release_sdist`; repetir el build con el mismo toolchain y exigir digests idénticos antes de cualificar.
- Corregir la discrepancia de versión v0.1/Public v1 antes de construir el artefacto final; no reconstruir después de qualification.

**Cierre de fase:** dos artefactos reproducibles identificados por digest y smoke de instalación limpio; versión y soporte declarados sin ambigüedad.

### Fase 4 — Viernes 30/10, mañana: workspaces, proyectos, permisos y API base

**Tareas**

- Cualificar creación/lectura/actualización/archivo de workspace y proyectos, manifiestos, entorno y binding con SQLite y PostgreSQL donde esté soportado.
- Verificar autorización del operador único con token válido, inválido, ausente y scope incorrecto; lecturas y mutaciones deniegan por defecto cuando no corresponde. El token representa la instalación/operador, no una función multiusuario.
- Probar aislamiento por workspace/proyecto, idempotencia, auditoría, paginación y errores de API; comprobar que los logs no imprimen bearer tokens, DSN ni valores de secretos.
- Comparar rutas implementadas, OpenAPI, CLI, `pyronin` y cliente web; revisar compatibilidad y respuestas 400/401/403/404/409/413/422/429/500.
- Confirmar que la release pública no expone login, perfiles, configuración, endpoints ni administración multiusuario; Pro queda fuera de alcance y no se cualifica OIDC, grupos o memberships.

**Cierre de fase:** recorridos de workspace/proyecto pasan en DB elegible y el operador único no puede escapar de los scopes concedidos.

### Fase 5 — Viernes 30/10, tarde: conectores, ingestión, lakehouse y SQL

**Tareas**

- Ejecutar origen local y PostgreSQL sintético de principio a fin: descubrir, paginar, previsualizar, validar, planificar y sincronizar; comprobar checkpoints, reintentos y cancelación.
- Validar read/write solo donde el conector anuncie esa capacidad. Incluir errores de esquema, credenciales, timeout, límite de bytes y respuesta parcial; no simular un proveedor como qualification real.
- Cualificar Parquet/Arrow, DuckDB, tablas y metadata; probar Iceberg/Delta únicamente en las versiones/runtime declarados. Medir uso de memoria, bytes, filas, wall-clock y cancelación.
- Probar SQL read-only, bindings tipados, límites de filas/bytes/timeout, QueryFlux, cursores estables, paginación, evidencia durable y comportamiento de `EXPLAIN` con relación registrada y no registrada.
- Levantar Floci con el compose dedicado, nombre/volumen efímero y puerto loopback; ejecutar `tools/cloud_studio_floci_qualification.py` con fixture sintética y `--terraform`. Confirmar plan, apply, refresh, destroy, `terraform state list` vacío y cero recursos del fixture después del teardown.

**Cierre de fase:** ingestión y consulta producen datos/evidencia reproducibles; accesos fuera del registro y presupuestos excedidos fallan de forma segura.

### Fase 6 — Viernes 30/10, noche: Data Engineering, notebooks y scheduler

**Tareas**

- Crear, editar, versionar y ejecutar un pipeline/notebook desde UI y API sobre el backend local real; comprobar que el SHA/revisión ejecutada es el enviado.
- Ejecutar workflow con dependencias, parámetros, cron/timezone, retry, timeout, backfill, cancelación y evidencia de cada intento.
- Interrumpir servidor/worker en entorno aislado, reiniciar y verificar reconciliación de estado, lease/fencing, outbox, no duplicación de efectos y estado terminal veraz.
- Inspeccionar persistencia SQLite y PostgreSQL en los escenarios soportados, incluyendo estado parcial, error de proveedor y evidencia de ejecución.
- Revisar los tres skills externos para que los comandos y límites descritos correspondan a la CLI instalada; validar y empaquetar ZIP determinista. No activar agentes dentro de Ronin.

**Cierre de fase:** journey de ingestión/pipeline/notebook/run/evidencia pasa contra la app y un worker real; tras fallo no se informa éxito ficticio.

### Fase 7 — Sábado 31/10, madrugada: catálogo, lineage, graph y RQL

**Tareas**

- Registrar y descubrir assets de workspace, tablas, jobs, ML y artifacts; verificar scopes, cursores y límites de inventario.
- Seguir lineage desde fuente a tabla, pipeline, run y asset derivado; contrastar identidad y digest.
- Ejecutar query RQL/graph con filtros tipados, nulls, joins, límites, deadline, cardinalidad y aislamiento entre proyectos.
- Probar import/export de ontology, replay exacto, conflicto tardío y rollback transaccional en SQLite y PostgreSQL cuando estén soportados.
- Confirmar que fallos de inventario parcial/timeout hacen fail-closed y no convierten resultados incompletos en “todo limpio”.

**Cierre de fase:** evidencia de catálogo/lineage/query enlazada al mismo workspace/proyecto; límites y errores son visibles y reproducibles.

### Fase 8 — Sábado 31/10, mañana: Quality y ML clásico

**Tareas**

- Validar contratos built-in de null, unique, range, domain, row-count, freshness, referential y resultados históricos; ejecutar policies de bloqueo solo con jobs sintéticos.
- Probar predicados Python/SQL en sandbox: límite temporal, memoria, aislamiento, expresiones inválidas, timeout, terminación del proceso y no filtración de secretos.
- Completar journey ML clásico: dataset gobernado/snapshot, train, evaluación, registro, selección de modelo, inferencia, drift, artefactos verificados y evidencia.
- Probar límites de filas/columnas/bytes, digest de pipeline/Lab, checkpoints, cancelación, reintentos y consistencia SQLite/PostgreSQL/S3-compatible si aplica.
- Confirmar por búsqueda de rutas/capacidades/configuración que Ronin no publica GenAI, RAG ni agentes integrados; no añadir provider keys, endpoints ni runtime. Las skills externas no son una capacidad GenAI de Ronin.

**Cierre de fase:** resultados de calidad y modelo están ligados a snapshots/digests y pueden verificarse desde la app instalada; el sandbox falla cerrado.

### Fase 9 — Sábado 31/10, tarde: semantic, dashboards, streaming y observabilidad

**Tareas**

- Cualificar semantic models, métricas, agregaciones, joins, filtros, dashboards y export/import; contrastar con fixture independiente, no con la misma salida generada por el código.
- Probar streaming con broker local si se anuncia en el perfil: bytes/mensaje/lote, backpressure, poison-message, offsets, replay, checkpoint, sink y reconexión.
- Verificar `healthy`, `lag`, particiones vacías, fuente caída y estado desconocido sin presentar lag cero como disponibilidad.
- Generar logs/métricas/traces, alertas, auditoría y presupuestos FinOps; probar severidades OK/WARN/ERROR, deduplicación y redacción.
- Si no existe política de bytes/backpressure aprobada o broker local no se puede levantar, dejar el claim de proveedor como no cualificado.

**Cierre de fase:** dashboard y alertas reflejan operaciones efectivas; streaming no pierde/duplica offsets sin señal explícita.

### Fase 10 — Sábado 31/10, noche: seguridad y operación local Compose/Kubernetes

**Tareas**

- Arrancar Compose desde un estado limpio con tokens locales distintos para Ronin y runner broker; validar salud real de server, broker, PostgreSQL y worker.
- Ejecutar quickstart CLI de forma backend-backed, observar logs/events/evidence, cancelar job y revisar limpieza de contenedor; probar límites de permisos del Docker socket y mounts read-only.
- Validar backup, restore, migración y compatibilidad de esquema; reproducir cierre/reinicio y almacenamiento lleno/worker muerto en volúmenes únicamente descartables.
- Ejecutar `helm lint`, `helm template` y desplegar el perfil Helm single-node en un cluster `kind` temporal; verificar Secret no aparece en ConfigMap/valores/artefactos, readiness, port-forward, operación básica y reinicio.
- Configurar una réplica, SQLite y scope single-operator. Retirar `server.multiUser` del schema/values del chart público; si el chart compartido sirve a Pro, separar el paquete/perfil público para que no se pueda activar multiusuario desde esta release.
- Revisar SSRF, IDOR entre recursos single-operator, SQL injection, XSS, CSRF, traversal, YAML/ZIP, secretos, CORS, CSP, dependencias, permisos Docker y superficie de red.
- Ejecutar el escaneo manual de secretos del historial y del árbol de trabajo, auditoría de dependencias Python y escaneo de la imagen; revisar findings y excepciones una por una. Los comandos están en §5.

**Cierre de fase:** Compose y Kubernetes local single-node funcionan y se limpian sin tocar otros proyectos/volúmenes/clusters; no quedan P0/P1 de seguridad abiertos.

### Fase 11 — Domingo 1/11, madrugada y mañana: Bundle, migración y perfiles vendor

**Antes de las 06:00**

- Probar Bundle Ronin nativo con export/import/replay y round-trip de proyectos, connections by reference, pipelines, notebooks, semantic, graph, ML y streaming incluidos en el scope.
- Verificar integridad, manifest/digests, atomicidad y rollback tras conflicto tardío; secretos nunca se exportan.

**Antes de las 12:00**

- Ejecutar fixtures versionadas de Databricks, Fabric, Dataiku y Palantir Foundry; validar inventario, objeto soportado/no soportado, pérdidas, mappings, reporte y round-trip.
- Separar pruebas locales sintéticas de certificación de proveedor real. Si una integración necesita una cuenta/entorno que no está disponible, marcar `blocked` y retirar del claim público.
- Completar la validación del paquete de Agent Skills como material externo: contenido, compatibilidad de CLI, paths, symlinks, ZIP determinista, permisos e instrucciones de activación en un agente concreto si se anuncia compatibilidad.

**Cierre de fase:** Bundle no pierde ni filtra datos; cada claim vendor indica subset/versiones y limitaciones, sin afirmar paridad completa.

### Fase 12 — Domingo 1/11, tarde y noche: navegación y UI visual funcional

**Antes de las 18:00 — cobertura funcional live**

- Ejecutar Playwright habitual y separar sus resultados mock/static de la suite contra Ronin levantado. Configurar `RONIN_STUDIO_E2E_URL` al server local y `RONIN_LIVE_*` con credenciales sintéticas para `test:live`; actualizar `web-tests/package.json` para que `test:live` incluya `ingestion-live.spec.mjs` y la nueva suite `product-live.spec.mjs`.
- Para Public v1, navegar las 25 rutas: `home`, `runs`, `workspaces`, `projects`, `quality`, `alerts`, `finops`, `migration`, `synthetic`, `mlstudio`, `workflows`, `sql`, `semantic`, `catalog`, `data`, `ingestion`, `notebooks`, `streaming`, `graphs`, `performance`, `debugger`, `cloud`, `deployments`, `environments`, `settings`. Si se adopta el MVP, cualificar las 12 rutas incluidas y comprobar que el resto no se promociona desde menú, búsqueda, tarjeta ni tutorial.
- En cada ruta probar carga, vacío, datos sintéticos, validación, submit/cancel, refresh, error API, token inválido y logs. La suite live no debe usar respuestas API mock: cada petición se envía al Ronin levantado, se registra método/ruta/status y se confirma que el mensaje visible corresponde a la respuesta real. Verificar mutaciones con lectura posterior de API o estado persistido.

**Antes de las 23:00 — QA visual manual**

- Probar 320×800, 375×812, 768×1024, 1440×900 y 1920×1080; zoom 100%, 200% y 400%; tema marrón uniforme, contraste, tipografía, foco y estados deshabilitados.
- Revisar sidebar agrupado, sin “Control plane”, logo completo, iconos visibles colapsado, toggle de zarpa dentro del panel y su orientación, tooltips y navegación por teclado.
- Confirmar scroll interno donde aplique, scrollbars de estilo marrón y ausencia de scroll general horizontal/vertical accidental.
- Recorrer tour general y tutoriales de features: búsqueda, resultado sugerido al terminar, siguiente/anterior, cerrar/interrumpir siempre disponible, reanudar o empezar de nuevo, puntero/bocadillo sin clipping y contenido instructivo vigente.
- Validar mensajes OK/WARN/ERROR, toasts, estados vacíos/cargando/error y logging visible; logs deben ayudar a diagnosticar sin incluir tokens, passwords, SQL sensible ni contenido personal.
- Capturar screenshots/traces sanitizados por ruta, viewport y estado. Revisar manualmente axe: cero violaciones serias/críticas bloqueantes y teclado/foco utilizable.

**Cierre de fase:** para Public v1 hay al menos 27 casos live sin skip —25 rutas más las dos pruebas PostgreSQL/autorización ya existentes—, todas las rutas tienen interacción y evidencia live, las peticiones pasan al servidor/API real y ninguna pantalla crítica queda solo verificada como maqueta. Para el MVP, sustituir este umbral por al menos 14 casos live sin skip y las 12 rutas del alcance publicadas.

### Fase 13 — Lunes 2/11, madrugada y mañana: candidato congelado y qualification completa

**Madrugada, antes de las 06:00**

- Integrar en `main` los cambios aprobados de `20261029`, sincronizar `origin/main` con push normal (sin force push) y comprobar que ambos refs apuntan al mismo SHA completo y que el árbol está limpio. Si la integración no se puede cerrar, detener qualification y mover la fecha.
- Congelar ese SHA candidato de `main`; confirmar rama/tag y no nuevas escrituras durante qualification.
- Construir una sola vez wheel, sdist e imagen; guardar SHA-256 y no recompilar para publicación.
- Generar y verificar SBOM/provenance enlazados a artifacts y SHA; calcular de nuevo digests de los bytes entregados.
- Los generadores `tools.generate_release_sbom` (CycloneDX 1.6), `tools.generate_release_provenance` (in-toto/SLSA provenance), `tools.bind_container_sbom` (Trivy CycloneDX 1.7) y `tools.supply_chain_evidence` implementan formatos separados y validación cruzada; `tools.generate_sbom.py` conserva el formato interno `ronin.sbom-provenance/v1` y no se usa como SBOM release. La CLI de `artifact_identity` rechaza un worktree sucio. En un candidato limpio, guardar wheel, sdist, TAR runtime/probe y SBOM Trivy bruto como archivos, generar identidad para esos bytes, crear y volver a verificar los SBOM ligados y provenance, y ejecutar positivos/negativos. El binder tiene cobertura local de líneas y ramas al 100%; la integración con artefactos reales está registrada en §17. Falta repetir este recibo completo contra un SHA limpio para cerrar `sbom-provenance`.

**Mañana, antes de las 12:00**

- Ejecutar desde entorno fijado: `make check`, suite Docker/15 pasos, PostgreSQL real, bloques Playwright y UI instalada/a11y de §5, escaneos locales Gitleaks/`pip-audit`/Trivy, Floci y Helm/kind según scope. Para el MVP, usar el perfil `local_mvp_required`, acceptance Docker de 7/7 journeys y 14 casos live/12 rutas; no ejecutar ni reportar como necesarios los gates de Floci, Helm o suites v0.1 fuera del alcance anunciado.
- Ejecutar `python tools/license_qualification.py --inventory third_party/licenses-v1.json --policy third_party/license-policy-v1.json` de solo lectura y revisar el expediente legal previamente actualizado; no inferir permisos desde metadata ambigua.
- Ejecutar pruebas negativas de agregación de evidencia: gate faltante, SHA desigual, skip, artefacto expirado y bytes adulterados.
- Para Public v1, verificar 13 journeys de familia, `capability-status`, SHA observado del ledger y diez recibos exactos. Si se adopta el MVP, verificar 7/7 journeys, estado del scope, 12/12 rutas, 14 casos live y diez recibos de `local_mvp_required`; no publicar 13/13 ni usar el perfil `release_required`.

**Cierre de fase:** un expediente candidate-bound completo; 0 skips obligatorios, 0 errores, 0 gates missing/blocked y veredicto local `passed`. Cada cambio de código reinicia la fase para el nuevo SHA.

### Fase 14 — Lunes 2/11, tarde y noche: pruebas manuales finales y decisión

**Tarde, antes de las 18:00**

- Repetir manualmente los journeys principales con instalación limpia y datos sintéticos: instalación → workspace/proyecto → ingestión → pipeline/notebook → SQL → catálogo/lineage → calidad → ML clásico → dashboard/alerta → export Bundle.
- Repetir en el navegador el tour, navegación, scroll, responsive, mensajes y operaciones live corregidas desde Fase 12; revisar cada screenshot posterior al último cambio.
- Revisar README, quickstart, límites, seguridad, compatibilidad, troubleshooting, changelog, soporte, versión y release notes como usuario nuevo.

**Noche, antes de las 23:00**

- Revisión final del expediente por mantenedor: para Public v1, 13/13 familias, 10/10 gates y 15/15 pasos; para MVP, 7/7 journeys, 10/10 gates `local_mvp_required`, 14 live cases/12 rutas; digests coherentes, issue/política no-CI resuelta, protección de refs, licencias y rollback.
- Registrar GO o NO-GO firmado con motivos y SHA. Si falta una condición, no liberar Public v1.
- Preparar checklist del 3/11 08:00: verificar tag/artefactos/release page y digests; publicar a las 09:00 solo con GO y sin reconstruir artefactos. Si Public v1 no tiene GO, retrasar. Solo publicar Ronin Local MVP si cumple sus criterios completos y el responsable elige expresamente ese alcance; no crear una alpha improvisada para conservar la fecha.

**Cierre de fase:** decisión verificable y reversible; la fecha no convierte un pendiente en PASS.

### Martes 3/11 — publicación, solo después de un GO firmado

- **08:00:** confirmar que `main` y `origin/main` apuntan al SHA candidato, que el tag remoto apunta a ese mismo commit, y que el árbol está limpio; comprobar expediente de diez gates, digests coincidentes, artefactos ya construidos y nota de release aprobada. No editar ni reconstruir el candidato.
- **08:30:** preparar la publicación manual de los artefactos exactos ya cualificados: release/source tag, wheel/sdist e imagen por digest. Confirmar notas, límites del producto, instalación limpia y que ni la página pública ni el menú prometen GenAI o multiusuario.
- **09:00:** hacer visible el release solo si el GO firmado sigue válido; descargar desde la distribución pública, comprobar hashes, instalar en entorno limpio, levantar Ronin y verificar health/UI/API con datos sintéticos.
- Si la verificación falla o el expediente deja de corresponder al candidato, detener publicación, registrar el fallo y retrasar. Corregir exige nuevo SHA, nueva qualification afectada y un nuevo GO; nunca reemplazar silenciosamente los artefactos publicados.

## 5. Catálogo de comandos locales

Ejecutar desde la raíz del checkout. Los comandos son operaciones previstas para las fases correspondientes; no se han ejecutado al escribir este plan. Mantener `$CandidateSha` y `$EvidenceDir` en la misma sesión PowerShell; al abrir una sesión nueva, volver a ejecutar la primera sección de identidad.

### Identidad y limpieza del candidato

```powershell
$CandidateSha = (git rev-parse HEAD).Trim()
$EvidenceDir = Join-Path $env:TEMP "ronin-release-evidence\$CandidateSha"
$QualificationProfile = 'release_required' # Use local_mvp_required only after a documented MVP decision.
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
git status --short --branch
git rev-parse HEAD
git diff --check
```

Anotar rama, SHA completo y estado antes y después de cada gate. No mover la rama ni editar código después de empezar la qualification del candidato.

### Preflight de herramientas

Ejecutar después de «Identidad y limpieza del candidato», desde el entorno local de qualification aprobado. Las versiones deben coincidir con el lockfile y las versiones fijadas en Fase 1; si falta una herramienta requerida por un claim, bloquear ese claim y no inferir compatibilidad:

```powershell
$RequiredCommands = @('git','docker','python','node','npm','make','pwsh','gitleaks','trivy')
if ($QualificationProfile -eq 'release_required') { $RequiredCommands += @('helm','kind','kubectl','terraform') }
foreach ($Name in $RequiredCommands) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Required qualification tool is missing: $Name" }
}
$ToolVersionLog = Join-Path $EvidenceDir 'tool-versions.log'
$PSVersionTable.PSVersion.ToString() | Set-Content -LiteralPath $ToolVersionLog -Encoding utf8
function Write-VersionCheck {
  param([string]$Name, [string[]]$Arguments)
  "### $Name $($Arguments -join ' ')" | Add-Content -LiteralPath $ToolVersionLog -Encoding utf8
  & $Name @Arguments 2>&1 | Tee-Object -FilePath $ToolVersionLog -Append
  if ($LASTEXITCODE -ne 0) { throw "Could not record version for $Name." }
}
Write-VersionCheck git @('--version')
Write-VersionCheck docker @('version')
Write-VersionCheck docker @('compose','version')
Write-VersionCheck python @('--version')
Write-VersionCheck node @('--version')
Write-VersionCheck npm @('--version')
Write-VersionCheck make @('--version')
Write-VersionCheck pwsh @('--version')
Write-VersionCheck gitleaks @('version')
Write-VersionCheck trivy @('version')
if ($QualificationProfile -eq 'release_required') {
  Write-VersionCheck helm @('version','--short')
  Write-VersionCheck kind @('version')
  Write-VersionCheck kubectl @('version','--client','--output=yaml')
  Write-VersionCheck terraform @('version')
}
```

Docker debe usar contenedores Linux. Los comandos `make` requieren GNU Make y un shell compatible instalado y accesible desde PowerShell.

### Entorno Python aislado y lock exacto

Crear un virtualenv nuevo fuera del checkout y del expediente para los gates Python de candidato; ejecutar los comandos de ese bloque con el entorno activo para que `make` resuelva el intérprete correcto. No reutilizarlo entre versiones de Python ni entre candidatos. El harness live tiene su propio cache de dependencias con lock exacto, huella de versión/proyecto, `pip check` y datos/servicios nuevos por ejecución, descrito en `docs/DEVELOPMENT_QUALIFICATION.md`:

```powershell
$PythonEnvRun = ((Get-Date).ToUniversalTime().ToString("yyyyMMdd'T'HHmmss'Z'") + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)).ToLowerInvariant()
$QualificationVenv = Join-Path $env:TEMP "ronin-python-$($CandidateSha.Substring(0,12))-$PythonEnvRun"
$QualificationScripts = Join-Path $QualificationVenv 'Scripts'
python -m venv $QualificationVenv
if ($LASTEXITCODE -ne 0) { throw 'Could not create a clean qualification virtualenv.' }
$env:PATH = "$QualificationScripts;$env:PATH"
python --version | Tee-Object -FilePath (Join-Path $EvidenceDir 'python-version.txt')
python -m pip --version | Tee-Object -FilePath (Join-Path $EvidenceDir 'pip-version.txt')
python -m pip install --require-hashes -r requirements-dev.lock 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'python-install.log')
if ($LASTEXITCODE -ne 0) { throw 'Could not install the exact locked Python qualification graph.' }
python -m pip check 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'pip-check.log')
if ($LASTEXITCODE -ne 0) { throw 'Locked Python environment has dependency conflicts.' }
python -m pip freeze --all | Set-Content -LiteralPath (Join-Path $EvidenceDir 'python-freeze.txt') -Encoding utf8
Get-FileHash requirements-dev.lock -Algorithm SHA256 | Out-File -LiteralPath (Join-Path $EvidenceDir 'requirements-dev-lock.sha256') -Encoding utf8
```

Para cada versión de Python que se incluya en la matriz de soporte, repetir en un virtualenv nuevo creado por ese intérprete y guardar el mismo conjunto de evidencia; no copiar resultados entre versiones ni sistemas operativos.

### Suite y gates Python

```powershell
$CandidateSha = (git rev-parse HEAD).Trim()
$EvidenceDir = Join-Path $env:TEMP "ronin-release-evidence\$CandidateSha"
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
python -m pytest -q tests/test_quality_runtime.py::test_custom_python_expression_uses_bounded_sandbox
if ($LASTEXITCODE -ne 0) { throw 'Isolated sandbox regression failed.' }
# `make check` below is the single full non-PostgreSQL suite for this source state.
# It already runs all ordinary pytest cases, coverage gates and performance tests.
make check 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'make-check.log')
if ($LASTEXITCODE -ne 0) { throw 'make check failed.' }
$SkillsPackageDir = Join-Path $EvidenceDir 'agent-skills-package'
make agent-skills-package "AGENT_SKILLS_OUTPUT=$SkillsPackageDir" 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'agent-skills-package.log')
if ($LASTEXITCODE -ne 0) { throw 'Agent Skills packaging failed.' }
$SkillZips = @(Get-ChildItem -LiteralPath $SkillsPackageDir -Filter 'skill.zip' -File -Recurse)
$ExpectedSkillNames = @('ronin-core','ronin-data-engineering','ronin-machine-learning') | Sort-Object
$ActualSkillNames = @($SkillZips | ForEach-Object { $_.Directory.Name } | Sort-Object)
if ($SkillZips.Count -ne 3 -or ($ActualSkillNames -join ',') -ne ($ExpectedSkillNames -join ',')) { throw 'Expected deterministic ZIPs for the three external coding-agent skills.' }
Get-FileHash $SkillZips.FullName -Algorithm SHA256
```

`make check` incluye la suite normal, gates de formato/lint/tipos/arquitectura/OpenAPI/rutas y el objetivo de rendimiento. La cobertura PostgreSQL completa se ejecuta en su fase con DB disponible; no ejecutar `coverage-storage-files-full` sin DSN.

### Docker, Compose y PostgreSQL

Primero ejecuta la sección «Identidad y limpieza del candidato» y conserva `$CandidateSha`/`$EvidenceDir` en la misma sesión. En una sesión PowerShell aislada, definir tokens aleatorios locales y únicos; nunca utilizar credenciales de producción ni guardar los tokens en el expediente:

El compose expone server en `127.0.0.1:18080` y PostgreSQL en `127.0.0.1:55432`, solo en loopback. La contraseña aleatoria es hexadecimal y no requiere URL-encoding. Este script mantiene el proyecto y su volumen aislados por SHA/fecha, archiva los informes y ejecuta `down --volumes` en `finally`, incluso si una suite falla:

```powershell
$env:RONIN_TOKEN = [guid]::NewGuid().ToString('N')
$env:RONIN_RUNNER_BROKER_TOKEN = [guid]::NewGuid().ToString('N')
$env:POSTGRES_USER = 'ronin'
$env:POSTGRES_PASSWORD = [guid]::NewGuid().ToString('N')
$env:POSTGRES_DB = 'ronin'
$env:RONIN_POSTGRES_PORT = '55432'
$env:RONIN_PORT = '18080'
$QualificationRun = ((Get-Date).ToUniversalTime().ToString("yyyyMMdd'T'HHmmss'Z'") + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)).ToLowerInvariant()
$ComposeProject = "ronin-qualification-$($CandidateSha.Substring(0,8))-$QualificationRun"
$ImageTag = "ronin:qualification-$($CandidateSha.Substring(0,12))"
$DockerEvidence = Join-Path $EvidenceDir "docker-$QualificationRun"
New-Item -ItemType Directory -Force -Path $DockerEvidence | Out-Null
try {
  docker compose version
  if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is unavailable.' }
  docker compose -p $ComposeProject up -d --build --wait --wait-timeout 180
  if ($LASTEXITCODE -ne 0) { throw 'Compose services did not become healthy.' }
  docker compose -p $ComposeProject ps
  docker compose -p $ComposeProject exec -T postgres postgres --version 2>&1 | Tee-Object -FilePath (Join-Path $DockerEvidence 'postgres-version.txt')
  if ($LASTEXITCODE -ne 0) { throw 'Could not record the PostgreSQL server version.' }

  $env:RONIN_TEST_POSTGRES_DSN = 'postgresql://{0}:{1}@127.0.0.1:55432/{2}' -f $env:POSTGRES_USER, $env:POSTGRES_PASSWORD, $env:POSTGRES_DB
  $env:RONIN_POSTGRES_TEST_DSN = $env:RONIN_TEST_POSTGRES_DSN
  python -m pytest -q --ignore=tests/perf --cov --cov-branch --cov-report= --junitxml (Join-Path $EvidenceDir 'python-postgres.xml') 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'python-postgres.log')
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL-backed Python suite failed.' }
  make coverage-storage-files-full 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'postgres-storage-coverage.log')
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL storage coverage gate failed.' }

  pwsh -File tools/run_docker_qualification.ps1 -ImageTag $ImageTag -EvidenceDirectory $DockerEvidence 2>&1 | Tee-Object -FilePath (Join-Path $DockerEvidence 'docker-qualification.log')
  $DockerExitCode = $LASTEXITCODE
  Get-ChildItem -LiteralPath $DockerEvidence -File | Get-FileHash -Algorithm SHA256
  if ($DockerExitCode -ne 0) { throw "Docker/worker/strict acceptance qualification failed with exit code $DockerExitCode; preserve this failed report." }
} finally {
  docker compose -p $ComposeProject ps -a
  docker compose -p $ComposeProject down --volumes --remove-orphans
  if ($LASTEXITCODE -ne 0) { throw 'Could not clean up the isolated Compose project; record cleanup as BLOCKED and do not release.' }
}
```

`tools/run_docker_qualification.ps1` debe aceptar `-EvidenceDirectory`, construir la imagen candidate-tagged, ejecutar Docker/worker y `tests/e2e/test_v01_journey.py`, escribir JUnit y aplicar `tools/v01_acceptance_gate.py` en ese directorio. El directorio exclusivo conserva también resultados fallidos y evita reutilizar un JSON anterior. Esta qualification no sustituye la suite PostgreSQL. No borres volúmenes globales ni otros proyectos Compose.

### Playwright, app real y accesibilidad

Ejecutar la suite estática como cobertura visual/comportamental de frontend; sus mocks no cualifican API ni persistencia:

```powershell
node web-tests/ensure-dependencies.mjs
$env:PLAYWRIGHT_WORKERS = '4' # Set 2–4 based on local CPU/RAM; live suites remain serial.
$env:PLAYWRIGHT_HTML_OUTPUT_DIR = Join-Path $EvidenceDir 'browser-static-html'
$env:PLAYWRIGHT_OUTPUT_DIR = Join-Path $EvidenceDir 'browser-static-artifacts'
$env:PLAYWRIGHT_HTML_OPEN = 'never'
$env:PLAYWRIGHT_JUNIT_OUTPUT_FILE = Join-Path $EvidenceDir 'browser-static.xml'
npm --prefix web-tests test -- --reporter=list,html,junit 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'browser-static.log')
if ($LASTEXITCODE -ne 0) { throw 'Playwright static/mock suite failed.' }
```

`npm test` excludes the explicitly named Live cases; `npm run test:live` and the harness below are the only API qualification. La cualificación funcional se ejecuta por medio del harness versionado: arranca PostgreSQL y Redpanda desechables, crea una base `ronin_test` aislada, aplica el fixture idempotente `web-tests/fixtures/live-postgres.sql`, levanta Ronin con dos listeners reales, lanza Chromium y elimina solo los recursos únicos creados para esa ejecución:

```powershell
$LiveEvidence = Join-Path $env:TEMP ("ronin-live-qualification-" + [guid]::NewGuid().ToString('N'))
$WorkerImage = 'ronin:qualification-<candidate-sha>' # imagen Docker cualificada; el runner resuelve y entrega al worker su ID sha256 inmutable
pwsh -NoProfile -File tools/run_live_product_qualification.ps1 -EvidenceDirectory $LiveEvidence -WorkerImage $WorkerImage
if ($LASTEXITCODE -ne 0) { throw 'Live Ronin/API/PostgreSQL/UI qualification failed; preserve and review its evidence.' }
```

El listener de Studio/Jobs y el de Control Plane son destinos distintos; el proxy de pruebas enruta cada superficie a su listener real. La suite incluye 25 casos de ruta activa (23 prueban contratos API; Home y Settings son UI-only), dos recorridos de ingestión PostgreSQL, el control de evidencia de tráfico, autorización live, el recorrido live de Runs que guarda la conexión y conserva el filtro, y la creación/versionado/ejecución de un notebook con worker Docker real (31 casos en total). La qualification completa requiere `-WorkerImage`; el runner inspecciona la imagen y configura el worker con su ID `sha256`, nunca con un tag mutable. Cada ruta con contrato API ejecuta desde la UI una lectura segura, envía autorización válida y recibe éxito; Runs y Quality completan explícitamente su contexto antes de consultar. La evidencia registra método, ruta, superficie, estado HTTP y, para fallos, solo el código de error. No registra token, cabeceras de autorización, cuerpos ni secretos.

El runner valida JUnit, rutas completas, cero skips/fallos, tráfico autenticado y cero errores 5xx/red, y restaura variables de entorno incluso ante fallo. -TestGrep sirve para diagnóstico aislado únicamente; nunca acredita los 31 casos. El seeder usa CREATE TABLE IF NOT EXISTS e INSERT ... ON CONFLICT; no elimina ni sobrescribe objetos preexistentes ajenos a las tablas de fixture. Conservar íntegramente la carpeta de evidencia de fallos.

Ejecutar también smoke de artefacto instalado y accesibilidad; ambos guardan informes fuera del checkout:

```powershell
$InstalledUiOutput = Join-Path $EvidenceDir 'ui-installed-wheel'
make ui-installed "RONIN_QUALIFICATION_OUTPUT=$InstalledUiOutput" 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'ui-installed.log')
if ($LASTEXITCODE -ne 0) { throw 'Installed-artifact browser smoke failed.' }
$A11yUiOutput = Join-Path $EvidenceDir 'ui-a11y-wheel'
make ui-a11y "RONIN_QUALIFICATION_OUTPUT=$A11yUiOutput" 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'ui-a11y.log')
if ($LASTEXITCODE -ne 0) { throw 'Accessibility gate failed.' }
```

La navegación visual en servidor estático, los recorridos funcionales contra Ronin y el test de artefacto instalado son evidencias separadas. Un resultado mock nunca se presenta como API real; cualquier skip en el live runner bloquea la qualification.
### Emulador cloud local y Helm/kind

Usar el compose dedicado ya fijado en Fase 1: imagen de Floci con versión/digest y puerto `127.0.0.1:4566` solamente. El nombre único de proyecto aísla su volumen; el script Terraform usa solo las credenciales sintéticas del fixture y su estado de workspace temporal:

```powershell
$FlociRun = ((Get-Date).ToUniversalTime().ToString("yyyyMMdd'T'HHmmss'Z'") + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)).ToLowerInvariant()
$FlociProject = "ronin-floci-$($CandidateSha.Substring(0,8))-$FlociRun"
$FlociCompose = 'examples/cloud-studio/compose.floci.yaml'
$FlociWorkspace = Join-Path $env:TEMP $FlociProject
$FlociEvidence = Join-Path $EvidenceDir 'floci-qualification.json'
$FlociWorkspaceCreated = $false
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
try {
  if (Test-Path -LiteralPath $FlociWorkspace) { throw 'Unique Floci workspace already exists; refusing to reuse it.' }
  $FlociWorkspaceCreated = $true
  docker compose -p $FlociProject -f $FlociCompose up -d --wait --wait-timeout 90 floci
  if ($LASTEXITCODE -ne 0) { throw 'Floci container did not start.' }
  python tools/cloud_studio_floci_qualification.py `
    --endpoint http://127.0.0.1:4566 `
    --workspace $FlociWorkspace `
    --evidence $FlociEvidence `
    --terraform 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'floci-qualification.log')
  if ($LASTEXITCODE -ne 0) { throw 'Floci/terraform lifecycle qualification failed.' }
  if (-not (Test-Path -LiteralPath $FlociEvidence)) { throw 'Floci qualification report was not written.' }
} finally {
  docker compose -p $FlociProject -f $FlociCompose ps -a
  docker compose -p $FlociProject -f $FlociCompose down --volumes --remove-orphans
  if ($LASTEXITCODE -ne 0) { throw 'Floci cleanup failed; record cleanup as BLOCKED.' }
  if ($FlociWorkspaceCreated) {
    $ResolvedFlociWorkspace = [IO.Path]::GetFullPath($FlociWorkspace)
    $ResolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if ([IO.Path]::GetDirectoryName($ResolvedFlociWorkspace).TrimEnd([IO.Path]::DirectorySeparatorChar) -ne $ResolvedTemp -or [IO.Path]::GetFileName($ResolvedFlociWorkspace) -ne $FlociProject) { throw 'Refusing to remove an unexpected Terraform workspace path.' }
    if (Test-Path -LiteralPath $ResolvedFlociWorkspace) { Remove-Item -LiteralPath $ResolvedFlociWorkspace -Recurse -Force }
  }
}
```

El gate debe comprobar el resultado de cada operación y dejar vacío `terraform state list` y el refresh del emulador después del destroy. Revisar el endpoint antes de correrlo; nunca apuntar a AWS u otro proveedor real. El `finally` borra solo el volumen Compose de Floci y el workspace Terraform exactos de esta ejecución.

```powershell
$ImageTag = "qualification-$($CandidateSha.Substring(0,12))"
$ImageRef = "ronin:$ImageTag"
$HelmRun = ((Get-Date).ToUniversalTime().ToString("yyyyMMdd'T'HHmmss'Z'") + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)).ToLowerInvariant()
$ClusterName = "ronin-qa-$($CandidateSha.Substring(0,8))-$HelmRun"
$HelmValuesFile = Join-Path $env:TEMP "$ClusterName-values.yaml"
 $HelmEnvNames = @('RONIN_TOKEN','RONIN_TOKEN_SCOPES')
 $HelmEnvBefore = @{}
 foreach ($Name in $HelmEnvNames) { $HelmEnvBefore[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process') }
 $ClusterMayExist = $false
 $HelmValuesCreated = $false
 $Forward = $null
 try {
  $env:RONIN_TOKEN = [guid]::NewGuid().ToString('N')
  $env:RONIN_TOKEN_SCOPES = '{"version":1,"grants":[{"version":1,"actions":["read","list","events","submit","execute","cancel","evidence:read"],"resource":{"kind":"project","identifier":"examples/demo"},"constraints":{}}]}'
  if (Test-Path -LiteralPath $HelmValuesFile) { throw 'Unique Helm values file already exists; refusing to overwrite it.' }
  $HelmValuesCreated = $true
  @"
image:
  repository: ronin
  tag: $ImageTag
  pullPolicy: IfNotPresent
server:
  replicas: 1
  token: $($env:RONIN_TOKEN)
  tokenScopes: '$($env:RONIN_TOKEN_SCOPES)'
  bindPolicy: insecure-plaintext-network
"@ | Set-Content -LiteralPath $HelmValuesFile -Encoding utf8

# Reuse the candidate image built by Docker qualification; build only for the earlier Phase 10 smoke.
  $ExistingClusters = @(kind get clusters)
  if ($LASTEXITCODE -ne 0) { throw 'Could not inspect kind clusters.' }
  if ($ExistingClusters -contains $ClusterName) { throw "Refusing to reuse existing kind cluster $ClusterName." }
  if (Test-NetConnection 127.0.0.1 -Port 18082 -InformationLevel Quiet) { throw 'Port 18082 is already in use.' }
  docker image inspect $ImageRef *> $null
  if ($LASTEXITCODE -ne 0) {
    docker build --file docker/Dockerfile --tag $ImageRef .
    if ($LASTEXITCODE -ne 0) { throw 'Could not build the single-node qualification image.' }
  }
  $ClusterMayExist = $true
  kind create cluster --name $ClusterName
  if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated kind cluster.' }
  $KubeContext = "kind-$ClusterName"
  kind load docker-image $ImageRef --name $ClusterName
  if ($LASTEXITCODE -ne 0) { throw 'Could not load the candidate image into kind.' }
  helm lint deploy/helm/ronin --values $HelmValuesFile
  if ($LASTEXITCODE -ne 0) { throw 'Helm lint failed.' }
  $RenderedManifest = helm template ronin deploy/helm/ronin --namespace ronin-qualification --values $HelmValuesFile | Out-String
  if ($LASTEXITCODE -ne 0) { throw 'Helm rendering failed.' }
  $EncodedToken = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($env:RONIN_TOKEN))
  $RenderedDocuments = @($RenderedManifest -split '(?m)^---\s*$' | Where-Object { $_.Trim() })
  $SecretDocuments = @($RenderedDocuments | Where-Object { $_ -match '(?m)^kind:\s*Secret\s*$' })
  $NonSecretDocuments = @($RenderedDocuments | Where-Object { $_ -notmatch '(?m)^kind:\s*Secret\s*$' })
  if ($SecretDocuments.Count -eq 0 -or @($NonSecretDocuments | Where-Object { $_.Contains($env:RONIN_TOKEN) -or $_.Contains($EncodedToken) }).Count -gt 0) { throw 'Rendered Helm manifests must keep the token confined to Secret resources.' }
  "Rendered $($RenderedDocuments.Count) manifests; no token in non-Secret resources." | Set-Content -LiteralPath (Join-Path $EvidenceDir 'helm-render-check.txt') -Encoding utf8
  $RenderedManifest = $null
  $RenderedDocuments = $null
  helm upgrade --install ronin deploy/helm/ronin --kube-context $KubeContext --namespace ronin-qualification --create-namespace --values $HelmValuesFile
  if ($LASTEXITCODE -ne 0) { throw 'Helm single-node installation failed.' }
  $Deployment = (kubectl --context $KubeContext get deployments -n ronin-qualification -o jsonpath='{.items[0].metadata.name}').Trim()
  if ($LASTEXITCODE -ne 0 -or -not $Deployment) { throw 'Could not find the Ronin deployment.' }
  kubectl --context $KubeContext rollout status "deployment/$Deployment" -n ronin-qualification --timeout=120s
  if ($LASTEXITCODE -ne 0) { throw 'Ronin deployment did not become ready.' }
  kubectl --context $KubeContext get pods,svc,pvc -n ronin-qualification
  if ($LASTEXITCODE -ne 0) { throw 'Could not collect the Kubernetes resource inventory.' }
  $Service = (kubectl --context $KubeContext get services -n ronin-qualification -o jsonpath='{.items[0].metadata.name}').Trim()
  if ($LASTEXITCODE -ne 0 -or -not $Service) { throw 'Could not find the Ronin service.' }
  $ForwardOut = Join-Path $EvidenceDir "$ClusterName-port-forward.log"
  $ForwardErr = Join-Path $EvidenceDir "$ClusterName-port-forward-error.log"
  $Forward = Start-Process -FilePath (Get-Command kubectl).Source -ArgumentList @('--context',$KubeContext,'port-forward','-n','ronin-qualification',"service/$Service",'18082:8080') -PassThru -WindowStyle Hidden -RedirectStandardOutput $ForwardOut -RedirectStandardError $ForwardErr
  $Deadline = (Get-Date).AddSeconds(30)
  $Ready = $false
  do {
    if ($Forward.HasExited) { throw "kubectl port-forward exited with code $($Forward.ExitCode)." }
    try { $null = Invoke-WebRequest 'http://127.0.0.1:18082/healthz' -TimeoutSec 2; $Ready = $true }
    catch { Start-Sleep -Seconds 1 }
  } while (-not $Ready -and (Get-Date) -lt $Deadline)
  if (-not $Ready) { throw 'Helm single-node service did not become healthy.' }
  $null = Invoke-WebRequest 'http://127.0.0.1:18082/studio/' -TimeoutSec 5
  $Headers = @{ Authorization = "Bearer $env:RONIN_TOKEN" }
  $null = Invoke-RestMethod 'http://127.0.0.1:18082/v1/jobs?project=examples%2Fdemo&limit=10' -Headers $Headers -TimeoutSec 5
} finally {
  try {
    if ($Forward -and -not $Forward.HasExited) { Stop-Process -Id $Forward.Id -Force }
    if ($ClusterMayExist) {
      $RemainingClusters = @(kind get clusters 2>$null)
      if ($LASTEXITCODE -ne 0) { throw 'Could not inspect kind clusters during cleanup.' }
      if ($RemainingClusters -contains $ClusterName) {
        kubectl --context "kind:$ClusterName" delete namespace ronin-qualification --ignore-not-found=true --wait=true 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'Could not remove the temporary qualification namespace.' }
        kind delete cluster --name $ClusterName
        if ($LASTEXITCODE -ne 0) { throw 'Could not delete the temporary kind cluster; record cleanup as BLOCKED.' }
      }
      $ClustersAfterCleanup = @(kind get clusters 2>$null)
      if ($LASTEXITCODE -ne 0 -or $ClustersAfterCleanup -contains $ClusterName) { throw 'Temporary kind cluster remains after cleanup; record cleanup as BLOCKED.' }
    }
  } finally {
    try {
      if ($HelmValuesCreated -and (Test-Path -LiteralPath $HelmValuesFile)) { Remove-Item -LiteralPath $HelmValuesFile -Force }
    } finally {
      foreach ($Name in $HelmEnvNames) {
        if ($null -eq $HelmEnvBefore[$Name]) { Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue }
        else { Set-Item -LiteralPath "Env:$Name" -Value $HelmEnvBefore[$Name] }
      }
    }
  }
}
```

El values temporal lleva token sintético, grant acotado y el opt-in explícito `server.bindPolicy: insecure-plaintext-network`: el chart sirve HTTP en una red privada de desarrollo local, no publica un Ingress y se accede mediante port-forward. No usar este modo en redes no confiables; para acceso remoto se requiere terminación TLS. La política `container-internal` queda reservada al bridge soportado de Compose. `server.replicas: 1` fija el perfil single-node; el chart no expone `server.profile` ni claves `multiUser` (Ronin Pro queda fuera). El token es un secreto y el archivo temporal no se versiona ni se archiva. Antes de crear el cluster, confirmar que `kind get clusters` no muestra uno con ese nombre. El valor por defecto de `server.tokenScopes` y `server.bindPolicy` no satisface el schema Helm: ambos deben configurarse explícitamente. Se ejecuta `/healthz`, descarga del Studio y consulta autenticada real a `/v1/jobs`; `helm template` no sustituye el smoke. Al cerrar, borrar solo el namespace y cluster temporales recién creados.

### Licencias y evidencia de artifacts

```powershell
$ArtifactDir = Join-Path $EvidenceDir 'artifacts'
New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null
$BuildStartedOn = (Get-Date).ToUniversalTime().ToString('o')
$SourceDateEpoch = [long](git show -s --format=%ct $CandidateSha)
$env:SOURCE_DATE_EPOCH = "$SourceDateEpoch"
python -m build --wheel --sdist --outdir $ArtifactDir
Remove-Item Env:SOURCE_DATE_EPOCH
$Wheels = @(Get-ChildItem -LiteralPath $ArtifactDir -Filter '*.whl')
$Sdists = @(Get-ChildItem -LiteralPath $ArtifactDir -Filter '*.tar.gz')
if ($Wheels.Count -ne 1 -or $Sdists.Count -ne 1) { throw 'Expected exactly one wheel and one sdist' }
$Wheel = $Wheels[0].FullName
$Sdist = $Sdists[0].FullName
python -m tools.normalize_release_sdist $Sdist --source-date-epoch $SourceDateEpoch
Get-FileHash $Wheel, $Sdist -Algorithm SHA256
$ImageTag = "qualification-$($CandidateSha.Substring(0,12))"
$ImageRef = "ronin:$ImageTag"
$CandidateShort = $CandidateSha.Substring(0,12)
$ProbeImageRef = "ronin:probe-$CandidateShort"
docker build --file docker/Dockerfile.probe --tag $ProbeImageRef .
if ($LASTEXITCODE -ne 0) { throw 'Could not build the candidate probe image.' }
$RuntimeImageArchive = Join-Path $ArtifactDir "ronin-runtime-$CandidateSha.tar"
$ProbeImageArchive = Join-Path $ArtifactDir "ronin-probe-$CandidateSha.tar"
docker save --output $RuntimeImageArchive $ImageRef
if ($LASTEXITCODE -ne 0) { throw 'Could not export the qualified runtime image.' }
docker save --output $ProbeImageArchive $ProbeImageRef
if ($LASTEXITCODE -ne 0) { throw 'Could not export the qualified probe image.' }
$TrivyImage = 'aquasec/trivy:0.76.1'
$ArtifactMount = [IO.Path]::GetFullPath($ArtifactDir).Replace('\', '/')
$EvidenceMount = [IO.Path]::GetFullPath($EvidenceDir).Replace('\', '/')
$RuntimeRawSbom = Join-Path $ArtifactDir 'runtime-trivy.cdx.json'
$ProbeRawSbom = Join-Path $ArtifactDir 'probe-trivy.cdx.json'
$RuntimeScanReport = Join-Path $EvidenceDir 'runtime-trivy-findings.json'
$ProbeScanReport = Join-Path $EvidenceDir 'probe-trivy-findings.json'
docker run --rm $TrivyImage --version | Tee-Object -FilePath (Join-Path $EvidenceDir 'trivy-version.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not read the pinned Trivy version.' }
docker run --rm --mount "type=bind,source=$ArtifactMount,target=/scan" $TrivyImage image --input "/scan/$([IO.Path]::GetFileName($RuntimeImageArchive))" --format cyclonedx --output '/scan/runtime-trivy.cdx.json'
if ($LASTEXITCODE -ne 0) { throw 'Could not create the runtime CycloneDX inventory.' }
docker run --rm --mount "type=bind,source=$ArtifactMount,target=/scan" $TrivyImage image --input "/scan/$([IO.Path]::GetFileName($ProbeImageArchive))" --format cyclonedx --output '/scan/probe-trivy.cdx.json'
if ($LASTEXITCODE -ne 0) { throw 'Could not create the probe CycloneDX inventory.' }
docker run --rm --mount "type=bind,source=$ArtifactMount,target=/scan" --mount "type=bind,source=$EvidenceMount,target=/evidence" $TrivyImage image --input "/scan/$([IO.Path]::GetFileName($RuntimeImageArchive))" --scanners vuln,secret --severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL --exit-code 1 --format json --output '/evidence/runtime-trivy-findings.json'
if ($LASTEXITCODE -ne 0) { throw 'Runtime Trivy threshold failed; retain the JSON report and stop release qualification.' }
docker run --rm --mount "type=bind,source=$ArtifactMount,target=/scan" --mount "type=bind,source=$EvidenceMount,target=/evidence" $TrivyImage image --input "/scan/$([IO.Path]::GetFileName($ProbeImageArchive))" --scanners vuln,secret --severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL --exit-code 1 --format json --output '/evidence/probe-trivy-findings.json'
if ($LASTEXITCODE -ne 0) { throw 'Probe Trivy threshold failed; retain the JSON report and stop release qualification.' }
Get-FileHash $Wheel, $Sdist, $RuntimeImageArchive, $ProbeImageArchive, $RuntimeRawSbom, $ProbeRawSbom -Algorithm SHA256
python tools/license_qualification.py --inventory third_party/licenses-v1.json --policy third_party/license-policy-v1.json
python -m tools.artifact_identity $Wheel $Sdist $RuntimeImageArchive $ProbeImageArchive $RuntimeRawSbom $ProbeRawSbom --commit $CandidateSha --output (Join-Path $EvidenceDir 'artifact-identity.json')
$Identity = Join-Path $EvidenceDir 'artifact-identity.json'
$RuntimeBoundSbom = Join-Path $EvidenceDir 'runtime-container-bound.cdx.json'
$ProbeBoundSbom = Join-Path $EvidenceDir 'probe-container-bound.cdx.json'
python -m tools.bind_container_sbom --trivy-sbom $RuntimeRawSbom --image-archive $RuntimeImageArchive --artifact-identity $Identity --expected-commit $CandidateSha --output $RuntimeBoundSbom
if ($LASTEXITCODE -ne 0) { throw 'Runtime SBOM does not bind to the candidate image bytes.' }
python -m tools.bind_container_sbom --trivy-sbom $ProbeRawSbom --image-archive $ProbeImageArchive --artifact-identity $Identity --expected-commit $CandidateSha --output $ProbeBoundSbom
if ($LASTEXITCODE -ne 0) { throw 'Probe SBOM does not bind to the candidate image bytes.' }
python tools/generate_sbom.py $Wheel $Sdist $RuntimeImageArchive $ProbeImageArchive --root . --output (Join-Path $EvidenceDir 'ronin-sbom-provenance.json')
python tools/generate_sbom.py $Wheel $Sdist $RuntimeImageArchive $ProbeImageArchive --root . --output (Join-Path $EvidenceDir 'ronin-sbom-provenance.json') --verify --expected-commit $CandidateSha
python -m tools.generate_release_sbom --artifact-identity $Identity --requirements-lock requirements-dev.lock --output (Join-Path $EvidenceDir 'ronin.cdx.json')
python -m tools.generate_release_sbom --artifact-identity $Identity --requirements-lock requirements-dev.lock --output (Join-Path $EvidenceDir 'ronin.cdx.json') --verify --expected-commit $CandidateSha
$BuildFinishedOn = (Get-Date).ToUniversalTime().ToString('o')
$TrivyVersionText = docker run --rm $TrivyImage --version
if ($LASTEXITCODE -ne 0) { throw 'Could not record the Trivy toolchain version.' }
$Toolchain = @{
  python = ((python --version) -split ' ')[1]
  docker_engine = (docker version --format '{{.Server.Version}}')
  docker_compose = ((docker compose version --short) -replace '^v', '')
  trivy = ($TrivyVersionText -split '\s+')[-1]
}
$Toolchain | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $EvidenceDir 'toolchain.json') -Encoding utf8
python -m tools.generate_release_provenance --artifact-identity $Identity --build-command 'python -m build --wheel --sdist; docker build runtime/probe; docker save; trivy 0.76.1 scan' --started-on $BuildStartedOn --finished-on $BuildFinishedOn --toolchain-json (Join-Path $EvidenceDir 'toolchain.json') --output (Join-Path $EvidenceDir 'provenance.json')
python -m tools.supply_chain_evidence --commit $CandidateSha --artifact-identity $Identity --artifact-directory $ArtifactDir --sbom (Join-Path $EvidenceDir 'ronin.cdx.json') --sbom $RuntimeBoundSbom --sbom $ProbeBoundSbom --require-container-inventory --provenance (Join-Path $EvidenceDir 'provenance.json') --output (Join-Path $EvidenceDir 'supply-chain.json')
```

Para el gate `installed-artifact`, instalar wheel y sdist en virtualenvs desechables que contengan primero el grafo dev bloqueado, salir del checkout y ejecutar el smoke desde un directorio vacío:

Antes de cualificar, repetir el build con el mismo SHA, toolchain y `SOURCE_DATE_EPOCH`; normalizar ambos sdists y exigir digests idénticos para wheel y sdist. El normalizador solo admite miembros regulares/directorios y rechaza rutas inseguras, duplicadas o especiales.

```powershell
$InstallRun = ((Get-Date).ToUniversalTime().ToString("yyyyMMdd'T'HHmmss'Z'") + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)).ToLowerInvariant()
$InstallRoot = Join-Path $env:TEMP "ronin-installed-$($CandidateSha.Substring(0,12))-$InstallRun"
$WheelVenv = Join-Path $InstallRoot 'wheel'
$SdistVenv = Join-Path $InstallRoot 'sdist'
$EmptyRunDir = Join-Path $InstallRoot 'run'
$InstallRootCreated = $false
try {
  if (Test-Path -LiteralPath $InstallRoot) { throw 'Unique installed-artifact directory already exists; refusing to reuse it.' }
  New-Item -ItemType Directory -Path $InstallRoot | Out-Null
  $InstallRootCreated = $true
  New-Item -ItemType Directory -Path $EmptyRunDir | Out-Null
  python -m venv $WheelVenv
  if ($LASTEXITCODE -ne 0) { throw 'Could not create wheel smoke virtualenv.' }
  python -m venv $SdistVenv
  if ($LASTEXITCODE -ne 0) { throw 'Could not create sdist smoke virtualenv.' }
  $WheelPython = Join-Path $WheelVenv 'Scripts/python.exe'
  $SdistPython = Join-Path $SdistVenv 'Scripts/python.exe'
  & $WheelPython -m pip install --require-hashes -r requirements-dev.lock 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'wheel-dependencies-install.log')
  if ($LASTEXITCODE -ne 0) { throw 'Could not prepare locked wheel smoke environment.' }
  & $SdistPython -m pip install --require-hashes -r requirements-dev.lock 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'sdist-dependencies-install.log')
  if ($LASTEXITCODE -ne 0) { throw 'Could not prepare locked sdist smoke environment.' }
  & $WheelPython -m pip install --no-deps $Wheel 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'wheel-artifact-install.log')
  if ($LASTEXITCODE -ne 0) { throw 'Wheel install failed.' }
  & $SdistPython -m pip install --no-deps --no-build-isolation $Sdist 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'sdist-artifact-install.log')
  if ($LASTEXITCODE -ne 0) { throw 'Sdist install failed.' }
  Push-Location $EmptyRunDir
  try {
    & $WheelPython -c "import importlib.metadata as m; print(m.version('ronin-studio'))" | Tee-Object -FilePath (Join-Path $EvidenceDir 'wheel-installed-version.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Wheel import/version smoke failed.' }
    & (Join-Path $WheelVenv 'Scripts/ronin.exe') --help 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'wheel-cli-help.log')
    if ($LASTEXITCODE -ne 0) { throw 'Wheel CLI entrypoint smoke failed.' }
    & $SdistPython -c "import importlib.metadata as m; print(m.version('ronin-studio'))" | Tee-Object -FilePath (Join-Path $EvidenceDir 'sdist-installed-version.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Sdist import/version smoke failed.' }
    & (Join-Path $InstallRoot 'sdist/Scripts/ronin.exe') --help 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'sdist-cli-help.log')
    if ($LASTEXITCODE -ne 0) { throw 'Sdist CLI entrypoint smoke failed.' }
  } finally { Pop-Location }
} finally {
  if ($InstallRootCreated -and (Test-Path -LiteralPath $InstallRoot)) {
    $ResolvedInstallRoot = [IO.Path]::GetFullPath($InstallRoot)
    $ResolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $ExpectedPrefix = "ronin-installed-$($CandidateSha.Substring(0,12))-"
    if ([IO.Path]::GetDirectoryName($ResolvedInstallRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) -ne $ResolvedTemp -or -not [IO.Path]::GetFileName($ResolvedInstallRoot).StartsWith($ExpectedPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Refusing to remove an unexpected installed-artifact path.' }
    Remove-Item -LiteralPath $ResolvedInstallRoot -Recurse -Force
  }
}
```

`python tools/license_qualification.py --write-inventory third_party/licenses-v1.json` y la revisión de `license-policy-v1.json` se hacen en Fase 3 y quedan versionados en un commit antes del SHA candidato. En Fase 13 solo se valida esa policy en modo lectura. `generate_sbom.py` sigue siendo evidencia interna `ronin.sbom-provenance/v1`; no se le pasa a `supply_chain_evidence.py`. El CycloneDX de la aplicación declara los archivos con SHA-256 y el lock Python; dos CycloneDX 1.7 de Trivy describen los paquetes OS del runtime y probe. `bind_container_sbom` verifica el digest del TAR, el digest del config del manifiesto Docker, el tag, el commit y los hashes de los dos archivos contra `artifact_identity`. El validador vuelve a reconstruir cada SBOM ligado desde los archivos originales, coteja el inventario completo y exige runtime + probe antes de PASS. Provenance registra los mismos artefactos y la versión efectiva de Trivy. Los SBOM brutos del escáner son entradas de identidad; los SBOM ligados son documentos derivados y sus hashes quedan en el recibo supply-chain.

El emisor existente es `tools.emit_release_evidence`; registra horas reales, fingerprint del entorno y alcance completo/diagnóstico. La política vigente excluye CI: el perfil local usa `local-quality`, y ningún recibo debe requerir ni insinuar un check de CI. Emite un recibo por cada gate solo después de ejecutar sus comandos; usar `--status passed` únicamente cuando todos sus criterios se cumplan. La licencia requiere además revisión humana de `third_party/license-policy-v1.json`, NOTICE y atribuciones; generar el inventario no implica aprobación legal. El agregador debe rechazar evidencia faltante, archivo alterado, commit distinto o digest de artefacto diferente del manifiesto de identidad.

Escaneos locales manuales (versiones fijadas en Fase 1; guardar versión, salida y reportes bajo `$EvidenceDir`, fuera del repo):

```powershell
gitleaks version | Tee-Object -FilePath (Join-Path $EvidenceDir 'gitleaks-version.txt')
gitleaks git --redact --report-format json --report-path (Join-Path $EvidenceDir 'gitleaks-history.json') .
gitleaks dir --redact --report-format json --report-path (Join-Path $EvidenceDir 'gitleaks-working-tree.json') .
python -m pip_audit --version | Tee-Object -FilePath (Join-Path $EvidenceDir 'pip-audit-version.txt')
python -m pip_audit -r requirements-dev.lock --require-hashes --strict --format json --output (Join-Path $EvidenceDir 'pip-audit-dev.json')
python -m pip_audit -r requirements-test.lock --require-hashes --strict --format json --output (Join-Path $EvidenceDir 'pip-audit-test.json')
trivy version | Tee-Object -FilePath (Join-Path $EvidenceDir 'trivy-version.txt')
trivy image --scanners vuln,secret --severity HIGH,CRITICAL --exit-code 1 --format json --output (Join-Path $EvidenceDir 'trivy-image.json') $ImageRef
```

Estos escáneres cubren clases distintas; no sustituyen el análisis manual de SSRF, autorización, SQL/XSS/CSRF, configuración, riesgo residual ni licencias. Consultar [Gitleaks](https://github.com/gitleaks/gitleaks#usage), [pip-audit](https://pypi.org/project/pip-audit/) y [reporting/exit codes de Trivy](https://trivy.dev/docs/latest/guide/configuration/reporting/).

### Recibos de gates y veredicto

En Fase 1 se extiende el CLI existente `tools.emit_release_evidence` con `--started-at` y `--ended-at`, se cambia el gate `ci` por `local-quality`, y se hace que `release_evidence.py`/`aggregate_release_evidence.py` verifiquen archivos, digests y caducidad. Antes de la Fase 13 ejecutar cada gate final contra el candidato congelado, guardar logs/reportes saneados en `$EvidenceDir`, y emitir un recibo separado por gate. Ejemplo para un `local-quality` que terminó PASS:

```powershell
$ReceiptsDir = Join-Path $EvidenceDir 'receipts'
New-Item -ItemType Directory -Force -Path $ReceiptsDir | Out-Null
$EnvironmentManifest = Join-Path $EvidenceDir 'environment.json'
$HelmVersion = 'not-installed'
if (Get-Command helm -ErrorAction SilentlyContinue) { $HelmVersion = (helm version --short | Out-String).Trim() }
$KindVersion = 'not-installed'
if (Get-Command kind -ErrorAction SilentlyContinue) { $KindVersion = (kind version | Out-String).Trim() }
[ordered]@{
  os = [Environment]::OSVersion.VersionString
  powershell = $PSVersionTable.PSVersion.ToString()
  python = (python --version 2>&1 | Out-String).Trim()
  docker = (docker version --format '{{.Server.Version}}' | Out-String).Trim()
  compose = (docker compose version --short | Out-String).Trim()
  node = (node --version | Out-String).Trim()
  helm = $HelmVersion
  kind = $KindVersion
} | ConvertTo-Json | Set-Content -LiteralPath $EnvironmentManifest -Encoding utf8
$EnvironmentFingerprint = (Get-FileHash -LiteralPath $EnvironmentManifest -Algorithm SHA256).Hash.ToLowerInvariant()
$GateStarted = (Get-Date).ToUniversalTime().ToString('o')
$GateFailures = [System.Collections.Generic.List[string]]::new()
# Ejecutar el grupo local-quality ahora y guardar sus cuatro logs; no reutilizar logs de otra ejecución.
make check 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'make-check-final.log')
if ($LASTEXITCODE -ne 0) { $GateFailures.Add('make check') }
make dependency-surfaces-check 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'dependency-surfaces-final.log')
if ($LASTEXITCODE -ne 0) { $GateFailures.Add('dependency-surfaces-check') }
make agent-skills-validate 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'agent-skills-validate-final.log')
if ($LASTEXITCODE -ne 0) { $GateFailures.Add('agent-skills-validate') }
$SkillsPackageDir = Join-Path $EvidenceDir 'agent-skills-package-final'
make agent-skills-package "AGENT_SKILLS_OUTPUT=$SkillsPackageDir" 2>&1 | Tee-Object -FilePath (Join-Path $EvidenceDir 'agent-skills-package-final.log')
if ($LASTEXITCODE -ne 0) { $GateFailures.Add('agent-skills-package') }
$SkillZips = if (Test-Path -LiteralPath $SkillsPackageDir) { @(Get-ChildItem -LiteralPath $SkillsPackageDir -Filter 'skill.zip' -File -Recurse) } else { @() }
$ExpectedSkillNames = @('ronin-core','ronin-data-engineering','ronin-machine-learning') | Sort-Object
$ActualSkillNames = @($SkillZips | ForEach-Object { $_.Directory.Name } | Sort-Object)
if ($SkillZips.Count -ne 3 -or ($ActualSkillNames -join ',') -ne ($ExpectedSkillNames -join ',')) { $GateFailures.Add('external skills ZIP inventory') }
$SkillHashLog = Join-Path $EvidenceDir 'agent-skills-package-hashes.txt'
if ($SkillZips.Count -gt 0) { Get-FileHash $SkillZips.FullName -Algorithm SHA256 | Out-File -LiteralPath $SkillHashLog -Encoding utf8 } else { 'No ZIP output was produced.' | Set-Content -LiteralPath $SkillHashLog -Encoding utf8 }
$GateEnded = (Get-Date).ToUniversalTime().ToString('o')
$GateStatus = if ($GateFailures.Count -eq 0) { 'passed' } else { 'failed' }
$GateReason = if ($GateFailures.Count -eq 0) { '' } else { 'Failed commands: ' + ($GateFailures -join ', ') }
python -m tools.emit_release_evidence `
  --gate-id local-quality `
  --commit $CandidateSha `
  --status $GateStatus `
  --execution-scope complete `
  --fingerprint $EnvironmentFingerprint `
  --command 'make check; make dependency-surfaces-check; make agent-skills-validate; make agent-skills-package' `
  --started-at $GateStarted `
  --ended-at $GateEnded `
  --reason $GateReason `
  --artifact (Join-Path $EvidenceDir 'make-check-final.log') `
  --artifact (Join-Path $EvidenceDir 'dependency-surfaces-final.log') `
  --artifact (Join-Path $EvidenceDir 'agent-skills-validate-final.log') `
  --artifact (Join-Path $EvidenceDir 'agent-skills-package-final.log') `
  --artifact (Join-Path $EvidenceDir 'agent-skills-package-hashes.txt') `
  --output (Join-Path $ReceiptsDir 'local-quality.json')
if ($LASTEXITCODE -ne 0) { throw 'Could not emit the local-quality receipt.' }
if ($GateStatus -ne 'passed') { throw "local-quality failed: $GateReason" }
```

Repetir la emisión para los otros nueve gates con sus archivos del mapeo de §3. `--execution-scope complete` solo se usa si se ejecutó todo el alcance declarado del gate; una selección, subconjunto o diagnóstico debe llevar `diagnostic` y no podrá producir un verdict GO aunque indique `status=passed`. Si un comando falla, conservar salida y JUnit, emitir el recibo con `--status failed --execution-scope complete --reason "..."` y no continuar como si hubiera PASS. Nunca registrar `passed` a mano ni usar una captura sin archivo/digest. El emisor calcula SHA-256 de cada archivo asociado; el agregador vuelve a verificarlo, comprueba que no supere 24 horas y lo liga a `$CandidateSha` y a `artifact-identity.json`.

El ejemplo del comando agregador usa el perfil `release_required` de Public v1. Si se cualifica el MVP, usar `local_mvp_required` en su lugar, con exactamente los diez recibos y el alcance reducido documentado en §3.

```powershell
$ReceiptFiles = @(Get-ChildItem -LiteralPath $ReceiptsDir -Filter '*.json' -File | Sort-Object Name | ForEach-Object FullName)
if ($ReceiptFiles.Count -ne 10) { throw "Expected ten distinct release gate receipts; found $($ReceiptFiles.Count)." }
python -m tools.aggregate_release_evidence $ReceiptFiles `
  --output (Join-Path $EvidenceDir 'release-bundle.json') `
  --verdict-output (Join-Path $EvidenceDir 'release-verdict.json') `
  --profile $QualificationProfile `
  --expected-commit $CandidateSha
if ($LASTEXITCODE -ne 0) { throw 'Release evidence did not produce an exact-candidate GO.' }
python -m tools.release_evidence validate (Join-Path $EvidenceDir 'release-bundle.json')
if ($LASTEXITCODE -ne 0) { throw 'Merged release bundle validation failed.' }
git status --short --branch
if ((git status --porcelain).Length -ne 0) { throw 'Candidate tree changed during qualification.' }
```

## 6. Matriz visual/manual de cierre

Cada comprobación se registra por `ruta × estado × viewport × tipo de operación`, con captura/traza sanitizada:

| Grupo | Qué recorrer y aprobar |
|---|---|
| Navegación | Las 25 rutas enumeradas en Fase 12 para Public v1 o las 12 rutas publicadas en el MVP; entrada desde sidebar, deep link, ruta activa, volver/avanzar, navegación por teclado y colapsar/expandir. En MVP, confirmar que las rutas excluidas no se ofrecen como funcionalidad. |
| Identidad | Tonos marrones consistentes en navegación, tarjetas, formularios, alertas, diálogos, tablas, breadcrumbs, tutoriales y barras de scroll; sin estilos browser-default. |
| Sidebar | Grupos comprensibles; sin rótulo “Control plane”; logo completo sin recorte; iconos legibles; botón de zarpa dentro del panel, visible al colapsar, vertical al expandir y girado a la derecha al colapsar; accessible name/tooltip y foco visible. |
| Scroll/layout | Sin desbordamiento horizontal ni scroll general innecesario; paneles largos con scroll interno y scrollbar marrón; modal/tour nunca atrapado fuera del viewport; header y controles principales alcanzables. |
| Responsive | 320×800, 375×812, 768×1024, 1440×900, 1920×1080; zoom 100/200/400%; texto largo, strings y tablas anchas, menús, modales y tutoriales. |
| Estados de API | Empty, loading, success, WARN parcial, ERROR/timeout, 401, 403, 404, 409, 422, 429, 500 y desconexión. El mensaje visual, acción permitida y log deben coincidir con la respuesta real. |
| Funciones | Crear/listar/editar/archivar y confirmar; submit/status/logs/evidence/cancel; paginación y límites; reintentos; errores sin cambios parciales; refresh mantiene estado. |
| Tour/tutoriales | Tour general al inicio, tutoriales por feature, búsqueda/contenido, sugerencia al terminar, navegación adelante/atrás, cerrar/interrumpir en cualquier paso, reentrada y puntero/bocadillo alineados al control real. |
| Accesibilidad | Axe en estados funcionales, navegación solo teclado, orden de foco, foco visible, Escape, labels/ARIA, lector de pantalla en recorridos clave, contraste WCAG AA y `prefers-reduced-motion`. |
| Logs/seguridad | Cada OK/WARN/ERROR tiene timestamp, componente y correlación útil; no aparecen tokens, passwords, DSN, datos personales ni SQL sensible; errores incluyen acción recuperable y no stacktrace interno. |

La evaluación de visual debe hacerse con la app conectada al backend real. Capturas del static server sirven para layout, pero no prueban resultados funcionales ni logs del servidor.

## 7. Expediente de evidencia obligatorio

Crear un directorio único local fuera de `dist/` y sin datos reales, nombrado por el SHA completo. Por cada gate/caso conservar:

- ID estable del maestro, familia/capacidad, prioridad, fase y criterio de aceptación.
- SHA completo, estado inicial/terminal del árbol, tag/candidato y versiones Python, OS, Docker, Compose, PostgreSQL (salida de `postgres --version` dentro del contenedor), Node, Playwright, Chromium (salida de `playwright install --list`) y Helm/kind aplicables.
- Comando exacto, hora inicio/fin con zona, duración, variables de configuración no secretas y huella del entorno.
- JUnit, JSON de acceptance, salida y logs saneados, capturas/traces/axe JSON, archivos de DB/bundle de fixtures cuando proceda.
- Digest SHA-256 de wheel, sdist, imagen, lockfile, SBOM/provenance y artifacts probatorios.
- Resultado explícito: `passed`, `failed`, `skipped` o `blocked`; motivo del skip/bloqueo y decisión humana. Un gate obligatorio con skip no pasa.
- Limpieza realizada y verificación de que solo se eliminaron recursos temporales propios.

No incluir valores de secretos en comandos guardados, capturas, logs ni archivos de evidencia. Si el commit cambia, archivar el expediente rechazado y repetir los gates afectados sobre el candidato nuevo; los resultados anteriores se conservan como históricos.

## 8. Bloqueos que pueden impedir el 3 de noviembre

1. **Alcance y etiqueta:** el estado público es 0/13 release-qualified; el build plan adjunto pide alcance incompatible y el ledger está stale. No hay base para prometer 13/13 en la fecha sin completar journeys reales.
2. **Política sin CI:** la instrucción del usuario está fijada: no habilitar CI. #199 sigue abierto porque pide CI; su texto debe reconciliarse con la política y el expediente debe usar evidencia local `local-quality`. Ningún workflow manual se presentará como CI.
3. **Suite y cobertura:** la reejecución completa contra PostgreSQL 16.4 real y Python 3.13 terminó con 4.306 passed, 24 skipped y 0 failed; `ResourceWarning` y `PytestUnraisableExceptionWarning` se elevaron a errores y ninguno ocurrió. Los skips de servicios externos y límites de plataforma no se cuentan como qualification. Los umbrales de cobertura configurados pasan en la base preservada, incluidos los 62 archivos de almacenamiento. La aplicación live pasó 29/29 casos y 56 llamadas API reales (53 `OK`, 3 `WARN` esperados por token inválido, 0 `ERROR`/5xx); el smoke de wheel recorrió las 25 rutas y el análisis axe/layout no encontró violaciones. Todo sigue siendo evidencia de árbol sucio: los journeys completos y candidate-bound de las 13 familias, incluida P11, siguen sin aceptación. Ver el registro detallado de §11.
4. **Artefactos:** paquete `0.0.0`, alpha v0.1, Helm 0.1.0 y objetivo Public v1 están desalineados.
5. **Providers y sistemas operativos:** PostgreSQL, Trino, S3-compatible, Kafka, Floci, Kubernetes local, Windows/Linux/macOS y distintas versiones de Python requieren carriles separados. La ausencia de credenciales/runners se registra como BLOCKED; no se sustituye con mocks.
6. **Humanos:** revisión de licencias/NOTICE, seguridad privada, configuración de tag/refs, aprobación del claim y publicación son acciones de mantenedor.

Al finalizar cada fase se actualiza un porcentaje **solo si existe una métrica definida**. Para Public v1, el cálculo verificable es `familias cualificadas / 13`; el ledger observado está stale en 0/13. Si se adopta el MVP, usar `journeys MVP cualificados / 7` más la métrica independiente `rutas incluidas verificadas / 12`. No usar conteo de tareas o tests para estimar porcentaje global de implementación.

## 9. Índice de fuentes del corte

- Adjuntos recibidos: `ronin_master_entrega_20261029.md` (sección 106, 29/10) y `RONIN_PUBLIC_V1_100_PERCENT_BUILD_PLAN.md` (revisión 25/10, SHA histórico `4686571…`).
- Ledger de claims evaluados para esta release: [`PUBLIC_V1_RELEASE_CLAIMS_DRAFT.md`](PUBLIC_V1_RELEASE_CLAIMS_DRAFT.md).
- Inventario completo de 305 IDs y 28 rutas: [`RELEASE_CASE_INVENTORY_2026-10-29.md`](RELEASE_CASE_INVENTORY_2026-10-29.md); generador reproducible: [`tools/generate_release_case_inventory.py`](../../tools/generate_release_case_inventory.py).
- Repositorio: `README.md`, `pyproject.toml`, `Makefile`, `compose.yaml`, `web/routes.json`, `web-tests/playwright.config.mjs`, `tests/e2e/test_v01_journey.py`, `tools/run_docker_qualification.ps1`, `tools/v01_acceptance_gate.py`.
- Release/QA: `docs/RELEASE_RUNBOOK.md`, `docs/DEVELOPMENT_QUALIFICATION.md`, `docs/product/public-v1-status.json`, `docs/product/PUBLIC_V1_SCOPE.md`, `docs/product/PUBLIC_V1_CAPABILITY_MATRIX.md`, `docs/operations/RONIN_HELM_MULTIUSER_PROFILE.md`.
- Quality policy: `docs/quality/MUTATION_CAMPAIGN_FINAL.md` (campaign closed; no recurring mutation execution by default).
- Producto y quality: `docs/product/PUBLIC_V1_BUILD_PLAN.md`, `docs/product/PLATFORM_PORTABILITY_V1.md`, `docs/product/LICENSE_QUALIFICATION_V01.md`, `tools/release_evidence.py`, `tools/aggregate_release_evidence.py`, `tools/cloud_studio_floci_qualification.py`.
- Pruebas live: `web-tests/tests/ingestion-live.spec.mjs`, `web-tests/playwright.config.mjs`, `web-tests/package.json`; evidencia/paquete: `tools/emit_release_evidence.py`, `tools/supply_chain_evidence.py`, `tests/test_release_evidence.py`, `requirements-dev.lock`.
- Referencias oficiales de comandos: [Docker Compose `up --wait`](https://docs.docker.com/reference/cli/docker/compose/up/) y [volúmenes de `compose down`](https://docs.docker.com/compose/gettingstarted/); [Playwright reporters](https://playwright.dev/docs/test-reporters); [pip-audit CLI](https://github.com/pypa/pip-audit#usage); [Helm upgrade `--kube-context`](https://helm.sh/docs/helm/helm_upgrade/); [Gitleaks usage](https://github.com/gitleaks/gitleaks#usage); [Trivy reporting/exit codes](https://trivy.dev/docs/latest/guide/configuration/reporting/).
- GitHub consultado: repo `SauronShepherd/ronin`, `main` en `f9a0456a`, solo rama remota `main`, 0 PR abiertas, 14 issues abiertas, workflows de qualification ausentes.

## 10. Registro de ejecución — jueves 29/10, fases 1 y 2; avance anticipado de fase 3

**Modo:** implementación y diagnóstico en árbol sucio sobre `f9a0456ab7df3e2bb77247d54b4336fca64903b0`. Las evidencias siguientes describen el árbol probado y no cualifican un candidato limpio para publicar.

### Fase 1 — alcance, claims y preparación

- El contrato escrito y los perfiles públicos mantienen un operador local, sin GenAI/RAG/runtime de agentes en Ronin, sin capacidades multiusuario de Ronin Pro y sin CI. Las skills siguen siendo instrucciones para coding agents externos; Helm limita el perfil público a una réplica.
- Se prepararon `PUBLIC_V1_RELEASE_CLAIMS_DRAFT.md`, `LOCAL_RELEASE_BUILD_TYPE_V1.md` y los ledgers públicos. Las 13 familias siguen bloqueadas. No se decidió formalmente Public v1 frente a Ronin Local MVP ni se aprobó una identidad/versionado coherente entre paquete `0.0.0`, README y chart `0.1.0`.
- La búsqueda de superficies publicadas no encontró rutas/UI/capacidades de GenAI ni `RONIN_AI_*`; los identificadores retirados permanecen únicamente en la denylist interna de plugins y en documentación de alcance. No se encontraron interfaces de multiusuario en la superficie pública.
- Floci quedó fijado a `2.1.0@sha256:f5aa8c18302cedb4f2385f5c4e455b3efc77fee6bf7b6e5d1712b2817ba102db`; el puerto usa loopback. Terraform `1.13.5` se descargó y su SHA-256 se contrastó con el manifiesto oficial; AWS provider `6.65.0` quedó fijado por el backend. Las pruebas reales están en la sección Fase 2.
- `requirements-dev.lock` se regeneró con resolución universal y hashes, preservando las versiones existentes y añadiendo `pyyaml-ft==8.0.0` condicionado a CPython 3.13, que `libcst` requiere. La instalación hash-locked en Docker/Python 3.11 y la resolución/auditoría completa en Windows/Python 3.13 pasaron; `pip-audit` no encontró vulnerabilidades en 33 dependencias. Evidencia: `%TEMP%\ronin-final-lock-docker-20261029\pytest.xml` y `%TEMP%\ronin-final-lock-audit-20261029\pip-audit.json`. No se probó Python 3.12. Helm, GNU Make, Gitleaks y Trivy no están instalados.

### Avance anticipado — Fase 3, instalación, lock integral y reproducibilidad

- La primera suite Python 3.12 con solo `requirements-dev.lock` falló durante la colección: faltaban `pyarrow`, `psycopg` y `scikit-learn`; también omitió casos PostgreSQL. Se generó `requirements-test.lock`, universal, con hashes y los extras `data-plane`, `open-tables`, `ml` y `streaming` además de `dev`. El lock contiene 84 paquetes y su auditoría encontró 0 vulnerabilidades. La instalación hash-locked pasó en un venv Windows/Python 3.12.
- Suite completa Windows/Python 3.12 con PostgreSQL 16.4 real: **4.204 passed, 24 skipped, 0 failed** (4.228 casos; 475,77 s). Los skips son servicios externos no configurados, qualification Docker optativa y limitaciones Windows/symlink. JUnit/log: `%TEMP%\ronin-python312-postgres-run3-20261029`.
- Wheel y sdist exploratorios se construyeron con setuptools `84.2.1`; ambos se instalaron fuera del checkout en Windows/Python 3.12 y pasaron **7/7** comandos: `--help`, `doctor --require core`, `validate`, `plan`, `skills list`, `skills validate`, `skills package`. El wheel instalado desde el archivo exacto pasó los mismos siete comandos en Linux/Python 3.11 fijado, con Git disponible; la ruta importada fue `site-packages`. Los digests exploratorios del build inicial son wheel `495f3803235cd56a2eca1ef77e24877ca973fda30c7f7527a3afa85f1f346b03`, sdist `9c2b07b175fb567d6edc22cedb8cab99e84e6e8be4e87363481ec822e7f3e66d`.
- Con el timestamp del commit como `SOURCE_DATE_EPOCH`, dos wheel builds tuvieron el mismo SHA-256. Los sdists no: 65 miembros variaban solo por timestamps tar. Se añadió `tools/normalize_release_sdist.py` y su suite de negativos; al normalizar dos sdists del mismo árbol produjeron el mismo SHA-256 `ef4a10a59b028824ee4475010190a0c539125e38b749ea98c55feae34485b417`. Tests de normalizador: **7 passed**; Ruff, formato y mypy pasaron.
- Evidencia de paquetes y smoke: `%TEMP%\ronin-installed-artifacts-20261029`; auditoría del lock integral: `%TEMP%\ronin-python312-postgres-20261029\pip-audit.json`. Estos son builds exploratorios sobre árbol sucio y versión `0.0.0`; no son artefactos de release.

### Fase 2 — triaje y pruebas observadas

- Reconciliación del maestro fuente: **305 IDs únicos** (102 en §3 + 203 posteriores) y **28 IDs históricos de ruta** (25 activas + 3 retiradas); 305 casos + 25 rutas activas = 330 entradas planificadas. La cifra anterior de “183 casos faltantes” era un error de conteo. `RELEASE_CASE_INVENTORY_2026-10-29.md` conserva los 305 criterios PASS, IDs, líneas fuente y mapeos. Familia/scope: 305/305 por grupo, aún pendiente de revisión QA. Prioridad etiquetada en origen: 203/305; tipo: 154/305; owner: 76/305; estado: 160/305. `N/D` significa que el maestro no contiene ese campo; no se inventa metadata ni se asigna PASS.
- Suite completa Python con PostgreSQL 16.4 real: **4.201 passed, 24 skipped, 0 failed** (4.225 casos, 663.865 s). JUnit/stdout/coverage: `%TEMP%\ronin-python-postgres-20261029-30b95eafad9b4e7c91d65e6e3913c34b`. Los skips restantes cubren servicios externos no configurados (S3, OTLP, Trino, Spark/SDP), aceptación Docker optativa de la suite general y límites Windows/POSIX/symlink; no se cuentan como qualification de esas plataformas/proveedores.
- Rendimiento: **3/3 passed**. Todos los umbrales de cobertura configurados en `Makefile` pasaron, incluidos almacenamiento por archivo (53 archivos), broker y herramientas de release. El gate de almacenamiento reportó `per-file coverage policy passed for 53 files`.
- Docker/worker real: **21 passed** en la corrida de qualification; los dos tests que inicialmente requerían DSN PostgreSQL se repitieron con PostgreSQL aislado y también pasaron (**2/2**). Total cubierto en las dos corridas: **23/23 pruebas**, sin skips. El gate estricto v0.1 pasó **15/15**, sin skips ni fallos. Evidencia: `%TEMP%\ronin-docker-qualification-20261029-3ff64f8d7c944459ad5100798520cdb7` y `%TEMP%\ronin-docker-postgres-tests-20261029-9773b7cb9ee04c31812ccf07ca3ef4d8`. El modo `DIRTY-WORKTREE DIAGNOSTIC` no es qualification final.
- Cloud Studio/Floci real: **PASS** en Terraform `1.13.5` y AWS provider `6.65.0`; `plan`, `apply`, `refresh`, `destroy` y `state list` terminaron con código 0; creó bucket+cola y confirmó estado vacío al destruir. Evidencia: `%TEMP%\ronin-floci-qualification-20261029-a298ca72f681418d80db5a33d190b05f\qualification.json`. Compose/volumen y workspace temporal fueron eliminados; no quedó estado Terraform en el repo.
- Live UI/API con servidor Ronin, PostgreSQL y Redpanda reales: **28/28 rutas activas pasaron**, **50 llamadas API reales** (47 HTTP 200 `OK`, 3 HTTP 401 `WARN` intencionales del test de token inválido, 0 `ERROR`/5xx). La prueba valida que el mensaje de autorización se vea en UI. Logs del servidor: 1.166 `INFO`, 0 `WARN`, 0 `ERROR`. Evidencia: `%TEMP%\ronin-live-qualification-1e75d16f3e4e42c18dc7814a31b72dff`. Esto valida navegación y operaciones seleccionadas, no cierra los journeys completos de las 13 familias; P11 streaming health pasa, el procesamiento integral sigue pendiente.
- Regresión de sandbox, Cloud Studio y parser/inventario: **49 passed** en suite focalizada. Ruff check/formato, mypy del generador de inventario, `git diff --check` y `docker compose config` pasaron.
- Gates estáticos de la pasada completa: Ruff y formato en 901 archivos, mypy en 434 archivos, arquitectura, gates-negative, dependencias/superficies, rutas/OpenAPI (185 operaciones), auditorías Studio/UI y presupuesto web, capability status, skills externas, canonical JSON Go (10 vectores/5 rechazos) y protocolo de runner Go (2 fixtures) pasaron. Se corrigió una aserción contractual obsoleta del runner Docker; la suite completa posterior terminó en verde.
- GitHub fue consultado en modo solo lectura: **14 issues abiertas, 0 cerradas**. No se cerraron issues ni se modificaron protecciones. #199 debe seguir la instrucción de no-CI; #47 permanece diferido. La reconciliación está en `RELEASE_TEST_TRIAGE_2026-10-29.md`.

**Cierre de hoy:** se implementaron el triaje reproducible y los carriles de prueba local/live disponibles para las fases 1–2. La matriz y la prueba completa están actualizadas; las fases no se declaran release-ready porque siguen pendientes la decisión humana de alcance/versión, la asignación de owners, la revisión QA de mapeos, qualification de servicios/SO no disponibles, el cierre del análisis de dependencias y la repetición sobre árbol limpio. No se ha completado la inspección visual/manual reservada a las fases posteriores. Public v1 queda en **0/13 familias cualificadas (0%)**; los recuentos de pruebas y tareas no se convierten en porcentaje de soporte.

**Recomendación al 29/10:** **NO-GO provisional** para publicar el 3/11 con la evidencia actual. Mantener la vía de producto completo y reevaluar al corte de Fase 10 (31/10, 23:00). Si no están verdes el alcance aprobado, los gates requeridos y la inspección visual/manual, retrasar; no rebajar criterios para conservar la fecha.

## 11. Registro de ejecución — viernes 30/10, fases 3–6 (cierre parcial)

**Modo:** diagnóstico en árbol sucio de la rama `20261029`, sobre `f9a0456ab7df3e2bb77247d54b4336fca64903b0`. Las evidencias no se atribuyen a un commit candidato. El progreso de release sigue en **0/13 familias cualificadas (0%)**.

### Fase 3 — instalación, CLI y artefactos

- Se añadió `third_party/qualification-tools-v1.in` y se regeneró `third_party/qualification-tools-v1.txt` como lock universal con SHA-256 para 36 herramientas y dependencias exactas. La instalación aislada Windows/CPython 3.12.10 con `pip install --require-hashes` terminó correctamente. La prueba detectó y corrigió dos defectos del lock anterior: hash obsoleto de `msgpack==1.2.2` (actualizado a `1.2.4`) y ausencia de dependencias transitivas.
- Wheel y sdist exploratorios se construyeron dos veces con el mismo toolchain y `SOURCE_DATE_EPOCH`; el sdist se normalizó. Los dos builds produjeron digests idénticos: wheel `c12dd913cf7f9cb580910620368eed4e452ee68a944be27b66bd0c0dd1849022`, sdist `6d16b53672db2df80cc068c76261fd1948320f8817c486b6703a4b63f0ef4727`.
- Ambos artefactos se instalaron fuera del checkout. `ronin --help`, `ronin doctor --require=core`, `ronin validate examples/demo`, `ronin plan examples/demo -t notebooks/etl` y `ronin skills list|validate|package` pasaron; el import procede de `site-packages`. El wheel contiene 56 recursos web y el paquete de skills produjo tres archivos.
- **La Fase 3 no cierra:** los artefactos llevan versión `0.0.0`. Resolver la identidad de versión y el soporte declarado antes del candidato final. Siguen pendientes builds/instalaciones en Linux y Python 3.11/3.13, revisión humana de licencias/NOTICE y repetición sobre árbol limpio. Recibo exploratorio: `%TEMP%\ronin-artifact-qualification-20261030-b9da9b13f244464ab8f7a913124de253\artifact-receipt.json`.

### Fases 4–6 — API, conectores, notebooks y scheduler

- Suite Python completa con PostgreSQL 16.4: **4.223 passed, 24 skipped, 0 failed** (4.247 casos; 705,64 s). JUnit y stdout están en `%TEMP%\ronin-python312-postgres-rerun-20261030`. Esa corrida precedió al último ajuste de logging; después del ajuste pasaron 57 tests focalizados de HTTP/integración y contrato. Los 24 skips incluyen Docker optativo de la suite general, límites Windows/POSIX/symlink y servicios externos no configurados; no cualifican dichos entornos.
- Docker con PostgreSQL aislado: **23/23 passed, cero skips**; acceptance estricto v0.1: **15/15**. Evidencia: `%TEMP%\ronin-docker-qualification-pg-20261030-5341b2c82da744b18520640c240409be`.
- App live con PostgreSQL y servicios reales configurados: **28/28** rutas; 53 llamadas API, 50 HTTP 200 `OK`, 3 HTTP 401 `WARN` intencionales por token inválido, 0 `ERROR`/5xx, 0 trazas inesperadas y 0 avisos/errores del servidor. Evidencia: `%TEMP%\ronin-live-qualification-logfix-20261030-9b84678d22c0481292702e80afdf8206`. Esto cubre rutas activas y operaciones seleccionadas, no todas las 13 familias.
- Floci/Terraform real: plan, apply, refresh, destroy y comprobación de estado con código 0; el estado remoto local quedó vacío. Evidencia: `%TEMP%\ronin-floci-qualification-20261030-5f59fdf07c5243f9bada5b908a819bca\qualification.json`.
- Se corrigió el logging de `BrokenPipeError`, `ConnectionAbortedError` y `ConnectionResetError` esperados cuando el navegador cancela una respuesta; las excepciones inesperadas conservan el handler y traceback. La regresión quedó cubierta en ambos servidores.
- Tras la corrección de disconnect logging pasaron **57 tests focalizados** incluyendo HTTP/integración; después, **44 tests focalizados** de paginación/cursor, superficies de dependencias, logging y Docker pasaron. JUnit y salidas estáticas finales: `%TEMP%\ronin-focused-qualification-20261030`. Ruff check/formato, mypy de los dos servidores y `git diff --check` pasaron. La suite completa no se repitió tras estos cambios: el código afectado sí se cubrió en las pruebas focalizadas y la prueba live.
- Los thresholds Makefile se reevaluaron desde una copia limpia de `.coverage`: T1, T2, T3 runtime, `pyronin`, T4, broker, tools, release gates y almacenamiento por archivo (53 archivos) pasaron. El control plane dio inicialmente 34% frente a 35%; se añadieron pruebas de query/cursor/path/serialización y ahora queda en **36%**. La corrida de cobertura original reportó un sidecar paralelo vacío/corrupto; se preservó y los thresholds se comprobaron con la base principal válida, sin combinar ese sidecar.

**Cierre parcial del día:** hay evidencia de instalación, API real, Docker/PostgreSQL y Floci en árbol sucio; fases 3–6 no quedan cerradas como release porque la versión `0.0.0`, la revisión legal, los carriles de OS/Python ausentes, la verificación manual visual y el candidato limpio siguen pendientes. Recomendación: mantener **NO-GO** hasta resolver esos bloqueos y cualificar cada familia sobre el mismo SHA limpio.

### Reejecución integral — viernes 30/10, evidencia final de la jornada

**Fuente:** rama `20261029`, HEAD `f9a0456ab7df3e2bb77247d54b4336fca64903b0`; árbol modificado. Estas ejecuciones son diagnósticas y no cualifican un candidato de release.

- Suite Python completa con PostgreSQL real `postgres:16.4-alpine` y Python 3.13, reejecutada con `ResourceWarning` y `PytestUnraisableExceptionWarning` convertidos en errores: **4.306 passed, 24 skipped, 0 failed** (4.330 casos; 499,14 s; cero avisos de recursos). JUnit, `.coverage`, transcript y salida completa: `%TEMP%\ronin-python313-postgres-plan-today-final-zero-resource-warnings-20261030`. Los 24 skips incluyen Docker optativo en la suite general, servicios sin endpoint/credenciales externos y diferencias Windows/POSIX; Docker se cualificó aparte en la siguiente viñeta. Esta corrida supersede el diagnóstico anterior que informó 72 avisos: los cierres detectados se corrigieron y no se silenciaron.
- Docker real sobre el árbol actual: imagen construida desde el checkout y worker probado con PostgreSQL 16.4 aislado: **23/23 passed, 0 skipped** (171,83 s). Acceptance gate estricto: **15/15 passed, 0 skipped, 0 xfailed, 0 failed**. Evidencia: `%TEMP%\ronin-docker-plan-today-final-20261030`; imagen `ronin:qualification-20261030-plan-today-final` (`sha256:755102d205000fde59ff2d3b9310c0715ff0b4f67d43f61824d7c7815e2379f6`). El artefacto interno informa versión `0.0.0`; es diagnóstico y no un build de release. El contenedor efímero de PostgreSQL se eliminó al terminar.
- UI/API live sobre servidor real `local-composed` (control plane SQLite), con fixtures PostgreSQL y Redpanda reales: **29/29 casos Playwright** y **56 llamadas HTTP reales** (53 `200 OK`, 3 `401 WARN` intencionales por token inválido; 0 `ERROR`/5xx). Se cubren las 25 rutas activas, los recorridos de ingestión/autorización, el guardado de conexión y filtro de Runs y el control de evidencia; la autorización inválida se confirma visualmente. Logs: **1.210 INFO, 0 WARN y 0 ERROR**. Evidencia: `%TEMP%\ronin-live-plan-today-final-20261030-v2`; se eliminaron los contenedores, volumen y red exclusivos del ensayo. La consola del entorno Python mostró avisos de pip sobre una distribución local incompleta `~ytest`; no afectó la ejecución ni procede del runtime de Ronin.
- Rendimiento: **3/3 passed**. Umbrales recalculados con el `.coverage` de la suite estricta actual: T1 **89%**, T2 **81%**, T3 runtime **77%**, pyronin **66%**, control plane **44%**, T4 **73%**, broker **46%**, tools **71%**, release gates **94%**. La política por archivo de almacenamiento pasó en **62 archivos** (mínimo 80% o ratchet individual).
- Gates locales actuales: Ruff check y format pasaron en los **905 archivos** de `CODE_PATHS`; mypy pasó en **435 archivos**; arquitectura y gates negativos pasaron; OpenAPI y consistencia de rutas cubrieron **185 operaciones**; capability status, superficies de dependencias, auditoría/presupuesto web, canonical JSON (**10 vectores, 5 rechazos**) y protocolo del runner (**2 fixtures**) pasaron. Agent Skills: validación de los tres skills pasó; los tres ZIP se empaquetaron en `%TEMP%\ronin-agent-skills-plan-today-final-20261030`. La verificación global adicional de Ruff detectó 9 documentos históricos con ejemplos Python sin formatear; no pertenece a los `CODE_PATHS` del gate y no se reescribieron en esta tarea.
- SHA-256 de los ZIP: `ronin-core` `23c6a771fb9c4aabf144eddfece6200bc33677d3680998e306ab6f5b18a12a97`; `ronin-data-engineering` `ce370e09e5cf78c2fb12864db1d0b14152499feb812b9f104a8d6e2d1a8db456`; `ronin-machine-learning` `a75485ebb135a6fe57fb48a6f1e366b21cc54fa5ed49faccab6338362b9cbdd3`.
- Navegador: suite Playwright estática **99 passed, 29 skipped**; los 29 casos omitidos por depender del carril live se ejecutaron en la qualification separada y pasaron **29/29**. El smoke del wheel instalado comprobó **25/25 rutas**, sin overflow, errores de consola, peticiones fallidas ni violaciones CSP. Axe WCAG 2 A/AA y layout sobre tres viewports: **0 violaciones graves/críticas y 0 fallos de layout**. Evidencia del wheel: `%TEMP%\ronin-ui-installed-plan-today-final-20261030`; evidencia Playwright estática: `%TEMP%\ronin-browser-static-plan-today-final-20261030`.
- Las fugas que motivaron esta pasada se corrigieron en conexiones SQLite, respuestas HTTP de error, sockets `HTTPError` y pipes de subprocesos después de `kill`/`wait`. La suite estricta confirma cero `ResourceWarning` y cero `PytestUnraisableExceptionWarning`.

**Estado actualizado de Fases 3–6:** suite Python/PostgreSQL, Docker estricto, recorridos live de UI/API, gates estáticos y Floci (evidencia previa de hoy) pasaron en árbol modificado. Esto no cierra el plan de release: el inventario de licencias necesita aprobación humana; la versión sigue en `0.0.0`; esta máquina no cualifica Linux ni todos los Python declarados; no se ha congelado un árbol limpio ni completado la inspección manual/visual; y los journeys completos de las 13 familias aún no están aceptados. Se mantiene **0/13 familias release-qualified (0%)** y **NO-GO** para publicar con la evidencia actual. Se respetan las restricciones del producto: sin GenAI integrado, sin multiusuario en Public y sin CI.

### Actualización de seguridad y Docker — viernes 30/10, árbol sucio

- El Dockerfile runtime actualiza los paquetes Debian disponibles y usa bases fijadas por digest: Python `3.11.18-slim-trixie` y Docker CLI `29.9.2-cli-alpine3.24`. Las dependencias Python de runtime ahora están separadas en un lock universal con hashes; el CLI Docker ya no introduce los avisos Go que aparecían en la imagen anterior.
- La cualificación real del runtime actualizado terminó con **23/23 pruebas Docker/worker**, sin skips, y acceptance v0.1 estricto **15/15**, sin skips/xfails/fallos. Evidencia diagnóstica: `%TEMP%\ronin-docker-security-refresh-20261030`; el runner y el contenedor efímero PostgreSQL finalizaron y se limpiaron. La imagen es `ronin:qualification-20261030-security-refresh`; no es un candidato limpio ni un artefacto de release.
- La imagen de probe se reconstruyó y arrancó como UID `65532`; el smoke confirmó Python `3.11.18`, Git `2.47.3`, Docker CLI `29.9.2`, la ausencia de pip/Setuptools/wheel/jaraco en runtime y el servicio HTTP real: `/healthz` respondió 200 con su payload esperado y una ruta desconocida 404, bajo `no-new-privileges`. Se sustituyó la configuración Git mediante variables `ENV` por configuración del sistema en build, eliminando la advertencia de BuildKit sobre posibles secretos. Se eliminó `setuptools`, `wheel` y `jaraco.context` del probe porque el servicio HTTP estándar solo usa la biblioteca estándar; esto quitó dos advisories Python sin afectar su ejecución.
- `pip-audit` sobre los locks hash-locked de desarrollo y test informó **0 vulnerabilidades conocidas** (53 y 92 dependencias). Gitleaks informó **0 secretos** tanto en el árbol de trabajo (70,62 MB) como en el historial de 1.873 commits. Informes locales: `%TEMP%\ronin-local-security-20261030`.
- Trivy 0.76.1 escaneó las imágenes runtime y probe del 30/10 con severidades HIGH/CRITICAL: **49 hallazgos HIGH en 10 CVE por imagen, 0 CRITICAL y 0 secretos**. Antes de quitar herramientas de empaquetado el probe tenía dos findings Python extra; el escaneo final ya no los detecta. Tampoco aparecen los 26 HIGH del Docker CLI Go anterior. El umbral del gate continúa fallando. CVE afectados en Debian: `CVE-2025-69720`, `CVE-2026-12064`, `CVE-2026-16742`, `CVE-2026-54369`, `CVE-2026-76642`, `CVE-2026-78408`, `CVE-2026-78409`, `CVE-2026-78410`, `CVE-2026-8458` y `CVE-2026-9538`. Debian marca varios paquetes Trixie como vulnerables pero `no-dsa`/aplazados; fixes disponibles solo en `forky`/`sid` para parte de ellos. No se cambiaron versiones a una distribución de pruebas y no se añadió una supresión automática. Informes: `%TEMP%\ronin-local-security-20261030\trivy-image-refresh.json` y `trivy-probe-refresh.json`.
- Revisión de aplicabilidad con componentes exactos: el upstream de curl confirma que `CVE-2026-12064` afecta solo al ejecutable `curl`, no a libcurl; ambas imágenes incluyen `libcurl` por Git, pero no el ejecutable. El advisory de systemd limita `CVE-2026-16742` a `systemd-homed`; ninguna imagen lo incluye. Se registraron tres findings de paquete (uno de curl y dos de systemd por imagen) como no afectados por composición, con PURL, versión, arquitectura y distro exactos en [`qualification-image-vex.openvex.json`](../../docker/qualification-image-vex.openvex.json). Fuentes primarias: [advisory de curl](https://curl.se/docs/CVE-2026-12064.html), [advisory de systemd-homed](https://github.com/systemd/systemd/security/advisories/GHSA-jm29-p7hh-vjhv), [estado Debian de curl](https://security-tracker.debian.org/tracker/source-package/curl) y [estado Debian de systemd](https://security-tracker.debian.org/tracker/CVE-2026-16742). La revisión de paquetes exactos quedó guardada en `%TEMP%\ronin-local-security-20261030\image-scope-triage.txt`.
- El VEX se contrastó contra los artefactos TAR exportados de ambas imágenes con Trivy `0.76.1`, `--vex` y `--show-suppressed`. Trivy produjo exactamente **46 HIGH visibles y 3 findings `not_affected`** por imagen. Los findings apartados son `CVE-2026-12064`/`libcurl3t64-gnutls`, y `CVE-2026-16742`/`libsystemd0` + `libudev1`; no se filtró ningún otro PURL. Informes: `%TEMP%\ronin-local-security-20261030\trivy-runtime-with-vex.json` y `trivy-probe-with-vex.json`; TAR escaneados: `ronin-runtime.tar` y `ronin-probe.tar`. Trivy documenta VEX local OpenVEX para contenedores y PURL exacto, pero la función sigue siendo **experimental** ([documentación local VEX](https://trivy.dev/docs/dev/supply-chain/vex/file/), [opciones CLI](https://trivy.dev/docs/dev/references/configuration/cli/trivy_image/)). La vista VEX no hace pasar el raw gate: siguen **46 HIGH de ocho CVE** sin resolver en cada imagen; el gate está bloqueado.
- Triaje del resto contra el Security Tracker oficial de Debian: los cuatro CVE de `util-linux` (`76642`, `78408`, `78409`, `78410`), `ncurses` (`2025-69720`), `acl` (`54369`), `curl` (`8458`) y `perl` (`9538`) siguen afectados en Trixie. Debian marca `no-dsa` algunos CVE de Trixie, aplaza el arreglo de Perl mientras se investigan regresiones y lista versiones corregidas para varios paquetes solo en `forky/sid`. `CVE-2025-69720` corresponde al overflow de `infocmp`; los cuatro advisories de `util-linux` describen vías en utilidades de montaje/namespace y algunas requieren contexto privilegiado. El advisory upstream de `CVE-2026-8458` clasifica el caso Negotiate de libcurl como Low, aunque Trivy lo incluye entre sus HIGH. Se conserva la severidad del gate y no se inventa una exclusión por falta de uso observado. Fuentes: [ncurses](https://security-tracker.debian.org/tracker/CVE-2025-69720), [acl](https://security-tracker.debian.org/tracker/CVE-2026-54369), [util-linux 76642](https://security-tracker.debian.org/tracker/CVE-2026-76642), [util-linux 78408](https://security-tracker.debian.org/tracker/CVE-2026-78408), [util-linux 78409](https://security-tracker.debian.org/tracker/CVE-2026-78409), [util-linux 78410](https://security-tracker.debian.org/tracker/CVE-2026-78410), [curl](https://curl.se/docs/CVE-2026-8458.html), [perl](https://security-tracker.debian.org/tracker/CVE-2026-9538). Por prudencia no se mezclan paquetes `forky/sid` en la imagen Trixie ni se rebaja el gate por la diferencia de severidad. La decisión técnica pendiente es reducir el set de paquetes/vulnerabilidades sin romper el contrato del runtime o adoptar y cualificar una base mantenida alternativa; después habrá que reconstruir, repetir escaneo raw/VEX y la cualificación Docker.
- Compose aplica `no-new-privileges:true` a server, runner-broker, worker y CLI, conservando el setup privilegiado del entrypoint antes de bajar el proceso a UID 65532. La qualification live con este control volvió a pasar **23/23** pruebas Docker/worker y **15/15** acceptance, sin skips/xfails/fallos. Evidencia: `%TEMP%\ronin-docker-no-new-privileges-20261030`; `docker compose config --quiet` y 22 tests de topología/qualification pasaron. Este control reduce escaladas por SUID dentro de los contenedores, pero no elimina los advisories ni cambia el resultado de Trivy.
- El contrato Docker, matriz y release evidence pasó **41 tests** antes del último cambio de Compose; después, los tests de Compose/topología/Docker pasaron **22/22** y el contrato de probe pasó **12/12**. El generador/status ledger, `capability_status`, Ruff, Ruff format, smoke del probe, `docker compose config --quiet` (con interpolación local ficticia) y `git diff --check` pasaron. El render con valores ficticios solo validó sintaxis; la acceptance real posterior levantó servicios con secretos efímeros propios y los limpió.
- Resultado: el reemplazo del CLI, el lock de runtime y la retirada del pip de build del probe reducen findings; Compose limita escaladas. **No se cierra el gate de seguridad de las imágenes.** La actualización puntual del apt repository sigue siendo mutable; antes de candidato limpio también hay que fijar snapshot/versiones del SO y repetir build, scan y qualification. No se cuentan estos resultados del árbol sucio como evidencia de release.


## 12. Reconciliación final de las fases 3–6 — viernes 30/10/2026

**Corte de evidencia:** base `f9a0456ab7df3e2bb77247d54b4336fca64903b0`, rama `20261029`, árbol de trabajo modificado. Son diagnósticos locales, no un candidato de release limpio ni evidencia candidate-bound. Esta sección supersede los recuentos anteriores del mismo día cuando difieran.

| Área de hoy | Resultado observado | Evidencia y límite |
|---|---|---|
| Suite Python + PostgreSQL 16.4 | **4.322 passed, 24 skipped, 0 failed** (4.346 casos; 613,51 s). `ResourceWarning` y `PytestUnraisableExceptionWarning` tratados como errores; ninguno. | `%TEMP%\ronin-python-postgres-sql-explain-final3-20261030`. Los skips son servicios/plataformas no disponibles u optativos, no PASS de esos entornos. |
| Docker y acceptance | Qualification real **23/23**; gate estricto v0.1 **15/15**, sin skips, xfails, fallos ni errores. | `%TEMP%\ronin-docker-qualification-sql-explain-final-20261030`. La imagen de prueba declara `0.0.0`; no es artefacto de release. |
| Playwright estático | **100 passed, 30 skipped** por requerir el carril live. | `%TEMP%\ronin-playwright-static-notebook-fix-20261030`. Los 30 casos live se ejecutaron por separado contra Ronin real. |
| UI/API live | **30/30 casos**; **72 peticiones HTTP reales**: 67 `200 OK`, 2 `201 OK` y 3 `401 WARN` esperadas por token inválido; 0 errores API inesperados/5xx. El servidor registró 1.260 eventos `INFO/OK`, sin niveles `WARN`/`ERROR`. El harness levanta `local-composed` real, con estado del control plane en SQLite, PostgreSQL y Redpanda aislados, Chromium real y worker Docker con imagen por ID `sha256`. | `%TEMP%\ronin-live-plan-today-worker-final-20261030`; el caso de notebook también se ejecutó aislado en `%TEMP%\ronin-live-notebook-worker-20261030-v7`. Incluye las 25 rutas, ingestión/autorización, Runs y el ciclo UI notebook → revisión 2 → job → worker → estado `succeeded` con evidencia de log. No es un journey completo de las 13 familias. |
| Regresión HTTP notebooks | **55 pruebas** entre el módulo de API, revisiones de notebook y contrato del runner; además Ruff y mypy limpios. `GET`, `PUT` y `DELETE` se enrutan al handler correcto; revisión esperada e historial pasan por HTTP real. | `tests/integration/test_workspace_project_http_api.py`, `tests/test_notebook_revisions.py`, `tests/test_docker_qualification_contract.py`; la regresión API forma parte de las 55 pruebas focused. |
| Floci/Terraform | Lifecycle real plan/apply/refresh/destroy; bucket y cola sintéticos visibles después de apply; borrados después de destroy y estado Terraform vacío. Terraform **1.13.5**, AWS provider **6.65.0**. Tests del gate Floci: **29 passed**, Ruff limpio y mypy sin errores en el gate. | `%TEMP%\ronin-floci-qualification-final-20261030-5a9d63242c7b.json`; SHA-256 Terraform `37095373BCF2775655502AC42BCFBCBAC2927A351952A2C9C478072782A96E1C`. El host del emulador se rechazó si no era loopback; se eliminó el compose efímero y `docker ps` quedó vacío. |
| Wheel y sdist | Dos builds idénticos por tipo. Wheel SHA-256 `1AEECDEFAFD156BE366BA75BCB9FAAABDCFDB6FE4CE6EB6B6D3AF595DA03309D`; sdist `FBBCFEF9DCB22FB312054D96A67AD071D5530C801ECA27C3A375CE8CB394D9DE`. Ambos se instalaron en venv limpios de Windows/Python 3.11, 3.12 y 3.13 fuera del checkout; `pip check`, los siete comandos CLI/skills, los 56 recursos web y el origen `site-packages` pasaron en los seis pares artefacto/intérprete. Cada uno empaquetó los tres skills. Los ZIP de skills generados desde ambos formatos son idénticos. | `%TEMP%\ronin-current-artifacts-20261030-c0c76c531d87` y recibos `%TEMP%\ronin-installed-current-20261030-e39b7881b675\artifact-install-smoke.json` y `%TEMP%\ronin-artifact-matrix-20261030\matrix-smoke.json`. Los dos artefactos siguen identificados como `0.0.0`. |
| Instalación Linux | Wheel y sdist instalados y ejecutados en `linux/x86_64`, CPython 3.11.18; `doctor --require=core`, validación/plan del demo, skills, 56 recursos web y `pip check` pasaron. | `%TEMP%\ronin-linux-artifact-smoke-runtime-20261030.log`; imagen runtime `ronin:qualification-20261030-plan-today-final`, ID `sha256:755102d205000fde59ff2d3b9310c0715ff0b4f67d43f61824d7c7815e2379f6`. El contenedor efímero se eliminó. |
| Limpieza y estado | No quedan contenedores Docker del ensayo. Los resultados y virtualenvs permanecen en `%TEMP%` para inspección. | Árbol de trabajo aún modificado; no se ha creado commit/tag candidato. |

### Resultado de las fases de hoy

- **Fase 3, instalación/CLI/artefactos: parcialmente completa.** Reproducibilidad e instalación de wheel/sdist en Windows/Python 3.11, 3.12 y 3.13 comprobadas. Faltan la decisión humana de versión, la revisión legal de licencias/NOTICE, completar la matriz Linux para Python 3.12/3.13 y la repetición contra un SHA limpio.
- **Fase 4, workspaces/proyectos/permisos/API: verificación funcional amplia, cierre parcial.** UI y API vivas cubren rutas y operaciones seleccionadas; no se da por cualificado el journey público íntegro ni aislamiento completo de P1.
- **Fase 5, conectores/ingestión/lakehouse/SQL: verificación parcial.** PostgreSQL real, Docker y SQL EXPLAIN con límites quedaron cubiertos por regresiones; Floci pasó su lifecycle real. Faltan los journeys completos por cada conector/formato y budgets de uso contra candidato.
- **Fase 6, Data Engineering/notebooks/scheduler: notebook cualificado en UI/API con worker real; scheduler parcial.** Se corrigieron rutas ubicadas en handlers HTTP equivocados: `GET notebook/{id}` trataba la lectura como borrado, `PUT` no tenía handler y devolvía 404, y `DELETE` también estaba en `do_GET`. Ahora `GET`, `PUT` y `DELETE` pasan una regresión HTTP y el navegador crea, versiona y ejecuta un notebook con worker Docker real. Siguen pendientes los journeys integrales del scheduler (cron/timezone, retry/timeout, backfill, cancelación), persistencia/reinicio y verificación de la revisión ejecutada en esos flujos; por eso P4/P5 no se dan por cerrados.

No existe una rúbrica válida para convertir estas fases en un porcentaje global de implementación. El estado de release sigue en **0/13 familias cualificadas (0%)**, lo que mide qualification y no código implementado. La recomendación permanece **NO-GO** por la falta de candidato limpio, journeys integrales, revisión visual manual y decisiones humanas de licencia, versión y claims. Los 46 hallazgos HIGH corresponden al escaneo histórico de las imágenes Debian y quedan supersedidos por el escaneo posterior de los TAR runtime/probe fijados con locks APK, que encontró 0 vulnerabilidades y 0 secretos en todas las severidades; aún se debe repetir el escaneo como recibo del SHA candidato limpio. Se mantienen los límites pedidos: sin CI, sin GenAI integrado y sin multiusuario en Public v1.

### Actualización posterior — scheduler, artifacts y qualification real — 30 October

Esta subsección supersede los resultados anteriores de hoy para las áreas
ejecutadas. Todo sigue siendo diagnóstico de worktree sucio en
20261029, derivado de f9a0456ab7df3e2bb77247d54b4336fca64903b0; no es
evidencia de un candidato limpio.

| Área | Resultado más reciente | Evidencia y límite |
|---|---|---|
| Python + PostgreSQL 16.4 | **4.335 passed, 24 skipped, 0 failed** (4.359 casos; 828,18 s). | %TEMP%/ronin-python-postgres-scheduler-20261030-56e25e29b78d46758c11940138d1992a. Skips de Docker opt-in, requisitos POSIX/symlink de Windows y servicios externos no disponibles; no se cuentan como PASS. |
| Docker y acceptance | **23/23** qualification Docker; **15/15** acceptance estricta v0.1, cero skips/errores. | %TEMP%/ronin-docker-scheduler-20261030-0a10ab82d59b42bcb23d91ae4ef614a6. Imagen local ronin:qualification-scheduler-20261030-f9a0456a; no es release artifact. |
| Navegación estática | **100 passed, 30 skipped** porque requieren APIs/servicios live. | %TEMP%/ronin-playwright-static-20261030-effc293209e64a9d840ae3fdf7c6b770. Los casos live se ejecutaron por separado. |
| Producto, UI y API live | **30/30 casos**, 99 peticiones reales: 89×200, 5×201, 1×202, 1×400 (cron inválido esperado) y 3×401 (credenciales inválidas esperadas); sin 5xx ni errores API inesperados. El servidor registró 1.260 INFO y 0 WARN/ERROR; Chromium tuvo 0 errores de consola/página. | %TEMP%/ronin-live-scheduler-20261030-833ea43248bc4956ac73c2fbe186bded. local-composed real con control plane SQLite aislado, PostgreSQL 16.4, Redpanda, Chromium y worker Docker. Incluye ejecución de notebook con estado succeeded, schedule, entrega de evento y ciclo de backfill/cancelación. No cualifica todos los journeys de Public v1 ni todos los providers. |
| Wheel y sdist instalables | Dos builds reproducibles por formato en Windows/CPython 3.13.15: wheel SHA-256 B82614479A616AD550F358DF192217AC42BC095A42142EFB3768496F12CFDB7B; sdist A57B144C7493ADBF291B5A2E1DDCFDDC0DBD0158F606CD1F40C1D502FED2683C. Ambos se instalaron en venv aislado, pasaron pip check, CLI/doctor, demo validate/plan y skills list/validate/package. Los tres ZIP de skills coinciden entre instalaciones wheel y sdist. | %TEMP%/ronin-root-artifacts-20261030-f33fbf0e3ee64164b776caacf9f54ddf. Son artefactos de diagnóstico versionados 0.0.0, no publicables. |
| Matriz limpia de instalación de artefactos | Los mismos wheel/sdist pasaron en entornos virtuales limpios de Windows/CPython 3.11, 3.12 y 3.13; import desde site-packages, pip check, help, doctor, validate/plan del demo y validación/empaquetado de tres skills. En Linux/CPython 3.11, ambos se instalaron con resolución de dependencias en venvs limpios dentro de contenedores efímeros y pasaron el mismo smoke. Se cubre el mínimo de Fase 3 (Windows para todas las versiones declaradas y un Linux). | Windows: %TEMP%/ronin-artifact-matrix-clean-20261030-d4526602e3444edfb943acfa62c9b4d6. Linux: %TEMP%/ronin-linux-artifact-smoke-clean-20261030-69bfbe232d424251aabda939b4eca7c3; imagen ronin:qualification-scheduler-20261030-f9a0456a, ID sha256:53ad4a4b6f30f072976de88562e2ef2a04c16cebf1e566900723d2917aae91a1. La etiqueta sigue siendo 0.0.0. |
| SDK pyronin | Se modernizaron sus metadatos de licencia a SPDX y se retiró el classifier de licencia obsoleto. **90 tests passed**; wheel y sdist se instalaron en venvs limpios con pip check e import desde site-packages. Wheel SHA-256 4b28077378779acc1128be06307a2c65aa747990f02fc1dea997d86565992ed2; sdist 728c19c4701e7885c60f08f365fb7d509a399b1f03e2d9c5b4bad49d11cf38b8. | %TEMP%/ronin-pyronin-modernized-20261030-afca4c45fac246ce84ad7848a5e67313. Build sin SetuptoolsDeprecationWarning. |
| Inventario de licencias del lock actual | Inventario regenerado desde el entorno aislado actual y enlazado a requirements-dev.lock con SHA-256 b1bbbd33e482242638fafa124e1385f2b76eff7cbe17ee57d349f0d9b3e50c18; 56 distribuciones. Los unit tests de licencias pasaron 101/101 y el JSON/digest coinciden. | El policy previo solo revisa 36 entradas: faltan 21 decisiones y queda una revisión obsoleta (pyyaml==6.0.3). third_party/licenses-v1.json se actualizó; third_party/license-policy-v1.json y la aprobación humana de NOTICE/licencias quedan bloqueadas. No se atribuye PASS al gate legal. |
| Regresión final de scheduler y Docker contract | **74 passed** tras el cambio de formato del test de contrato Docker; incluye daemon/lease/retry, cron, events, backfills, outbox/recovery, local composition y server composition. | Ejecución focalizada: tests/test_docker_qualification_contract.py, tests/test_scheduler_daemon.py, tests/test_scheduler_backfill_http.py, tests/test_scheduler_events.py, tests/test_scheduler_cron.py, tests/test_scheduler_execution_outbox.py, tests/test_local_composed.py y tests/test_server_composition.py. |
| Controles estáticos del árbol modificado | Ruff, mypy (381 source files), formato de 113 Python modificados, OpenAPI snapshot, Compose config, sintaxis JavaScript y git diff --check pasaron. El smoke de artefactos se corrigió para esperar tres skills y usar la sintaxis de ronin plan --target; ambos errores eran del harness, no del paquete. | Los tres ZIP se compararon por nombre y SHA-256 entre wheel y sdist. |
| Auditoría de locks | pip-audit con --require-hashes y --strict pasó contra requirements-dev.lock (**53 distribuciones, 0 vulnerabilidades**) y requirements-test.lock (**92 distribuciones, 0 vulnerabilidades**). | %TEMP%/ronin-lock-audit-20261030/requirements-dev.json y requirements-test.json; cada consulta usó una caché aislada. |

La Fase 6 ya cuenta con cobertura funcional live para el scheduler: cron,
leases/lifecycle/reintento del daemon, persistencia SQLite/PostgreSQL,
historial de eventos y vínculo a runs, backfill con plan inmutable y
cancelación. El contrato actualizado está en
[SCHEDULER_API_V1.md](SCHEDULER_API_V1.md). La cobertura observada permite
cerrar el bloque de implementación y diagnóstico de hoy para scheduler, pero
no las 13 familias ni Public v1. Sigue pendiente revisar en un candidato
limpio persistencia/reinicio de extremo a extremo y revisar visualmente de
forma manual todas las rutas.

Para las fallas de proceso, el corte de hoy también pasó los 15 pasos Docker
de acceptance: los pasos 7–9 matan y reinician un worker, esperan vencimiento
de lease y comprueban reanudación, evidencia y estado terminal. La suite
PostgreSQL integra la recuperación del daemon sin duplicar fires y replay
del outbox tras terminación abrupta; el focused run de 74 pruebas volvió a
pasar. Estos carriles son pruebas aisladas del runtime y del store; no se
afirma que cada fallo se haya inyectado en el mismo recorrido live de UI/API.

El release permanece **NO-GO; 0/13 familias release-qualified (0%)**. Siguen
abiertos versión/identidad 0.0.0, repetir Trivy sobre un SHA candidato limpio,
revisión legal de licencias/NOTICE (21 decisiones pendientes), journeys
completos de cada familia, revisión visual manual, propietario/aprobación de
claims y qualification sobre SHA limpio. El escaneo posterior de los TAR de
runtime y probe del worktree dirty dio 0 vulnerabilidades y 0 secretos en todas
las severidades; el hallazgo de 46 HIGH pertenece al escaneo anterior y no es
el estado técnico más reciente. La matriz mínima de artefactos requerida por
Fase 3 sí pasó; esto no declara soporte general de cualquier SO/versión no
probados.
La cuenta 0/13 expresa qualification, no el porcentaje de código
implementado. No se habilitó CI ni se añadieron GenAI o multiusuario.

## 13. Cierre de ejecución del 30/10 — Docker y producto live

Esta actualización reemplaza los resultados Docker y live anteriores de hoy.
Se ejecutó sobre el árbol modificado de la rama `20261029`, con base
`f9a0456ab7df3e2bb77247d54b4336fca64903b0`; no es evidencia de un candidato de
release limpio.

| Área | Resultado comprobado | Evidencia y límite |
|---|---|---|
| Docker runtime y probe | Python 3.11 Alpine 3.24.3 (`sha256:09d17d5e4c16d0a7a1eea690bcb7c6ab8616b211f8421e429e97c1bef5bd0ed2`) y Docker CLI Alpine (`sha256:5e6baf67325a79f64ed3bed6863954d5e05d0f3d4e57cbdb14809346814bbfdb`) están fijados por digest. `docker/apk-runtime.lock` y `docker/apk-probe.lock` fijan los 19/18 paquetes añadidos y todas sus versiones exactas; se eliminó `apk upgrade`. Runtime `sha256:0e96ad353b1285b9ec560f70145a0f10ca46b9d60ad2990862cc16885505d19c`; probe `sha256:3b344da8d8ee4095ad8e6c8562e2db165d7eff63f26e1f11372bbbdb61ad2084`. UID/GID 65532, sin pip/setuptools/wheel y `no-new-privileges`. | `%TEMP%\ronin-docker-apk-locked-20261030`; qualification **23/23**, aceptación estricta **15/15**, cero skips, fallos, errores y xfails. El probe real pasó `/healthz` 200 y ruta desconocida 404 bajo filesystem read-only y capacidades retiradas. |
| Seguridad de imágenes | Trivy 0.76.1, `vuln,secret`, severidades UNKNOWN–CRITICAL: **0 vulnerabilidades y 0 secretos** en los TAR exactos de runtime y probe con locks APK. | `%TEMP%\ronin-apk-locked-scan-20261030\runtime.json` y `probe.json`; los IDs de config Trivy corresponden a los IDs Docker de la fila anterior. Diagnóstico del árbol sucio, no candidato de release. |
| Aplicación UI/API live | **30/30 Playwright**, sin fallos, skips, errores, reintentos ni avisos Node. **96 llamadas** reales: 86×200, 5×201, 1×202, 1×400 esperado por cron inválido y 3×401 esperados por credenciales inválidas; 92 outcome `OK`, 4 `WARN`, 0 respuestas 5xx. El notebook se creó, versionó y ejecutó en worker Docker. Discovery PostgreSQL: 3.767 ms primera página, 112 ms segunda página. | `%TEMP%\ronin-live-apk-locked-final-20261030`; venv temporal con `requirements-test.lock` hashado, Python 3.13.15 y `live-python-freeze.txt`. PostgreSQL, Redpanda, red y volúmenes se eliminaron. `live-api-traffic.json` guarda método, ruta, estado, resultado y duración sin tokens. |
| Logs funcionales | El servidor emitió **1.262 INFO/OK**, **0 WARN** y **0 ERROR**. La UI presentó el rechazo de autorización y la validación de cron como avisos esperados; no hubo 5xx ni errores de consola/página. | `live-server.stderr.log`, `live-api-traffic.json`, `browser-live.xml` y `browser-live.log` en la evidencia live anterior. Los cuatro WARN del tráfico son 3×401 y 1×400 esperados; no son WARN del proceso servidor. |
| Scheduler con PostgreSQL | **4/4** tests reales: adapter HTTP de schedules/calendario, crear/leer/cancelar workflow por HTTP autenticado, recuperar liderazgo sin duplicar cron y replay tras matar el proceso sin crear un Job duplicado. | %TEMP%/ronin-scheduler-postgres-requalification-20261030-0cde01677ce1481b9931c79c3e10321b; contenedor PostgreSQL 16.4 aislado y eliminado al terminar. Evidencia focalizada; conformance integral de scheduler/operador sigue pendiente. |
| Aislamiento del runner | El runner instala Ronin y el plugin en un venv efímero desde el lock hashado y guarda el inventario; el Python global queda intacto. Playwright mantiene colores desactivados con `DEBUG_COLORS=0`, sin combinar `NO_COLOR` con el `FORCE_COLOR` que fija en sus workers. | La corrida completa 30/30 confirmó cero advertencias de color. El runner restaura las variables de entorno originales y elimina servicios y datos temporales al terminar. |
| Regresión focalizada | **12 pruebas de contrato Docker** pasaron; Ruff, formato, sintaxis Node, estado de capabilities y `git diff --check` pasan. La suite Python/PostgreSQL amplia previa del mismo código de producto pasó **4.335**, con 24 skips documentados; no se repitió por cambios acotados a imagen, runner, test live y documentación. | Los skips históricos de Docker opt-in y condiciones de Windows no se cuentan como PASS. |

### Pendiente antes de cualquier release

Los paquetes añadidos a Alpine quedan ahora fijados a versiones exactas y la
base Python a digest; los builds fallan si una versión fijada deja de estar
disponible, en vez de resolver silenciosamente a otra. También permanecen la
versión 0.0.0 sin decisión, 21 revisiones
de licencia pendientes, la aprobación humana de NOTICE/claims, journeys
completos de las 13 familias, scheduler/operator and notification-provider conformance, revisión visual manual y evidencia ligada a un
SHA candidato limpio. Por eso el ledger sigue en **0/13 familias
release-qualified (0%) — NO-GO**; el porcentaje refleja qualification, no
implementación. Se mantienen fuera de alcance GenAI, multiusuario en Public v1
y CI.

## 14. Reejecución integral del 30/10 — resultado actual

**Alcance de evidencia:** rama 20261029, HEAD f9a0456ab7df3e2bb77247d54b4336fca64903b0, worktree modificado. Todo lo siguiente es diagnóstico del árbol local; no califica un commit de release. Se respetó el alcance: sin GenAI integrado, sin multiusuario público y sin CI.

| Carril | Resultado | Evidencia y límite |
|---|---|---|
| Python + PostgreSQL 16.4 | **4.352 passed, 24 skipped, 0 failed**; 4.376 casos totales en 565,52 s. | %TEMP%\ronin-pg-final-20261030; JUnit, salida, transcript y .coverage. Los skips son servicios externos sin configurar, pruebas Docker opt-in y diferencias Windows/POSIX/symlink; Docker se ejecutó aparte. |
| Docker worker y acceptance | **23/23 passed**; aceptación estricta v0.1 **15/15**, 0 skips, xfails, errores o fallos. | %TEMP%\ronin-docker-final-20261030; imagen ronin:qualification-plan-today-20261030, ID sha256:9da1d260245555cbe2f80d26f69f309a361fb6112f51434512990cfb219a1524. El runner creó y eliminó PostgreSQL aislado; no quedaron contenedores del ensayo. Sigue siendo un artefacto diagnóstico con versión 0.0.0. |
| UI y API live | **30/30 Playwright** y **102 llamadas HTTP reales**: 92×200, 5×201, 1×202, 1×400 y 3×401; 0 respuestas 5xx. El flujo incluye workspace, proyecto/entorno, ingestión PostgreSQL, scheduler (zona Europe/Madrid, siguiente ejecución, idempotencia, cancelación, eventos y backfill) y notebook ejecutado por worker Docker. | %TEMP%\ronin-live-lineage-ml-logging-20261030. PostgreSQL y broker reales en Compose aislado. El 400 de cron inválido y los tres 401 con credenciales inválidas son negativos intencionales y se verifican en UI. |
| Logs live | **1.348 INFO/OK, 4 WARNING/WARN, 0 ERROR** en 1.352 eventos estructurados. Las cuatro advertencias corresponden exactamente al 400 y los tres 401 esperados; todas tienen request ID, ruta normalizada y tamaño de respuesta. No se observó secreto ni token en el inventario de tráfico. | live-server.stderr.log y live-api-traffic.json en la evidencia live anterior. Los WARN del servidor ahora reflejan respuestas 4xx del control plane, no solo los logs del router. |
| Web E2E estático | **100 passed, 30 skipped** de 130 pruebas. | npm --prefix web-tests test; skips: casos que requieren API/servicios live, ejecutados en el carril live separado. El servidor estático devuelve 404 a llamadas API no servidas y Node avisa por NO_COLOR heredado junto con FORCE_COLOR; estos mensajes pertenecen al harness estático, no a la aplicación live. |
| Wheel instalado y UI | El wheel diagnóstico se abrió con Playwright en **25 rutas**; 0 errores de consola, requests fallidas, violaciones CSP o fallos de layout. Auditoría de accesibilidad: **0 violaciones y 0 fallos de layout**. | %TEMP%\ronin-ui-final-20261030. El smoke de artefacto simula respuestas API para comprobar renderizado; las operaciones reales se validan en el carril UI/API live. Playwright Python se ejecutó con el Node del sistema porque Windows denegó el node.exe incluido en el paquete pip (WinError 5); no se modificó el producto por ese bloqueo. |
| Coverage y rendimiento | Pasaron todos los umbrales configurados (T1–T4, broker, herramientas, release gates y política de **53** archivos de storage); tests/perf: **3/3 passed**. | El reporte de cobertura se conserva con la corrida PostgreSQL. No se contaron los skips como pass. |
| Gates estáticos locales | Ruff format/check, mypy (**435 source files**), OpenAPI snapshot, arquitectura y negativos, consistencia de **186 operaciones**, presupuesto de UI, canonical JSON (**10 vectores/5 rechazos**), protocolo de runner (**2 fixtures**), superficies de dependencias, capability status y validación de los tres skills pasaron. | tools/seed_live_studio.py se formateó y ordenó después de que Ruff lo detectara. docs/ui/web-budget.json se actualizó con la medición revisada de **1.940.576 bytes, 59 assets y 34 módulos**; el gate vuelve a pasar. make no está instalado en el host Windows, por lo que se ejecutaron directamente sus comandos equivalentes. |

### Estado al cerrar las tareas ejecutables de hoy

Las fases 3–6 tienen cobertura amplia de instalación, API, conectores locales/PostgreSQL, Floci, SQL, scheduler y worker, pero **no se cierran como fases de release**. La versión publicada sigue sin decidirse y los artefactos declaran 0.0.0; faltan decisiones humanas de licencia/NOTICE y aprobación de claims; el conjunto de journeys completos de las 13 familias no está cualificado sobre un SHA limpio; no se hizo la revisión visual manual final. El smoke del wheel es una comprobación visual automatizada, no reemplaza esa revisión ni demuestra funcionalidad API. El scheduler probado live tampoco equivale a conformance de todos los proveedores de notificaciones ni a todos los escenarios de fallo/reinicio en un único journey.

Por tanto el ledger permanece en **0/13 familias release-qualified (0%) — NO-GO**. No hay un porcentaje defendible de implementación global derivable de los tests. Las 24 omisiones Python se mantienen explícitas y no se suman como éxitos. No se habilitó CI ni se añadió GenAI o multiusuario público.

#### Artefactos reproducibles y escaneo actual

- Se construyeron wheel y sdist dos veces con SOURCE_DATE_EPOCH del HEAD base (1793134348); el sdist se normalizó antes de comparar. Ambos formatos reprodujeron el mismo digest en las dos ejecuciones: wheel a6761aed7ca78e9170a8f46f528f7f253d69672596c5984464311fcc72d34bfe, sdist cfd46ae0cdc37806281d2b2ee87789e3095500ece957a82cd145dea9ba570431. Recibos y logs: %TEMP%\ronin-artifacts-final-20261030. Siguen siendo versiones 0.0.0 de un árbol sucio.
- Wheel y sdist se instalaron en venvs separados; con tzdata 2026.4 fijado por hash, ambos pasaron pip check, import desde site-packages, ronin --help, doctor --require=core, validate y plan del demo, y skills list|validate|package. Los tres ZIP de skills se generaron fuera del checkout.
- El wheel y el sdist instalado pasaron el smoke de 25 rutas y la auditoría accesible: cero errores de consola, requests fallidas, CSP, violaciones axe o fallos de layout.
- Trivy 0.76.1 escaneó la imagen runtime exacta mediante vuln,secret, severidades UNKNOWN–CRITICAL: **0 vulnerabilidades y 0 secretos**. JSON: %TEMP%\ronin-trivy-final-20261030\trivy.json. La base de datos de Trivy se descargó para esta ejecución.
- docker compose config --quiet pasó usando valores de token de prueba solo en el proceso; no se inició Compose. docker ps -a confirmó que no quedaron contenedores de la qualification.

El criterio previo de cierre por **10 iteraciones consecutivas sin hallazgos** tampoco se cumple todavía: esta reejecución encontró y corrigió el formato/import del seeder y detectó que debía actualizarse el presupuesto web medido. No se declara cerrado el build plan global.

## 15. Iteración del gate de licencias — 30/10/2026

La ejecución actual de `python -m tools.license_qualification` encontró que el lock contiene 56 distribuciones frente a 36 decisiones de política: faltan decisiones para 21 paquetes y existe una revisión obsoleta de `pyyaml==6.0.3`. El error anterior solo decía que las claves no coincidían, lo que obligaba a inspeccionar ambos JSON manualmente.

Se mejoró `tools/license_qualification.py` para listar las claves sin revisión y las obsoletas en un único diagnóstico, y para devolver un error CLI legible sin traceback. No se añadieron decisiones `allow` ni se alteró el NOTICE: las conclusiones de licencia y atribución son aprobación humana.

La suite focalizada `tests/test_license_qualification.py` y `tests/test_license_qualification_coverage.py` pasó **103/103**; Ruff, formato y mypy del módulo pasaron. La ejecución del gate sobre el expediente real continúa en **FAIL** con la cola exacta de 21 revisiones. Este cambio mejora el diagnóstico; no desbloquea el release ni cambia su **0/13 — NO-GO**.

## 16. Reejecución completa y limpieza del entorno de procesos hijos — 30/10/2026

La suite completa sobre PostgreSQL 16.4 real terminó con **4.354 passed, 24 skipped y 0 failed**, 4.378 casos en JUnit, en 975,66 s. Evidencia: `%TEMP%\ronin-full-pg-after-licensefix-20261030`. Los skips documentados corresponden a servicios externos sin configuración, Docker opt-in y diferencias de plataforma Windows; la qualification Docker y la UI/API live siguen en sus carriles separados.

La primera corrida imprimió un `CoverageWarning`: un proceso hijo terminado deliberadamente heredó los hooks de pytest-cov y dejó un SQLite `.coverage.*` vacío. Se modificó el entorno de los hijos que mueren en los tests de crash del scheduler y se amplió el helper de qualification para retirar todas las variables `COV_CORE_*`. Verificación posterior: `tests/test_artifact_qualification.py` + `tests/test_scheduler_execution_outbox.py` **23 passed**; dos recuperaciones con PostgreSQL real —daemon tras crash y replay del outbox— **2 passed**. El expediente `%TEMP%\ronin-postgres-child-env-20261030` contiene un solo `.coverage` válido y el JUnit; el contenedor efímero se eliminó. La primera repetición integral detectó una propiedad Hypothesis sin límites superiores, por lo que se acotó a cadenas de hasta 32 caracteres y 100 ejemplos, conservando Unicode. La segunda repetición localizó un `HealthCheck.too_slow` no determinista en una propiedad de identidad T1 ya acotada; se mantienen 100 ejemplos y se suprime exclusivamente esa alerta del generador, sin omitir ni reducir el test. El test de timeout del sandbox de calidad evita heredar hooks de cobertura en el proceso que termina deliberadamente.

La tercera repetición integral quedó limpia: **4.354 passed, 24 skipped, 0 failed**, 4.378 casos JUnit, en 807,37 s con PostgreSQL 16.4 real. No hubo `CoverageWarning`; el expediente `%TEMP%\ronin-full-pg-final-after-harness-fixes-20261030` contiene únicamente `.coverage`, stdout/transcript y JUnit, sin archivos `.coverage.*`. El contenedor PostgreSQL temporal se eliminó. Ruff, formato, `git diff --check` y `tools.capability_status` pasan. Los skips son servicios externos no configurados, qualification Docker opt-in y límites propios de Windows. Este resultado sigue siendo evidencia diagnóstica de un árbol modificado; no califica un SHA de release limpio.

El requisito de **10 iteraciones consecutivas sin hallazgos** sigue abierto: las dos reejecuciones anteriores detectaron defectos del harness antes de la tercera pasada limpia. No se declara 10/10 ni se cuentan como limpias revisiones que encontraron y corrigieron problemas.

El release continúa **NO-GO, 0/13 familias cualificadas**: siguen sin resolverse la versión de publicación, 21 revisiones humanas de licencia/NOTICE, aprobación de claims, journeys completos en un único candidato limpio y revisión visual manual. Docker qualification 23/23, acceptance estricta 15/15, UI/API live 30/30 con 102 llamadas reales y los gates estáticos anteriores son evidencia complementaria del árbol sucio; no cierran esas decisiones ni familias.

Se contrastó el bloqueo de versión con `PUBLIC_V1_SCOPE.md`: allí la línea `0.1.0a*` se define como alpha de ingeniería/fundación, no como el gate del producto Public v1. El documento no asigna un número final de paquete. Por ello no se cambia automáticamente `ronin-studio 0.0.0` ni `pyronin 0.0.1a0` a `0.1.0` o `1.0.0`: esa versión sigue pendiente de decisión de producto y los artefactos actuales siguen siendo diagnósticos no publicables.

El gate real de licencias continúa fallando hasta que haya aprobación humana de las 21 entradas y de la política de NOTICE. Progreso release-qualified: **0/13 (0%) — NO-GO**; ni esta corrida ni los diagnósticos del árbol sucio constituyen una qualification de candidato limpio.

## 17. SBOM de contenedores ligado a imagen y candidato — 30/10/2026

Se cerró el hueco entre el CycloneDX de dependencias Python y el inventario OS
de las imágenes. `tools.bind_container_sbom` acepta el CycloneDX 1.7 real de
Trivy, exige que imagen TAR y SBOM bruto estén en `artifact_identity`, abre el
TAR sin extraerlo, valida su manifest/config, recalcula el SHA-256 del config,
compara digest y tag con el root Trivy y añade commit, hashes, referencia y
versión del scanner. Limita el tamaño de los metadatos leídos del TAR y rechaza
manifiestos multi-imagen, rutas config inseguras o inventarios OS incompletos.

`tools.supply_chain_evidence` acepta CycloneDX 1.7 y, para cada SBOM de
contenedor, vuelve a generar la salida desde el TAR y SBOM bruto fijados en el
manifiesto de identidad; compara el documento completo para detectar cambios
en paquetes. `--require-container-inventory` exige dos imágenes distintas;
el recibo informa cantidad OS, archive SHA, config SHA, referencia y Trivy.
La provenance permite registrar `trivy`. El procedimiento de la Fase 13 ahora
exporta runtime y probe por separado, genera inventarios y escaneos del TAR
exacto, incluye archivos brutos en la identidad y valida ambos SBOM ligados.

La prueba de integración usó TAR reales y CycloneDX 1.7 emitidos por Trivy
0.76.1 en `%TEMP%\ronin-exact-image-scan-20261030`, reconstruyó el SBOM de
aplicación desde `requirements-dev.lock`, generó provenance local y pasó el
validador exigiendo runtime + probe. Inventario: runtime **57 paquetes OS**,
config SHA-256 `6acacaa53ba5c3c85a3370873e3b52d4103f6c6221bed9d6c71a68e825d76a9f`;
probe **56 paquetes OS**, config SHA-256
`e68de5971207a8d40cfcec9c55e5f86554751f14a386ca87043faa7c91ff8ebe`. El
resultado, los SBOM ligados y la identity de diagnóstico están en
`%TEMP%\ronin-container-sbom-bound-smoke-20261030`. Pruebas focalizadas:
**123 passed**; el binder tiene **100% de cobertura de líneas y ramas** y quedó
añadido al gate `coverage-release-gates` con suelo de 90%. Ruff, Ruff format y
mypy pasan. La suite completa final con PostgreSQL 16.4 terminó con **4.404
passed, 24 skipped, 0 failed**, **4.428 casos JUnit**, en **659,30 s**.
Expediente: `%TEMP%\ronin-full-pg-final-container-sbom-20261030-20261030-155155-64df587f`.
No hubo `CoverageWarning`; quedó solo `.coverage`, sin archivos secundarios
`.coverage.*`, y el runner eliminó el contenedor PostgreSQL temporal. El gate
`coverage-release-gates` pasó con suelo de 90% para sus 15 módulos (95% total);
el binder conserva 100% de cobertura de líneas y ramas. `tests/perf` pasó
**3/3** en 0,56 s. Los skips son Docker opt-in, proveedores/servicios externos
no configurados y límites de plataforma Windows. Esta reejecución verifica el
árbol actual después de añadir los casos de límites, pero no satisface el
criterio separado de diez iteraciones limpias consecutivas.

Esta integración es un diagnóstico del worktree modificado en `20261029` sobre
`f9a0456ab7df3e2bb77247d54b4336fca64903b0`, no un recibo release. Sigue
**NO-GO, 0/13** hasta repetir los gates sobre candidato limpio y resolver las
aprobaciones humanas, journeys, claims, versión y revisión visual manual.

## 18. Suite Linux corregida y estabilidad del sandbox — 30/10/2026

Se repitió la suite completa en Docker con Python 3.11.18, dependencias de
`requirements-test.lock` instaladas con hashes y PostgreSQL 16.4 aislado. El
snapshot de fuentes conservó la rama `20261029`, `HEAD` y `origin/main` en
`f9a0456ab7df3e2bb77247d54b4336fca64903b0`, y las modificaciones del
worktree como cambios locales. La suite terminó con **4.412 passed, 16
skipped, 0 failed** (4.428 casos JUnit) en **730,15 s**; `tests/perf` pasó
**3/3** en **2,37 s**. No hubo `CoverageWarning` ni
`PytestUnraisableExceptionWarning`. El expediente está en
`%TEMP%\ronin-full-pytest-linux-final-20261030-b0fc103f`; al finalizar se
eliminaron el PostgreSQL temporal y su red.

La primera ejecución Linux (`4.411 passed, 16 skipped, 1 failed`) usó un
commit sintético para representar el árbol sucio; `test_public_v1_status` no
pudo resolver el SHA base porque ese objeto no estaba en el snapshot. En la
segunda ejecución (`4.410 passed, 16 skipped, 2 failed`) ya estaba disponible
el commit real como `origin/main`, pero el `HEAD` seguía siendo sintético:
`test_changed_surface` intentó clasificar más de mil rutas de archivos del
snapshot. Esos fallos se separaron de problemas del producto al alinear el
`HEAD` temporal a `f9a0456`, preservando el worktree modificado. Después,
`test_changed_surface.py` y `test_public_v1_status.py` pasaron en el full run.

El primer full run con Git corregido también expuso un timeout intermitente de
`test_custom_python_expression_uses_bounded_sandbox` cuando `pytest-cov`
inyectaba hooks de cobertura en el proceso aislado. Una repetición de diagnóstico
observó el timeout del predicado trivial a los **10,067 segundos** frente al límite
de diez segundos. Se ajustó el test positivo para retirar del worker esos
hooks (`COV_CORE_*`, `COVERAGE_FILE` y `COVERAGE_PROCESS_START`), igual que ya
se hacía en la prueba del worker terminado por timeout. El límite de seguridad
del runtime no se amplió. Tras el ajuste pasaron **47 tests focalizados** de
superficie/calidad/sandbox en Linux con cobertura y **47/47** en una repetición
Linux sin cobertura y otra Windows. Ruff check/format y mypy del test modificado
pasaron; la suite completa Linux quedó verde.

Esta evidencia corresponde a un **worktree modificado** sobre el baseline
`f9a0456`, no a un candidato limpio ni a una release qualification. Los 16
skips son servicios externos sin endpoint/credenciales y casos Docker optativos
de la suite Python general; Docker runtime/acceptance se verificó en su carril
separado. El release sigue **NO-GO, 0/13 familias**: faltan decisiones de
versión, revisión humana de licencias/NOTICE y claims, journeys integrales sobre
un candidato único, y revisión visual manual.

## 19. Corrección y requalification live de workspaces — 30/10/2026

La matriz live completa descubrió un hueco que no aparecía en las pruebas de
composición: con las rutas de plugins activas, `GET /v1/workspaces` se
interceptaba antes del handler paginado y la UI no recibía `{items,
next_cursor}`. La creación por plugin tampoco podía autorizarse porque el path
no contiene un `workspace_id`. Se corrigió el dispatch para que el listado
raíz use el handler integrado de workspaces; la mutación de creación se
autoriza contra el workspace local configurado, responde `201 Created` y
registra el workspace recién creado en el alcance conocido del operador
estático. Al arrancar, la composición registra los workspaces persistidos; los
IDs desconocidos siguen denegados por defecto. Este alcance es de un solo
operador local y no añade multiusuario.

Se añadieron regresiones para la forma paginada del listado, la creación por
plugin con permiso `workspace.write`, el registro de workspaces conocidos y el
rechazo de IDs desconocidos. Tras el cambio pasaron **68 pruebas** de
`test_static_control_plane`, `test_local_composed`, `test_server_composition` y
`test_workspace_project_http_api`; también pasaron Ruff check/formato, mypy de
los tres módulos Python tocados, `node --check` del test live y
`git diff --check`.

La corrida completa Docker-backed terminó con **31/31 casos Playwright**, cero
fallos, skips o errores, y **108 llamadas API reales**: 101 `OK` (94×200,
6×201 y 1×202) y 7 `WARN` esperados (5×401 por credenciales inválidas/ausentes,
1×400 por cron inválido y 1×403 por workspace fuera de scope), sin respuestas
5xx. El worker ejecutó el notebook y PostgreSQL/Redpanda aportaron los datos
live. Los logs del servidor contienen **1.394 INFO/OK, 7 WARNING/WARN y 0
ERROR**; los siete warnings corresponden a los mismos rechazos/validación
esperados. JUnit informa 31 tests, cero fallos, skips y errores. El runner
eliminó los contenedores, volumen y red al cerrar. Expediente:
`%TEMP%\ronin-live-plan-today-full-p4-20261030`.

La suite Python/PostgreSQL completa más reciente (4.412 passed, 16 skipped)
precede a esta corrección acotada; después del cambio se ejecutaron las 68
pruebas afectadas y la matriz live completa. No se presenta ese resultado
anterior como reejecución integral posterior al cambio.

**Cierre técnico de hoy:** las tareas automatizables de las fases 3–6 tienen
evidencia amplia y el hueco live de workspace quedó corregido. Esto no cierra
los gates humanos ni la release: versión final, aprobación legal/NOTICE,
aprobación de claims, inspección visual manual y repetición sobre un candidato
limpio siguen pendientes. El estado de release permanece **NO-GO, 0/13 (0%)**;
esa cuenta mide qualification de release, no código implementado. La corrida
live y las regresiones de esta sección son diagnóstico de un worktree sucio.

## 20. Journey live de Graph: RQL, objetos y vecinos — 30/10/2026

La revisión del test de rutas de Studio encontró que Graph únicamente
disparaba RQL y aceptaba cualquier respuesta exitosa a una de las rutas
declaradas. Se amplió el fixture aislado con una Persona y una Organización
unidas por una relación; el test live ahora ejecuta RQL, lista los objetos
`Person` y consulta sus vecinos. Para cada operación comprueba HTTP 200, el
payload que devolvió el API y el resultado visible en la UI. No ejecuta la
acción de escritura desde ese recorrido de solo lectura.

Evidencia posterior al cambio: test live de Graph **1/1 passed**, **3 llamadas
API reales, todas HTTP 200/OK**, expediente
`%TEMP%\ronin-live-graph-phase7-20261030`; las regresiones locales
`test_ontology_http.py` y `test_graph_runtime.py` pasaron **31/31**. También
pasaron `node --check`, Ruff, Ruff format y `git diff --check`. El harness
eliminó PostgreSQL, Redpanda, volumen y red. Esto profundiza P6/RQL, pero no
cierra P6: faltan recorridos completos enlazados a catálogo/activos y la
qualification del journey sobre un único SHA limpio.

## 21. Quality Studio: fallo de gate como conflicto y journey live — 30/10/2026

El recorrido de Quality mostró que `enforce_blocking=True` persistía correctamente
una ejecución fallida, pero `QualityExecutionBlocked` llegaba al manejador genérico
y se devolvía como `500 internal_error`. Ahora se representa como `409
quality_gate_blocked` con un mensaje seguro y estable. Se documentó el `409` en
OpenAPI y se regeneró `api/openapi-v1.sha256`; el snapshot valida con digest
`c579b9cc87e4d1be351fd217aa31eb01ff6f12b962493797e23e3d2040e979ed`.

La prueba HTTP de regresión confirma que el error del dominio se convierte en
conflicto, no en error interno. El journey live guarda un contrato sobre un activo
registrado, ejecuta una fila válida, fuerza el bloqueo con una fila inválida y
carga después el estado persistido para comprobar el resultado fallido. El primer
intento usó un activo inexistente y recibió `404`; se corrigió el fixture para usar
`live-lineage-target@1`, cuya revisión se registra en el catálogo aislado.

Después del cambio pasaron **51/51** pruebas focalizadas de HTTP/Quality, mypy,
Ruff y formato; `tools.openapi_snapshot` y sus seis pruebas de snapshot también
pasaron. La reejecución Docker completa de la matriz web pasó **31/31** con **113
llamadas API reales**: 105 `OK` (97×200, 7×201 y 1×202) y 8 `WARN` esperados
(5×401, 1×400, 1×403 y 1×409); cero 5xx. El servidor registró 1.398 `INFO`, 8
`WARNING` y 0 `ERROR`. JUnit informa cero fallos, omisiones o errores. El runner
eliminó PostgreSQL, Redpanda, volumen y red. Evidencia:
`%TEMP%\ronin-live-plan-regression-final-20261030`.

Esta reejecución es diagnóstico del worktree sucio sobre `f9a0456`, no
qualification de release. La suite Python/PostgreSQL completa (**4.412 passed,
16 skipped**) es anterior a esta corrección; después se ejecutaron las 51 pruebas
focalizadas y la matriz web completa. P8 continúa parcial y la release sigue
**NO-GO, 0/13 familias release-qualified** hasta tener un SHA limpio, recorridos
integrales, inspección manual y visual, versión decidida y aprobaciones humanas de
licencias/NOTICE y claims.

## 22. Machine Learning Studio: journey clásico live y registro durable — 30/10/2026

La ruta `mlstudio` solo comprobaba antes que la pantalla cargara. Se amplió el
journey de Playwright para crear un Lab, ejecutar su quality check, buscar dos
trials, entrenar con el backend local y registrar el modelo candidato. La prueba
confirma el resultado HTTP y la salida visible tras cada operación. También se
añadieron estados accesibles `role=status`/`role=alert`; durante quality/search el
botón se deshabilita y anuncia el trabajo. El proxy live permite hasta 90 s para
`/search` y el caso ML tiene un presupuesto de prueba de 240 s.

La primera ejecución mostró dos problemas. El proxy de test abortaba a los 15 s;
al elevarlo a 60 s todavía cancelaba la búsqueda. El API finalizó la búsqueda en
**73 s**, pero el navegador perdió la respuesta y Playwright agotó su minuto. Se
ajustó el presupuesto de esta operación para reflejar la ruta real. Queda como
hallazgo de rendimiento P8: el endpoint de búsqueda es síncrono y su primer uso en
frío tarda 73 s en este entorno Windows. La UI ya ofrece feedback, pero hay que
optimizar la carga/ejecución fría o mover la búsqueda a un trabajo asíncrono antes
de considerar P8 cerrada.

Al repetir, el entrenamiento asíncrono acabó en `succeeded`, pero el registro
respondió `400 invalid_request`: la lectura terminal de `JobStoreExecutionStore`
descartaba `rows_json`, necesario para construir la firma del modelo. Se añadió
`get_for_registration`, que recupera y verifica entradas inline o desde el
artifact store solo para la operación explícita de registro. Los GET normales de
estado siguen sin devolver filas privadas. Pasaron las regresiones de datos inline
y de 1,1 MB basados en artefacto.

Las suites focalizadas de almacenamiento/orquestación/registro/HTTP ML pasaron
**67/67**; Ruff, formato y mypy también pasaron. El journey live filtrado pasó
**1/1** con **21 llamadas reales**, todas satisfactorias. La repetición completa de
Playwright pasó **31/31** en **3,1 min**, con **130 llamadas API**: 122 `OK`
(114×200, 7×201 y 1×202) y 8 `WARN` esperados (5×401, 1×400, 1×403 y 1×409), sin
5xx. Los logs del servidor registraron 1.415 `INFO`, 8 `WARNING`, 0 `ERROR`; JUnit
no tuvo fallos, skips ni errores. Se eliminaron los contenedores, volumen y red.
Evidencia focused: `%TEMP%\ronin-live-ml-e2e-final2-20261030`; matriz completa:
`%TEMP%\ronin-live-full-after-ml-20261030`.

La suite completa Python/PostgreSQL (**4.412 passed, 16 skipped**) es anterior a
los últimos cambios ML; después se ejecutaron las 67 pruebas afectadas y el live
completo. Todo es diagnóstico en el worktree modificado `20261029` sobre
`f9a0456`, no evidencia de candidato limpio. P8 sigue parcial por la latencia fría
y por los recorridos de promoción/deployment/predicción que faltan; la release
permanece **NO-GO, 0/13 familias qualified**. Sin cambios de alcance: no se añadió
GenAI integrado, multiusuario Public ni CI.

## 23. Reejecución completa tras las correcciones de Quality y ML — 30/10/2026

**Candidato observado:** rama `20261029`, HEAD `f9a0456ab7df3e2bb77247d54b4336fca64903b0`, worktree modificado. Esta corrida valida el estado actual del árbol y no constituye qualification de un candidato limpio.

| Carril | Resultado actual | Evidencia y límite |
|---|---|---|
| Python completo con PostgreSQL real | **4.406 passed, 24 skipped, 0 failed**; JUnit contiene 4.430 casos. Se ejecutó en Windows/Python 3.13.15 con PostgreSQL 16.4 aislado, en 551,77 s. | `%TEMP%\ronin-postgres-full-after-ml-20261030`; transcript, salida, JUnit y cobertura. Los skips cubren prerequisitos opcionales, integraciones externas no configuradas y diferencias de plataforma/privilegios Windows; no se cuentan como PASS. Contenedor eliminado al finalizar. |
| Playwright completo contra servidor estático | **100 passed, 31 skipped**, 131 en total, en 3,8 min. | `npm test --prefix web-tests`. Los 31 casos que requieren API/servicios reales se excluyen en este carril y se recorren en la fila live. El servidor estático responde 404 a llamadas API que no hospeda; esos mensajes de consola de este carril no representan la respuesta de Ronin live. |
| Playwright live contra Ronin | **31/31 passed**, **130 llamadas API reales**, 0 respuestas 5xx: 122 OK (114×200, 7×201, 1×202) y 8 WARN esperados (5×401, 1×400, 1×403, 1×409). El proceso registró 1.415 INFO, 8 WARNING y 0 ERROR; JUnit sin fallos, skips ni errores. | `%TEMP%\ronin-live-full-after-ml-20261030`; Docker Compose con PostgreSQL/Redpanda, navegador Chromium y worker Docker reales; contenedores, red y volúmenes eliminados por el harness. Incluye Quality bloqueante y ML Studio con quality, búsqueda, ejecución durable y registro de modelo. |
| Rendimiento Python | **3/3 passed** en 2,43 s. | `python -m pytest -q tests/perf`; umbrales configurados pasaron, pero esta suite no cubre la latencia de la búsqueda ML live que se indica abajo. |
| ML Studio focalizado | **67/67** pruebas de almacenamiento/orquestación/registro/API; Ruff, formato y mypy pasaron. Live ML: **1/1**, 21 llamadas reales con éxito; entrenamiento durable `succeeded` y registro HTTP 200. | `%TEMP%\ronin-live-ml-e2e-final2-20261030`. La suite Python completa de arriba vuelve a incluir estas regresiones con PostgreSQL habilitado. |

La matriz live midió la búsqueda ML síncrona fría en **73 s**. El navegador ahora presenta estado accesible y mantiene el control deshabilitado mientras espera; el proxy de qualification acepta hasta 90 s. La solicitud termina correctamente, pero la latencia es demasiado alta para cerrar P8: aún requiere perfilar el coste de inicialización/ejecución y reducirlo o convertir el contrato en una ejecución asíncrona observable. No se atribuye el tiempo a una causa no medida.

Los 24 skips de Python y 31 skips de Playwright se conservan explícitos; la prueba estática no reemplaza el recorrido API live. Docker/worker sí se ejercitó en el harness live, y la qualification dedicada más reciente registrada arriba sigue en 23/23, pero esta reejecución Python/web no vuelve a medir todos los gates de supply chain ni la matriz de SO/intérpretes.

El trabajo sigue siendo diagnóstico del árbol sucio: no hay SHA limpio cualificado, no se han completado journeys de las 13 familias sobre un mismo candidato, ni la revisión visual manual, ni las decisiones humanas de versión, licencias/NOTICE y claims. Por tanto el release permanece **NO-GO, 0/13 familias release-qualified (0%)**. Tampoco se declara cumplida la condición de diez iteraciones consecutivas sin hallazgos. Sin cambios de alcance: no se añadió GenAI integrado, multiusuario Public ni CI.

## 24. Reejecución final de hoy: evaluación ML, Docker y matriz live — 30/10/2026

Esta pasada parte del mismo `f9a0456ab7df3e2bb77247d54b4336fca64903b0`, rama
`20261029`, con worktree sucio. Su resultado es evidencia diagnóstica del árbol
actual, no una qualification limpia de release.

### Corrección funcional: revisión explícita antes de promover modelos

El ciclo durable de ML ya registraba modelos, pero no guardaba la decisión del
operador que justifica la promoción. Se añadió
`POST /v1/ml-studio/models/{model_id}/{version}/evaluations`: acepta un resultado
`passed`, `failed` o `unknown` y una referencia acotada; toma dataset y métricas
del run fuente inmutable del modelo, no de datos enviados por el navegador. La
tarjeta del modelo expone el historial. La promoción continúa bloqueada hasta que
exista una evaluación `passed`; intentos incompatibles se expresan como `409` y
no como error interno. SQLite permite reintentos idempotentes y limita cada
historial a 100 revisiones. PostgreSQL serializa el límite bloqueando la fila del
modelo y conserva la misma regla. La UI muestra dataset y métricas, exige elegir
el resultado del operador y permite guardar la evidencia antes de promover.

OpenAPI y su SHA se actualizaron. Hay regresiones HTTP para `409`, datos extra y
payloads inválidos, historial visible, bloqueo `unknown` y promoción posterior
al resultado aprobado; SQLite y PostgreSQL prueban también idempotencia y el
límite de 100.

### Resultados reproducidos

| Carril | Resultado | Evidencia/límite |
|---|---|---|
| Python completo + PostgreSQL 16.4 | **4.408 passed, 24 skipped, 0 failed**; 4.432 casos JUnit, Python 3.13.15, 636,67 s. Incluye 12 integraciones PostgreSQL ML y los tests HTTP/SQLite del flujo de evaluación. | `%TEMP%\ronin-postgres-full-after-ml-evaluation-20261030`. Skips conservan sus prerequisitos externos/plataforma; no cuentan como PASS. Contenedor aislado eliminado. |
| Rendimiento Python | **3/3 passed** en 2,37 s. | `python -m pytest -q tests/perf`; no mide la demora del primer `search` ML live. |
| Playwright estático | **101 passed, 31 skipped**, 132 casos. | Los skips son pruebas live ejecutadas aparte; la maqueta estática no valida el API. |
| Docker worker + aceptación v0.1 | **23/23 passed**; gate estricto **15/15**, cero skips/fallos/errores. La imagen runtime se construyó y usó por digest; PostgreSQL 16.4 se aisló y eliminó. | `%TEMP%\ronin-docker-qualification-plan-today-final-acf433140dc74f088304d3644c4c4966`. Diagnóstico del worktree sucio. |
| Producto live, Playwright/Chromium + API real | **31/31 passed**, las **25/25 rutas activas** aparecen en JUnit; **143 llamadas**: 126×200, 7×201, 1×202 y 9 WARN esperados (1×400, 5×401, 1×403, 2×409). Cero errores 5xx/red y cero faltas de autorización inesperadas. El servidor registró 1.427 INFO, 9 WARNING correspondientes a esos WARN y 0 ERROR. PostgreSQL, Redpanda, worker, red y volumen quedaron eliminados. | `%TEMP%\ronin-live-qualification-plan-today-final-f3fcae4acfc94d108137d3ec7c539684`; JUnit sin skips/fallos. Incluye `409` al promover sin revisión aprobada, creación de evaluación, lectura de tarjeta y promoción después de aprobación, además de notebook sobre worker Docker real. |
| Contratos/scripts de qualification | **19/19** tests de los contratos de Docker/OpenAPI; Ruff y parser de Windows PowerShell pasan. | Cubre compatibilidad con Windows PowerShell 5.1, captura stderr de `docker logs` sin impedir el cleanup, aplanado explícito de arrays JSON para verificar rutas/eventos y recuentos completos. |

La matriz live midió la búsqueda ML fría en aproximadamente **78 s** (la prueba
Playwright reportó 1,4 min). El estado de UI hace observable la espera y el runner
ya no pierde la respuesta, pero la búsqueda síncrona sigue siendo lenta y P8
continúa abierto. No se declara optimizada ni se atribuye la demora a una causa
sin perfil medido.

La qualification Docker anterior a la corrección de cleanup llegó a 23/23 y
15/15, pero devolvió código 1 por el mensaje `locale: not found` de stderr al
guardar logs. Se corrigió `finally` y se repitió: ahora el runner completa cleanup
y devuelve 0. La matriz live encontró tres defectos del propio runner de Windows:
resolución incorrecta de `pwsh.exe`, `Invoke-WebRequest` dependiente de IE y
enumeración anidada del JSON al comprobar las rutas y contar tráfico. Se
corrigieron y se repitió de extremo a extremo; solo la última ejecución arriba se
cuenta como resultado global aprobado.

**Estado al terminar hoy:** no se han aprobado versión final, licencias/NOTICE,
claims ni revisión visual manual; no se han recorrido las 13 familias sobre un
SHA limpio único ni todas las plataformas admitidas. P8 sigue parcial; la
qualification limpia pendiente significa que las familias permanecen
**0/13 release-qualified (0%)** y el release está **NO-GO**. No se añadieron CI,
GenAI integrado ni multiusuario a Public.

## 25. Continuación: búsqueda ML y presupuesto web — 30/10/2026

La qualification live aislada volvió a completar el journey ML con **1/1 casos**,
36 llamadas API reales y sin errores de navegador, servidor o red. La nueva
telemetría registra preparación y duración por trial sin incluir filas,
parámetros ni identificadores. En el entorno precompilado, la búsqueda tomó
**37,38 s**: primer trial **37,27 s**, segundo **43 ms**, preparación **32 ms**.
Se eliminó `pip --no-compile` del instalador live para compilar bytecode durante
la preparación; esta medida no basta para cerrar el cuello de botella. P8 sigue
abierto y no se atribuye la variación frente a las corridas de 73–82 s a una
causa no demostrada. Evidencia: `%TEMP%\ronin-live-ml-precompiled-8db6e26cc348443cba7f90e2f6d11958`.

El budget gate encontró **3.069 bytes** sobre el límite revisado anterior
(1.940.576 bytes), ligados a nuevas vistas/acciones de SQL Explain y revisión de
ML y ajustes de estudios existentes. La inspección confirmó que no se añadieron
assets ni solicitudes. Se actualizó el límite al valor medido de **1.943.645
bytes**, manteniendo **59 assets, 34 módulos, 6 hojas de estilo y 4.871 bytes de
HTML**. `tools.studio_budget --check` y `tools.studio_web_audit` pasan; la
auditoría recorrió 60 archivos y 172 invocaciones de ruta sin fallos. Este es un
ajuste de presupuesto explícito y pequeño (0,16%), no una qualification de
rendimiento ni una aprobación de release.

Las pruebas focalizadas de ML y contratos live/Docker pasaron **45/45** en la
ejecución secuencial. Una corrida anterior en paralelo tuvo un fallo temporal
por la ventana de 30 s en el test de ejecución; el caso pasó aislado y el módulo
completo pasó después en serie. Ese primer fallo queda registrado y no se cuenta
como verde.

**Estado:** continúa **NO-GO, 0/13 familias qualified (0%)**. El resultado live
es del worktree sucio; faltan la resolución de P8, candidate SHA limpio, journeys
completos de las 13 familias y aprobaciones humanas de versión, licencias/NOTICE,
claims y revisión visual. No se declara completa la condición de diez iteraciones
limpias consecutivas. Se mantiene fuera de alcance CI, GenAI integrada y
multiusuario Public.

## 26. Verificación integral repetida del árbol actual — 30/10/2026

**Árbol examinado:** rama `20261029`, base `f9a0456ab7df3e2bb77247d54b4336fca64903b0`, con cambios locales. Los informes siguientes no pertenecen a un commit limpio.

| Carril | Resultado | Evidencia y límites |
|---|---|---|
| Suite Python completa + PostgreSQL 16.4 | **4.408 passed, 24 skipped, 0 failed**, 4.432 casos JUnit, 532,23 s, Python 3.13.15. | `%TEMP%\ronin-postgres-full-continuation-20261030`. Los skips de Windows, Docker opt-in y servicios externos constan en el log y no se cuentan como pass. PostgreSQL aislado eliminado. |
| Rendimiento Python | **3/3 passed** en 0,52 s. | `python -m pytest -q tests/perf`. No mide el coste frío ML live. |
| Playwright estático | **101 passed, 31 skipped**, 132 casos, 3,9 min. | Los skips son precisamente journeys que requieren API/servicios live; los 404 visibles en este carril proceden del servidor estático, no de Ronin. |
| Docker runtime, worker y acceptance | **23/23 passed**; acceptance estricta **15/15**, cero skips, xfails, fallos o errores. | `%TEMP%\ronin-docker-full-continuation-20261030`, imagen `ronin:qualification-plan-today-continuation-20261030`. PostgreSQL temporal y recursos de qualification limpiados. |
| Ronin live, API real, PostgreSQL/Redpanda y Chromium | **31/31 passed**, 25/25 rutas, **146 llamadas API reales**, 0 errores de red/5xx y 0 brechas de autorización inesperadas. Respuestas: 129×200, 7×201, 1×202 y 9 WARN esperados (1×400, 5×401, 1×403, 2×409). | `%TEMP%\ronin-live-full-continuation-20261030`; worker Docker real. El log estructurado del servidor registró 1.430 INFO/OK, 9 WARNING/WARN y 0 ERROR; las otras cuatro líneas son eventos ML de duración sin filas, parámetros ni IDs. Contenedores, red y volumen se eliminaron. |
| Gates estáticos y de contratos | Ruff, formato (**909 archivos**), mypy (**436 archivos**), arquitectura, negativas, 187 rutas, Studio surface, audit web (**60 archivos/172 invocaciones/0 fallos**), budget, dependencias, capability status, OpenAPI y skills pasaron. | El budget revisado mide **1.943.645 bytes**, 59 assets, 34 módulos, 6 hojas de estilo y 4.871 bytes HTML. Los tres skills validan sin errores. |

La búsqueda live ML completó y guardó el resultado, pero duró **38,33 s**: primer trial **38,23 s**, segundo **59 ms**, preparación **27 ms**. El runner precompila dependencias ahora; la medición actual demuestra que la cold start sigue siendo un defecto de rendimiento y no permite cerrar P8. La ejecución aislada anterior también pasó; las distintas duraciones de 37–82 s se conservan, no se suavizan ni se atribuyen a una causa no medida.

El gate de licencias continúa fallando hasta recibir decisiones de revisión: faltan **21** entradas (`boolean-py`, `cachecontrol`, `certifi`, `charset-normalizer`, `cyclonedx-python-lib`, `defusedxml`, `filelock`, `idna`, `license-expression`, `msgpack`, `packageurl-python`, `pip-api`, `pip-audit`, `pip-requirements-parser`, `pip`, `py-serializable`, `pyparsing`, `pyyaml-ft`, `requests`, `tomli-w`, `urllib3`) y sobra la entrada obsoleta `pyyaml==6.0.3`. No se asignaron aprobaciones automáticas. La versión publicada y los claims también requieren aprobación del mantenedor; la inspección visual de automation no sustituye la revisión manual.

**Resultado release:** **NO-GO, 0/13 familias qualified (0%)**. La suite completa da confianza diagnóstica al árbol sucio, no sustituye las 13 journeys ligados a un mismo SHA limpio, la matriz de SO/Python, la aprobación humana ni las 10 iteraciones limpias exigidas. No se habilitaron CI, GenAI ni multiusuario Public.

## 27. Reproducibilidad del paquete — 31/10/2026

Se generaron dos veces wheel y sdist desde el mismo árbol sucio, fijando
`SOURCE_DATE_EPOCH=1793134348`. Ambas compilaciones terminaron correctamente y
produjeron bytes idénticos:

| Artefacto diagnóstico | SHA-256 |
|---|---|
| `ronin_studio-0.0.0-py3-none-any.whl` | `0230ed664aa32e89902d2a581993be840b96e9eeb775f94664b7cda6bb10ef4e` |
| `ronin_studio-0.0.0.tar.gz` | `8dec5b0785c53429f95f4acb8b942e32d329a44d932fa883bb88f4d5653b2b04` |

Los dos pares se conservaron en `%TEMP%\ronin-artifacts-repro-20261031`.
Esto demuestra reproducibilidad del empaquetado para ese árbol y entorno; no
califica su contenido para publicar. El nombre conserva la versión diagnóstica
`0.0.0`, la fuente contiene cambios sin commit y no se generó identidad de
candidato ligada a un SHA limpio.

Se intentó repetir el perfil P8 dentro de la imagen Docker usada por el worker,
pero esta imagen no instala el extra opcional de `scikit-learn`; no representa
el proceso API que ejecutó la búsqueda. El runner live crea su propio venv a
partir de `requirements-test.lock` y lo elimina al limpiar la qualification.
Por tanto, la medición de 38,33 s sigue siendo válida a nivel de trial, pero no
se aisló la causa interna ni se justifica un cambio de código a partir de ese
benchmark. P8 queda abierto.

La revisión de licencias confirmó que `requirements-dev.lock` selecciona
`pyyaml==6.0.3` fuera de Python 3.13 y `pyyaml-ft==8.0.0` en Python 3.13. El
inventario actual refleja solo el entorno 3.13; por eso el calificador marca la
decisión de PyYAML como stale para ese inventario, aunque la dependencia siga
presente en la matriz del lock. No se quitó la aprobación existente. El
calificador también requiere **21 decisiones humanas** para distribuciones del
inventario actual. Hace falta calificar inventarios por cada entorno soportado
o representar explícitamente el conjunto de variantes antes de cerrar este
gate. `tests/test_license_qualification.py` y
`tests/test_license_qualification_coverage.py` pasan **103/103**.

**Estado actual:** los carriles que aprobaron en §26 conservan sus resultados,
con los skips y límites allí documentados. P8 (búsqueda ML fría), la
qualification de licencias/NOTICE con sus 21 decisiones pendientes, versión y claims,
revisión visual manual, qualification de las 13 familias en un candidato limpio
y la matriz completa de plataformas siguen abiertos. Release **NO-GO, 0/13
(0%)**; las diez iteraciones limpias no se han completado.

## 28. Optimización y transparencia del ciclo de pruebas — 3/11/2026

Se separó el carril de navegador estático de los journeys que requieren servicios
reales, y se añadieron cachés locales bloqueadas para dependencias Python/browser.
Las cachés solo reutilizan dependencias cuando coinciden el intérprete/versión,
los locks y la huella de manifiestos; cada ejecución conserva su base de datos,
credenciales y datos de prueba aislados. El instalador de navegador comprueba
Chromium por existencia y evita reinstalarlo en cada pasada. Los journeys live
quedan nombrados explícitamente como live API o UI-only para que un pase mock no
se presente como prueba de backend.

| Carril diagnóstico del worktree sucio | Resultado | Qué demuestra y qué no |
|---|---|---|
| Playwright estático, sin journeys live | **101 passed, 0 skipped**, 1,8 min, 4 workers. | Evidencia de navegación/UI estática; no valida API, PostgreSQL ni Kafka. Evidencia: `%TEMP%\ronin-test-optimization-static-filtered-20261103`. |
| Qualification funcional live | **31/31 passed, 0 skipped**, 151,27 s; 25 rutas (23 con contrato API real, 2 UI-only); PostgreSQL, Kafka, Ronin API y worker image presentes. | 144 eventos HTTP: 135 OK, 9 WARN esperados, ningún 5xx/error de red/brecha auth; logs: 1.428 INFO, 9 WARNING, 0 ERROR. Cache Python/browser HIT. Evidencia: `%TEMP%\ronin-test-optimization-release-check-20261103\qualification-summary.json`, JUnit y tráfico API adyacentes. Sigue siendo diagnóstico porque el worktree no está limpio. |
| Repetición live focalizada (diagnóstico) | Workspace: 1 journey; 3 llamadas API OK; 48 INFO y 0 ERROR; 41,78 s contando compose. | Confirma que el filtro conserva llamadas reales y el control de servicios, pero no sustituye el recorrido completo. Evidencia: `%TEMP%\ronin-test-optimization-final-live-diag-20261103\qualification-summary.json`. |
| Contratos de qualification | **14 passed, 0,41 s**; parser PowerShell y `node --check` pasaron; helper reporta caché HIT. | Comprueba los nuevos contratos del arnés, no el producto completo. |

La suite Playwright estática anterior mostraba 31 skips de journeys live. El
carril se separó y dejó de presentarlos como pruebas omitidas dentro de la pasada
estática; esos 31 recorridos se ejecutan en el carril live separado. La mejora
principal de tiempo viene de evitar reinstalar dependencias: la qualification
live bajó de 327,37 s en cache miss a 151,27 s en cache hit (**53,8% menos**).
La ejecución live sigue serial y el setup/servicios explican la mayor parte del
tiempo; no se afirma que 31 journeys cubran las 13 familias de producto.

Se perfiló la carga fría de scikit-learn con `PYTHONPYCACHEPREFIX` temporal: el
import público `sklearn.linear_model` cargó el paquete completo y acumuló
aproximadamente 11,6 s de tiempo de importación en ese perfil. Una búsqueda live
anterior registró 65,9 s en el primer request y 6,0 s al repetirlo con el proceso
caliente. No se cambió el runtime ML porque los imports de submódulo siguen
ejecutando el `__init__` del paquete; se necesita optimización arquitectónica y
un benchmark frío reproducible antes de tocar la semántica de entrenamiento.
P8 sigue abierto.

**Decisión al 3/11, 08:25 Europe/Madrid:** **NO-GO para publicar a las 09:00.**
La prueba live está mejor aislada y auditada, pero el candidato no es limpio ni
está congelado; siguen sin completarse los journeys de aceptación de las 13
familias, la revisión visual manual, matriz de plataformas, decisiones de
versión/claims/licencias/NOTICE y el paquete de evidencia de artefactos del mismo
SHA. La fecha objetivo no sustituye esos gates. Recomendar retrasar el anuncio
Public v1 y mantener este trabajo como qualification diagnóstica hasta resolver
los bloqueos; no afirmar GO ni representar el progreso de implementación como
0/13 (ese porcentaje solo mide familias release-qualified).

## 29. Journey live de ingestión gobernada — 3/11/2026

Se amplió el caso live de Ingestion Studio para dejar de depender de que otra
prueba haya creado `examples/demo`. El arnés asegura el proyecto, instala un
fixture de catálogo con vínculo de origen a `pg-live-e2e` (sin credenciales) y
una tabla destino, y usa la tabla `public.ui_page_accounts` de PostgreSQL
efímero. El navegador recorre descubrimiento paginado, preview, plan,
checkpoint-health, envío de sync snapshot, polling hasta `succeeded`, lectura
del recibo `scheduler-result` con digest SHA-256, lineage observado y checkpoint
persistido.

**Resultado focalizado:** 1/1 Playwright; 11 llamadas API reales, sin fallos de
autorización ni 5xx/red; el sync produjo un digest de resultado y destino/lineage
gobernados. Evidencia: `%TEMP%\ronin-ingestion-governed-sync-verified-20261103`.

**Regresión live completa:** 31/31 casos, 0 skip/fallo, 195,91 s totales
(141,52 s Playwright); 25 rutas, 23 con contrato API y 2 UI-only. PostgreSQL,
Kafka, Ronin API y worker Docker real estuvieron activos. Se auditaron 148
eventos HTTP (139 OK, 9 WARN esperados), sin error de red/5xx ni brechas de
autorización; logs 1.434 INFO, 9 WARNING y 0 ERROR. Cachés Python y browser HIT.
El runner eliminó servicios, volumen y red al terminar. Evidencia:
`%TEMP%\ronin-live-full-after-ingestion-20261103\qualification-summary.json`,
JUnit, API traffic y logs adjuntos.

La prueba quedó autosuficiente y se verificó en la suite serial completa. Esto
mejora la evidencia de ingestión PostgreSQL gobernada, pero no cierra P2: faltan
la matriz de conectores/formato, incremental con modificación y replay, fallos y
reintentos de sincronización, qualification de proveedores y evidencia en SHA
candidato limpio. Sigue sin cualificar ninguna familia Public v1.

## 30. Bootstrap, watermark incremental y replay live — 3/11/2026

Se amplió el fixture PostgreSQL con `updated_at` y se añadieron una conexión con
watermark `updated_at + id`, y activos de catálogo gobernados separados. El
journey crea el checkpoint con snapshot, confirma por preview que una fila nueva
es visible, sincroniza en modo incremental y repite sin más cambios. Lee el
checkpoint por la respuesta real de la API para no aceptar un estado anterior
que todavía aparezca en la UI.

**Journey incremental focalizado:** 1/1 Playwright, 13 llamadas API reales, 0
WARN/error, 61 INFO y 0 ERROR; el `checkpoint_digest` cambia después de la nueva
fila y permanece igual después del replay. Evidencia:
`%TEMP%\ronin-ingestion-watermark-verified-20261103\qualification-summary.json`
y archivos adyacentes.

**Suite live completa tras ambos journeys de ingestión:** 32/32 casos, 0
skip/fallo, 211,74 s totales (147,18 s Playwright), 25 rutas (23 con contratos
API y 2 UI-only), 162 eventos HTTP (153 OK, 9 WARN esperados), cero 5xx/error
de red/brechas de autorización, 1.493 INFO, 9 WARNING y 0 ERROR. Ronin API,
PostgreSQL, Kafka y el worker Docker real estuvieron activos; cachés Python y
browser HIT y el runner limpió los servicios, red y volumen. Evidencia:
`%TEMP%\ronin-live-full-ingestion-watermark-final-20261103\qualification-summary.json`,
JUnit, tráfico y logs.

Estos recorridos califican una ruta concreta de ingestión local PostgreSQL,
incluido avance/replay del watermark. P2 continúa parcial: faltan proveedores,
formatos, incremental tras modificaciones concurrentes, fallos/reintentos y
recovery más amplios. Toda esta evidencia sigue siendo diagnóstico del worktree
sucio, no del candidato release; 0/13 familias permanecen release-qualified.

## 31. Optimización y comprobación funcional del carril live — 3/11/2026

La auditoría de los resultados mostró que un smoke de ruta podía considerar
suficiente que la UI enviara una petición, aunque el SQL recibiera un 404.
El caso SQL ahora prepara su propio proyecto usando primero `GET projects`
(contrato `{items: [...]}`) y, si falta, lo crea con `Idempotency-Key`; no
depende del orden paralelo de Playwright ni de otra ruta. Tras ejecutar
`SELECT 1 AS value`, exige HTTP 200, columna `value`, resultado `[[1]]`,
`row_count = 1` y el mismo resultado renderizado en el panel. La primera
ejecución detectó 404 por precondición ausente; dos iteraciones más detectaron
el contrato contenedor y la clave de idempotencia. La repetición corregida pasó
contra Ronin real.

| Ejecución focalizada SQL | 1/1 Playwright, 4,55 s dentro del caso, 1 HTTP real `OK`, resultado exacto validado; 48 INFO, 0 WARN y 0 ERROR. PostgreSQL, Kafka y Ronin API activos; ambos caches HIT; servicios, red y volumen eliminados. | `%TEMP%\\ronin-live-sql-result-fast-rerun-20261103\\qualification-summary.json` y JUnit/tráfico/logs. Diagnóstico del worktree sucio, no qualification de release. |

El modo `-TestGrep` ya no construye ni instala el plugin Performance en el
entorno aislado: ese plugin solo es necesario en la suite completa, que requiere
ejecución notebook con worker Docker real. No se omite en calificación completa.
Antes, el build del plugin consumía aproximadamente 3–5 s del ciclo focalizado.
La medición del nuevo recorrido pasó en 39,06 s totales: 11,18 s servicios,
5,60 s preparación Python/browser, 10,93 s seed/servidor, 9,31 s navegador y
1,81 s limpieza. El caso Playwright fue 4,55 s. La repetición previa, antes de
la optimización del plugin, fue más lenta; los tiempos varían por arranque de
contenedores. La suite completa conserva sus 32 casos y worker. Evidencia:
`%TEMP%\\ronin-live-sql-result-verified-pass-20261103` (primer pase funcional)
y `%TEMP%\\ronin-live-sql-result-fast-rerun-20261103` (repetición optimizada).

Uso recomendado del carril: primero `-TestGrep` para depurar el journey
afectado sobre servicios reales; después ejecutar la suite live completa antes
de cerrar una tanda de cambios. La suite estática sirve para render, estados y
accesibilidad con mocks, pero no demuestra comportamiento API. La suite live
audita los contratos de las 25 rutas y tráfico/logs; aun así no reemplaza los
journeys de aceptación de las 13 familias, la revisión visual manual, la matriz
de plataformas ni evidencia contra un candidato limpio.

**Revalidación completa posterior al cambio SQL:** 32/32, cero skips/fallos,
200,88 s totales y 166,76 s Playwright. Se auditaron las 25 rutas (23 con API,
2 UI-only), 165 eventos HTTP (156 OK, 9 WARN esperados), cero 5xx/error de red
y ninguna brecha inesperada de autorización; logs 1.497 INFO, 9 WARNING y
0 ERROR. PostgreSQL, Kafka, Ronin API y worker Docker estuvieron activos; las
cachés Python/browser dieron HIT y el stack temporal se eliminó. Evidencia:
`%TEMP%\\ronin-live-full-after-sql-assertion-20261103\\qualification-summary.json`,
JUnit, tráfico API y logs. Es una qualification diagnóstica del worktree sucio
en el baseline `f9a0456`; no crea SHA limpio ni cierra ninguna familia Public v1.

## 32. Qualification real S3-compatible en el carril Docker — 3/11/2026

El plan requería probar S3-compatible y había dos pruebas reales condicionadas
por `RONIN_TEST_S3_ENDPOINT`, pero el runner Docker solo preparaba PostgreSQL.
Se extendió `run_docker_qualification.ps1` para levantar Floci con imagen fijada
por digest, puerto aleatorio publicado únicamente en loopback y proyecto/volumen
Compose aislados; el runner inyecta credenciales sintéticas, espera al servicio,
ejecuta las integraciones y elimina Floci/volumen/red además del PostgreSQL
existente. El puerto de `compose.floci.yaml` ahora admite override; su valor
predeterminado conserva `127.0.0.1:4566`.

Las pruebas incorporadas ejercitan el write/read/retry y digest del conector
JSON S3, así como entrada durable, salida de modelo y retención de artefactos ML
contra Floci real. El runner Docker completo pasó **25/25 pruebas en 182,13 s**;
la acceptance estricta registró **15/15**, cero skips, fallos, errores o casos
inesperados. Incluyó worker Docker y PostgreSQL real. Imagen Ronin de este
diagnóstico: `sha256:aab59aad3a0ebc6aa5adf5fc1bdb8116f10daeafb793c58c83ad6be27f8c4ce3`.
Evidencia: `%TEMP%\\ronin-docker-s3-expanded-20261103` (JUnit, stdout,
acceptance JSON y logs Floci/PostgreSQL); la qualification focalizada previa de
las dos integraciones pasó **2/2 en 7,37 s** en
`%TEMP%\\ronin-s3-connector-real-20261103`. Tras el `finally`, no quedaron
contenedores ni volúmenes `ronin-docker-s3-*`.

El contrato del runner/Compose pasó **26/26** tests de pytest, Ruff y parser de
PowerShell; `docker compose config` confirmó loopback y el puerto override. La
configuración sintética no se reutiliza fuera del proceso y se restauran las
variables previas.

Esto cierra la omisión de qualification S3-compatible con Floci para esas dos
rutas, pero no la matriz P2: faltan qualification real Azure Blob, generic JDBC
contra driver/proveedor declarado, HTTP/REST contra fixture local gobernado y
la familia completa de formatos/errores/reintentos. Tampoco prueba AWS real ni
certifica compatibilidad general S3. Es diagnóstico del worktree sucio, no del
candidato limpio; Public v1 permanece **NO-GO, 0/13 familias qualified**.

## 33. Integración real Azure Blob y feedback del carril Docker — 3/11/2026

Se añadió el extra opcional `azure` con `azure-storage-blob` al lock de tests y
un servicio Azurite fijado por digest, con puerto loopback aleatorio, volumen y
proyecto Compose aislados. El runner entrega una clave pública del emulador
solo al proceso de tests; no usa credenciales de Azure real. El conector acepta
HTTP únicamente con `allow_local_http=true` y host loopback; permite configurar
`api_version` validada para emuladores. Se fijó `2025-11-05`, compatible con la
versión fijada de Azurite y el SDK actual. El test escribe un JSONL, descubre
por prefijo, lee dos filas, confirma columnas y digest de snapshot, comprueba
replay sin filas y verifica que el secreto no se persiste en la conexión.

La primera integración real detectó que la paginación llamaba a
`ItemPaged.by_page(results_per_page=...)`, argumento que la API real no admite.
Se corrigió pasando `results_per_page` a `ContainerClient.list_blobs` y dejando
el cursor opaco en `by_page`. La integración volvió a pasar contra Azurite:
**1/1**. Los tests unitarios y contratos Azure/Docker/matriz pasaron **29/29**;
Ruff, formato, parser PowerShell y `docker compose config` quedaron limpios.

La nueva qualification Docker ampliada construyó la imagen Ronin
`sha256:e84e54cd335c061c04e36ad7c9abd8b4814d9dbcb67d887649c6c4a36c87783c` y
pasó **26/26 pruebas en 178,00 s**, sin skips ni fallos, junto con acceptance
estricta **15/15**. Ejecutó worker/runtime y journeys v0.1, PostgreSQL real,
S3 JSON y artefactos ML contra Floci, y Blob JSONL contra Azurite. Evidencia:
`%TEMP%\ronin-docker-expanded-floci-azurite-20261103` (JUnit, stdout, JSON de
acceptance, resumen del runner y logs de PostgreSQL/Floci/Azurite). Los
servicios, volúmenes y redes efímeros se limpiaron. Esta es evidencia diagnóstica
del worktree sucio.

Para que la duración no oculte si se ejecutan casos reales, el runner declara
antes el alcance integrado y pytest usa `-v --durations=15`: cada caso aparece
con resultado y se identifican los 15 más lentos. Durante desarrollo se
recomienda ejecutar primero las pruebas unitarias/contrato focalizadas (<5 s),
luego la integración del proveedor tocado (unos segundos), y solo una vez por
lote el carril Docker completo (aprox. 3 min en esta máquina). El carril rápido
reduce iteraciones sin presentar un mock como validación funcional. El resumen
de release sigue **NO-GO, 0/13**: JDBC genérico, HTTP/REST y el resto de la
matriz de proveedores, journeys de familias, revisión manual y candidato limpio
siguen pendientes.

**Endurecimiento posterior de Azure:** una revisión del límite de 10 MiB halló
que el conector comprobaba el tamaño tras `readall()`, por lo que no era un
límite efectivo de memoria. Ahora consulta propiedades antes de descargar,
rechaza tamaño/ETag inválidos y objetos sobredimensionados, realiza streaming
por chunks con condición `IfNotModified` del ETag observado, aborta si los bytes
superan el máximo o el tamaño declarado, y rechaza una lectura truncada. Los
unit tests verifican preflight sin descarga, crecimiento durante streaming y
condición ETag; pasan **13/13**. La integración con Azure SDK real contra
Azurite pasó **1/1 en 4,44 s**; evidencia en
`%TEMP%\ronin-azure-blob-azurite-bounded-20261103`.

El XML de duración sitúa los tres recorridos dominantes en **39,415 s** (worker
SIGKILL y reuso), **40,252 s** (igual flujo persistido en PostgreSQL) y
**40,441 s** (journey Compose de aceptación, restart/reclaim y reanudación).
Los tres esperan la lease de 30 s, como exige la semántica de producción; no se
recortará ni se sustituirá por alterar el reloj o marcar el run recuperado a
mano. Así la salida detallada permite ver que la espera pertenece a cobertura
de recuperación, no a un proceso de test sin actividad.

**Reejecución posterior al endurecimiento Azure:** Docker pasó **26/26 en
157,19 s** (155,957 s en JUnit), cero skips/fallos/errores; acceptance estricta
**15/15**. Imagen local `sha256:08e30345d7568edf7d18314775a1ac95b949e7587463e8944d0c47d118bc7bf8`.
`-v --durations=15` transmitió los casos durante la ejecución y mostró los tres
caminos de recuperación en ~37 s cada uno; la mayoría de casos restantes
terminaron en menos de dos segundos. Evidencia:
`%TEMP%\ronin-docker-azure-bounded-final-20261103`. No quedaron contenedores
`ronin-docker-*`, volúmenes ni redes temporales de Floci/Azurite.

## 34. Inventario legal reconciliado con Python 3.12 — 3/11/2026

El gate legal anterior quedaba oculto detrás de un fallo de grafo: el inventario
committed correspondía a la variante Python 3.13 (`pyyaml-ft==8.0.0`), mientras
la ejecución actual y el lock para Python 3.12 seleccionan `pyyaml==6.0.3`.
Regeneré `third_party/licenses-v1.json` con el entorno bloqueado Python 3.12.
El inventario ahora coincide exactamente con **56/56** distribuciones y con el
SHA actual de `requirements-dev.lock` (`b1bbbd33e482242638fafa124e1385f2b76eff7cbe17ee57d349f0d9b3e50c18`).

Al repetir `tools/license_qualification.py`, desapareció el error de grafo y el
gate avanzó hasta la policy. Resultado actual: **20 decisiones exactas faltan**
(boolean-py, cachecontrol, certifi, charset-normalizer,
cyclonedx-python-lib, defusedxml, filelock, idna, license-expression, msgpack,
packageurl-python, pip-api, pip-audit, pip-requirements-parser, pip,
py-serializable, pyparsing, requests, tomli-w y urllib3). Ya no informa una
entrada obsoleta PyYAML: `pyyaml==6.0.3` está en la policy actual de este
entorno. Las filas faltantes requieren inspección upstream de la evidencia y
aprobación humana; no agregué decisiones ni una conclusión nueva de NOTICE.

Las pruebas del generador/validador legal, cobertura adversarial y archivos
declarados pasaron **105/105**. Esto prueba que el gate falla de forma
reproducible y fail-closed ante decisiones ausentes; no sustituye la lectura ni
aprobación legal de esas veinte entradas.

Validación: generador de inventario terminó correctamente; segunda ejecución
del gate llegó a `policy review keys must exactly match the locked graph` y
enumeró solo las veinte decisiones anteriores. No es un PASS legal. El
inventario puede variar con marcadores de plataforma/versión, así que el futuro
candidato debe repetirlo para cada entorno soportado y revisar la evidencia
correspondiente antes de congelar los recibos. Public v1 sigue **NO-GO**.

También se instaló el mismo lock de forma limpia en Windows/Python 3.13.15 con
`pip install --require-hashes`; se generó
`third_party/licenses-v1-py313.json` (56 distribuciones, mismo lock SHA) y una
policy de perfil filtrada `third_party/license-policy-v1-py313.json` que solo
conserva decisiones previas aplicables, sin crear aprobaciones. La ejecución
`python tools/license_qualification.py --inventory third_party/licenses-v1-py313.json --policy third_party/license-policy-v1-py313.json`
valida ese inventario y falla por **21 revisiones humanas ausentes**, incluida
`pyyaml-ft==8.0.0`; no reporta PyYAML 6.0.3 como stale en ese perfil. Python
3.12 requiere las 20 decisiones comunes y no PyYAML-FT. Así quedan separadas
las dos variantes Windows, pero falta producir/evaluar inventarios para los
otros entornos de la matriz (incluido Linux/Python 3.11) antes de cerrar #58.

Los tests de qualification legal pasaron **105/105** tanto en Windows/Python
3.12 como en el venv limpio Windows/Python 3.13.15; Ruff también pasó en 3.13.

El perfil Linux/Python 3.11.18 se instaló con `--require-hashes` en la imagen
Debian fijada `python@sha256:673719e071ecf27434fd2635bbd8d00f49f4fdd81f243143438a42ced8bedf60`.
Se guardó `third_party/licenses-v1-py311-linux.json` y su policy filtrada
`third_party/license-policy-v1-py311-linux.json` (55 distribuciones). El gate
en Linux valida el inventario y expone las mismas 20 decisiones pendientes que
Python 3.12, sin stale entries; sus tests legales pasaron **105/105**. Pytest
emitió un warning solo porque el repo estaba montado read-only y no pudo crear
`.pytest_cache`; no hubo fallos de tests. Evidencia completa:
`%TEMP%\ronin-license-linux-py311-verify-20261103`.

Quedan así inventarios reproducibles para los perfiles mínimos probados:
Windows/Python 3.12 y 3.13, Linux/Python 3.11. El gate legal **no pasa** en
ninguno: faltan las decisiones del mantenedor (20 comunes y, para 3.13, la
revisión adicional de PyYAML-FT). La revisión debe completar las policies sin
modificar `evidence_sha256` ni decidir NOTICE por inferencia.

## 35. Aceleración y legibilidad de la qualification — 3/11/2026

Se revisaron las duraciones antes de tocar los criterios: el live completo
anotado tardó **200,88 s** (171,28 s en journeys); Docker tardó **157,19 s**
(155,96 s en pytest). La mayor parte de Docker está en tres pruebas distintas
que esperan la lease real de 30 s para verificar recuperación en SQLite,
PostgreSQL y Compose. Se conservan esas esperas porque forman parte del
contrato de producción. Playwright live sigue serial para no cruzar fixtures
mutables. La guía de desarrollo ahora separa feedback enfocado de las
qualifications completas y prohíbe contar un servidor estático como evidencia
de API/DB/worker.

`run_live_product_qualification.ps1` ahora finaliza con casos aprobados,
omitidos y fallidos, cobertura de rutas, preparación real del API, tráfico por
resultado, errores de logs y tiempo total; indica explícitamente cuándo un
filtro evita la auditoría de todas las rutas. El test enfocado `route sql loads
and reaches the live API` pasó **1/1 en 44,41 s** contra Ronin real, con
PostgreSQL/Kafka activos, **1 API OK**, cero errores de log y cachés calientes.
Un primer comando usó un título de test inexistente y pytest recogió cero
casos; se corrigió el selector, y el runner ahora imprime también la fase y
causa de cualquier fallo del harness.

El modo opcional `-TestFilter` de `run_docker_qualification.ps1` permite probar
un nombre pytest en un entorno Docker con dependencias lockeadas y fixtures
reales; no ejecuta ni representa el gate estricto 15/15. La primera prueba
filtrada descubrió que el runner tomaba Python global sin `azure-storage-blob`
instalado y fallaba antes de Azure. Se corrigió para reusar o crear una venv
cacheada por fingerprints de `requirements-test.lock` y `pyproject.toml`, sin
alterar Python global. Al repetir, `azure_blob_discovers` pasó **1/1** contra
Azurite, cero skips/fallos; el caso tardó **14,29 s** y pytest **33,48 s**
(incluye instalación inicial del entorno de pruebas/colección). Tras calentar
las cachés, el mismo diagnóstico pasó **1/1 en 2,11 s**, con 0,74 s en el caso.
El recibo lista el node ID y avisa que la aceptación estricta no se ejecutó.
Evidencia:
`%TEMP%\ronin-docker-azure-filtered-fixed-7f6f86f1425a4a009cb3b934da36b545`.

La optimización reduce vueltas durante desarrollo al ejecutar primero el
conjunto mínimo que cubre el cambio; mantiene el recorrido completo de release
como comprobación final. La suite legal focalizada pasó **112/112** y Ruff
pasó en los archivos legales modificados. La qualification completa aún debe
repetirse sobre el candidato limpio; los resultados citados son diagnósticos
de worktree sucio y no suben el release de **NO-GO, 0/13**.

**Corrección del estado legal:** se volvieron a ejecutar los gates de perfiles
Windows/Python 3.12 y 3.13 con las policies filtradas actuales. El primero
informa **29 claves de revisión ausentes**, el segundo **30** (incluye
`pyyaml-ft==8.0.0`). La reproyección de las decisiones existentes retuvo 27/56
y 26/56 revisiones respectivamente, y omitió 9 digests de evidencia obsoletos
en cada perfil. El gate Linux/Python 3.11 había informado 21 claves ausentes
(20 sin revisión + `packaging==26.3` con evidencia obsoleta). Por tanto, las
cifras antiguas de “20/21 revisiones humanas faltantes” no describían todo el
trabajo legal: además hay que volver a revisar las entradas cuyo digest cambió.
No se añadió ni aprobó ninguna decisión.

**Optimización adicional de Python/PostgreSQL:** la ejecución completa anterior terminó con **4.429/4.454 aprobados, 25 skips, 0 fallos en 447,78 s**; esa sigue siendo la referencia completa más reciente. El runner ahora admite `-TestPath` para ejecutar una sola prueba/archivo contra PostgreSQL real sin descubrir los más de 4.000 tests, `-TestFilter` como filtro pytest opcional, omite instrumentación de coverage en diagnósticos, e imprime los casos seleccionados, skips de colección y los 15 casos más lentos. El mismo test PostgreSQL pasó **1/1 en 1,92 s de pytest** por `-TestPath`; con `-k` solo había tardado **21,91 s**, incluidos 4.451 tests deselegidos durante la colección. Es una reducción de aproximadamente **89% en el tiempo de pytest** para esa iteración, no de la qualification completa ni del arranque del contenedor.

También se eliminó el escaneo duplicado de inventario: la prueba que comprobaba JSON vuelve a usar el inventario que ya se construye dos veces para comprobar determinismo. Los tests del runner y del inventario pasaron **19/19 en 14,57 s** (el test de determinismo, que escanea dos veces el repo, ocupó 8,91 s). El parser PowerShell pasó y `git diff --check` no encontró errores. Estos resultados son diagnósticos en worktree sucio; no se repitió la suite completa después de estos cambios y no sustituyen la siguiente qualification completa de PostgreSQL ni los gates de coverage.

Se recuperó correctamente el `.coverage` de esa ejecución completa (la opción CLI `--data-file` no existe en Coverage.py; se cambió a `COVERAGE_FILE`). Pasaron todos los umbrales agregados: T1 **89/80%**, T2 **81/70%**, T3 plataforma **78/75%**, SDK **66/65%**, control plane **48/35%**, T4 **74/60%**, broker **46/45%**, tools **72/60%** y release gates **95/90%**. El gate de storage completo con PostgreSQL pasó **62/62 archivos**, incluidas las adaptaciones PostgreSQL y el ratchet configurado. Los tests `tests/perf` pasaron **3/3 en 0,58 s** (sus casos tardaron 0,02–0,04 s cada uno). Esta evidencia de coverage procede de la suite completa de 447,78 s; el pase de rendimiento se ejecutó después y por separado. Todo sigue atado a worktree sucio, no a candidato de release.

## 36. Fixture HTTP/REST real para la qualification local — 3/11/2026

La revisión de P2 confirmó que `HttpJsonConnector` tenía tests unitarios con transporte simulado, pero no una prueba de socket contra un servidor de integración gobernado. Se añadió `tests/integration/test_http_json_connector_real.py`: servidor HTTP temporal en `127.0.0.1`, sin llamadas externas ni credenciales, con cinco escenarios del conector real: lectura paginada + replay snapshot, retry tras HTTP 503, rechazo de redirect, límite de bytes y rechazo de `next` cross-origin. El servicio usa puerto efímero, se detiene en `finally` y la espera de apagado quedó reducida para que el fixture no añada medio segundo por caso.

La qualification pasó **5/5 en 2,83 s**; Ruff pasó. Es evidencia directa de contrato HTTP/REST, límites y fallos del conector contra un socket real. No ejercita la ruta completa UI/API de ingestion, credenciales HTTPS ni un proveedor externo, así que P2 y la familia completa permanecen parciales. Este test se integra en la suite normal; la suite completa aún debe repetirse después de añadirlo. Estado: worktree sucio, sin SHA candidato limpio; **NO-GO, 0/13 familias release-qualified**.

## 37. Suite completa actual, cobertura y gates estáticos — 3/11/2026

Se repitió la suite Python/PostgreSQL completa después de añadir el test HTTP
real y la optimización de selección por archivo: **4.433 passed, 25 skipped,
0 failed de 4.458 casos**, PostgreSQL 16.4, en **589,02 s**. El JUnit incluye
los cinco escenarios HTTP de §36. Los 25 skips quedan declarados, no aprobados:
servicios Docker/worker del carril Docker, Trino, Azurite, S3, OTLP, Spark/SDP,
symlinks/atributos POSIX no disponibles en Windows y skips de colección
relacionados. Evidencia: `%TEMP%\ronin-postgres-full-after-http-real-e1b622dad4424bc3937b9f32add46eab`.

Los thresholds recalculados desde el `.coverage` de esta misma ejecución
pasaron: T1 **89%**, T2 **81%**, T3 plataforma **78%**, SDK **66%**, control
plane **48%**, T4 **74%**, broker **46%**, tools **72%**, release gates **95%**;
el gate PostgreSQL por archivo de storage pasó **62/62**. `tests/perf` pasó
**3/3 en 5,32 s**. Mypy pasó en 437 archivos; Ruff check pasó y format informó
**896 archivos ya formateados**. OpenAPI, route consistency (**187 operaciones**),
architecture, negative gates, dependency surfaces, Studio surface/web audit,
canonical JSON (10 vectores, 5 rechazos), runner protocol (2 fixtures),
capability status, skill validation y `git diff --check` pasaron.

Se corrigió el sweep mypy: `project_policy` ahora estrecha tipos con validación
explícita y Azure imports ya no llevan `type: ignore` obsoletos. El budget web
detectó una regresión medible de 20 bytes en el CSS mobile añadido para descontar
la navegación inferior fija y mantener el scroll dentro del panel; tras revisar
que los asset requests siguen en **59** y el comportamiento solicitado requiere
los cálculos `100dvh`, el ratchet se avanzó exactamente de **1.943.645** a
**1.943.665 bytes**. `studio_budget --check` pasa con el valor medido; no se
añadieron módulos ni requests.

Esta repetición y los static gates son diagnósticos del árbol sucio en
`20261029@f9a0456`; no incluyen Docker acceptance, el barrido live de API/browser
ni todos los proveedores opcionales en este mismo pase. Los gates históricos
Docker/live no se transfieren a un candidato nuevo. Faltan el bridge/driver JDBC
operativo, journeys/provider matrix restantes, security/Helm exactos, bundle
cross-domain y las decisiones humanas de versión/claims/licencias/NOTICE. Sigue
**NO-GO, 0/13 familias cualificadas**, y se debe retrasar la publicación hasta
un candidato limpio con gates completos.

## 38. Menor coste del ciclo de feedback — 3/11/2026

El test `test_inventory_is_deterministic_and_contains_plugin_surfaces` hacía
dos escaneos AST completos de `python/` y `tests/` en cada suite. Se conserva
un escaneo real del repositorio para comprobar que las superficies publicadas
siguen presentes; la propiedad de determinismo ahora se comprueba dos veces
sobre un fixture pequeño con rutas, paquete y entry point. Resultado local:
**3/3 tests en 36,08 s**, con el escaneo real en **31,25 s** y el test de
determinismo en **0,23 s**. Antes, el full suite registró dos escaneos del
inventario determinista y llegó a **48,39 s** en ese test. El ahorro evita un
recorrido repetido, no oculta ni sustituye la inspección de todos los módulos.

Validación tras la edición: tests del inventario 3/3, Ruff, Ruff format y
`git diff --check` pasaron. La suite Python/PostgreSQL completa aún no se ha
repetido después de esta edición; ese pase focalizado no sustituye la siguiente
ejecución completa con coverage.

## 39. Corrección de checkpoints incrementales JDBC — 3/11/2026

La revisión de reanudación encontró tres defectos en el contrato V2: tras una
primera lectura vacía se aplicaba `> NULL`, por lo que las filas insertadas
después nunca aparecían; se ignoraba la huella del esquema persistida; y el
checkpoint no podía serializar fechas, horas, `Decimal` ni bytes. Ahora el
checkpoint vacío inicia una lectura completa al reanudarse, la lectura falla
si la huella del esquema cambia, y el formato V2 serializa esos escalares con
tipo explícito. El decoder conserva compatibilidad con el formato V2 anterior
sin marcador de esquema. Se rechazan columnas no identificadoras, duplicadas,
huellas inválidas, generaciones booleanas y watermark/tie-breaker nulos.

La validación focalizada final de JDBC, discovery y registry pasó **50/50 en
20,38 s**. El decoder mantiene compatibilidad con checkpoints previos; las
pruebas cubren tipos escalares, filas añadidas tras una lectura vacía, cambio
de esquema y rechazo de URLs con credenciales. Ruff check/format, mypy
focalizado y `git diff --check` pasaron. Estas son pruebas de contrato con
bridge DB-API inyectado: todavía no prueban un driver JDBC real. La imagen de
Ronin es Alpine y no incluye JRE ni driver; el conector predeterminado sigue
fallando de forma cerrada sin bridge. Por tanto esto corrige la semántica del
checkpoint, pero **no cierra generic JDBC/P2** ni cambia el estado **NO-GO**.

## 40. Separación del benchmark HTTP del carril de coverage — 3/11/2026

La suite Python/PostgreSQL con pytest-cov ejecutó `test_real_http_submit_status`
desde `tests/integration`. En la carga global GET p95 fue **33,609 ms** frente
al límite de **30 ms** (POST sí pasó); el suite terminó **4.464/4.465 casos
pasados, 1 fallido**, en el worktree sucio. La repetición aislada pasó tres
veces: GET p95 **9,145**, **9,135** y **8,844 ms**. El test sí carga Ronin API
real, SQLite y el cliente SDK, pero pytest-cov introduce instrumentación que
no forma parte del perfil que mide ese presupuesto.

El benchmark, incluidos sus 200 POST y 200 GET medidos, se movió a
`tests/perf/test_http_contention_budgets.py`. `make check` ya ejecuta primero
la suite completa sin `tests/perf` con coverage y luego `make performance` sin
coverage; por ello conserva el gate de rendimiento y mide el mismo contrato en
el carril correcto. Tras el movimiento, `python -m pytest -q tests/perf
--durations=10` pasó **5/5 en 9,37 s**, y el caso HTTP tardó **3,96 s**. Se
regeneró `docs/architecture/plugin-inventory.json` para reflejar el árbol
actual y la nueva ruta.

La primera ejecución completa sigue siendo un fallo válido y permanece en su
recibo: GET p95 33,609 ms bajo cobertura. Después del movimiento se repitió el
scope completo Python/PostgreSQL: **4.440 passed, 25 skipped, 0 failed de
4.465**, PostgreSQL 16.4, en **884,06 s**. Evidencia:
`%TEMP%\ronin-postgres-after-perf-isolation-69dd7cb13747472f82e2511f9124b47b`.
Los skips siguen siendo ambientales/opt-in (Docker workers, servicios externos
y capacidades POSIX de Windows), y no se suman a los pases. No hubo
`CoverageWarning` ni quedó un `.coverage.*` secundario.

Sobre ese mismo `.coverage` pasaron T1 **89%**, T2 **81%**, plataforma T3
**78%**, SDK **66%**, control plane **48%**, T4 **74%**, broker **46%**,
tools **72%**, release gates **95%** y el gate completo PostgreSQL storage
**62/62 archivos**. `tests/perf` pasó **5/5 en 9,37 s**; mypy **437 archivos**,
Ruff check, formato (**913 archivos**), architecture gate, capability status
y `git diff --check` pasaron. Todo es evidencia del worktree sucio en
`20261029@f9a0456`, no de un candidato limpio. La repetición no resuelve el
bridge/driver JDBC, los journeys/provider matrix restantes, Helm/security,
artefacto cross-domain ni revisiones humanas. El release permanece **NO-GO,
0/13 familias**.

## 41. Optimización del ciclo de pruebas y recibo Docker — 3/11/2026

La corrida Docker posterior construyó la imagen Ronin
`sha256:5a700637d836fc0e5ba38c02a099d2f8170c3cbdd905135058706438c1a3d750` y
pasó **26/26 integraciones en 175,99 s de pytest**, sin skips ni fallos; el gate
estricto v0.1 pasó **15/15**. Incluyó PostgreSQL 16.4, workers Docker reales,
Floci/S3 y Azurite/Azure. Evidencia:
`%TEMP%\ronin-docker-after-jdbc-checkpoint-7674c094952a4c2687ee2b7b2c3d4647`.
La suite completa Python/PostgreSQL más reciente fue **4.440 passed, 25
skipped, 0 failed de 4.465 en 884,06 s** (evidencia en
`%TEMP%\ronin-postgres-after-perf-isolation-69dd7cb13747472f82e2511f9124b47b`).
Los skips son ambientales/opt-in y no cuentan como pruebas aprobadas.

Los datos de duración identifican los costes más grandes: la suite Python tuvo
un test de build/discovery de plugin de **46,44 s**. La subprocess de
discovery escaneaba todos los `site-packages` globales pese a que validaba un
wheel clean-room. Se añadió `python -S` para excluirlos: el test focalizado
pasó en **13,91 s** (**15,09 s** contando pytest). La comparación es entre una
ejecución completa y una focalizada, no una medición controlada con la misma
carga. En Docker, las dos pruebas
de recuperación tras matar el proceso tardaron **42,50 s** y **37,34 s**, ya que
esperan al vencimiento del lease de producción de 30 s. No se acortan esos
tiempos ni se paraleliza el journey que comparte estado: eso debilitaría o
volvería ruidosa la validación. Para cada cambio, usar el `-TestPath` más
pequeño (evita recopilar los 4.000+ casos), y después solo el diagnóstico del
servicio real afectado. Reservar la suite Python con coverage, Docker/strict
acceptance y live API/browser para un lote coherente y el SHA final limpio.
`make check` ya contiene suite, coverage y performance; no ejecutar también
`make test` para el mismo estado. La suite completa anterior al cambio menor
del subprocess (`python -S`) es diagnóstico de árbol sucio; el cambio de test
pasó focalizado pero todavía necesita la próxima regresión completa. Ninguna
ejecución constituye evidencia de candidato limpio. Estado release:
**NO-GO, 0/13 familias**.

## 42. Gate Helm single-node contra kind real — 3/11/2026

Se descargó Helm v3.22.1 en un directorio temporal; el SHA-256 de Windows
`32ce9f4509b81782c9740898c43946e1f97c4d93ec5d10222c9b6eeec21ea043` coincidió
con el checksum de la release oficial. No se instaló en el sistema. Los dos
primeros intentos encontraron dos defectos reales: `kind` crea el contexto
`kind-<cluster>` (no `kind:<cluster>`) y el chart olvidaba
`RONIN_BIND_POLICY`, por lo que el servidor rechazaba el bind no-loopback y
entraba en `CrashLoopBackOff`. Ambos clústeres temporales se eliminaron; se
conservan sus recibos fallidos como diagnósticos, no como aprobación. `helm
lint` sin los values explícitos también falló como se esperaba, al exigir
token, grants y bind policy; el default no habilita HTTP de forma implícita.

Se añadió `tools/run_helm_qualification.ps1`, con evidencia fuera del repo,
verificación dirty/clean, identificación inmutable de imagen, nombres de
clúster únicos, render del chart con comprobación de Secret, smoke HTTP real y
limpieza exacta del clúster temporal. El chart ahora exige que el operador
configure `server.bindPolicy: insecure-plaintext-network`; no está activo en
valores por defecto. Esta es una aceptación explícita de HTTP solo para un
clúster local de desarrollo confiable, con Service privado y port-forward; el
acceso remoto requiere TLS. `container-internal` sigue reservado al bridge de
Compose. Se documentó la limitación y se corrigió el contexto kind en el
procedimiento de release.

La ejecución repetida pasó `helm lint` (solo la recomendación informativa de
añadir un icono), renderizó cuatro recursos y confirmó que el token no aparece
fuera de Secret. En el clúster `kind` aislado, usando la imagen Ronin
`sha256:5a700637d836fc0e5ba38c02a099d2f8170c3cbdd905135058706438c1a3d750`,
Helm instaló la release; el deployment single-replica quedó Ready; `/healthz`
y `/studio/` respondieron HTTP 200; la consulta autorizada de jobs respondió
HTTP 200; POST `/v1/jobs` devolvió HTTP 201 y el mismo job `queued` permaneció
tras `kubectl rollout restart`. El runner eliminó el clúster temporal y dejó
recibo, inventario de recursos y logs en
`%TEMP%\ronin-helm-kind-74de55168b294afa80b8866926417df1`. El test estructural
de Helm pasó 1/1, Ruff y formato pasaron y PowerShell parser pasó.

Esto demuestra el recorrido local de instalación/health/UI/API y persistencia
tras reinicio en este árbol sucio. No cualifica el SHA de release, backup/
restore, migraciones, seguridad operacional completa, otras plataformas ni
la familia P14 completa. Release permanece **NO-GO, 0/13 familias**.

La repetición integrada con recibo Docker obligatorio terminó correctamente en
`%TEMP%\ronin-helm-bound-49a2297fd8da49f5ada9fe030f31c821`. El runner ahora
rechaza la instalación si falta el transcript Docker o el recibo estricto
15/15, si no coinciden SHA/modo del checkout o si el ID inmutable de la imagen
no coincide con el de aceptación Docker. El recibo Docker enlazado registra
26/26 pruebas, cero skips/fallos y la aceptación estricta 15/15 (pytest:
175.99s). Esta repetición verificó esos vínculos, `helm lint`, render/Secret,
despliegue real, health/UI/API, creación 201, persistencia tras reinicio y
limpieza; el clúster terminó eliminado. La prueba contractual
`tests/test_helm_chart_structure.py` pasó 2/2 y el parser PowerShell informó
cero errores. Sigue siendo un diagnóstico sobre árbol sucio con HEAD
`f9a0456ab7df3e2bb77247d54b4336fca64903b0`, no evidencia de release.

## 43. Cualificar backup/restore PostgreSQL real y endurecer el checksum

La inspección de P14 detectó que el backup lógico PostgreSQL tenía solo una
prueba con `subprocess` simulado; el restore aceptaba un dump sin sidecar SHA-256.
Se añadió `tests/integration/test_postgres_appliance_backup_real.py`: inicia un
proyecto Compose temporal con PostgreSQL real, crea una tabla y una fila, invoca
el CLI documentado, comprueba dump y sidecar, modifica los datos, restaura con
`--force`, verifica que solo permanece la fila previa al backup y elimina el
proyecto/volumen temporal en `finally`. `tools/ronin_postgres_backup.py` ahora
publica el sidecar por escritura temporal, `fsync` y reemplazo atómico; restore
rechaza checksum ausente, mal formado o incorrecto antes de llamar a Compose.
El runbook explica que se deben conservar juntos dump y sidecar.

La prueba live pasó primero 1/1 y, tras endurecer el checksum, volvió a pasar
integrada en el gate Docker: **27/27**, cero skips/fallos, acceptance estricta
**15/15**; pytest tardó 247.62 s. Recibos en
`%TEMP%\ronin-docker-backup-hardening-4b3ae664111a47ec887ad570ea44e23e`.
Las pruebas focalizadas de backup pasaron 4/4. Esta evidencia mejora el alcance
P14, pero no cualifica la copia/restauración combinada de base de datos más
artefactos, upgrades, plataforma completa ni candidate SHA; el ledger permanece
**0/13 — NO-GO**.

Para no hacer que la suite Python general levante Docker implícitamente, el
recorrido real es opt-in mediante `RONIN_REAL_DOCKER_QUALIFICATION=1`; el runner
Docker fija esa variable antes de pytest. Se verificó el modo normal: 1 caso
skip con razón explícita; y el modo Docker enfocado: **1 passed, 26 deselected**
(16.34 s de test; 23.42 s de pytest), sin acceptance estricta porque el filtro
la omite intencionadamente. El gate Docker completo anterior incluyó el mismo
caso activo con 27/27 y strict 15/15. No quedan proyectos, contenedores ni
volúmenes `ronin-docker-*` o `ronin-backup-*`.

La revisión adicional halló y corrigió un bug para dump names con espacios:
restore ahora compara el SHA fijo de 64 caracteres y el nombre completo del
archivo, no tokens separados por espacios. Se cubre con una prueba unitaria.
Comprobación final: suite de backup **4 passed** y 1 skip opt-in esperado; el
test live de PostgreSQL real pasó **1/1** tras esta corrección. Ruff, formato,
mypy focalizado, validador del ledger y `git diff --check` pasaron. No se volvió
a ejecutar el Docker gate completo tras el cambio de parser; su ejecución
completa anterior pasó 27/27 y el recorrido Docker enfocado ya había pasado
1/1.

## 44. Iteración de pruebas más rápida y con alcance explícito

Para acortar el feedback sin confundir un diagnóstico con cobertura completa,
se documentaron cinco capas: unitarias, contratos del arnés, integración live
focalizada, regresión completa por familia y gates de release. La nueva guía
`docs/testing/TESTING_FAST_TO_FULL.md` incluye comandos, alcance y límites de
cada capa, criterios de evidencia, comprobación manual visual y cómo verificar
que los mensajes OK/WARN/ERROR corresponden a respuestas API y logs reales.

El runner Docker tiene modo `-TestFilter` y `-ImageId` para iteración: el digest
se reutiliza solo en filtros y permite omitir el build de imagen. Se documenta
que esto prueba la imagen recibida, no los cambios locales del Dockerfile o del
runtime. Los proveedores locales se seleccionan por familia (PostgreSQL,
Floci/S3, Azurite/Azure); el gate sin filtro construye desde el checkout y
ejecuta acceptance estricta. Se añadieron contratos que fijan esa separación.
El runner rechaza además un informe JUnit con cero casos seleccionados.
El resumen de salida distingue imagen construida frente a imagen reutilizada e
indica la lista efectiva de fixtures; la etiqueta `PASS` sigue limitada a los
tests del alcance seleccionado.

También se endureció la restauración del bundle local del appliance: el helper
común verifica el sidecar SHA-256 contra el dump y el manifiesto antes de
consultar Compose, detener escritores o reemplazar datos. Se añadió una prueba
unitaria para rechazar un sidecar corrupto antes de tocar servicios. El runbook
de upgrades ahora prescribe backup completo DB + `/var/lib/ronin` para el
appliance local y backup separado para el object store externo.

**Evidencia anterior a los últimos cambios del runner:** el journey combinado
DB + volumen local sí ejecutó un roundtrip real Compose/PostgreSQL y pasó como
diagnóstico filtrado, 1 caso seleccionado (26 deselected), 44,58 s de pytest
y 38,05 s dentro del test. Recibo: `%TEMP%\ronin-docker-appliance-final-489bc4b7f8474ebdb67ab8f06acb75e9`.
Ese resultado antecede la selección condicional de fixtures y el resumen de
imagen/fixtures; no valida esas ediciones ni la nueva prevalidación de checksum
de la revisión actual.

Por la instrucción persistente del operador, esta edición solo modifica
ficheros: no se ejecutaron pytest, Docker, linters, parsers ni validadores. Por
tanto los contratos y la regresión nueva están pendientes de ejecución y no
hay resultado atribuible a estos cambios. La evidencia §43 precede a esta
edición y no la verifica. El siguiente paso manual es seguir las capas 1–3 de
`docs/testing/TESTING_FAST_TO_FULL.md`, corregir lo que revelen y después correr
el gate Docker completo, la suite PostgreSQL y la qualification live UI/API.
Estado conservador: release **NO-GO, 0/13 familias**; ningún gate completo se
declara aprobado por esta edición.

## 45. Validar bloqueos explícitos del ledger de release — 3/11/2026

El manifiesto machine-readable ya enlaza el checklist GO/NO-GO e identifica
bloqueos independientes: identidad del candidato, journeys incompletos,
decisiones legales/de producto y revisión visual. `tools/capability_status.py`
ahora valida esos campos cuando el manifiesto incluye `qualification_status`:
un estado `blocked` necesita causas; los IDs deben ser únicos y cada causa
requiere estado conocido, explicación y referencia de evidencia. Se añadieron
casos positivos y negativos a `tests/test_capability_status.py`. Los manifiestos
antiguos de pruebas sin estado de release conservan compatibilidad.

Esto evita que el ledger acepte `blocked` sin explicación y distingue la
qualification técnica pendiente (`qualification_pending`) de decisiones
humanas (`human_decision`). No convierte la existencia de una referencia en
prueba de que el bloqueo está resuelto; el checklist sigue siendo la fuente de
GO/NO-GO y la evidencia candidate-bound se debe aportar por separado.

Por la restricción vigente del operador, no se ejecutaron el validador ni los
tests nuevos. No hay resultado de verificación para esta edición; el siguiente
paso es ejecutar `tests/test_capability_status.py` y el gate de consistencia del
ledger, corregir cualquier hallazgo, y volver a cualificar el candidato limpio.
Release **NO-GO, 0/13 familias**.

## 46. Medición por caso para acelerar el feedback — 3/11/2026

La iteración de diagnóstico ahora carga `tools.pytest_timing_report` en el
runner Python/PostgreSQL y guarda `pytest-timings.json` junto a JUnit y logs.
El informe registra fases y duración por node ID, colección, tiempo de sesión,
resultado/reintentos, selección exacta, perfil de servicio y estado de
coverage. `runner-timings.json` separa resolución del entorno Python, arranque y
readiness de PostgreSQL, wall time de pytest, cleanup y duración total; así se
puede saber si la demora está en el entorno, el servicio o los tests.
Ambos recibos registran SHA fuente, worktree limpio/sucio, modo de qualification,
selección, coverage y perfil de servicio; las comparaciones solo son válidas
entre contextos equivalentes y worktrees limpios. Dos árboles sucios con el
mismo HEAD no identifican el mismo código; sus timings son solo diagnóstico.
`tools.pytest_slowest_selection` lee el esquema versionado, rechaza
node IDs duplicados y duraciones inválidas, y genera una selección reproducible
por node ID para las vueltas siguientes; con `--run` pasa cada ID a pytest como
argumento independiente y reenvía el código de salida. Se añadieron tests de
contrato para orden estable, entrada corrupta y forwarding de IDs; el selector
omite los casos skipped, valida outcomes y duraciones JSON sin tipos/valores
inválidos o desbordados, y solo permite `--run` desde un informe local-only sin
servicios ni coverage. Los errores de lectura/escritura se presentan como
errores de entrada controlados. Los IDs de informes PostgreSQL pueden exportarse, pero
deben reejecutarse con el runner de familia. El perfil `-LocalOnly` elimina los DSN PostgreSQL
heredados durante la pasada y los restaura al cerrar, para impedir que un test
se conecte por accidente a una base externa. Los campos históricos `ci` del
formato se conservan por compatibilidad; el runner actual es manual y no
activa CI.

El flujo se mantiene separado en tres niveles: selección local sin servicios
(`-LocalOnly`), selección contra PostgreSQL 16.4 real sin coverage y suite
completa no-performance contra PostgreSQL con coverage. Los runners live UI/API
y Docker siguen siendo gates independientes; la selección de los casos más
lentos solo sirve para diagnóstico y nunca cierra una familia ni sustituye un
gate completo. `-LocalOnly` exige un archivo explícito y rechaza rutas de
integration/e2e/perf y el marcador integration; elimina también DSNs heredados
durante la ejecución y los restaura al salir. Esto acota la colección, pero la
ausencia de dependencias de servicio en un módulo unitario sigue siendo un
contrato que requiere revisión y pruebas. El runner filtrado falla si el JUnit
solo contiene skips de colección y ningún test ejecutable seleccionado. Los
directorios de evidencia de los ejemplos son distintos, porque cada ejecución
requiere un directorio nuevo y vacío. Se documentaron comandos y límites en
`docs/testing/TESTING_FAST_TO_FULL.md`.

No se ejecutaron tests, Docker, parsers ni comprobaciones estáticas para estos
tests de contrato incluidos. Por ello aún no existe medición de ahorro, no se
ha verificado la salida del plugin en los tres perfiles, la estructura del
ledger actualizado, la guarda contra selección vacía ni la aceptación de node
IDs por el comando de reejecución.
El siguiente operador debe ejecutar
`tests/test_pytest_slowest_selection.py` y los contratos del runner, hacer una
ejecución local y una PostgreSQL filtrada, revisar JUnit y timings, reejecutar
la selección lenta y medir la duración comparativa en la misma máquina; después
deben ejecutarse los gates completos.
Esta edición no altera el denominador: release **NO-GO, 0/13 familias** y se
recomienda retrasar hasta tener un candidato limpio y gates completos.

## 47. Alcance explícito y fail-closed en recibos de release — 3/11/2026

El agregador ya exigía los gates requeridos, un único commit, profile correcto,
digests de artifacts íntegros y evidencia no caducada, pero el recibo `passed`
no decía si el comando había ejecutado la suite completa o solo un filtro. La
checklist lo advertía sin poder hacerlo cumplir. Se añadió `execution_scope`
(`complete` o `diagnostic`) al emisor; es obligatorio en CLI y queda dentro del
hash del verdict junto con comando, fingerprint de entorno, fechas y digests.
Los gates requeridos solo pasan si tienen `status=passed` y
`execution_scope=complete`. Un diagnóstico filtrado con `status=passed`, un
recibo legacy sin alcance y cualquier scope desconocido no pueden producir GO.
Los bundles legacy siguen pudiendo leerse para revisión, pero no cierran un gate.
El verdict también rehasha los archivos cuando se invoca con `--required-gate`
individual, no solo con un profile; un archivo alterado hace fallar cualquier
camino de verdict.

Se añadieron regresiones para scope diagnostic, recibos legacy sin scope,
valores de scope no admitidos, rehash sin profile y el CLI agregador con un gate
requerido marcado diagnostic; se actualizó el comando completo del ejemplo de
`local-quality`.
No se ejecutaron estas pruebas ni los gates de release por
la restricción vigente de no ejecutar; la nueva aplicación del contrato,
compatibilidad y el ejemplo quedan pendientes de probarse. El estado permanece
**NO-GO, 0/13 familias**; la regla reduce el riesgo de sobredeclarar evidencia,
pero no cualifica el producto.

## 48. Rechazo controlado de informes de timing malformados — 3/11/2026

La herramienta que genera una selección rápida de los tests lentos ahora
rechaza outcome con tipo no textual o fuera del enum, duración negativa, NaN,
infinito y enteros cuya conversión a segundos desborda. Los errores de sistema
al leer el informe o escribir el archivo de selección se convierten en un
mensaje de CLI en vez de un traceback inesperado. Se añadieron casos de
contrato para outcomes no textuales y duración no representable.

No se ejecutó la suite del selector ni los gates de estilo/tipos. El nuevo
contrato está pendiente de verificación y no hay medición comparativa de
tiempos. Release **NO-GO, 0/13 familias**.

## 49. Identidad de fuente en las mediciones de pruebas — 3/11/2026

Los informes `pytest-timings.json` y `runner-timings.json` ahora registran el
SHA fuente, estado limpio/sucio, modo de qualification, selección, coverage y
perfil del servicio. Se amplió el contrato del runner para comprobar que esos
datos se pasan al plugin y al recibo de fases. La guía aclara que solo se deben
comparar mediciones de worktrees limpios con el mismo commit y contexto; dos
árboles sucios pueden compartir HEAD y contener cambios diferentes.

No se ejecutaron los contratos ni el plugin; tampoco se midió una pareja de
ejecuciones. La utilidad para explicar el coste es una mejora propuesta, no un
ahorro demostrado. Release **NO-GO, 0/13 familias**.

## 50. Optimización por capas y lectura verificable de resultados — 3/11/2026

`docs/testing/TESTING_FAST_TO_FULL.md` ahora define un ciclo de menor coste:
prueba local del cambio, integración focalizada con el servicio real afectado,
familias completas y gates de release. Separa explícitamente Python/PostgreSQL,
Docker/proveedores, Playwright estático con mocks, navegador/API live y revisión
visual humana. Cada lane declara lo que prueba, lo que no prueba y qué evidencia
debe revisarse; así un resultado estático o filtrado no se presenta como
funcionalidad live.

El runner PostgreSQL escribe `cleanup_status` y `cleanup_error` en
`runner-timings.json`. Si falla la eliminación del contenedor, fuerza código de
salida fallido y señala `INCOMPLETE`, aunque pytest haya terminado en verde.
Se añadió una aserción de contrato para esa regla y una plantilla breve de
reporte que exige scope, selección, resultado, servicios/digests, evidencia,
limpieza y siguiente gate. Para UI/API añade conteos HTTP y logs OK/WARN/ERROR
correlacionados.

No se ejecutaron las nuevas aserciones ni los carriles, conforme a la
instrucción vigente de no ejecutar. Tampoco existe una comparación de duración
antes/después; la optimización reduce ejecuciones innecesarias en el ciclo de
edición, pero su ahorro de tiempo no está medido. Antes de usar el runner en un
expediente de release, el operador debe ejecutar el contrato del runner, una
selección local, una selección PostgreSQL, provocar/verificar el informe de
cleanup y completar cada familia requerida sobre un único SHA limpio.
Esta aclaración no altera el estado: release **NO-GO, 0/13 familias**; retrasar
la publicación si faltan gates o decisiones humanas.

## 51. Fail-closed en cursores JDBC incrementales — 3/11/2026

La lectura JDBC comprobaba NULL únicamente en los campos de cursor de la última
fila. Un motor que ordenase NULL antes de una fila válida podía devolver una
selección con un watermark final no nulo y, aun así, dejar una fila sin una
posición reanudable. Ahora se inspeccionan los campos de watermark y todos los
tie-breakers en cada fila devuelta; cualquier NULL hace fallar la lectura antes
de emitir un checkpoint. Se añadió una regresión cuyo primer registro tiene
cursor NULL y cuyo último es válido, precisamente el caso que escapaba a la
comprobación anterior. El constructor y decoder del checkpoint V2 también
exigen que el marcador de origen vacío tenga watermark y tie-breakers nulos, y
que un cursor poblado tenga todos esos componentes no nulos. Así un cursor
malformado no puede activar accidentalmente la lectura completa sin predicado.
También se amplió el rechazo de credenciales embebidas en URLs JDBC a `pwd`,
`pass`, `login`, variantes `user id`/`user_id`, userinfo URI y la forma
usuario/clave de Oracle Thin; se agregaron regresiones de contrato para esas
formas comunes.

El cambio no verifica aún comportamiento contra un driver JDBC real: el módulo
usa un bridge inyectado y la matriz de producción sigue pendiente. Por la
restricción vigente no se ejecutaron las pruebas. Antes de aceptar la corrección
hay que correr `tests/test_jdbc_connector.py` y la suite de conectores; después,
cualificar al menos un perfil JDBC real soportado y sus casos incremental de
NULL, empates, reanudación y cambio de esquema. P2 permanece parcial y el
release sigue **NO-GO, 0/13 familias**.

## 52. Cierre del stream de lectura S3 — 3/11/2026

La lectura del conector S3 consumía `get_object()['Body']` pero no cerraba el
stream del SDK. Ahora el cuerpo se cierra en `finally` inmediatamente después
de la lectura acotada, tanto si la lectura termina bien como si lanza una
excepción. También se valida que el bridge haya devuelto bytes antes de medir
el tamaño o decodificar JSON. Las regresiones comprueban cierre en lectura
normal y al rechazar un objeto mayor al límite configurado.

No se ejecutaron los tests por la restricción vigente. Falta comprobar el cierre
con boto3/botocore reales y contra Floci/LocalStack, incluidos JSON inválido,
fallo de lectura y respuesta sobredimensionada; los tests del fake solo cubren
el contrato local. P2 sigue parcial y el release **NO-GO, 0/13 familias**.

## 53. Rechazo de snapshots HTTP paginados incompletos — 3/11/2026

`HttpJsonConnector.read` podía salir de su bucle al alcanzar `max_pages` aunque
el último resultado indicara otra página. Devolvía entonces las filas parciales
y un digest de snapshot normal, sin señal de truncamiento; una sincronización
podía consolidar ese checkpoint y perder el resto de los registros. Ahora
falla explícitamente si `page_param` llena la página máxima (no hay token para
saber si existe otra página) o si `next_url_field` anuncia una continuación al
consumir el último slot.

Se añadieron dos regresiones a la integración de HTTP loopback real: una para
cada modalidad, verificando que solo se hace el número permitido de requests y
que no se emite un resultado parcial. El servicio es HTTP real local, pero no
es certificación de un proveedor remoto. No se ejecutaron las pruebas. P2 sigue
parcial hasta verificar las regresiones, los perfiles de proveedor y la
persistencia/reanudación de checkpoints en la ruta completa; release **NO-GO,
0/13 familias**.

## 54. Detección temprana de ciclos de paginación HTTP — 3/11/2026

Cuando `next_url_field` devolvía una URL previamente solicitada, el cliente
repetía la llamada hasta agotar `max_pages` o el presupuesto de tiempo. Ahora
mantiene el conjunto de URLs solicitadas y rechaza la repetición antes de abrir
otra conexión. Esto limita el coste y carga de un cursor de servidor cíclico y
evita guardar un snapshot basado en una respuesta repetida.

Se añadió un caso de integración contra el servidor HTTP loopback que devuelve
la misma URL siguiente, con aserción de que solo se recibe un request. No se
ejecutó; falta verificar la regresión junto a ambas pruebas del límite de
`max_pages` y la suite HTTP. Release **NO-GO, 0/13 familias**.

## 55. Alcance explícito del veredicto de gates — 3/11/2026

`release_verdict` también puede evaluar un conjunto personalizado de gates para
diagnóstico o una comprobación acotada. Antes devolvía `status: passed` sin
distinguir ese resultado del perfil completo; el agregador de release ya
comprobaba el perfil, pero un consumidor del CLI podía interpretar el resultado
de una selección como release verde. El verdict ahora incluye
`qualification_scope`: `complete-profile` solo si el conjunto solicitado
coincide exactamente con todos los gates de un perfil nombrado; en caso
contrario, `custom-gate-set`. Ese campo queda cubierto por `verdict_sha256`.

Se añadieron casos para un subset genérico, un subset de un bundle que declara
`release_required` y el perfil completo agregado. No se ejecutó el suite de
evidencia ni el agregador, por lo que el cambio está sin verificar. El perfil
completo sigue requiriendo los diez gates, evidencia completa y revisión humana;
la release permanece **NO-GO, 0/13 familias**.

## 56. Selección y omisiones visibles en los recibos de pytest — 3/11/2026

El recibo `pytest-timings.json` pasa a esquema v3 y deja de emitir metadatos de
CI. Conserva por separado los node IDs seleccionados y los retirados mediante
filtros de pytest, informa los totales seleccionados, filtrados, ejecutados y
no ejecutados, desglosa los outcomes y guarda el motivo de cada skip/xfail. El
selector de pruebas lentas reconoce el nuevo esquema. El comparador de shards,
ligado al antiguo flujo de CI, se retiró. Esto permite detectar una selección
vacía, una interrupción antes de ejecutar todo lo seleccionado o skips cuyo
servicio requerido no estaba disponible, en lugar de depender de un mensaje
genérico de éxito.

La guía ahora recomienda ejecutar el módulo afectado, luego la familia real de
servicios correspondiente y reservar las familias completas para cuando el
cambio de funcionalidad haya terminado. Esto evita repetir arranques de Docker,
PostgreSQL y navegador tras cada cambio pequeño sin rebajar la matriz exigida
para una afirmación de release. No se ejecutó la nueva suite contractual ni se
midió ninguna ejecución antes/después; no se puede afirmar todavía que haya
una aceleración observada ni que el recibo v3 funcione correctamente. Hay que
ejecutar `tests/test_pytest_timing_report.py`,
`tests/test_pytest_slowest_selection.py`, los contratos del runner y una
selección local con skip deliberado; comparar el JSON con la salida JUnit y
confirmar que los filtros y node IDs coinciden. La suite completa y las
familias release continúan pendientes; estado **NO-GO, 0/13 familias**.

## 57. Correlación live de respuestas API y logs — 3/11/2026

La auditoría posterior a la suite live mostró que Ronin emitía `X-Ronin-Request-Id`
pero el proxy Playwright buscaba `x-request-id`; por ello, aunque servidor y
navegador registraban los eventos, el recibo no podía unirlos. El proxy ahora
captura el header correcto y el runner exige para cada llamada API un evento
estructurado `http.request` con el mismo request ID, status y outcome. El test
live exige asimismo un ID `req-<32 hex>` en cada evento. Una llamada sin pareja
hace fallar el runner y queda contabilizada en el resumen.

La suite completa volvió a pasar **32/32 casos**, 0 skips/fallos, con 25 rutas
activas auditadas (23 API-backed, 2 UI-only), PostgreSQL, Kafka, Ronin API y
worker Docker reales. Se registraron 158 llamadas HTTP: 149 `OK`, 9 `WARN`
(400/401/403/409); las 158 quedaron correlacionadas con logs por request ID,
status y outcome. No hubo 5xx ni errores de red. Los logs contenían 1.490
`INFO`, 9 `WARNING` y 0 `ERROR`; dependencias Python/browser en caché y cleanup
de servicios correcto. Duración total 162,75 s; Playwright 130,35 s. Evidencia:
`%TEMP%\ronin-live-correlated-20261103\qualification-summary.json`, JUnit,
tráfico y logs.

El carril live no fuerza fallos 5xx en el producto para poder informar verde.
Separadamente, `test_control_plane_access_logs_ok_warn_and_error_with_redacted_correlation`
pasó 1/1: servidor HTTP real con fallo de dependencia inyectado respondió 500
`internal_error`, emitió nivel `ERROR`/outcome `ERROR`, mantuvo correlación por
request ID y redactó el secreto simulado. El test de contrato del runner pasó
17/17, la suite focalizada HTTP pasó 1/1 y PowerShell parseó sin errores.

Esto corrige el hueco de observabilidad y acredita los estados OK/WARN/ERROR
sin confundir un error deliberado con una aceptación de producto. Sigue siendo
diagnóstico de árbol sucio en `20261029@f9a0456`; **no cierra el gate candidate-
bound ni cambia NO-GO, 0/13**. Faltan los recorridos de familia, revisión visual
manual y decisiones de release indicadas en el checklist.

## 58. Instalación limpia de wheel y sdist — 3/11/2026

Se generaron artefactos diagnósticos del árbol actual: wheel SHA-256
`2a619eef3409d7b3df364242a4e28f5545a514925383f6b07332c1acc3caefb3` y sdist
SHA-256 `3fa0cd033617251dc1f74360f3dc982c19e5d24ddada337e7f64435bdbea9c58`.
Ambos se instalaron por separado en entornos virtuales limpios. En cada uno,
`ronin --help` respondió correctamente y se encontraron 4/4 assets esenciales
(`index.html`, `routes.json`, `js/app.js` y `ronin-logo-full.png`). La inspección
de los artefactos encontró cero rutas de paquetes GenAI; el wheel incluye los
12 archivos del paquete de skills de coding agents.

La primera llamada a `pip download --no-binary :all: .` no produjo un sdist
local, aunque informó que había descargado el proyecto; se cambió la prueba a
`setuptools.build_meta.build_sdist` y se exigió el `.tar.gz` antes de continuar.
Después, la instalación desde sdist reconstruyó el wheel y pasó los mismos
smokes. El output vive en
`%TEMP%\ronin-artifact-diagnostic-9f3006ca00e34b899bc085e3941dcf45`.

Esto detecta problemas básicos de empaquetado e instalación, pero no es un
release receipt: el árbol está sucio, el package version sigue `0.0.0`, no hay
decisión de versión aprobada y no se verificaron todos los comandos, rutas,
upgrade/rollback o plataformas declaradas. No se generaron SBOM/provenance con
una identidad que afirmase falsamente que el contenido sucio corresponde al
SHA base. El gate de artefactos queda abierto; Public v1 **NO-GO, 0/13**.

## 59. Auditoría de advisories del lock Python — 3/11/2026

`pip-audit 2.10.1` consultó el lock `requirements-test.lock` fijado: **101
dependencias, cero vulnerabilidades conocidas**, exit code 0. Se ejecutó sin
resolver ni reinstalar dependencias (`--no-deps --disable-pip`), lo que redujo
la comprobación a unos segundos. Recibo JSON:
`%TEMP%\ronin-pip-audit-locked-noresolve-20261103.json`.

El resultado cubre advisories Python conocidos para ese lock en la consulta de
hoy; no detecta secretos, vulnerabilidades de la imagen Docker, problemas de
licencias ni configuraciones de otros SO. En este checkpoint no se había
ejecutado un escáner de imágenes; el resultado Docker Scout posterior y su
VEX se documentan en §61. Gitleaks y scans de artefactos finales sobre un
candidato limpio siguen pendientes. El gate Security queda abierto hasta la
evaluación de hallazgos y revisión humana. Release **NO-GO, 0/13**.

## 60. Optimización y claridad de los carriles de prueba — 3/11/2026

Se analizaron los recibos completos en vez de inferir el estado desde el
resumen de consola. La pasada Python/PostgreSQL seleccionó 4.489 casos: 4.465
PASS, 24 SKIP con razón conservada en JUnit/timing JSON y 0 FAIL. Pytest tardó
549,09 s y el runner completo 558,86 s. El informe por prueba suma 472,19 s;
el resto incluye colección, cobertura, generación de informes y overhead del
runner. PostgreSQL arrancó en 2,17 s y la preparación del entorno en 6,17 s,
por lo que reutilizar la DB o entorno no recortaría el grueso del tiempo.

El carril Docker se volvió a ejecutar con imagen reconstruida tras actualizar
libexpat; 27/27 pruebas pasaron, 0 skips/fallos, aceptación estricta 15/15,
en 187,45 s, digest `sha256:b23d6470f27f39bb6ca8d4c69a922338ffcb844b9f92bdff22584401fe7effda`.
El navegador/API real, repetido con esa misma imagen, pasó 32/32 en 163,78 s
con 25 rutas inspeccionadas y
158/158 eventos HTTP correlacionados con logs. Evidencias detalladas, fases y
límites están en `docs/testing/TESTING_FAST_TO_FULL.md`.

La optimización aplicada es ejecutar primero el módulo/filtro afectado y
ensanchar al runner de servicios correspondiente, evitando repetir los tres
carriles completos por cambios locales ajenos. No se afirma que la suite
completa sea más rápida: no existe comparación equivalente antes/después. No
se activa paralelismo, porque los tests con servicios comparten procesos y
base de datos; primero haría falta un piloto que demuestre aislamiento sin
perder nodos, cobertura ni resultados. Los carriles completos siguen siendo
necesarios para el candidato final. El diagnóstico permanece sucio y Public v1
sigue **NO-GO, 0/13**.

La imagen de calificación se escaneó con Docker Scout: la primera lectura
detectó cuatro advisories HIGH de libexpat y uno LOW de musl. Tras actualizar
libexpat a `2.10.0-r0` y reconstruir/recalificar la imagen, el único resultado
restante fue el advisory de musl. Su VEX y verificación efectiva quedan
registrados en §61. Gitleaks y los escaneos finales ligados a artefactos de
un candidato limpio continúan pendientes.

## 61. Disposición reproducible del advisory musl para la imagen Docker — 3/11/2026

Docker Scout identifica el componente como
`pkg:apk/alpine/musl@1.2.6-r3?os_name=alpine&os_version=3.24` y su versión
genérica upstream marca `CVE-2026-107891` como afectado. El tracker oficial de
Alpine marca `1.2.6-r3` de la rama `3.24-main` como `fixed` ([Alpine Security
Tracker](https://security.alpinelinux.org/vuln/CVE-2026-107891)); el anuncio de
Alpine 3.24.3 incluye el CVE entre las correcciones de seguridad ([release
Alpine 3.24.3](https://www.alpinelinux.org/posts/alpine-3.21.9-3.22.7-3.23.7-3.24.3-released/)).

El primer intento de VEX no fue válido como prueba porque Scout no aceptaba el
autor, aunque había cargado el archivo. La CLI filtra autores con su allow-list
por defecto; al especificar exactamente el autor con `--vex-author`, Scout
confirmó que la excepción se aplicaba ([documentación Docker Scout VEX](https://docs.docker.com/scout/how-tos/create-exceptions-vex/)).
Para `ronin:qualification` con digest
`sha256:b23d6470f27f39bb6ca8d4c69a922338ffcb844b9f92bdff22584401fe7effda`, el
escaneo raw contiene solo ese finding exacto; con el VEX bound al PURL
`pkg:docker/ronin@sha256:b23d6470f27f39bb6ca8d4c69a922338ffcb844b9f92bdff22584401fe7effda`,
el escaneo aplicado devuelve **cero findings**. El comprobador
`tools/verify_docker_vex.ps1` falla ante un digest distinto, otro finding raw
o cualquier hallazgo que sobreviva a VEX. La prueba contractual pasó junto con
las 18 pruebas de `test_docker_qualification_contract.py` (2,60 s). El runner
guardó versión de Scout, estado del worktree, digest y ambos informes SARIF.
Recibos raw, VEX y resumen:
`%TEMP%\ronin-docker-vex-qualified-final-20261103`; fuente VEX:
`docker/qualification-image-vex.openvex.json`.

Gitleaks 8.30.1, fijado por digest, encontró **0 secretos** en el árbol actual
(73,25 MB, 20 s) y en los **1.873 commits** alcanzables desde `20261029` (54,1
s). Evidencia: `%TEMP%\ronin-gitleaks-current-final-20261103` y
`%TEMP%\ronin-gitleaks-history-20261103`. `pip-audit 2.10.1` detectó cero
advisories en los locks fijados de test (101 paquetes), runtime (3) y bootstrap
(1): `%TEMP%\ronin-pip-audit-locked-noresolve-20261103.json` y
`%TEMP%\ronin-pip-audit-runtime-locks-20261103`. Estos son recibos del árbol
sucio y del SHA base, no del artefacto publicable.

Esta excepción es específica de un digest de diagnóstico; no se reutiliza en
una nueva imagen. La siguiente build necesita regenerar/revisar el PURL y
repetir ambos escaneos. Esto confirma el backport oficial, no reemplaza el
escaneo ligado a artefactos finales ni la revisión humana. Security permanece
**OPEN** y Public v1 **NO-GO, 0/13**.


## 62. Tiempos actuales, seguridad del paralelismo y evidencia Helm — 3/11/2026

Se actualizó la evidencia con una nueva ejecución live sobre la misma imagen
inmutable usada por Docker y Helm: `sha256:3cffbb1acd492a0d8ccd290232edfb8526055924ede4d4ee78702f8d192d7158`.
La suite del navegador pasó 32/32 casos (0 skips y 0 fallos), cubrió 25 rutas
(23 con contratos API), generó 161 llamadas reales (152 `OK`, 9 `WARN`), y
correlacionó cada llamada con su log `http.request` por request ID, status y
outcome. No hubo 5xx ni errores de red. Duró 196,62 s total, de los cuales
116,15 s fueron Playwright. La ejecución Docker pasó 27/27, aceptación estricta
15/15, en 259,39 s de pytest. Helm/kind pasó sus once fases: lint, límite del
secreto, despliegue, readiness, health 200, Studio/API autorizada, job 201,
reinicio, persistencia del mismo job y limpieza. Evidencias:
`%TEMP%\ronin-live-helm-current-20261103`,
`%TEMP%\ronin-docker-helm-prep-20261103` y
`%TEMP%\ronin-helm-kind-qualification-20261103`.

Se refrescó Gitleaks 8.30.1 sobre el árbol de trabajo actualizado, con salida
redactada: unos 73,28 MB escaneados sin detectar secretos (8,5 s). El historial sigue
con 0 hallazgos en 1.873 commits. Recibo del árbol:
`%TEMP%\ronin-gitleaks-current-release-final-20261103`; el historial está en
`%TEMP%\ronin-gitleaks-history-20261103`. Docker Scout/VEX se volvió a aplicar
al digest actual: una detección raw del backport Alpine exacto y cero hallazgos
con VEX. El resumen conserva digest, autor VEX explícito, hash del VEX y ambos
SARIF en `%TEMP%\ronin-docker-vex-current-20261103`.

Optimización: el carril Python completo sigue costando 558,86 s; 472,19 s son
setup/call/teardown de casos y el resto se concentra principalmente en la
colección/cobertura. No se redujo la selección ni la cobertura. Docker y live
siguen seriales porque varios casos reinician workers, restauran datos y
mutan proyectos, contratos, labs y workflows compartidos. No existe prueba de
aislamiento que justifique añadir workers; el entorno hash-lock tampoco incluye
pytest-xdist. Para iterar, la guía dirige primero al archivo/filtro afectado y
luego al runner real de la familia, dejando cada suite completa para el cierre
de integración/candidato. No se afirma una aceleración del mismo conjunto de
tests: la mejora es reducir ejecuciones globales innecesarias sin falsear la
cobertura de los gates finales.

Todo lo anterior sigue siendo diagnóstico de worktree sucio en
`20261029@f9a0456`; no consolida un candidato release. El gate Security sigue
abierto para revisión humana y escaneo de artefactos finales; las 13 familias
continúan **OPEN 0/13**, y el resultado de release sigue **NO-GO**.



## 63. P1 project Bundle UI/API real journey — 3/11/2026

La inspección de la ruta de proyectos llevó a un test de navegador con backend
real. El flujo de UI enviaba `POST /v1/workspaces/{workspace}/projects/{project}/bundle/import`,
pero el bloque de implementación estaba accidentalmente dentro de `do_GET`.
La documentación OpenAPI ya declaraba el método POST correcto, por lo que el
servidor respondía 404 al importar desde la interfaz. Se movió el handler al
`do_POST` existente, conservando autorización `project.write`, `Idempotency-Key`,
verificación de archive y digest, rechazo si el ID no coincide, auditoría
fail-closed, no-op idempotente si el contenido coincide y conflicto si difiere.

La nueva prueba de regresión de loopback HTTP confirma que GET devuelve 405,
POST sin clave idempotente devuelve 400 y no muta el proyecto, POST válido
persiste el manifiesto y digest correctos, y el reintento es un no-op estable.
El módulo completo `tests/integration/test_workspace_project_http_api.py`
pasó 44/44 en 26,42 s.

La nueva prueba Playwright `live Projects create, export, and reimport a
secret-safe Bundle through the UI` usa la API local real, PostgreSQL y Kafka:
- intenta crear un proyecto con usuario/contraseña incrustados en la URL Git;
  Ronin devuelve WARN visible sin repetir el secreto;
- crea después un manifiesto portable, verifica API 200/201 y ausencia de
  `auth_ref`/token en la representación exportada;
- descarga el Bundle por la interfaz, verifica tipo y digest SHA-256, instala
  el archivo en el formulario y lo reimporta; confirma proyecto persistido y
  digest de importación igual al archive descargado.

El primer POST import de este recorrido falló 404 y sirvió como evidencia del
bug. Tras mover el handler, el caso focalizado pasó 1/1 con nueve llamadas API
reales correlacionadas a sus logs: 8 OK, 1 WARN; 0 errores de servidor/red.
La suite live completa pasó 33/33, 25 rutas auditadas (23 API-backed), 168/168
llamadas correlacionadas (158 OK, 10 WARN), 0 skips/fallos/5xx y cleanup
correcto en 159,83 s. Logs: 1.542 INFO, 10 WARNING, 0 ERROR. Evidencia:
`%TEMP%\ronin-live-p1-bundle-real-fixed-20261103` y
`%TEMP%\ronin-live-p1-bundle-full-20261103`.

Esto fortalece P1, pero no cierra su fila: source-control/revision identity,
SDK y auditoría con store durable aún necesitan un journey integrado y el resto
de familias siguen sin cualificar. También es diagnóstico de worktree sucio;
la evidencia Docker/Helm/security aún no comparte un candidato limpio con el
cambio del handler. Release **NO-GO, 0/13**.

## 64. Latest full-family rerun and current image binding — 3/11/2026

Se repitieron los gates costosos sobre el checkout actual, sin cambiar la
selección para reducir artificialmente los tiempos. El entorno Python y las
dependencias de navegador estaban cacheados; los servicios se aislaron y
limpiaron al terminar:

| Carril | Resultado | Evidencia |
| --- | --- | --- |
| Python + PostgreSQL 16.4 | JUnit/pytest: 4.467 passed, 26 skipped, 0 failed; 4.493 casos en total con branch coverage; 538,81 s de pytest, 546,36 s total; cleanup correcto. El timing v3 omitió 2 módulos skip en colección; el recibo JUnit y el resumen terminal sí los incluyen. | `%TEMP%\ronin-python-full-current-20261103` |
| Docker + providers locales | 27/27, 0 skips/fallos; PostgreSQL, worker Docker, Floci/S3 y Azurite/Azure; aceptación estricta 15/15; 173,31 s de pytest; limpieza correcta. | `%TEMP%\ronin-docker-full-current-20261103` |
| Helm/kind | 11 fases: lint/render, aislamiento de Secret, carga de imagen, readiness, health/API, persistencia del job tras reinicio y cleanup; todas pasaron. Helm v4.3.0. | `%TEMP%\ronin-helm-full-current-20261103` |
| Browser/API live | 33/33; 25 rutas, 23 API-backed; 168/168 llamadas correlacionadas con logs (158 OK, 10 WARN esperados), sin 5xx ni errores de red; PostgreSQL y Kafka reales; 163,43 s total; limpieza correcta. | `%TEMP%\ronin-live-full-current-20261103` |
| Browser estático | Suite completa 101/101 en unos 3 min. Luego, navegación de 25 rutas + responsive sweep pasó 26/26 tras endurecer manejo de fallos HTTP/red. Los 404 `/v1` del servidor estático son misses API esperados; otros recursos HTTP fallidos o solicitudes de red fallidas provocan fallo del test. | Informe HTML `web-tests/test-results-html`; la pasada focalizada final se ejecutó tras añadir el guard. El pase completo precede ese guard. |
| Docker Scout + OpenVEX | 1 raw finding del backport musl documentado; 0 tras aplicar excepción exacta. VEX/SARIF ligados al digest de la imagen nueva. | `%TEMP%\ronin-docker-vex-full-current-20261103` |

La imagen común a Docker, Helm, live y VEX es
`sha256:fb9029dad0d8d5aade4bb5809c8a4e027f416a158fedc633c65667d0b21b01b8`.
El source HEAD es `f9a0456ab7df3e2bb77247d54b4336fca64903b0`, pero el árbol
sigue sucio: son diagnósticos, no evidencia de candidato publicable. La suite
Python deja 24 skips explícitos; Docker/provider locales se cubren aparte,
mientras POSIX, symlink y credenciales de proveedores externos no se
certifican en este host.

Gitleaks 8.30.1 escaneó el árbol actualizado (72,98 MB) en 27,9 s y no halló
secretos; SARIF:
`%TEMP%\ronin-gitleaks-tree-final-20261103\worktree.sarif`.
El historial sigue limpio según el scan previo de 1.873 commits. La corrida de
árbol incluye las últimas ediciones del test de navegación y del ledger, aunque
sigue siendo evidencia de worktree sucio, no de artefactos publicables.

La mejora al proceso es reutilizar los entornos hash-pinned y filtrar servicios
solo durante la iteración; en este checkpoint se ejecutaron completas Python,
Docker y live, y Helm usó el mismo digest. No se paralelizaron journeys que
comparten estado ni se acortaron pruebas de recuperación. La release sigue
**NO-GO, 0/13 familias**: faltan candidato limpio/tag, gates ligados a
artefactos finales, journeys por familia, revisión manual visual y decisiones
humanas de versión, claims, soporte y licencias.

## 65. Local quality and coverage gate refresh — 3/11/2026

Al revisar el gate `make check` se confirmó que GNU Make no está instalado en
este host. Para no duplicar la suite Python de 9 minutos, se ejecutaron
directamente todos los objetivos estáticos y de performance del Makefile con
el intérprete hash-pinned y las herramientas presentes:

- Ruff format y lint: **899 archivos**, ambos PASS.
- mypy: **437 source files**, sin errores.
- OpenAPI snapshot, arquitectura, gates negativos, consistencia de rutas (**187
  operaciones**), Studio surface (**125/229**), web audit (**60 archivos, cero
  fallos**), web budget, canonical JSON, runner protocol, dependency surfaces,
  capability status y validación de agent skills: PASS.
- Performance: **5/5** en 5,25 s.
- Los floors de cobertura configurados en Makefile, todos contra el
  `.coverage` de la suite Python de esta misma corrida, pasaron: T1, T2, T3
  plataforma/SDK/control-plane, T4, broker, tools, release gates y el ratchet
  per-file de storage (**53 archivos**).
- El módulo `tests/test_docker_qualification_contract.py` mostró un digest
  VEX hard-coded obsoleto tras regenerar el VEX para la imagen nueva. Se
  reemplazó por una validación del PURL y formato SHA-256; la igualdad real con
  el digest inspeccionado la hace el runner de Scout/VEX. Tras formato, Ruff
  pasó y ambos módulos afectados (`test_docker_qualification_contract.py`,
  `test_workspace_project_http_api.py`) pasaron **62/62** en 30,01 s.

Recibos: `%TEMP%\ronin-static-quality-current-20261103`,
`%TEMP%\ronin-coverage-gates-current-20261103` y
`%TEMP%\ronin-python-full-current-20261103`.

Esta ejecución directa cubre los objetivos correspondientes, pero no es una
invocación literal de `make check`. Todo sigue en árbol sucio; el gate local de
release continúa OPEN hasta repetirlo sobre candidato limpio. Los tests de
producto no se redujeron, y los skips de proveedores/plataformas siguen
explícitos. Sin alterar scope ni claims, la decisión permanece **NO-GO** hasta
resolver gates de artefactos, journeys por familia, revisión manual visual y
decisiones humanas.

## 66. Optimización y legibilidad del ciclo de pruebas — 3/11/2026

El perfil de la suite completa de Python/PostgreSQL sitúa el coste principal en
la ejecución de pruebas y la colección/importación de pytest; no conviene
paralelizar las pruebas que comparten estado ni reducir esperas que validan
recovery real. Aunque el §38 había dejado anotada la eliminación del escaneo
duplicado, el estado de trabajo volvía a generar el inventario dos veces: cada
escaneo recorría unos 950.000 nodos AST con `ast.walk` y resolvía rutas
repetidamente.

Se dejó una sola generación de inventario real y el determinismo se comprobó
dos veces sobre un fixture pequeño. También se sustituyó el recorrido por una
pila explícita, se normalizan rutas sin consultar el sistema de archivos y solo
se resuelven los casos con symlinks. Se añadió una regresión para evitar
asignar un paquete a rutas que escapan del source root. El inventario conserva
842 archivos, 104 rutas, los mismos paquetes, entry points y superficies
inspeccionadas. Las diferencias JSON quedan limitadas al AST y a los
contadores de marcadores del fichero de test que cambió; el inventario de
producción y las rutas permanecen iguales. En esta máquina, el caso de escaneo
tardó 10,83 s frente a los 27,92 s del recibo previo; el módulo completo pasó
4/4 en 13,64 s. No es un benchmark aislado y no afirma una mejora de la suite
completa.

Ruff format/lint, tests de inventario y `git diff --check` pasaron. Se añadió
una referencia breve a `docs/testing/TESTING_FAST_TO_FULL.md` que explica qué
prueba cada lane y qué evidencia debe inspeccionarse; la cobertura de release
sigue requiriendo Python/PostgreSQL completo, Docker, Helm, browser/API live,
seguridad y revisión visual sobre un mismo candidato limpio. Estado release:
**NO-GO, 0/13 familias cualificadas**.

## 67. Reconciliación de skips de colección en timings — 3/11/2026

La auditoría de recibos encontró que `pytest-postgres.xml` y la salida terminal
registraban **4.467 passed + 26 skipped = 4.493 casos**, pero el timing JSON v3
solo contaba 4.491: pytest representa dos módulos omitidos durante la colección
como casos JUnit, aunque no llegan al hook de ejecución de tests. Por eso el
conteo `tests` del recibo v3 no incluía esos skips.

El reporter ahora emite esquema v4 con `collection_skips` (node ID del módulo y
razón normalizada, sin rutas absolutas), además de separar tests seleccionados
de omisiones en colección; se conservan los recibos v3 en el selector lento. La
regresión crea un skip dentro de un test y un skip a nivel de módulo, genera
JUnit y exige que totales y skips de v4 coincidan con ese XML. `tests/test_pytest_timing_report.py`
y `tests/test_pytest_slowest_selection.py` pasaron **14/14 en 2,65 s**; Ruff
format/lint pasaron en los cuatro ficheros afectados. El conteo histórico de la
suite completa se corrige a partir del JUnit conservado; no se repitieron sus
nueve minutos con el reporter v4. Los skips externos y de plataforma siguen
siendo gaps explícitos, no éxitos.

Se sincronizaron la guía de tests, el checklist de release y el ledger de
capability con la discrepancia y el resultado actual. Este arreglo mejora la
fiabilidad del reporte, pero no cierra el gate candidate-bound ni las 13
familias; estado **NO-GO, 0/13**.

## 68. Qualification real del binding Trino — 3/11/2026

El inventario de skips del full suite dejó dos pruebas de Trino sin ejecutar
porque no estaba configurado `RONIN_TRINO_TEST_URL`. Había una imagen local
Trino 484 con digest conocido, por lo que se añadieron el runner reproducible
`tools/run_trino_qualification.ps1` y contratos que comprueban digest, binding
loopback, versión, manifest exacto, cero skips/fallos y limpieza del servicio.
El runner guarda JUnit, timing v4, log del servicio, transcript y un recibo con
SHA, estado dirty/clean, digest, duración y cleanup.

La ejecución contra el servidor real pasó **2/2**: prepared scalar bindings
(string con comilla, BIGINT máximo, boolean, double y NULL) y límites de bytes
aceptando exactamente el tamaño esperado y rechazando un byte menos. Trino
484 arrancó ACTIVE y el contenedor se eliminó correctamente. La medición más
reciente separa el arranque (13,85 s), pytest (5,69 s) y limpieza (1,38 s):
22,73 s en total. La selección exacta se ejecutó en 5,69 s; los contratos del
runner pasan **3/3**. Recibo más reciente:
`%TEMP%\ronin-trino-qualification-20261103-e7a48077`.

Esto cierra esos dos skips para este diagnóstico local; no es certificación de
un despliegue de Trino externo ni cierra P3, que aún requiere el viaje integrado
de tabla/SQL/resultado/persistencia y evidencia en un mismo candidato limpio.
El proveedor opcional SDP JSON-stdio no está configurado; su contrato sí tiene
una prueba que inicia un proceso real y valida stdin/stdout JSON. El CLI SDP
instalado no anuncia una interfaz `compile --json-stdio`, por lo que no se
afirma interoperabilidad con ese proveedor concreto. La documentación de Data
Engineering lo declara opcional y el gate del CLI oficial es independiente.
La validación oficial del CLI de SDP y Spark Connect, además de las demás
pruebas indicadas arriba, pasaron en carriles aislados con este árbol dirty.
OTLP ya pasó en un Collector real y los ocho casos
POSIX-skipped pasaron en un contenedor Linux; ambas son evidencias
dirty-worktree. Release **NO-GO, 0/13**.

## 69. Qualification real de OTLP — 3/11/2026

Se añadió `tools/run_otlp_qualification.ps1`, con imagen inmutable,
publicación solo en loopback, configuración efímera del Collector, manifest
exacto, JUnit, timing v4 por fase y limpieza verificada. El test envió traces,
metrics y logs a un Collector real `otel/opentelemetry-collector-contrib`
(`sha256:45392d534c1edcc809c2d112394029246bc679d2ae5ea7081414a1fc74f2c621`)
y comprobó los tres lotes aceptados y exportados: **1/1**, sin skips ni
fallos. Tiempo total 5,03 s: startup 0,02 s, pytest 1,97 s, cleanup 1,17 s.
Contratos del runner: **3/3**. Recibo:
`%TEMP%\ronin-otlp-qualification-20261103-f933985d`.

Esto cierra el skip de OTLP en este diagnóstico, no el journey P12 de alertas,
FinOps y logs correlacionados ni la evidencia del candidato limpio. El runner
no requiere backend externo ni credenciales; usa un Collector efímero con
exporter `debug` y elimina el contenedor al terminar.

## 70. Qualification Linux de casos omitidos en Windows — 3/11/2026

Se añadió `tools/run_posix_contract_qualification.ps1` para ejecutar los ocho
node IDs que el full suite de Windows omitió por diferencias de plataforma:
modo ejecutable Git, creación/lectura de symlinks, permisos POSIX y reap de
proceso hijo. Usa un contenedor Debian 13/Python 3.11.18 fijado por digest,
instala Git y los plugins de pytest fijados por versión en un filesystem
efímero y monta el checkout **read-only**. Emite JUnit, timing v4, versión de
Git, transcript y recibo con commit/modo/resultado/cleanup.

Resultado Linux: **8/8**, cero skips/fallos; pytest 11,81 s y total 22,22 s
incluyendo setup efímero. Se reutilizó la imagen Ronin qualification fijada a
`sha256:fb9029dad0d8d5aade4bb5809c8a4e027f416a158fedc633c65667d0b21b01b8`
(Git 2.54.0); solo se añadió un harness pytest mínimo con hashes de paquetes
y dependencias constrained por `requirements-test.lock`. Recibo
`%TEMP%\ronin-posix-qualification-20261103-0841ce5d`.
Esto valida los ocho contratos POSIX en ese entorno Linux, pero no equivale a
una matriz multi-distribución/Python aprobada ni a evidencia del candidato
limpio. El checkout se mantuvo read-only; el directorio del recibo vive fuera
del repo.

## 71. Qualification con el CLI oficial de SDP Studio — 3/11/2026

El runner `tools/run_sdp_cli_qualification.ps1` crea un proyecto `retail-etl`
de ejemplo bajo `SDPSTUDIO_DATA_ROOT` aislado y pasa su ID al test exacto de
validación del CLI oficial. Se separan stdout y stderr para no confundir los
mensajes `INFO` con el ID del proyecto; el runner retiene versión del CLI,
JUnit, timing v4, transcripción y recibo. No usa ni migra el almacén SDP del
usuario.

El test real pasó **1/1**, sin skip/fallo; pytest tardó 10,90 s y el carril
26,71 s incluyendo creación y limpieza del proyecto. Recibo:
`%TEMP%\ronin-sdp-cli-qualification-20261103-60a9aa44`. Esto cierra solo el
CLI oficial en este árbol dirty; no certifica el producto SDP completo ni el
candidato limpio. El modo opcional JSON-stdio no tiene proveedor externo
configurado y la CLI instalada no anuncia esa interfaz. La frontera del
adaptador sí tiene un subprocess test real: la selección
`tests/test_data_engineering_sdp_adapter.py tests/e2e/test_data_engineering_external.py -k sdp`
pasó **4/4**, con dos skips explicados (`SDP_PROJECT_ID` y
`SDP_STUDIO_COMMAND` ausentes) en 0,77 s. Por contrato documental, esos skips
no bloquean el gate del CLI oficial.

## 72. Preparación cacheable del cliente Spark Connect — 3/11/2026

El primer diseño instalaba en cada invocación el cliente y todas sus
dependencias en una carpeta nueva de evidencia, deshabilitando la caché de pip.
Eso repetía build, descarga y extracción antes de empezar el test. Se cambió a
un lock hash-fijado (`tools/spark-connect-client.lock`) y una caché local
dedicada bajo `%LOCALAPPDATA%`, identificada por el SHA-256 del lock. La
instalación exige hashes y separa la caché de Ronin y de las evidencias; la
primera invocación aprovisiona y las siguientes reutilizan el mismo conjunto.
Un lock exclusivo evita dos instalaciones simultáneas y cada recibo conserva
el informe de instalación, la identidad del lock y el resultado de JUnit.

La primera instalación quedó lenta (229,08 s de preparación/ejecución) y la
primera prueba falló por una dependencia ausente: `pytz`, requerida por pandas.
El contenedor se limpió y ese resultado no se contó como pase. Se añadió `pytz`
al lock y se repitió con la caché local lista: Spark Connect real pasó **1/1**,
sin skips/fallos; pytest 21,70 s, servicio 0,04 s, cleanup 1,97 s y total
27,91 s. La caché se validó por SHA-256 del lock. Recibo:
`%TEMP%\ronin-spark-connect-qualification-20261103-ccbb305d`.

Esto califica el smoke del proveedor Spark en este árbol dirty. El provider
específico SDP JSON-stdio permanece opcional y sin una implementación externa
compatible configurada; se prueba la frontera del adapter localmente. No cierra
otra familia de release. Release **NO-GO, 0/13**.

## 73. Streaming run-once y loop de prueba selectivo — 3/11/2026

Se cerró el camino que faltaba entre la definición persistida y el micro-lote
real: API autenticada con permiso `workspace.write`, límite y timeout acotados,
Kafka con offsets manuales, commit idempotente al sink local y CAS del
checkpoint. La UI muestra el recibo del micro-lote y permite volver a consultar
el lag. No se marca P11 como aceptado: siguen pendientes recuperación,
backpressure, Bundle/reset-resume y el journey completo candidate-bound.

El loop rápido exacto de runtime, salud, API, autorización, validación,
redacción de errores y OpenAPI pasó **9/9 en 5,28 s**, sin skips. El live
Playwright con Ronin real y Redpanda real pasó **1/1**, validó lag inicial,
consumo de un evento, checkpoint persistido, lag cero y un HTTP 400 esperado
que la UI presenta como error de ejecución. Hubo 4 peticiones reales, las 4
correlacionadas con logs (3 `OK`, 1 `WARN`), cero 5xx/errores de red y limpieza
completa. Recibo:
`%TEMP%\ronin-live-streaming-final-verified-20261103`.

El modo filtrado del runner ahora evita PostgreSQL y los fixtures de
graph/catalog/workflow no relacionados: el mismo smoke pasó de **79,08 s a
36,96 s** (≈53 % menos), con cachés de dependencias y navegador reutilizadas.
El recibo identifica PostgreSQL como no iniciado y Kafka como activo. Un
primer intento de la ruta negativa llegó al 400 correcto pero encontró una
lista incompleta de WARN esperados en la aserción global; esa aserción se
ajustó al endpoint/código `invalid_request` exactos y la reejecución pasó.
Diagnóstico de árbol sucio: no reemplaza la suite live completa, Docker ni la
aceptación P11; Release **NO-GO, 0/13**.

## 74. Límites de memoria y ciclo reset/resume live de Streaming — 3/11/2026

La revisión del consumidor Kafka encontró que el límite del API restringía el
número de mensajes, pero no sus bytes ni el buffering previo al parseo. El
consumidor local ahora aplica 1 MiB por registro JSON y 8 MiB por micro-lote,
limita `fetch.max.bytes`, `max.partition.fetch.bytes`,
`receive.message.max.bytes` y la cola local de librdkafka, y rechaza opciones
de conexión que intenten ampliar esos límites. El mensaje sobredimensionado,
el lote que excede el presupuesto y el poison message fallan antes de escribir
el sink o avanzar el checkpoint. El error expuesto por API permanece
redactado; el poison record deja el stream detenido en ese offset para evitar
pérdida silenciosa. Los límites por bytes están cubiertos por tests unitarios;
el caso de poison message también se verificó después contra Redpanda real.
Queda pendiente inducir el límite de bytes y la presión de cola contra un
broker real.

La primera qualification real de esta modificación devolvió HTTP 503: se había
configurado `receive.message.max.bytes` igual que `fetch.max.bytes`, relación
inválida para librdkafka. Se ajustó para dejar los 512 bytes adicionales
requeridos. La creación directa de `confluent_kafka.Consumer` aceptó la
configuración final y el smoke Redpanda confirmó que el runtime consume y
confirma un evento.

La UI live también se amplió para guardar la definición con `reset`, consumir
el evento, guardar la misma definición con `resume` y comprobar que la
repetición queda `idle`. El journey contra Ronin y Redpanda pasó **1/1**, con
**10 llamadas API reales** (9 `OK`, 1 `WARN`/400 esperado), todas
correlacionadas con logs; cero 5xx/errores de red, duración total **43,96 s**,
caso Playwright **13,6 s** y limpieza de contenedor/red completada. Se añadió
además una prueba estática UI→API simulada para el ciclo editar/guardar.

Después se añadió un topic real con JSON inválido. Dos ejecuciones UI/API
devolvieron HTTP **422 `stream_input_rejected`**, con el mensaje de error
redactado; entre ambos reintentos el lag siguió en uno, confirmando que el
offset poison no se avanzó. El fixture válido se amplió a cinco eventos y la
UI procesó tres lotes **2, 2, 1**, con lag **5 → 3 → 1 → 0**, antes de recibir
`idle` al repetir. La qualification pasó **1/1**, con 20 llamadas reales (17
`OK`, 3 `WARN` esperados por límite/poison), todas correlacionadas con logs;
cero 5xx/errores de red, **88,16 s** total y 19,8 s Playwright. PostgreSQL no
se arrancó; el runner limpió Redpanda al terminar. Recibo más reciente:
`%TEMP%\ronin-live-streaming-batch-bounds-final-20261103`.

El conjunto Python enfocado (Kafka source, runtime, health, Bundle, HTTP API y
OpenAPI) pasó **37/37**, con 50 deselected, cero fallos en **14,23 s**. Ruff
check/format y `node --check` pasaron. El comando aparece en
`docs/testing/TESTING_FAST_TO_FULL.md`; el recibo live es
`%TEMP%\ronin-live-streaming-batch-bounds-final-20261103`.

P11 sigue **OPEN**: faltan casos contra broker real para límite por bytes
(los tests actuales verifican esos límites localmente), recuperación de fallos,
evidencia operativa más amplia y qualification ligada a un candidato limpio.
La ruta de Bundle con reset/resume ya se completó en el recorrido siguiente
(§75). Ninguno de estos resultados cierra las otras doce familias ni los gates
de artefacto, licencias, revisión visual manual o decisión de producto.
Release continúa **NO-GO, 0/13**.

## 75. Bundle de Streaming en API y Studio — 3/11/2026

Se completó la integración del Bundle de Streams que existía solo a nivel de
servicio de dominio. La API autenticada permite exportar hasta 700 KiB,
previsualizar un archivo verificado y recibir sus streams/bindings, y después
importarlo con mappings explícitos, un reset/resume por stream y el SHA-256
aprobado durante la previsualización. El límite conserva el presupuesto global
de 1 MiB por petición JSON. La importación verifica el archivo y aplica de
forma atómica las definiciones y políticas; las respuestas no incluyen
checkpoints ni secretos. El Studio permite descargar, seleccionar archivo,
verificar y revisar bindings/offsets antes de habilitar el botón de importación.

La primera prueba live detectó que el planificador comparaba solo el segmento
posterior a la última `/`, rechazando IDs jerárquicos válidos como
`events/main`. La validación ahora compara el ID completo y una regresión cubre
ese formato. También se mantuvo el límite arquitectónico: el servicio Bundle
vive en `studio_streaming`, mientras `studio_execution.bundle_streaming`
conserva exports compatibles.

Evidencia enfocada: **11/11** pruebas de Python/API/OpenAPI/arquitectura
pasaron en 14,48 s en la última selección; el módulo Bundle más API pasó
**9/9** en 8,53 s tras añadir la regresión de ID jerárquico. Chromium pasó
**2/2** casos de Streaming Studio en 16,3 s. Redpanda y Ronin reales pasaron
**1/1** caso live; export→plan→import reset→consumo→import resume preservó el
lag en 3, luego el journey existente procesó 2/2/1, llegó a lag 0 y validó
idle/poison. Las 27 llamadas se correlacionaron con logs (24 `OK`, 3 `WARN`
esperados), con cero errores de servidor/red y limpieza correcta. El recibo
live está en `%TEMP%\ronin-live-streaming-bundle-retry-20261103-201633`.

P11 continúa OPEN por overload de bytes y recuperación medidos contra broker
real, evidence operativa más amplia y qualification de candidato limpio.
Las pruebas enfocadas no califican P11 entero ni la release: **NO-GO, 0/13**.

## 76. Rechazo real de record oversized y recuperación de Streaming — 3/11/2026

El test de Streaming ahora configura un tópico Redpanda con límite de broker
de 2 MiB y produce un objeto JSON válido mayor que el límite de Ronin de 1 MiB.
La UI ejecuta el batch contra Ronin real: recibe `422 stream_input_rejected`,
el error visible queda redactado, el contenido no aparece en la respuesta y
el lag sigue en 1, demostrando que el checkpoint no avanzó. La recuperación
requiere una acción explícita del operador: cambiar el stream a un tópico sano,
guardar con `reset`, consumir el mensaje válido y comprobar lag 0.

La primera ejecución encontró que `confluent-kafka` exige un diccionario de
configuración incluso para tópicos sin overrides; se corrigió el fixture a
`{}`. Después la primera aserción mostró que la API oculta deliberadamente el
detalle interno de 1 MiB; se cambió la expectativa a la respuesta genérica y
se conservó la comprobación independiente de ausencia de fuga y lag estable.
La repetición contra Ronin, Chromium y Redpanda pasó **1/1**, con **36/36**
llamadas HTTP correlacionadas con logs estructurados (32 `OK`, 4 `WARN`
esperados), cero errores de red/servidor, limpieza correcta y 60,07 s total.
PostgreSQL no se inició en este carril de Kafka solamente. Evidencia:
`%TEMP%\ronin-live-streaming-overload-final-7b49698233e9452c8954a8c5b1cc1ed8`.

Esto cierra el caso live de sobrecarga por record y recuperación explícita,
pero no demuestra todas las rutas de backpressure, particiones, caídas y
operación continua. P11 sigue parcial y requiere qualification de familia en
candidato limpio. Release **NO-GO, 0/13**.

## 77. Semantic Studio: export, revisión e import de Bundles — 3/11/2026

Se cerró el recorrido que faltaba entre los Bundles semánticos de dominio y el
Studio/API: exportación autenticada, preview que valida el archivo, importación
por digest revisado, límites de 700 KiB, permisos `project.read` para export/plan
y `project.write` para importar, y evento de auditoría antes de mutar. La UI
verifica SHA-256 y tamaño en exportación y contra el plan del servidor; muestra
los IDs de modelos/dashboards y desactiva el import al cambiar archivo o scope.
Tras importar actualiza ambas listas y diferencia un import exitoso de un error
de refresco.

Se añadió el contrato OpenAPI y el inventario de rutas, más tests contra HTTP
real y SQLite para round-trip, scope de proyecto con slash codificado, replay
exacto, digest cambiado, conflicto 409 sin import parcial y autorización. Dos
journeys Playwright cubren descarga, integridad, preview, cambios de archivo y
destino, límite de tamaño y refresco visible. Evidencia focal: **2 tests HTTP y
2 Playwright en Chromium**, más contratos OpenAPI, Ruff y checks sintácticos;
no se ejecutó la suite global ni una qualification de candidato limpio.

Esta mejora amplía la capacidad entregada, no cierra P10: siguen pendientes la
calificación del alcance por workspace de objetos semánticos almacenados, el
presupuesto/cancelación de ejecución de dashboards, import PostgreSQL y la
qualification integral del API/Studio en candidato exact-head. La release
permanece **NO-GO, 0/13**.

## 78. Aislamiento workspace/proyecto de Semantic Studio — 3/11/2026

La ficha RG-SEM-TENANT-SCOPE-001 encontró que el control plane comprobaba los
permisos con `(workspace_id, project_id)`, pero enviaba al store semántico solo
`project_id`. Se corrigió el key persistido para todas las rutas de modelos,
dashboards, consultas, ejecución y Bundles: incluye ambos identificadores con
un prefijo de longitud no ambiguo. El ID del proyecto que se valida y muestra
en la API continúa siendo el original; el namespace compuesto solo se usa en
persistencia y runtime.

La prueba HTTP real usa dos workspaces que contienen el mismo ID de proyecto y
comprueba modelos, dashboards y target de importación aislados, además de
lectura/escritura autorizada. El módulo `test_workspace_project_http_api.py`
pasó **54/54** después del cambio de aislamiento y de las pruebas de dashboard.
Un journey Playwright detectó además que el ejemplo de dashboard inicial no
cumplía el schema y que el submitter no llegaba a `FormData`; se corrigieron el
ejemplo y la selección entre listar/guardar/ejecutar. Playwright cubrió Bundle
export/revisión/import y guardado del ejemplo mediante la ruta PUT del Studio.

Las filas SQLite históricas de semantic usan únicamente project_id y no
contienen workspace de origen. El cambio no las reasigna silenciosamente: la
utilidad `tools/migrate_semantic_project_scope.py` permite al operador elegir
workspace/proyecto de destino explícitamente. Su operación verifica conflictos
de modelos y dashboards, mueve ambas familias en una transacción y conserva
todo el origen ante conflicto; debe ejecutarse con backup previo y únicamente
después de determinar el workspace correcto a partir del inventario del
operador. La prueba de store cubre migración, replay y rollback por conflicto.

La pasada Playwright del ejemplo pasó **3/3** después de corregir el bug de
submitter. P10 continúa parcial: la ejecución aún necesita definir/verificar
presupuestos de fan-out y cancelación de dashboards, import PostgreSQL,
qualification del flujo completo contra un candidato limpio y decisión
operativa sobre migrar cada base SQLite existente. Por tanto esta corrección no
cierra el riesgo de migración ni cambia la release: **NO-GO, 0/13**.

## 79. Qualification live de Semantic Bundle — 3/11/2026

Se amplió `product-live.spec.mjs` y el fixture aislado para que Semantic Studio
no se verifique solo con API simulada: el seed crea un modelo y dashboard bajo
el namespace real `(workspace, examples/demo)`. Chromium, contra Ronin en vivo,
lista el modelo, descarga el Bundle, revisa el plan del servidor, importa el
archivo, comprueba el digest y vuelve a leer modelos y dashboards persistidos.
El recibo `%TEMP%\ronin-live-semantic-bundle-retry-20261103` pasó **1/1** en
11,9 s; las seis llamadas (list, export, plan, import, refresh models, refresh
dashboards) fueron HTTP 200/`OK`, todas correlacionadas con logs, cero
errores/red o huecos de autorización, `real API ready=True`; PostgreSQL y
Redpanda se limpiaron correctamente. Al ser `-TestGrep semantic` en worktree
sucio, esto es diagnóstico real, no evidencia de candidato limpio.

La primera ejecución agotó 60 s por un matcher exacto que no reconocía la ruta
URL codificada de `examples/demo`, aunque el API había respondido 200. El
recorrido se corrigió para reconocer el sufijo de ruta estable y sus esperas
ahora fallan en 10 s. La repetición pasó. La pasada de tests focales incluye
84/84 casos semánticos/API/OpenAPI en 39,81 s, y las pruebas Browser mock 3/3;
Ruff y mypy focales pasaron. La release sigue **NO-GO, 0/13**: P10 aún debe
cerrar presupuesto/cancelación de dashboards, import PostgreSQL, migración de
datos existentes, journeys completos y qualification sobre un candidato limpio.

## 80. SQL y Semantic Studio comparten Parquet aislado por proyecto — 3/11/2026

La prueba live del §79 solo probaba la portabilidad semántica. Al intentar
ejecutar el dashboard, se descubrió que `local-composed` construía dos motores
DuckDB sin relaciones registradas: la interfaz podía guardar/importar modelos,
pero una consulta contra ellos fallaba al no encontrar la tabla. Se corrigió
la composición para que SQL y Semantic Studio compartan el mismo motor
proyecto-scoped. El control plane envía el namespace completo de workspace y
proyecto a ambos endpoints; el motor carga y refresca Parquet por namespace,
rechaza symlinks y escapes de ruta, borra vistas de archivos retirados y
descarta la conexión si falla la carga.

El layout es configurable por `RONIN_SQL_PARQUET_ROOT`; por defecto es
`sql-parquet` junto al archivo `RONIN_DB`. Cada carpeta usa el scope
workspace/proyecto codificado y el stem del `.parquet` determina el nombre de
relación. Se añadió el contrato operativo en
`docs/operations/LOCAL_SQL_PARQUET_LAYOUT.md`.

El journey live ya incluye listar modelo, exportar/revisar/importar Bundle y
ejecutar `live_overview` en Chromium contra el endpoint real. El fixture crea
cinco filas Parquet y la UI muestra el resultado `[[5]]`. La repetición pasó
**1/1** en 34,73 s, con **7/7** llamadas API HTTP 200/OK correlacionadas a logs,
cero WARN/ERROR/CRITICAL, y limpieza correcta; evidencia
`%TEMP%\ronin-live-semantic-dashboard-retry-20261103`. PostgreSQL y Kafka no se
iniciaron porque no forman parte de este caso. Además pasaron **59/59** pruebas
entre SQL/DuckDB, runtimes semánticos, OpenAPI, SQL local-composed y el endpoint
HTTP de dashboard; la regresión Chromium estática de Semantic Studio pasó
**3/3**. Ruff/mypy se ejecutaron en los módulos tocados; el chequeo mypy inicial
detectó una duplicación de nombres y una incompatibilidad preexistentes en el
área, corregidas con nombres locales distintos y el cast de adaptador que el
contrato del servidor requiere. P10 sigue sin cerrar import PostgreSQL,
migración operativa de datos existentes, fallos visuales/operacionales de la
familia completa y evidencia de candidato limpio. Release **NO-GO, 0/13**.

## 81. Límites globales para ejecutar Semantic dashboards — 3/11/2026

Se cerró el hallazgo de fan-out no acotado en el runtime. Ambos caminos —SQL
directo y SQL scoped por proyecto— comparten la misma política versionada en
`studio_semantic.runtime`: máximo 12 tiles; suma de límites de filas solicitadas
no superior a 100.000; presupuesto SQL agregado de 15.000 ms; respuesta de
8 MiB, con 1 MiB reservado a metadatos y wrappers. Los tiles se ejecutan en
serie. Antes de consultar se comprueban fan-out, presupuesto de filas, todas
las referencias a modelos y la compilación de cada query. En ejecución, cada
tile recibe el tiempo y presupuesto de bytes que quedan; el primer error o
timeout aborta el dashboard, no inicia consultas posteriores y no entrega
resultados parciales. El adaptador comprueba además el tamaño exacto del JSON
final. OpenAPI documenta límites y HTTP 408/413.

Verificación focal: **33/33** pruebas de runtime y OpenAPI; incluyen los dos
runtimes con SQL real DuckDB, fixture Parquet, respuestas por encima de los
límites, plazo agotado y validación de todas las tiles antes de iniciar la
primera query. El módulo de API workspace/proyecto pasó completo **55/55**;
incluye una petición real al control plane con DuckDB/Parquet y confirma que 13
tiles devuelven HTTP 400 sin ejecutar otra query. El conjunto combinado pasó
**88/88**. Ruff y mypy focales pasaron. P10 sigue abierto por import PostgreSQL,
migración operativa de datos existentes y qualification de familia en candidato
limpio; release **NO-GO, 0/13**.

## 82. Faster, clearer test feedback — 3/11/2026

The two real SQLite/artifact worker-contention tests were waiting on the
production 10-second heartbeat interval before releasing their deliberately
blocked storage calls. The shared fixture still asserts the production
30-second lease and 10-second heartbeat defaults; only those two stress
scenarios now use a two-second lease and 100-ms heartbeat. They continue to
observe the persisted heartbeat and lease expiry directly in SQLite while
storage is blocked, and assert successful completion/reclaim. Focused
verification passed **2/2**; combined call time measured **2.96 s**, against
**32.42 s** for those cases in the previous full-suite receipt. Timings vary by
host and load, so this is a local diagnostic comparison, not a whole-suite
speedup claim. Ruff and formatting passed on the changed test module.

A new `tools.test_run_summary` command renders pytest and runner receipts as a
compact account of source/cleanliness, selection, services, coverage, outcomes,
slowest case, phase times, real API/log correlation, route audit and cleanup.
It returns failure when evidence reports test failure or failed cleanup. Its
regressions plus the timing-report and slowest-selection tests passed **19/19**.
The helper can also reconcile pytest timing totals against JUnit and exits
nonzero when counts differ. The helper makes evidence easier to inspect but
does not expand test coverage.

The available full-suite timing JSON is schema v3 and predates collection-skip
capture; it disagrees with its JUnit ledger (4,491 pytest items/24 skips versus
4,493 JUnit cases/26 skips). The new summary detects this mismatch and exits
nonzero. Generate schema-v4 timings and compare fresh receipts from the same
qualification run before using counts for a candidate decision.
Current release remains **NO-GO, 0/13**; this diagnostic optimization does
not close any release gate.

## 83. Avoid redundant source-path resolution in the test inventory — 3/11/2026

`inspect_python_file` previously tried to resolve every file under `tests/`
against the separate `python/` source root to decide whether it belonged to a
product package. Those paths are known from the inventory walk to be external
test files, so the inspector now skips only that redundant package lookup for
such files. Product-source paths and paths not identified as external tests
retain the existing traversal/escape and symlink checks. A regression makes
the skipped lookup observable. The repository-scan case measured **46.97 s before and
10.10 s after** on this Windows host; the updated inventory module passed
**5/5 in 13.29 s**. This is a separate, host/load-sensitive rerun from the
earlier marker-lowercase optimization and not a full-suite speedup claim.

The combined selected regression set (run-summary/timing, worker contention,
and plugin inventory) passed **26/26 in 26.74 s**. Ruff and formatting passed
on all five changed Python files; mypy passed on both changed tools. JUnit
reconciliation correctly rejects the historical schema-v3 full-suite receipt
because it records 4,491 cases/24 skips while the paired JUnit has 4,493/26.
The complete Python/PostgreSQL suite has not been rerun after these
test-infrastructure changes. Release remains **NO-GO, 0/13** pending
candidate-bound gates and human decisions.

## 84. Recortar el arranque de la ruta live de ML y separar el diagnóstico — 3/11/2026

La ruta de diagnóstico de Machine Learning Studio se puede lanzar con
`-TestGrep mlstudio`. El runner usa la API real de Ronin sobre SQLite aislado y
no inicia PostgreSQL ni Kafka; esa restricción queda registrada en el recibo.
Tras preparar las dependencias cacheadas, compila solamente el árbol propio
`python/` y los dos seeders live mediante `compileall`; no compila ni modifica
las dependencias científicas de terceros.

La ejecución con este precompile pasó **1/1** en **19.54 s**: preparación de
dependencias 1.78 s, compilación 0.43 s, seed/servidor 3.89 s y journey
Playwright/API 13.05 s. La ruta generó 36 eventos API, todos correlacionados
con logs HTTP (**35 OK, 1 WARN esperado**), y cero ERROR/CRITICAL. El primer
import del estimador scikit-learn tomó **3.72 s**; preparación de búsqueda
28.71 ms y búsqueda total 3.90 s. No es una cualificación de ML completa ni
de PostgreSQL/Kafka, y el worktree estaba sucio: es diagnóstico reproducible
con recibo, fuera de candidato de release.

Esta separación hace visible el coste por fase y evita levantar servicios
ajenos al journey. Mantener el import de ML por debajo del objetivo UX sigue
siendo trabajo abierto; no se debe ocultar dentro del tiempo de setup. Release
permanece **NO-GO, 0/13**.

## 85. Resumen de pruebas que explicita el alcance y valida recibos live — 3/11/2026

`tools.test_run_summary` ahora lista las cinco pruebas más lentas, motivos de
skips de colección e IDs de fallos. Para recibos live devuelve error si el
recuento de casos del navegador no suma o si los eventos API no cuadran con los
logs correlacionados. La prueba focal del resumen pasó **6/6** en **0.55 s**
de sesión pytest (runner local-only, sin PostgreSQL ni cobertura).

Al resumir el recibo Python histórico de 3/11, encontró el desfase real de
4.491 casos/24 skips en timing JSON contra 4.493/26 en JUnit y devolvió error.
La inspección confirmó dos skips de módulos Docker opt-in que el plugin de ese
recibo no capturó. Un probe de dos módulos validó que el hook actual registra
ambos skips correctamente. La suite completa se repitió: **4.558/4.558** casos
reconciliados, 4.531 passed, 26 skipped y 1 failed en **508.75 s** total; la
limpieza de PostgreSQL pasó. El resumen mostró las dos omisiones de colección
con sus razones. El fallo único fue el gate arquitectónico: el control plane
importa `studio_semantic` para servir sus APIs, pero la matriz permitía
`studio_ml` y no declaraba esta dependencia. Se añadió la relación explícita
`studio_server → studio_semantic`; los tests de arquitectura y del resumen
pasaron **25/25 en 2.94 s** después del cambio. Como la corrección es posterior
a la suite completa, esa corrida conserva el fallo original y la pasada focal
verifica la reparación; el próximo gate completo debe repetirla. Los 26 skips
son brechas de plataforma/proveedor/opt-in, no se cuentan como casos probados.
La salida corta mejora la lectura, pero no amplía cobertura. Las rutas live y
pruebas de UI mantienen su alcance exacto y no pueden presentarse como suite
completa. La release permanece **NO-GO, 0/13**.

## 86. Revisión del 4 de noviembre — release vencida y siguiente gate

La fecha objetivo del 3 de noviembre a las 09:00 ya pasó sin candidato GO.
Mantener la release retrasada es la decisión correcta: en esa auditoría el worktree estaba sucio. La rama quedó limpia en `667bd4a4`, pero ninguna de las 13 familias está cualificada sobre un SHA común y hay
decisiones humanas y revisión visual pendientes.

No paralelicé la suite Python/PostgreSQL: sus tests comparten la base
PostgreSQL y no hay una prueba de aislamiento por worker que mantenga idéntica
selección, cobertura y resultados. El runner guarda la suite completa como una
sola corrida, y la fase de edición queda en pruebas focales (cientos de
milisegundos/segundos) más lanes live filtrados. En esta revisión, el test
focal de arquitectura y resumen pasó **25/25 en 2.96 s**; el full suite
pre-fix tardó 508.75 s y su timing/JUnit quedó reconciliado. La suite completa
debe repetirse una vez más al congelar el siguiente candidato, después de todos
los cambios restantes; no repetirla entre cada corrección focal.

## 87. Cualificación reproducible del wheel y sdist — 4/11/2026

En el SHA limpio `667bd4a4060a7da58f751525a7db5efebc96e6a9` se construyeron dos
veces wheel y sdist con Python 3.13.15, `build==1.6.0`, `setuptools==84.2.1`,
el toolchain de qualification instalado con `--require-hashes` y
`SOURCE_DATE_EPOCH=1793763268`. Los dos wheels produjeron SHA-256
`d171e6f9a2c6695ab6e0c7ddc9e872b7973d2a770585f8fe18df6f299b4b01f7` y los
dos sdists normalizados produjeron `07bf0353b439c3c454c640f428c86c01bc8444e5127b312e938be56a9edba3d2`.

Se instalaron ambos formatos en entornos desechables con el lock de desarrollo
verificado por hash. Desde un directorio vacío, wheel y sdist devolvieron
`ronin --help` correctamente y el metadato informó `ronin-studio==0.0.0`. El
smoke de navegador contra cada artefacto cargó las 25 rutas y los tres coding
agent skills; cero fallos de ruta, peticiones, consola, CSP u overflow. El audit
axe/responsive del wheel cubrió las 25 rutas en 320, 768 y 1440 px: cero
violaciones críticas/serias y cero desbordamientos.

Recibos y logs: `%TEMP%\\ronin-artifact-667bd4a4060a-241f76c7`. Esta evidencia
cierra el diagnóstico de instalación y recursos incluidos, pero no habilita
publicación: el metadato sigue en `0.0.0`, la versión pública necesita decisión
explícita de producto y los gates quedan ligados a una build diagnóstica. El
gate Docker/PostgreSQL y las demás familias de release siguen pendientes; GO
no está autorizado y la recomendación continúa siendo retrasar.

## 88. Cierre de hallazgos de calidad local — 4/11/2026

El pase completo de gates estáticos detectó que dos pruebas estaban sin formato y
mypy 1.20.2 ya no acepta dos imports opcionales de Azure cuando el extra Azure no
está instalado. Se reformatearon los tests y se añadieron ignores de
`import-not-found` solo a esos imports, que permanecen protegidos por guards de
`ImportError` y mensajes explícitos de dependencia. Ruff format/check pasaron
sobre 928 archivos; mypy pasó sobre 442 módulos. El conector Azure pasó 13/13 y
los tests de OpenAPI/contrato del runner pasaron 15/15.

`capability-status`, consistencia de 196 operaciones, Studio surface, auditoría
web (60 archivos, 179 invocaciones, cero fallos), skills (3/3), negativos de
arquitectura, OpenAPI snapshot, 10 vectores/5 rechazos de JSON canónico y 2
fixtures del protocolo del runner pasaron. El Studio budget falló inicialmente
porque el ratchet no incluía el crecimiento funcional del commit `c4e3a780`, que
añadió 589 líneas a Semantic y Streaming Studio. Se actualizó el valor observado
de 1.943.665 a 1.970.850 bytes (+27.185; +1,40%); requests, módulos, CSS y HTML
no crecieron. La repetición del budget pasó y futuras subidas vuelven a requerir
un ratchet explícito.

La suite integral PostgreSQL y la qualification Docker siguen pendientes por la
disponibilidad del engine. Estos checks locales no sustituyen esos gates ni
cambian la recomendación **NO-GO**.

## 89. Corregir respuestas tardías de Synthetic Studio — 4/11/2026

La suite estática de UI del candidato `849529e5` pasó **106/106**, pero su
barrido de navegación registró una excepción que no hacía fallar el test:
Synthetic Studio intentaba escribir resultados tras haber cambiado de ruta. La
causa era una petición de catálogo pendiente durante el `hashchange`. Se añadieron
revisiones de render y catálogo para descartar respuestas obsoletas, guardas para
los resultados de generación/export/lineage y un test que libera deliberadamente
la respuesta después de navegar fuera de la ruta. El recorrido responsive completo
y la regresión de carrera pasaron **2/2**; los cinco tests focales de Synthetic,
incluidos generación, exportación y cancelación, pasaron **5/5**. El harness de
traversal ahora falla ante excepciones JavaScript no capturadas en vez de solo
imprimirlas.

El fix añade 1.712 bytes a la descarga web (0,09% sobre el ratchet anterior); no
añade requests, módulos, CSS ni HTML. Se actualizó el baseline a la medición real
del fix, y las regresiones futuras siguen rechazándose. La repetición completa de
107 casos, empaquetado y audit de accesibilidad del nuevo SHA quedan como los
siguientes recibos de candidato; no se debe usar el resultado de `849529e5` para
aprobarlos. El gate release sigue **NO-GO** por Docker/PostgreSQL, policy de
licencias y decisiones de versión/claims.

## 90. Iteración de seguridad de imagen — 10/11/2026

El candidato `f52af3104d1d3f77db84a59414ebdee3c413f557` actualiza el lock de
runtime para solicitar `krb5=1.22.3-r0` y `zlib=1.4-r0`, y vuelve a ejecutar la
cualificación en checkout limpio. Docker pasa **27/27** integraciones y la
aceptación estricta v0.1 pasa **15/15**, con imagen
`sha256:a1386eaf2fb1ca97c1c0901023f7e207dec4325b113c0878fb02b0111e1540c0`.

El escaneo exacto de Docker Scout sobre esa imagen baja de 24 a **23
vulnerabilidades**, elimina la crítica de zlib, pero conserva **9 HIGH, 8
MEDIUM y 6 UNSPECIFIED**: `krb5 1.22.2-r1`, `musl 1.2.6-r3` y `sqlite
3.53.4-r0`. SQLite mantiene `CVE-2026-119586` sin versión corregida
publicada. No se amplía el VEX ni se presenta este resultado como un cierre
de seguridad; siguen abiertas la remediación/aceptación formal, el SBOM de
contenedor, la procedencia, las revisiones humanas y las familias Public v1.
La decisión sigue **NO-GO, 0/13**.

## 91. Iteración de seguridad de dependencias transitivas — 10/11/2026

La revisión del escaneo mostró que `krb5=1.22.3-r0` no actualizaba su
biblioteca transitiva. El commit `69609ff` añade también
`krb5-libs=1.22.3-r0`. La imagen reconstruida
`sha256:828140139c707dc4b8dd1403aac6d68689098da9cd9c5b6a32c622b6011da36f`
contiene Kerberos 1.22.3-r0 y zlib 1.4-r0; Scout baja a **2 HIGH**.

Persisten solamente `musl 1.2.6-r3` (`CVE-2026-107891`, fix publicado
1.2.6-r6 aún no disponible en el repositorio Alpine configurado) y
`sqlite 3.53.4-r0` (`CVE-2026-119586`, sin fix publicado). No se amplía el
VEX para ocultar hallazgos. Falta repetir la cualificación Docker completa
para este último cambio, generar SBOM/provenance exactos y cerrar la
aceptación de seguridad; la decisión continúa **NO-GO, 0/13**.

## 92. Cierre técnico del escaneo de imagen — 10/11/2026

El commit `1cf4beafd2748c4e3219a40033e34b9117975da5` añade el repositorio
Alpine Edge de forma explícita y fija `musl=1.2.6-r6`, `musl-utils=1.2.6-r6`
y `sqlite-libs=3.54.1-r0`, además de los locks parcheados previos. El
candidato exacto producido por la cualificación,
`sha256:ff4e7c6a4207c3505d649a25851961a689482f68bbd6db1b6b4450d2e36aaedd`,
queda en **0 vulnerabilidades Scout**, **27/27** integraciones Docker y
**15/15** aceptación estricta v0.1.

Este resultado cierra el hallazgo técnico del escáner, pero no equivale aún a
GO: hay que revisar formalmente el uso de Alpine Edge, generar los recibos
exactos de SBOM/provenance y repetir Helm, live y artifacts sobre este SHA.
Las gates humanas, visuales, legales, de proveedores y las 13 familias
Public v1 siguen pendientes. Se mantiene **NO-GO** hasta completar esas
pruebas y aprobaciones.

## 93. Recibos completos del candidato final — 10/11/2026

Sobre el mismo SHA `1cf4beafd2748c4e3219a40033e34b9117975da5` y la imagen
`sha256:ff4e7c6a4207c3505d649a25851961a689482f68bbd6db1b6b4450d2e36aaedd`:

- Helm/kind pasó lint, frontera de Secret, render, carga de imagen,
  instalación, readiness, health, Studio/API, creación de job, restart,
  persistencia del job y cleanup.
- Live UI/API pasó **33/33**, con 25 rutas activas, 24 API-backed, 250 eventos
  correlacionados y cero errores de servidor/red.
- Artefactos instalables pasaron **90/90** pruebas de contrato e instalación.
- Se generaron y verificaron el SBOM interno, CycloneDX de release y
  provenance local; el escaneo Scout del TAR exacto reporta **0
  vulnerabilidades**.

Esto cierra los recibos técnicos locales del candidato, pero no convierte el
producto en GO automáticamente: siguen pendientes la revisión formal de la
política Alpine Edge, aprobación humana/legal de licencias y claims, revisión
visual, matriz de proveedores/OS/Python, rollback y las 13 familias de
capacidad Public v1. La recomendación permanece **NO-GO** hasta que esos gates
sean aceptados por sus responsables.

## 94. Reconciliación VEX y probe — 10/11/2026

La imagen probe también queda alineada con la base Python fijada y los
paquetes Alpine Edge parcheados (`musl`, `musl-utils` y `sqlite-libs`). El
VEX histórico de tres excepciones se reemplazó por un documento vacío para
no conservar afirmaciones de vulnerabilidad ya inexistentes. El verificador
ahora exige cero hallazgos crudos cuando el VEX no tiene statements y se
ejecutó contra la imagen exacta: **0 raw / 0 post-VEX**, PASS.

La regresión contractual Docker pasa **24/24**. Esto fortalece el cierre de
la cadena técnica, pero no cambia el estado de release: siguen pendientes
las gates humanas, legales, visuales, proveedor/OS/Python y las 13 familias
Public v1.

## 98. Cualificación Trino real — 10/11/2026

El proveedor Trino 484, fijado por digest
`sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f`,
se levantó en servicio aislado y la prueba real pasa **2/2**, sin skips ni
fallos. Recibo: `ronin-trino-bc0fc45-20261110`.

Esto cierra el carril Trino local; no certifica otros proveedores externos.
Spark Connect y SDP siguen requiriendo endpoints/comandos externos explícitos.
La decisión Public v1 continúa **NO-GO** por los gates humanos, legales,
rollback, proveedores pendientes y familias no cualificadas.

## 99. Cualificación Spark Connect real — 10/11/2026

Spark Connect 4.2.0 se levantó en servicio aislado de loopback y el cliente
real pasó **1/1** prueba, sin skips ni fallos. Recibo:
`ronin-spark-bc0fc45-20261110`.

Con Trino **2/2** y Spark Connect **1/1**, los carriles de proveedores locales
reproducibles quedan verdes. SDP continúa pendiente porque requiere un
comando/proyecto externo explícito; no se simula como provider certification.
La decisión Public v1 sigue **NO-GO** por legal/humano, rollback y familias
no cualificadas.

## 100. Gate SDP bloqueado por instalación externa — 10/11/2026

El wrapper local `sdpstudio.exe` existe, pero la ejecución del gate falla
antes de poder consultar la versión: `ModuleNotFoundError: No module named
'sdpstudio_cli'`. El recibo `ronin-sdp-856ff88-20261110` conserva el error y
la limpieza. No se declara certificación SDP; hace falta instalar/configurar
el CLI oficial y un proyecto/credencial externos. El resto de los carriles
Trino y Spark Connect sí tiene pruebas reales verdes. Public v1 continúa
**NO-GO**.

## 95. Repetición completa Python/PostgreSQL en candidato limpio — 10/11/2026

La suite completa ejecutada en checkout limpio `d01df297426deb623aee38ddf73bb6e980b09d13`
recoge **4588 casos**, con **4563 passed, 27 skipped y 0 failed** en
883,41 segundos. PostgreSQL 16.4 se levantó en un servicio aislado y la
limpieza terminó correctamente. Los skips están explicitados por Docker
opt-in, proveedores externos no configurados, symlinks no disponibles en
Windows y capacidades POSIX; los journeys Docker, Helm y live tienen recibos
separados y verdes.

La divergencia documental encontrada durante esta corrida (JSON, ledger
Markdown y capability matrix con distintos SHAs observados) fue corregida y
los tests de consistencia pasan **6/6**. La decisión global continúa **NO-GO**
solo por los gates humanos, legales, visuales, de proveedores y de familias
Public v1 aún no aprobados.

## 97. Matriz POSIX/Linux cerrada — 10/11/2026

El runner POSIX fallaba inicialmente en Windows porque el script inline se
codificaba con CRLF y BusyBox `sh` interpretaba `set -eu` con un retorno de
carro. Se normalizó a LF y se añadió una regresión contractual. La nueva
ejecución limpia sobre la imagen final pasa **8/8** casos POSIX/Linux, con
**0 skips y 0 fallos**, y cleanup correcto. El recibo está en
`ronin-posix-bc0fc45-20261110`.

La matriz de plataforma mejora, pero no cambia el NO-GO: permanecen los gates
humanos/legal, proveedores externos, rollback y cualificación de familias.

## 96. Gate legal/licencias reproducido — 10/11/2026

La ejecución de `tools/license_qualification.py` contra
`requirements-dev.lock`, `third_party/licenses-v1.json` y
`third_party/license-policy-v1.json` falla de forma fail-closed. La cola
exacta es:

- **22 decisiones humanas faltantes:** `boolean-py`, `cachecontrol`,
  `certifi`, `charset-normalizer`, `cyclonedx-python-lib`, `defusedxml`,
  `filelock`, `idna`, `license-expression`, `msgpack`, `packageurl-python`,
  `pip-api`, `pip-audit`, `pip-requirements-parser`, `pip`, `py-serializable`,
  `pyparsing`, `pyyaml-ft`, `requests`, `tomli-w` y `urllib3` (con sus
  versiones exactas del lock).
- **1 entrada stale de policy:** `pyyaml==6.0.3`.
- **9 evidencias stale/mismatched:** `coverage`, `greenlet`, `libcst`,
  `librt`, `mypy`, `packaging`, `playwright`, `setproctitle` y `tomli`.

La corrección mecánica de inventario/evidencia puede prepararse, pero la
decisión de licencia, NOTICE, atribución y claims no puede inferirse del
código ni ser aprobada automáticamente. Public v1 permanece **NO-GO** hasta
que el responsable humano revise y acepte/rechace cada entrada y actualice la
policy de forma trazable.

## 101. Secret scanning del árbol actual — 10/11/2026

Gitleaks `v8.0.0` escaneó el árbol actual y sus **2049 commits**, unos
**17,14 MB**, y encontró **0 leaks**. Recibo SARIF:
`ronin-gitleaks-8d1fdb-20261110/worktree.sarif`.

Este gate de secretos queda verde; no sustituye la revisión humana de
licencias/NOTICE, claims, proveedores ni familias Public v1. La decisión
global permanece **NO-GO**.

## 102. Continuidad, migraciones y rollback local — 10/11/2026

La batería dirigida de continuidad pasa **33/33**: backup PostgreSQL y
appliance, SQLite, manifiestos, registro de migraciones, cualificación de
migraciones, certificación de fixtures y rollback del ciclo de plugins. No se
detectan regresiones en el contrato de migraciones forward-only ni en la
integridad de los manifiestos.

La certificación ejecutable de fixtures genera recibos válidos para los cuatro
perfiles declarados —Fabric, Databricks, Foundry y Dataiku—, incluyendo
descubrimiento, traducción, importación, exportación y round-trip del bundle.
Estos recibos certifican únicamente el conjunto golden local y no implican
compatibilidad autenticada con tenants, APIs o proyectos reales de esos
proveedores. Para cerrar el release aún faltan pruebas de restore/rollback en
un entorno operativo representativo, retención y restauración ante fallo, y
la cualificación externa de SDP/proveedores cuando se disponga de sus
instalaciones y credenciales. Public v1 permanece **NO-GO**.

## 103. Regresión UI del control plane — 10/11/2026

La regresión dirigida de Chromium pasa **7/7** sobre el árbol actual: barra de
contexto, command palette, workbench de Environments, workbench de Deployments,
responsive y accesibilidad de ambos workbenches. Se confirma que el contexto
activo se conserva, que las decisiones Observe/Author/Govern y
Observe/Bind/Operate siguen visibles, y que las acciones de gobierno no
ocultan el estado real del backend.

La dirección de producto UI queda explícita: RONIN debe comportarse como un
control plane coherente —contexto persistente, objetos navegables, decisiones
por etapas, estados loading/empty/error honestos, accesibilidad y responsive—
con identidad propia, tomando como referencia la claridad operativa de
Databricks, Dataiku, Palantir y Fabric. Esta regresión confirma el contrato
automatizado, pero no sustituye una revisión visual humana firmada sobre el
candidato final. Public v1 continúa **NO-GO** por los gates externos y
humanos ya enumerados.

## 107. Reconciliación semántica del ledger — 10/11/2026

La auditoría del estado detectó que el SHA del ledger ya era actual, pero sus
campos narrativos aún describían candidatos históricos: UI 140/140, un VEX
antiguo, policy stale y el candidato `74fb533`. Se corrigieron el resumen de
observación, el estado del workspace y los bloqueadores para reflejar los
recibos vigentes: UI 147/147, Scout/VEX 0/0, policy mecánicamente
reconciliada, Trino 2/2, Spark Connect 1/1, POSIX 8/8, live 33/33 y artefactos
90/90.

El ledger sigue declarando correctamente **0/13** familias cualificadas y
**NO-GO**. Esta corrección evita que una decisión de release se base en
descripciones históricas aunque el SHA sea correcto.

## 108. Inspección visual asistida del workbench — 10/11/2026

Se inspeccionó el render Chromium real del recorrido de Ingestion Studio en
desktop, incluyendo rail persistente, topbar, contexto workspace/proyecto/
runtime, agrupación de acciones, paneles de decisión y estado de operación.
La composición conserva jerarquía clara, contraste consistente, foco visible y
un lenguaje visual coherente con el control plane; no se observó overflow ni
un control ambiguo en la captura revisada. El recorrido funcional asociado
pasó **1/1**.

Esta inspección es evidencia asistida del candidato y complementa la matriz
responsive/accesibilidad automatizada; no reemplaza la revisión visual humana
firmada que exige el gate de release. Public v1 permanece **NO-GO**.

## 109. Inspección visual móvil — 10/11/2026

Se inspeccionó el shell real a **390×844 px** con Chromium: topbar con
contexto, acceso a conexión y búsqueda; home con CTA y contexto; y rail
inferior compacto con iconos y foco activo. El contenido mantiene márgenes,
contraste y jerarquía legibles, y la navegación no introduce overflow
horizontal en el viewport revisado. La captura de página completa muestra
espacio vertical adicional por el modo `fullPage`, pero el viewport operativo
no presenta ese defecto.

La revisión móvil asistida queda verde para esta superficie y complementa el
test responsive automatizado. No sustituye la aprobación visual humana
firmada ni la revisión de todas las rutas. Public v1 permanece **NO-GO**.

## 110. Suite estática Chromium completa sobre el candidato — 10/11/2026

La ejecución completa del paquete `web-tests` sobre el árbol actual pasa
**147/147** en Chromium, en 5,8 minutos y con dos workers. Incluye
accesibilidad de las superficies, journeys funcionales, command palette y
contexto, navegación por 25 rutas, responsive de 320 a 1440 px, workbenches de
Workspace/Projects/Data Engineering/Connections/Environments/Deployments y
las regresiones de streaming, semantic, ML, scheduler y synthetic.

No hay skips ni fallos en esta lane estática. El resultado confirma la
regresión frontend del candidato; no equivale a cualificación live de API,
proveedores o persistencia, que conserva sus recibos separados y sus gates
abiertos. Public v1 permanece **NO-GO**.

## 106. Reconciliación de ledgers al SHA actual — 10/11/2026

La auditoría detectó y corrigió una divergencia documental: los ledgers
`PUBLIC_V1_IMPLEMENTATION_STATUS.md` y `public-v1-status.json` registraban
`e3181c28`, mientras el candidato publicado ya estaba en `dd5575e1`, con 13
commits de distancia. Se sincronizaron ambos al SHA actual y el chequeo
fail-closed de estado, junto con la batería legal, pasa **109/109**.

La sincronización sólo corrige la identidad de la evidencia; no cambia las
capacidades cualificadas ni la decisión de release. SDP continúa bloqueado por
la ausencia del módulo `sdpstudio_cli` en el wrapper local. Public v1 sigue
**NO-GO**.

## 104. Inventario legal reproducible y estable — 10/11/2026

Se corrigió el generador de evidencia legal para excluir bytecode `.pyc` y
directorios `__pycache__`: esos archivos son artefactos de importación local,
no textos de licencia, y hacían que el hash de una misma distribución
dependiera del momento en que se ejecutaba el proceso. El inventario se
regeneró desde un entorno temporal limpio instalado con
`requirements-dev.lock` y hashes exactos.

La batería contractual de licencias pasa **106/106**. El gate completo sigue
fallando de forma intencionadamente fail-closed con los mismos blockers
legítimos: **22 decisiones humanas faltantes**, una entrada stale de policy y
nueve evidencias de revisión desalineadas. Esta iteración elimina un falso
cambio de evidencia, pero no convierte ninguna aprobación legal en automática
ni cambia Public v1 de **NO-GO**.

## 105. Reconciliación mecánica de la policy legal — 10/11/2026

Se actualizaron las nueve referencias de evidencia stale al hash estable del
inventario reproducible y se retiró la revisión obsoleta de `pyyaml==6.0.3`,
que ya no pertenece al grafo activo. La suite de contrato de licencias vuelve
a pasar **106/106**.

El gate completo ahora falla únicamente por las **22 decisiones humanas
faltantes**; no quedan entradas stale de policy ni evidencias desalineadas.
Esto cierra el trabajo mecánico del gate, pero no permite asignar decisiones
legales, NOTICE, atribución o claims automáticamente. Public v1 permanece
**NO-GO** hasta la revisión y aceptación formal del responsable.

## 111. Limpieza de bloqueadores históricos del ledger — 10/11/2026

Se actualizaron dos condiciones machine-readable que todavía arrastraban
diagnósticos antiguos: `latest-implementation-edits` ahora refleja Chromium
147/147 y los carriles POSIX, Trino y Spark actuales; `security-vex-human-
acceptance` ya no reclama CVEs ni excepciones VEX activas y registra el
resultado vigente **0 raw / 0 post-VEX** y Gitleaks **0**.

El trabajo no elimina la revisión humana de la política Alpine Edge ni la
aceptación final de seguridad. Sí garantiza que el NO-GO no se apoye en
hallazgos técnicos ya resueltos. Las condiciones de familias, proveedores,
legal, rollback y gobierno permanecen abiertas.
