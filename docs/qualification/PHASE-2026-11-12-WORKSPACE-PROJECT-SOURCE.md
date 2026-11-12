# Phase receipt — workspace, project, and source-control contracts — 2026-11-12

## Candidate

- Source candidate before this receipt: `2bef2b1b477b4d8eb06ce69964418de05c8660d2`.

## Evidence

The focused P1 selection covered workspace/project services and manifests, project configuration/UI, source-control and VCS behavior, checkpoints, grants/scope projection, environment bindings, plugin settings/events/ports, and project bundle inventory/import contracts.

It was run in two terminal groups:

- Group 1: **295 passed, 1 skipped in 39.92s**.
- Group 2: **143 passed, 2 skipped in 8.29s**.
- Aggregate: **438 passed, 3 skipped, 0 failures**.

All three skips were Windows symlink cases requiring Developer Mode or equivalent privilege (`WinError 1314`). They remain explicit skips and are not counted as passes.

## Scope boundary

This is local contract evidence. It does not claim the full installed Studio workspace journey, cross-tenant production authorization certification, or external source-provider certification.

## Result

PASS for the local P1 workspace/project/source-control contract surface: **438/438 executed tests passed**. P1 and Public V1 remain incomplete; release-qualified progress remains `0/13 (0%)`.
