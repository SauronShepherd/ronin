# Release test triage — 29 October 2026

This is the implementation-facing triage for Phases 1–2 of
[`PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`](PLAN_FINAL_RONIN_RELEASE_2026-11-03.md).
It retains the source IDs and priorities. `P0` blocks release; `P1` must be
resolved or have an explicit, approved mitigation; `P2` is required when the
related public claim is retained. A proposed test or green isolated test is not
release evidence.

## Scope dispositions

| Source cases | Current disposition | Required control |
| --- | --- | --- |
| P1–P8, P10–P14 | Active Public v1 families | Qualify complete end-to-end paths and applicable providers/security evidence on one clean candidate. |
| `AI-001`–`AI-003` | Retired; no GenAI/RAG/agent runtime in any Ronin tier | Do not run the retired feature steps or count them as release gates. Reuse the existing product-boundary negative test. |
| `IAM-003` groups/bindings; `IAM-004` OIDC | Ronin Pro / out of Public v1 | Do not expose these controls in the Public UI, API, CLI, configuration or chart. |
| `WEB-ROUTE-014`, `WEB-ROUTE-021`, `WEB-ROUTE-022` (`access`, `ai`, `genai`) | Historical routes, out of scope | Test their absence as a regression boundary; do not require retired features. |
| `REL-001` CI exact-SHA | Incompatible with the user's no-CI policy | Replace the release requirement with local `local-quality` receipts; do not create or enable CI workflows. |
| `REL-003` Kubernetes | Public claim limited to one local single-replica chart; Pro HA/multi-user is out of scope | Validate chart schema/render and local cluster only after the pinned Helm/kind toolchain is available. |

## Structured test cards and family mapping

The canonical master contains **305 unique case IDs across the full document**:
102 cards in §3 plus 203 later additions. §4 preserves 28 historical route IDs;
25 remain active and `access`, `ai`, `genai` are retired. The source's raw
catalogue arithmetic is 305 + 25 = 330 planned cases, not executed or
release-qualified cases. An earlier version of this triage incorrectly treated
the 102 §3 cards as the whole catalogue and reported 183 unreconciled cards;
that discrepancy is corrected by the full inventory in
[`RELEASE_CASE_INVENTORY_2026-10-29.md`](RELEASE_CASE_INVENTORY_2026-10-29.md).
The inventory lists each canonical ID once, copies declared priorities, and
marks GenAI, Pro and no-CI scope dispositions. Composite headings in appendices
are not counted as new IDs. Shared API, browser, storage, security and release
cards still apply to their related family; they are not family completions.

