# P1.7 — Project archive HTTP idempotency boundary

Date: 2026-11-13  
Status: PASS for the bounded contract below; concurrent compare-and-swap qualification remains open.

## Scope

- Move the project archive handler to the declared `POST` route. The previous implementation was unreachable because it lived in the `GET` handler.
- Require a non-empty `Idempotency-Key` on project archive requests.
- Make a repeated archive a durable no-op when the project is already archived, returning `200` with `idempotent_replay: true`.
- Preserve the existing authorization and mutation-audit boundary.

## Evidence

- `python -m pytest -q tests/integration/test_workspace_project_http_api.py -k 'archive_requires_key or missing_and_archived_project_mutations or project_routes_require_exact_workspace_grant'`
  - **3 passed, 54 deselected**
- `python -m pytest -q tests/test_workspace_project_services.py tests/test_storage_ports.py -k 'project or workspace'`
  - **10 passed, 6 deselected**
- Ruff on the changed implementation and integration test files: **clean**.
- The integration test verifies: missing key → `400`; first archive → `200`; same key after a new service/store instance → `200` and `idempotent_replay: true`.

## Explicit residual boundary

This phase does not claim a durable request-key receipt table, payload/key conflict detection, or concurrent interleaving qualification. Those remain required before treating project archive as fully qualified under RTEST-147.

## Progress

- P1 project-authoring subphase: **7/7 bounded implementation slices evidenced in this iteration = 100% of this local slice**.
- Official Public v1 denominator: **0/13 active families, 0%, NO-GO**. This phase does not promote a Public v1 family to release-qualified.
