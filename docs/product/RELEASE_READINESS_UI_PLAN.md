# Release readiness UI — plan de construcción y prueba

## Decisión actual

Studio no debe mostrar el ledger `docs/product/public-v1-status.json` como si fuera telemetría runtime. El ledger es evidencia documental del árbol y del candidato observado; no es una respuesta del servidor ni una cualificación de proveedores. Por eso Home no inventa un indicador de “ready”. La postura actual sigue siendo `NO-GO` mientras `release_status` no sea `complete`, `qualification_status` no sea `qualified` y no exista evidencia exact-SHA de todos los gates obligatorios.

## Contrato futuro

Cuando el servidor disponga de una fuente autorizada, añadir `GET /v1/platform/release-readiness` con una respuesta explícita:

- `status`: `go | review | no_go`;
- `release_status`: `complete | incomplete`;
- `qualification_status`: `qualified | pending | blocked`;
- `candidate_sha`: SHA exacto evaluado;
- `required_gates`: lista con `id`, `state`, `evidence_ref` y `observed_at`;
- `claims`: lista de claims ofertados con `qualified`, `unqualified` y motivo;
- `observed_at`: timestamp UTC.

El endpoint debe fallar cerrado: ausencia de ledger, SHA, gate o evidencia convierte el estado en `no_go`; nunca debe inferir `go` desde un número de tests o desde la ausencia de errores.

## Experiencia Home

La tarjeta “Release posture” sólo se puede mostrar como estado operativo cuando el endpoint exista y esté autorizado. Debe enseñar el estado, el candidato, los gates pendientes y un enlace a la vista de cualificación. Mientras tanto, Home conserva el lenguaje de checkpoints sugeridos y no live telemetry.

## Pruebas de aceptación

1. `go` sólo aparece con todos los gates requeridos en `passed`, `candidate_sha` coincidente y `qualification_status=qualified`.
2. Un ledger ausente, stale, con `0/N`, o con un gate `pending/blocked` muestra `NO-GO` y el motivo legible.
3. La UI no expone secretos, URLs internas ni claims no cualificados.
4. El snapshot exact-SHA y `observed_at` permanecen visibles para auditoría.
5. Playwright cubre `go`, `review` y `no_go`; OpenAPI, ruta, permisos y pruebas negativas cubren el contrato del servidor.

## Dependencias de release

La implementación queda bloqueada hasta que exista un propietario del endpoint, una decisión de alcance Public v1 y receipts exact-SHA de las cualificaciones reales. El documento no reclasifica ninguna familia ni autoriza una publicación.
