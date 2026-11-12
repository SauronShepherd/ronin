# Phase receipt — provider and format contracts — 2026-11-12

## Candidate

- Source candidate before this receipt: `639f60d2f0bbc4efabe55fb24972b4513d7d0a3a`.

## Evidence

Executed the focused P2 contract selection covering connector capabilities/registry/checkpoints, HTTP/JDBC/PostgreSQL/S3/Azure/Ozone connector behavior, data-engineering compilation/execution/revisions/runtime/plugin surfaces, local ingestion, Studio formats, and synthetic-data persistence/publication:

Result: **245 passed, 1 skipped in 27.53s**.

The sole skip was `tests/test_local_file_ingestion.py` symlink rejection on Windows because the host lacks the required symlink privilege (`WinError 1314`). It was not relabeled as a pass.

## Scope boundary

This is local contract evidence. Real provider/emulator services and production provider certification remain separate gates; the integration/e2e modules requiring explicit service configuration were not claimed here.

## Result

PASS for the local P2 provider/format/failure-contract surface, with one documented host-capability skip. P2 and Public V1 remain incomplete; release-qualified progress remains `0/13 (0%)`.