| Source area | Public family mapping | Priority and in-scope IDs | External or optional infrastructure |
| --- | --- | --- | --- |
| `CORE` | P14, with execution controls shared by P1/P5 | P0: `CORE-001`–`003`; P1: `CORE-004`–`007`; P2: `CORE-008`–`009` | Clean venv/wheel/sdist, Docker for installed/worker checks |
| `API` | Cross-cutting P1–P14 | P0: `API-001`–`003`; P1: `API-004`–`007` | Live Ronin server; PostgreSQL for PG adapters; no mock responses for live claims |
| `WEB` | Cross-cutting P1–P14 and installed UI | P0: `WEB-001`–`003`; P1: `WEB-004`–`007`; P2: `WEB-008` | Installed app, Playwright/Chromium, keyboard/accessibility checks, live API |
| `IAM` | P1 and P13 | P0: `IAM-001`, `IAM-002`, `IAM-005`, `IAM-006`; Pro/out of scope: `IAM-003`, `IAM-004` | Synthetic workspaces/tokens; Git; no OIDC or membership fixture in Public v1 |
| `DATA` | P2, P3, P4 | P0: `DATA-001`–`003`; P1: `DATA-004`–`007`; P2: `DATA-008`–`010` | Real PostgreSQL; optional S3/Azure/Ozone/JDBC, DuckDB/Arrow/Trino and notebook runtimes per claim |
| `SCHED` | P5 | P0: `SCHED-001`–`003`; P1: `SCHED-004`–`007` | PostgreSQL, Docker worker; SMTP/HTTPS notifications only with synthetic endpoints |
| `ML` | P8 classical ML only | P0: `ML-001`–`003`; P1: `ML-004`–`007`; P2: `ML-008`–`012` | Optional ML extra, PostgreSQL and S3-compatible store per profile |
| `GRAPH` | P6 | P0: `GRAPH-001`–`003`; P1: `GRAPH-004`–`005` | SQLite and PostgreSQL profiles |
| `QUALITY` | P7 | P0: `QUALITY-001`–`003`; P1: `QUALITY-004` | Bounded Python/SQL runtime and real alert route |
| `AI` | P9 retired; P10 semantic | Retired: `AI-001`–`003`; P1 active semantic: `AI-004`–`005` | No model provider or agent service; semantic SQL/browser only |
| `OBS` | P11 and P12 | P0: `OBS-001`–`003`; P1: `OBS-004` | Kafka for P11; Prometheus and synthetic SMTP/HTTPS for P12 |
| `PORT` | P14 and applicable P2/P3 provider migration | P0: `PORT-001`–`003`; P1: `PORT-004`–`005` | Isolated vendor fixtures; real credentials only in an approved provider-cert lane |
| `STORAGE` | Cross-cutting P1/P5/P6/P8/P13/P14 | P0: `STORAGE-001`–`005` | Real PostgreSQL, SQLite, local artifact store and S3-compatible service where required |
| `SEC` | P13 plus package/container claims | P0: `SEC-001`–`005` | `pip-audit` available; Gitleaks and Trivy currently missing; no secrets or production endpoints |
| `REL` | P14 and candidate-wide release gates | P0: `REL-002`; `REL-001` is replaced by local-only evidence; P1: `REL-004`–`007`; P2: `REL-008`–`010`; `REL-003` single-replica local Helm only | Docker/Compose; Helm/kind missing; Terraform must match pinned 1.13.5; Floci 2.1.0 |

## Active installed routes

The source master §4 lists 28 stable route IDs. Its 25 active routes map as
follows; the three retired routes are listed under Scope dispositions above.

| Route ID | Product family coverage |
| --- | --- |
| `WEB-ROUTE-001` home | Shared discovery across the active Public v1 families |
| `WEB-ROUTE-002` runs | P5, P12 |
| `WEB-ROUTE-003` workspaces; `WEB-ROUTE-004` projects; `WEB-ROUTE-027` environments | P1 |
| `WEB-ROUTE-005` quality | P7 |
| `WEB-ROUTE-006` alerts; `WEB-ROUTE-007` finops; `WEB-ROUTE-023` performance | P12 |
| `WEB-ROUTE-008` migration; `WEB-ROUTE-025` cloud; `WEB-ROUTE-026` deployments | P14, plus the provider family exercised by the operation |
| `WEB-ROUTE-009` synthetic; `WEB-ROUTE-016` data; `WEB-ROUTE-017` ingestion | P2 and related P7 checks |
| `WEB-ROUTE-010` mlstudio | P8 |
| `WEB-ROUTE-011` workflows | P5 |
| `WEB-ROUTE-012` sql | P3 |
| `WEB-ROUTE-013` semantic | P10 |
| `WEB-ROUTE-015` catalog; `WEB-ROUTE-020` graphs | P6 |
| `WEB-ROUTE-018` notebooks; `WEB-ROUTE-024` debugger | P4 |
| `WEB-ROUTE-019` streaming | P11 |
| `WEB-ROUTE-028` settings | P13 local single-operator preferences |

For every active route, the installed-browser journey must cover direct/deep
link and menu navigation, API-backed state, empty/loading/error, validation,
keyboard/focus, responsive layout and an evidence capture. The live suite's
Streaming health is now exercised against a real broker in live qualification;
the full streaming processing journey remains open under P11.

## Reconciliation and owners

