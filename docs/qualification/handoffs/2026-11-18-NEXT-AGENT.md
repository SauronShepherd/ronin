# Handoff para el siguiente agente — Ronin — 18 noviembre 2026

## Estado transferido

D95 queda cerrado con evidencia local nueva; D93 sigue siendo la última celda
live, pero el release no es GO:

```text
production implementation boundary: 633980dd3b08affcc604dc918c1a6cbf026cc408
qualification-harness/current main at D95: e5ef16525164bfb346def250dd7d4d8053526144
documentation state: D94 receipt and status updates are included in current main history
worktree at handoff creation: main, limpio
familias: 1/13
release gates: 0/10
P11: in_progress
P13: blocked
release: NO-GO
```

`e5ef1652` sólo añade una regresión de cualificación local; no cambia el runtime
de producción respecto de `633980dd`. D95 prueba cuatro segmentos de 16
micro-lotes con sink Parquet local, reset/replay y checkpoint durable; D94
mantiene la celda SQLite de 1.024 registros. D93 califica por separado el
arnés y el journey live de `549ffe30`; ninguna de las fronteras debe ocultarse.

## Evidencia más reciente

- [D95](2026-11-18-D95.md): soak Parquet local bounded de `64` registros en
  cuatro segmentos más replay tras reset, `1/1` caso nuevo y `98/98` en la
  selección combinada; ficheros, offsets, idempotencia y cleanup verificados.

- [D94](2026-11-18-D94.md): soak local bounded de `1.024` registros en cuatro
  segmentos, `1/1` caso nuevo y `97/97` en la selección combinada; checkpoint,
  sink, límites y cierre de sesiones verificados.

- [D93](2026-11-18-D93.md): `65.536` registros en Redpanda single-broker
  real, cap `73`, ocho reanudaciones de máximo `8.192`, lag `0`, idle replay,
  reset y dos replays de `7`; `1/1` Playwright, `19/19` eventos correlacionados
  `OK`, cleanup correcto. Evidencia:
  `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-live-d93-backpressure-65536-candidate-549ffe30-20261118`.
- [D92](2026-11-17-D92.md): celda anterior de `32.768` registros, bounded,
  sobre `633980dd`.
- D90/D91: route-wide con un skip explícito y failover RF3 focalizado,
  respectivamente; no se combinan en una cualificación completa de P11.
- D83–D89: regresión Python/PostgreSQL, Docker, Helm/kind y supply-chain,
  todos ligados al candidato de implementación `633980dd`.

## Cambios del arnés

`tools/run_live_product_qualification.ps1` expone
`-BackpressureTimeoutSeconds` (`240–1800`, default `240`), lo propaga como
`RONIN_LIVE_BACKPRESSURE_TIMEOUT_SECONDS` y lo registra en el resumen. El caso
live segmenta reanudaciones de gran volumen para respetar un límite bounded por
petición. Contratos de cualificación: `25 passed`; Node y PowerShell syntax:
PASS.

## Límites que siguen abiertos

1. operación indefinida/soak y continuidad del supervisor a duración de
   producción; D94 y D95 sólo cubren soaks locales bounded;
2. topología productiva, multi-worker y HA;
3. amplitud de proveedores externos y matriz completa de sinks, replay y
   recovery;
4. journey completo de P11 y agregación de las 13 familias;
5. decisiones humanas de licencia, NOTICE, VEX, producto, soporte, versión,
   plataformas y freeze;
6. cualificación P13 con proveedor externo de secretos.

D93 sigue siendo un diagnóstico streaming-only: PostgreSQL y worker no
aplican, `routeCoverage.audited=false` y los límites explícitos no equivalen a
operación indefinida.

## Reglas de continuación

- Trabajar sólo en `main`; no crear ramas, worktrees ni workflows hospedados.
- D49 es contexto técnico, no autorización para relajar la matriz de evidencia.
- Mantener SHA exacto, logs, hashes y cleanup. No usar mocks para certificar
  proveedores reales.
- Cualquier cambio de producción exige una nueva frontera y recualificación;
  no reatribuir D83–D93 automáticamente.
- Antes de publicar el siguiente recibo, ejecutar:

```powershell
python -m tools.ronin_daily_progress --check --report
python -m tools.generate_public_v1_status --check
python -m tools.capability_status docs/product/public-v1-status.json
git diff --check
```

## Próximo paso recomendado

No repetir D93, D94 ni D95. Elegir una brecha P11 externa nueva: cualificar una
celda bounded con proveedor/topología autorizados y criterio de parada
explícito; o, si el entorno no permite esa duración, HA o proveedor, registrar
el bloqueo reproducible y preparar la matriz de decisión humana. Mantener P11
`in_progress`, P13 `blocked` y release `NO-GO`.
