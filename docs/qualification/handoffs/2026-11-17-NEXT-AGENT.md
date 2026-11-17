# Handoff para el siguiente agente — Ronin — 17 noviembre 2026

## Estado de transferencia

La ronda solicitada queda cerrada y el objetivo se entrega para continuación
posterior. El estado no es un GO:

```text
implementation candidate: 633980dd3b08affcc604dc918c1a6cbf026cc408
main/origin HEAD:        ed8999c0a3996e85d8da1ce14fb7127f18503503
worktree:                main, limpio
familias:                1/13
release gates:           0/10
P11:                     in_progress
P13:                     blocked
release:                 NO-GO
```

El SHA `633980dd…` es la frontera de implementación. Los commits posteriores
son sólo documentación/estado; no se debe atribuir evidencia de código al HEAD
documental sin mantener explícita la frontera exacta.

## Evidencia current-candidate disponible

Todos los recibos siguientes apuntan al candidato exacto
`633980dd3b08affcc604dc918c1a6cbf026cc408`:

- [D83](2026-11-17-D83.md): Python/PostgreSQL `4,753 passed`, `31 skipped`,
  `0 failed`.
- [D84](2026-11-17-D84.md): Docker `27/27` y aceptación estricta `15/15`.
- [D85](2026-11-17-D85.md): backpressure single-broker de `16,384` registros,
  `1/1`, `12/12` eventos correlacionados `OK`.
- [D86](2026-11-17-D86.md): failover three-broker RF3, `1/1`, `5/5` eventos
  correlacionados `OK`.
- [D87](2026-11-17-D87.md) y [D88](2026-11-17-D88.md): Docker→Helm/kind,
  instalación, readiness, restart persistence, upgrade, rollback y cleanup.
- [D89](2026-11-17-D89.md): wheel/sdist, imágenes runtime/probe, SBOM,
  provenance e inventarios; Trivy `vuln,secret` reporta `0/0` en runtime y
  probe.
- [D90](2026-11-17-D90.md): route-wide live con PostgreSQL, Redpanda, API y
  worker real; `25` rutas (`24` API-backed, `1` UI-only), `39/40` casos y
  `379/379` eventos correlacionados. El único skip es el caso multi-broker,
  que el runner exige como diagnóstico focalizado.
- [D91](2026-11-17-D91.md): ese failover multi-broker focalizado con worker
  disponible pasa `1/1`, `5/5` `OK` y `0` errores inesperados.
- [D92](2026-11-17-D92.md): backpressure bounded single-broker ampliado a
  `32,768` registros; `1/1`, `12/12` `OK`, timeout explícito de `600 s` y
  cleanup correcto.

Las pruebas locales posteriores pasan `71` casos de streaming/API y `16`
casos del runtime worker, con un skip explícito de Docker real por ser opt-in.
La regresión documental reciente pasa `197` casos con un skip de symlinks no
disponibles en Windows.

## Frontera y artefactos

La frontera D83 permanece en:

```text
C:\Users\angel.alvarez\AppData\Local\Temp\ronin-candidate-633980dd-d83
files:    1,599
bytes:    16,765,557
archive:  b355a0a2e6dd3c83fc18b3b1e5e203b00e98c0c5d69a2e75d069ce2f7f47d2a2
manifest: 2344f1e39c8449ce4e4bc3392c214c5daa5de2049153a405150835ffe7ee80ec
```

Las evidencias live permanecen en sus rutas `%TEMP%` descritas en D85/D86 y
D90–D92. Los checkouts temporales y las imágenes de worker fueron retirados
por identidad exacta. La última verificación no dejó contenedores Ronin,
imágenes Ronin ni clusters kind.

## Lo que todavía no está demostrado

No elevar ninguna de estas afirmaciones a PASS de familia o gate:

1. operación indefinida/soak y continuidad del supervisor a duración de
   producción;
2. topología productiva y operación multi-worker/HA;
3. amplitud de proveedores externos autorizados y matriz completa de sinks,
   replay y recovery;
4. journey completo de P11 y agregación de las 13 familias;
5. decisiones humanas de licencias, NOTICE, VEX, producto, soporte, versión,
   matriz de plataformas y freeze de release;
6. cualificación P13 con proveedor externo de secretos.

El caso route-wide con un skip no se convierte en PASS. D91 y D92 son celdas
bounded separadas; tampoco prueban operación indefinida.

## Reglas para continuar

- Trabajar sólo en `main`; no crear ramas, worktrees ni workflows hospedados.
- D49 es contexto técnico y criterios de trazabilidad, no autorización para
  ignorar los límites del estado actual.
- Mantener candidate boundary, sandbox limpio, SHA, hashes, logs y cleanup.
- Cualquier cambio de código invalida la evidencia D83–D92 y exige una nueva
  cualificación exact-SHA; no reatribuir D76–D82 al candidato actual.
- No usar mocks para certificar un proveedor real. Si falta un perfil externo,
  registrar el bloqueo exacto, no convertirlo en skip verde.
- Antes de publicar un nuevo recibo, ejecutar al menos:

```powershell
python -m tools.ronin_daily_progress --check --report
python -m tools.generate_public_v1_status --check
python -m tools.capability_status docs/product/public-v1-status.json
git diff --check
```

## Siguiente acción recomendada

Elegir una sola brecha P11 y cubrirla con evidencia nueva, no repetir D90/D92:

1. implementar o cualificar un soak/supervisor prolongado con checkpoint y
   sink observables, manteniendo límites explícitos y criterio de interrupción;
2. o, si el entorno autorizado no permite proveedores/topología adicionales,
   registrar el bloqueo reproducible y preparar la matriz de decisión humana.

El siguiente agente debe leer este archivo, D49, D90–D92,
`docs/product/public-v1-status.json` y
`docs/product/PUBLIC_V1_CAPABILITY_MATRIX.md` antes de modificar nada.