The master section 106 arithmetic is reproducible: 305 unique case cards + 25 active routes = 330 planned entries. Retaining all 28 historical route IDs gives 333 case/route identifiers. The earlier claim that 183 cards were missing was a counting error: section 3 has 102 cards and later sections add 203. The generated inventory contains all 305 cards and 28 routes. Family/scope assignments are traceable by ID group but remain subject to maintainer/QA review; missing source fields and case preconditions are not inferred. No inventory row records PASS.

| Workstream | Responsible role | Current dependency/decision |
| --- | --- | --- |
| Product scope, release type/version, claims | Product maintainer | Approve Public v1 versus a separately named Local MVP; approve package/tag version. Until then release is NO-GO. |
| Test inventory, owners, P0/P1 acceptance | Release/QA lead | 305 cards and 28 historical route IDs are inventoried; 25 routes are active. Family/scope mapping is by documented ID group and requires review; named individuals have not been assigned. |
| No-CI policy, local gate receipts | Release owner | User decision is no CI; reconcile issue #199 and require exact-candidate local evidence. |
| Licensing, `NOTICE`, package provenance | Maintainer + legal/security reviewer | Human license review and final approval remain open. |
| Supply chain/provenance | Release/packaging owner | Positive/negative generator tests implemented; exact candidate artifacts are not built yet. |
| Security scans | Security owner | `pip-audit` is available; Gitleaks and Trivy are absent. |
| Docker/PostgreSQL/live UI | QA/operator | Docker, PostgreSQL and Redpanda available; reruns are dirty-worktree diagnostics. Broker-backed health is wired; full P11 processing remains incomplete. |
| Helm/Kubernetes and Floci/Terraform | Platform owner | Helm missing; installed Terraform 1.16.2 does not match expected 1.13.5. Do not claim provider qualification. |

## GitHub issue reconciliation — read-only snapshot, 29 October

GitHub search returned 14 open issues for `SauronShepherd/ronin`. Their status
and acceptance criteria were reviewed without changing or closing any issue.
The work below is implementation/diagnostic evidence; it does not close a
release issue until its own criteria pass on a clean candidate.

