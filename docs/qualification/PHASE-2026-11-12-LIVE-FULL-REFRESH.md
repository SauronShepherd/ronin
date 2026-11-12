# Phase receipt — full live product qualification refresh — 2026-11-12

## Candidate and services

- Source candidate: `01ca264884d7c4c1bf30cd1a15e25e2ce65a48c8`.
- Worktree mode: `DIRTY-WORKTREE DIAGNOSTIC` because pre-existing untracked user artifacts remain.
- Worker image: `sha256:9b50b39d9aa8616dbaf1e748b4a4f4b14a8376b8e5f14cc9ada9b416d62fb7e4`.
- Real services: PostgreSQL, Kafka/Redpanda, Ronin API, and Docker worker.

## Evidence

Executed the full live runner with the worker image. Result: `status=passed`, duration 310.01s.

- Playwright: **33 executed, 33 passed, 0 skipped, 0 failed**.
- Active routes: 25; routes with API contracts: 24; UI-only routes: 1.
- API traffic: **279 events**, all **279 correlated** with structured HTTP logs; 263 OK and 16 expected WARN.
- Application logs: 2,033 INFO, 16 expected WARNING, 0 ERROR, 0 CRITICAL.
- Notebook Studio worker journey, Projects Bundle export/reimport, authorization, streaming, routes, and traffic-without-credentials cases all passed.
- Cleanup: completed successfully in 2.55s.

## Scope boundary

This is a complete live product diagnostic bound to one source SHA and worker digest, but the worktree was intentionally allowed dirty to preserve pre-existing user artifacts. It is not the clean 10-gate release candidate dossier and does not by itself close all 13 Public V1 families.

## Result

PASS for the full live UI/API diagnostic: **33/33** with real services and correlated traffic. Public V1 release-qualified progress remains `0/13 (0%)` pending clean-candidate aggregation, license/human gates, and family-specific completeness.