| Issue | Priority | Disposition after today's work | Closure still requires |
| --- | --- | --- | --- |
| [#22](https://github.com/SauronShepherd/ronin/issues/22) architecture audit | P0/P1 | Architecture gate passes; preserve as open umbrella. | Reconcile every remaining contract item against source and exact-candidate evidence. |
| [#43](https://github.com/SauronShepherd/ronin/issues/43) provenance/reproducibility | P1 | Generator/validator tests are present; no release wheel, sdist, image, or final attestation qualified. | Build reproducible exact-candidate artifacts and verify subjects, digests, and provenance. |
| [#47](https://github.com/SauronShepherd/ronin/issues/47) mutation campaign | P1 | Deferred; no mutation campaign was run. | A separately approved, bounded campaign and plan; it is not needed to close today's phase. |
| [#57](https://github.com/SauronShepherd/ronin/issues/57) frozen v0.1 journey | P1 | Strict Docker acceptance was 15/15; latest live product diagnostic passed 28/28 with real broker-backed Streaming health. | All required journeys pass against one clean exact candidate. |
| [#58](https://github.com/SauronShepherd/ronin/issues/58) lock/licenses | P1 | Universal hashed lock now includes `pyyaml-ft==8.0.0` for CPython 3.13 while preserving prior pins. Full `--require-hashes`/`pip-audit --strict` resolution passed on Windows/Python 3.13 (33 dependencies, 0 advisories); locked install passed in Linux/Python 3.11 Docker. Python 3.12 and human license/NOTICE review remain open. | Repeat on every claimed interpreter/OS and complete reviewed license/NOTICE evidence. |
| [#59](https://github.com/SauronShepherd/ronin/issues/59) portable open-table journey | P2 | Remains future scope; no new provider claim was made. | Complete the narrow post-v0.1 journey when the scope freeze is lifted. |
| [#63](https://github.com/SauronShepherd/ronin/issues/63) branch/tag protection | P1 | No repository protection settings were changed. | Maintainer/admin verifies main and release-ref protection before tagging. |
| [#69](https://github.com/SauronShepherd/ronin/issues/69) performance guards | P2 | Existing bounded performance suite passed 3/3; this is not the full published budget campaign. | Retain exact-candidate measurements for every published budget. |
| [#96](https://github.com/SauronShepherd/ronin/issues/96) fail-closed acceptance | P1 | Strict acceptance passed 15/15; live UI/API diagnostic passed 28/28, including actual Kafka watermarks. | Repeat strict acceptance and live qualification on the same clean candidate with no required skips. |
| [#102](https://github.com/SauronShepherd/ronin/issues/102) tool coverage | P1 | Full suite ran with coverage; tools-specific coverage was not separately qualified. | Establish and meet explicit release-gate-tool coverage thresholds. |
| [#115](https://github.com/SauronShepherd/ronin/issues/115) observed resource usage | P2 | Docker qualification passed its strict gate; no candidate-bound per-cell CPU/memory overhead report was retained. | Qualify actual cgroup measurements and collection overhead against the issue's workload. |
| [#199](https://github.com/SauronShepherd/ronin/issues/199) CI/release qualification | P1 | Conflicts with the user's explicit no-CI policy. Keep workflows disabled and use local-only qualification; issue remains open for maintainer disposition. | Reconcile the issue text with the user's policy. Do not enable CI to satisfy it. |
| [#201](https://github.com/SauronShepherd/ronin/issues/201) operational budgets | P2 | Not fully qualified. Earlier observed GET p95 was 30.832 ms against the documented `<30 ms` target; the broader evidence campaign remains open. | Repeat all bounded budgets on one exact candidate and meet their frozen thresholds. |
| [#202](https://github.com/SauronShepherd/ronin/issues/202) Compose/evidence acceptance | P1 | Strict Docker acceptance passed 15/15, exercising the dedicated real-Compose acceptance path. | Preserve the JUnit/evidence with a clean exact candidate and reconcile the issue after that run. |

The observed status remains **14 open; 0 closed**. The user policy (no CI,
no in-product GenAI, and no Public multi-user features) takes precedence over
conflicting issue text; it does not imply that other acceptance criteria have
passed.

## 29 October execution evidence

All records below are **DIRTY-WORKTREE DIAGNOSTIC** evidence, not release
qualification. Source baseline was `f9a0456ab7df3e2bb77247d54b4336fca64903b0`.

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| Full Python + PostgreSQL suite | 4,201 passed, 24 skipped, 0 failed (663.865 s; 4,225 cases) | `%TEMP%\ronin-python-postgres-20261029-30b95eafad9b4e7c91d65e6e3913c34b\pytest-postgres.xml`; remaining skips cover opt-in Docker tests, unavailable external services, and Windows/POSIX/symlink limits. Provider/platform skips are not release passes. |
| Focused regressions | 49 passed, including bounded Python sandbox, Floci qualification contract and complete release inventory parser | `tests/test_quality_runtime.py`, `tests/test_cloud_studio_floci_qualification.py`, `tests/test_release_case_inventory.py`; latest inventory parser run is post-suite and therefore supported by this focused run. |
| Performance tests | 3 passed | Does not replace the broader operational-budget evidence required by #69/#201. |
| Docker qualification | 21 passed, then the two PostgreSQL cases passed separately (23/23 distinct); strict v0.1 acceptance 15/15 | `%TEMP%\ronin-docker-qualification-20261029-3ff64f8d7c944459ad5100798520cdb7` and `%TEMP%\ronin-docker-postgres-tests-20261029-9773b7cb9ee04c31812ccf07ca3ef4d8`. Dirty-worktree diagnostics, not clean candidate qualification. |
| Cloud Studio + Floci + Terraform | plan/apply/refresh/destroy/state-list all returned 0; final state empty | `%TEMP%\ronin-floci-qualification-20261029-a298ca72f681418d80db5a33d190b05f\qualification.json`; pinned Floci digest, Terraform 1.13.5 and AWS provider 6.65.0. |
| Live app and API | 28/28 routes; 50 real API calls: 47 `OK`, 3 expected invalid-token `WARN`, 0 `ERROR`/5xx | `%TEMP%\ronin-live-qualification-1e75d16f3e4e42c18dc7814a31b72dff`; 1,166 server `INFO` log entries, 0 server `WARN`/`ERROR`. Full P11 processing remains open. |
| Coverage gates | All configured Makefile thresholds passed, including storage per-file gate (53 files), broker and release tooling | Coverage and storage JSON are in the Python/PostgreSQL evidence directory. |
| Static gates | Ruff/format (901 files), mypy (434 files), architecture, negative gates, dependency surfaces, route/OpenAPI (185 operations), Studio audits/budgets, capability status, skills, Go canonical JSON and runner protocol passed | Helm, GNU Make, Gitleaks and Trivy are not installed. The qualification used a verified Terraform 1.13.5 binary; the system Terraform remains 1.16.2. |
| `pip-audit` and locked install | Full hash-locked resolution passed; 33 dependencies, 0 known vulnerabilities; Python 3.11 Linux install and 15 inventory/Floci contract tests passed | `%TEMP%\ronin-final-lock-audit-20261029\pip-audit.json`; `%TEMP%\ronin-final-lock-docker-20261029\pytest.xml`; lock is universal. Python 3.12 matrix and license/NOTICE review remain open. |

The live debugger defect was caused by stale, ignored editable-install metadata
under `python/ronin_studio.egg-info`; that metadata shadowed the installed
entrypoint set and omitted Data Engineering routes. The qualification runner
now refreshes the root editable package metadata before starting the app, and
`tests/test_local_composed.py` exercises health, debugger creation, and
breakpoint routes through the actual local HTTP composition. The plugin
inventory test also guards the Data Engineering entrypoint.

The prior 27/28 run exposed the unwired P11 health route. Local composition now
reads the stored stream definition/checkpoint and queries real Kafka partition
watermarks without consuming records. The 28/28 live run closes that route
regression only; it does not qualify P11's complete processing journey or a
clean release candidate. Its three HTTP 401 records are intentional assertions
that an invalid token produces an understandable UI error, not unexpected
failures.

**Launch decision checkpoint:** recommend provisional NO-GO for 3 November on
the evidence available today. Continue the full product plan through its
31 October cutoff. If the approved scope, all required gates and visual/manual
acceptance are not green by then, delay the launch; do not promote an
unqualified MVP or lower release thresholds to preserve the date.

## 30 October execution update

These are later dirty-worktree diagnostics on branch `20261029`, base commit
`f9a0456ab7df3e2bb77247d54b4336fca64903b0`. They do not replace the dated
29 October snapshot above and do not qualify a release candidate.

| Check | Result | Evidence / remaining limitation |
| --- | --- | --- |
| Full Python + PostgreSQL suite | 4,223 passed, 24 skipped, 0 failed (4,247 total; 705.64 s) | `%TEMP%\ronin-python312-postgres-rerun-20261030`; this preceded the final HTTP disconnect handler change, which was followed by 57 focused HTTP/integration passes. The skips are platform and external-service gaps, not passes for those targets. |
| Docker qualification | 23/23 passed with isolated PostgreSQL and zero skips; strict acceptance 15/15 | `%TEMP%\ronin-docker-qualification-pg-20261030-5341b2c82da744b18520640c240409be`. |
| Live product/API | 28/28 active routes; 53 API requests: 50 `OK`, 3 expected invalid-token `WARN`, 0 `ERROR`/5xx; no unexpected tracebacks or server warnings/errors | `%TEMP%\ronin-live-qualification-logfix-20261030-9b84678d22c0481292702e80afdf8206`; selected operations only; no claim of 13-family qualification. |
| Cloud Studio/Floci | Real plan/apply/refresh/destroy/state verification passed; final state empty | `%TEMP%\ronin-floci-qualification-20261030-5f59fdf07c5243f9bada5b908a819bca\qualification.json`. |
| Wheel and sdist | Two identical builds; SHA-256 `c12dd913cf7f9cb580910620368eed4e452ee68a944be27b66bd0c0dd1849022` and `6d16b53672db2df80cc068c76261fd1948320f8817c486b6703a4b63f0ef4727`; both installed and CLI/skills/demo smoke passed | `%TEMP%\ronin-artifact-qualification-20261030-b9da9b13f244464ab8f7a913124de253\artifact-receipt.json`; exploratory artifacts identify as `0.0.0`, so not releaseable. Only Windows/Python 3.12.10 was tested. |
| Qualification tool lock | 36 exact packages, universal SHA-256 lock; `pip install --require-hashes` passed | `third_party/qualification-tools-v1.in` and `.txt`; this fixes stale msgpack hash and missing transitive pins. License/NOTICE approval remains open. |
| Coverage | All Makefile package/line thresholds passed from a preserved clean copy of the main coverage DB; storage gate passed 53 files; control-plane coverage is 36% against 35% | `%TEMP%\ronin-coverage-gates-20261030-e0d76e59620742708b7ef05b6617963d`; an earlier empty sidecar was invalid, so it was excluded and preserved. |
| Focused/static | 57 HTTP/integration tests after the disconnect fix; later 44 focused pagination, dependency-surface, logging and Docker-contract tests; Ruff, format, targeted mypy, dependency-surface validation and `git diff --check` passed | Final 44-test JUnit and tool outputs: `%TEMP%\ronin-focused-qualification-20261030`; full suite was not rerun after the disconnect handler and pagination cases, while affected paths passed focused and live qualification. |

The API logging fix now suppresses only expected peer-disconnect exceptions in
the two HTTP servers while retaining tracebacks for unexpected failures. Added
pagination/cursor/path serialization tests close the control-plane coverage
threshold miss found during gate review.

The launch remains **NO-GO**. Public v1 is still **0/13 release-qualified**;
the 0.0.0 package version, clean candidate, Linux/Python matrix, legal review,
complete family journeys and manual visual acceptance remain unresolved.

## 30 October — final same-day reconciliation

The later complete Python/PostgreSQL run supersedes the earlier `4,223 passed` entry above: **4,322 passed, 24 skipped, 0 failed** in 613.51 seconds with PostgreSQL 16.4 and resource warnings promoted to errors. Docker remained **23/23**, strict v0.1 acceptance **15/15**. Static Playwright finished **100 passed / 29 live-only skipped**; the separate real-app run passed **29/29**, sent 56 real API requests (53 expected successes, 3 intentional invalid-token 401 responses), and recorded 1,210 INFO with no server WARN/ERROR. This real-server harness used the `local-composed` profile with SQLite-backed control-plane state; real PostgreSQL coverage came from the full suite and Docker qualification. Floci/Terraform 1.13.5 verified fixture resource creation and destruction and an empty final state. Wheel/sdist rebuilt with identical hashes and both artifacts passed installed CLI smoke on Windows/Python 3.11, 3.12 and 3.13; the exploratory package version remains `0.0.0`.

Evidence paths and phase-by-phase limitations are recorded in `PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`, section 12. The worktree is dirty and these are diagnostics, not candidate-bound release receipts. the complete Linux/runtime-version matrix, legal approval, a human-approved version, full Public v1 journeys, manual visual acceptance and clean candidate evidence remain open. Trivy still reports 46 unresolved HIGH findings per image after VEX triage. Public v1 therefore remains **0/13 release-qualified; NO-GO**.

### Actualización posterior: recorrido live de notebooks — 30 October

La siguiente ejecución añadió un worker Docker real al harness live y detectó
que los handlers HTTP de leer, guardar y borrar notebooks estaban ubicados en
métodos incorrectos. Tras moverlos y añadir una regresión de crear → leer →
guardar revisión → historial → borrar, el bloque relacionado quedó **55/55**;
Ruff y mypy pasaron. El navegador estático quedó **100 passed / 30 live-only
skipped**. La qualification live completa pasó **30/30 casos y 72 llamadas
API reales** (67×200, 2×201, 3×401 intencionales); el worker ejecutó el notebook
y terminó `succeeded`, con evidencia de log. El servidor registró 1.260
eventos INFO/OK, sin WARN/ERROR ni 5xx inesperados. Evidencias:
`%TEMP%\ronin-live-plan-today-worker-final-20261030`,
`%TEMP%\ronin-playwright-static-notebook-fix-20261030`.

La Fase 6 mejora, pero no se cierra: quedan journeys de scheduler y
persistencia/reinicio. La evidencia es de worktree sucio; versión `0.0.0`,
46 HIGH de Trivy por imagen, revisión legal, journeys de las 13 familias,
manual visual y qualification candidate-bound siguen pendientes. El release
continúa **NO-GO; Public v1 0/13**.

## 30 October — scheduler y smoke de artifacts, resultado más reciente

Este bloque supersede las cifras previas del día para estos carriles. Es
**DIRTY-WORKTREE DIAGNOSTIC** sobre rama 20261029, base
f9a0456ab7df3e2bb77247d54b4336fca64903b0; no es evidencia candidate-bound.

| Carril | Resultado |
|---|---|
| Python/PostgreSQL 16.4 | 4.335 passed, 24 skipped, 0 failed; 828,18 s. %TEMP%/ronin-python-postgres-scheduler-20261030-56e25e29b78d46758c11940138d1992a. |
| Docker | 23/23; strict v0.1 acceptance 15/15, sin skips ni fallos. %TEMP%/ronin-docker-scheduler-20261030-0a10ab82d59b42bcb23d91ae4ef614a6. |
| Playwright estático | 100 passed, 30 skipped como live-only; ejecutados aparte contra aplicación real. %TEMP%/ronin-playwright-static-20261030-effc293209e64a9d840ae3fdf7c6b770. |
| Aplicación live | 30/30; 99 requests reales: 89×200, 5×201, 1×202, un 400 esperado por cron inválido y 3×401 esperados por autorización. Sin 5xx, errores API inesperados ni errores del navegador; servidor 1.260 INFO, 0 WARN/ERROR. %TEMP%/ronin-live-scheduler-20261030-833ea43248bc4956ac73c2fbe186bded. |
| Scheduler | Live exercise de cron, historial, entrega de eventos/run IDs y backfill con plan snapshot/cancelación. local-composed usó SQLite control plane, PostgreSQL, Redpanda y worker Docker aislados. API descrita en SCHEDULER_API_V1.md. |
| Root wheel/sdist | Ambos formatos reproducibles en dos builds, instalados en venv limpio Windows/CPython 3.13.15; pip check, CLI/doctor, demo validate/plan y las tres skills pasaron. Los tres ZIP generados coinciden entre formatos. La expectativa inicial del smoke sobre un solo ZIP falló por el propio harness; la comparación corregida verificó los tres. Wheel B82614479A616AD550F358DF192217AC42BC095A42142EFB3768496F12CFDB7B, sdist A57B144C7493ADBF291B5A2E1DDCFDDC0DBD0158F606CD1F40C1D502FED2683C; versión 0.0.0. %TEMP%/ronin-root-artifacts-20261030-f33fbf0e3ee64164b776caacf9f54ddf. |
| SDK pyronin | Metadatos modernizados a SPDX, classifier de licencia antiguo retirado. 90 tests; wheel/sdist instalados en venv limpio, pip check e import aislado; cero SetuptoolsDeprecationWarning. Wheel 4b28077378779acc1128be06307a2c65aa747990f02fc1dea997d86565992ed2, sdist 728c19c4701e7885c60f08f365fb7d509a399b1f03e2d9c5b4bad49d11cf38b8. %TEMP%/ronin-pyronin-modernized-20261030-afca4c45fac246ce84ad7848a5e67313. |
| Matriz de instalación | Wheel y sdist del mismo build pasaron en venvs Windows limpios para Python 3.11, 3.12 y 3.13. En Linux/CPython 3.11, ambos se instalaron con resolución de dependencias en venv limpio y pasaron pip check, CLI/doctor, demo, skills y los tres ZIP. Windows: %TEMP%/ronin-artifact-matrix-clean-20261030-d4526602e3444edfb943acfa62c9b4d6; Linux: %TEMP%/ronin-linux-artifact-smoke-clean-20261030-69bfbe232d424251aabda939b4eca7c3; contenedores eliminados al terminar. |
| Inventario de licencias | Regenerado contra el lock actual; 56 distribuciones y SHA-256 b1bbbd33e482242638fafa124e1385f2b76eff7cbe17ee57d349f0d9b3e50c18. JSON y digest válidos; tests de license qualification 101/101. |
| Revisión legal | Bloqueada: la policy todavía tiene 36 reviews; faltan 21 paquetes del lock nuevo y sobra una revisión pyyaml 6.0.3. Se actualizó licenses-v1.json; no se inventa una aprobación de licencia/NOTICE y el gate no se da por pasado. |
| Regresión focalizada | 74 passed en scheduler, outbox/recovery, composición del servidor y contrato Docker. Ruff, mypy (381 source files), formato de 113 Python, OpenAPI, Compose, JavaScript syntax y git diff --check pasan. |
| pip-audit | Con require-hashes y strict: requirements-dev.lock 53 distribuciones/0 vulnerabilidades; requirements-test.lock 92 distribuciones/0 vulnerabilidades. JSON: %TEMP%/ronin-lock-audit-20261030. |

Skips de Python corresponden a Docker opt-in, requisitos POSIX/symlink de
Windows y servicios externos no disponibles. Se confirma el diagnóstico
funcional del scheduler de hoy, pero no se cierra Public v1: permanecen el
árbol sucio, versión no aprobada, revisión legal y visual manual, escaneo de
imagen sin resolver, journeys de las familias y matriz/plataformas pendientes.
El ledger permanece **0/13 cualificadas; NO-GO**.

## 30 October — cierre Docker y producto live más reciente

La evidencia Docker/imagen anterior queda supersedida por imágenes Alpine
3.24.3 fijadas por digest, con locks de versiones exactas para los paquetes
APK añadidos y sin herramientas pip en runtime: Trivy 0.76.1 con todas las
severidades encontró 0 vulnerabilidades y 0 secretos en runtime y probe;
Docker pasó 23/23 y la aceptación v0.1 estricta 15/15, sin skips. Evidencias:
`%TEMP%/ronin-apk-locked-scan-20261030` y
`%TEMP%/ronin-docker-apk-locked-20261030`. El build falla si falta una de las
versiones fijadas. Es evidencia del árbol sucio, no un build reproducible de
release ni qualification de candidato.

El runner aislado pasó 30/30 casos Playwright contra el servidor Ronin real,
96 llamadas a API (86×200, 5×201, 1×202, 1×400 esperado, 3×401 esperados),
0 respuestas 5xx, 1.262 logs de servidor INFO/OK y 0 WARN/ERROR. El test de
notebook ejecutó un worker Docker real. PostgreSQL, Redpanda, red y volúmenes
temporales se limpiaron. Discovery PostgreSQL tardó 3.767 ms en la primera
página y 112 ms en la segunda. Evidencia: `%TEMP%/ronin-live-apk-locked-final-20261030`.

El runner usa un venv efímero con `requirements-test.lock` hashado, guarda el
inventario y restaura el entorno original. Playwright mantiene los colores
desactivados sin combinar `NO_COLOR` con el `FORCE_COLOR` fijado por sus
workers; la última corrida no produjo avisos de Node.

Los locks fijan las versiones de paquetes APK añadidas sobre las bases por
digest; el build falla si una versión fijada deja de estar disponible. Siguen
pendientes 21 revisiones legales, decisión sobre la versión 0.0.0, SHA limpio,
journeys completos de las familias, revisión visual manual y decisión de
release.
**NO-GO; 0/13 familias release-qualified (0%)**.
